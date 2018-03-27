"""

:synopsis: Molecular search job driver

.. moduleauthor:: Vitaly Kovalev <intscorpio@gmail.com>
"""
import time
from importlib import import_module
from pprint import pformat
from datetime import datetime
from pyspark import SparkContext, SparkConf
import logging

from sm.engine.isocalc_wrapper import IsocalcWrapper
from sm.engine.msm_basic.msm_basic_search import MSMBasicSearch
from sm.engine.dataset import DatasetStatus
from sm.engine.dataset_reader import DatasetReader
from sm.engine.db import DB
from sm.engine.fdr import FDR, DECOY_ADDUCTS
from sm.engine.search_results import SearchResults
from sm.engine.ion_centroids_gen import IonCentroidsGenerator
from sm.engine.util import proj_root, SMConfig, read_json, sm_log_formatters
from sm.engine.work_dir import WorkDirManager, local_path
from sm.engine.es_export import ESExporter
from sm.engine.mol_db import MolecularDB, MolDBServiceWrapper
from sm.engine.errors import JobFailedError, ESExportFailedError
from sm.engine.queue import QueuePublisher
from sm.engine.png_generator import ImageStoreServiceWrapper
from sm.engine.queue import QueuePublisher, SM_ANNOTATE, SM_DS_STATUS

logger = logging.getLogger('engine')

JOB_ID_MOLDB_ID_SEL = "SELECT id, db_id FROM job WHERE ds_id = %s"
JOB_INS = "INSERT INTO job (db_id, ds_id, status, start) VALUES (%s, %s, %s, %s) RETURNING id"
JOB_UPD = "UPDATE job set status=%s, finish=%s where id=%s"
TARGET_DECOY_ADD_DEL = 'DELETE FROM target_decoy_add tda WHERE tda.job_id IN (SELECT id FROM job WHERE ds_id = %s)'


class SearchJob(object):
    """ Main class responsible for molecule search. Uses other modules of the engine.

    Args
    ----
    no_clean : bool
        Don't delete interim data files
    """

    def __init__(self, img_store=None, no_clean=False):
        self.no_clean = no_clean
        self._img_store = img_store

        self._job_id = None
        self._sc = None
        self._db = None
        self._ds = None
        self._ds_reader = None
        self._status_queue = None
        self._fdr = None
        self._wd_manager = None
        self._es = None

        self._sm_config = SMConfig.get_conf()

        logger.debug('Using SM config:\n%s', pformat(self._sm_config))

    def _configure_spark(self):
        logger.info('Configuring Spark')
        sconf = SparkConf()
        for prop, value in self._sm_config['spark'].items():
            if prop.startswith('spark.'):
                sconf.set(prop, value)

        if 'aws' in self._sm_config:
            sconf.set("spark.hadoop.fs.s3a.access.key", self._sm_config['aws']['aws_access_key_id'])
            sconf.set("spark.hadoop.fs.s3a.secret.key", self._sm_config['aws']['aws_secret_access_key'])
            sconf.set("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
            sconf.set("spark.hadoop.fs.s3a.endpoint", "s3.{}.amazonaws.com".format(self._sm_config['aws']['aws_region']))

        self._sc = SparkContext(master=self._sm_config['spark']['master'], conf=sconf, appName='SM engine')

    def _init_db(self):
        logger.info('Connecting to the DB')
        self._db = DB(self._sm_config['db'])

    def store_job_meta(self, mol_db_id):
        """ Store search job metadata in the database """
        logger.info('Storing job metadata')
        rows = [(mol_db_id, self._ds.id, 'STARTED', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))]
        self._job_id = self._db.insert_return(JOB_INS, rows)[0]

    def _run_annotation_job(self, mol_db):
        try:
            self.store_job_meta(mol_db.id)
            mol_db.set_job_id(self._job_id)

            logger.info("Processing ds_id: %s, ds_name: %s, db_name: %s, db_version: %s",
                        self._ds.id, self._ds.name, mol_db.name, mol_db.version)

            self._fdr = FDR(job_id=self._job_id,
                            decoy_sample_size=20,
                            target_adducts=self._ds.config['isotope_generation']['adducts'],
                            db=self._db)
            self._fdr.decoy_adducts_selection(mol_db.sfs.values())

            isocalc = IsocalcWrapper(self._ds.config['isotope_generation'])
            centroids_gen = IonCentroidsGenerator(sc=self._sc, moldb_name=mol_db.name, isocalc=isocalc)
            centroids_gen.generate_if_not_exist(isocalc=isocalc,
                                                sfs=mol_db.sfs.values(),
                                                adducts=self._fdr.all_adducts())

            search_alg = MSMBasicSearch(sc=self._sc, ds=self._ds, ds_reader=self._ds_reader,
                                        mol_db=mol_db, centr_gen=centroids_gen,
                                        fdr=self._fdr, ds_config=self._ds.config)
            ion_metrics_df, ion_iso_images = search_alg.search()

            search_results = SearchResults(mol_db.id, self._job_id, search_alg.metrics.keys())
            mask = self._ds_reader.get_2d_sample_area_mask()
            img_store_type = self._ds.get_ion_img_storage_type(self._db)
            search_results.store(ion_metrics_df, ion_iso_images, mask, self._db, self._img_store, img_store_type)
        except Exception as e:
            self._db.alter(JOB_UPD, 'FAILED', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self._job_id)
            msg = 'Job failed(ds_id={}, mol_db={}): {}'.format(self._ds.id, mol_db, str(e))
            raise JobFailedError(msg) from e
        else:
            self._export_search_results_to_es(mol_db, isocalc)

    def _export_search_results_to_es(self, mol_db, isocalc):
        try:
            self._es.index_ds(self._ds.id, mol_db, isocalc)
        except Exception as e:
            self._db.alter(JOB_UPD, 'FAILED', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self._job_id)
            msg = 'Export to ES failed(ds_id={}, mol_db={}): {}'.format(self._ds.id, mol_db, str(e))
            raise ESExportFailedError(msg) from e
        else:
            self._db.alter(JOB_UPD, 'FINISHED', datetime.now().strftime('%Y-%m-%d %H:%M:%S'), self._job_id)

    def prepare_moldb_id_list(self):
        moldb_service = MolDBServiceWrapper(self._sm_config['services']['mol_db'])
        finished_job_moldb_ids = [r[1] for r in self._db.select(JOB_ID_MOLDB_ID_SEL, self._ds.id)]
        moldb_id_list = []
        for mol_db_dict in self._ds.config['databases']:
            data = moldb_service.find_db_by_name_version(mol_db_dict['name'],
                                                         mol_db_dict.get('version', None))
            if data:
                mol_db_id = data[0]['id']
                if mol_db_id not in finished_job_moldb_ids:
                    moldb_id_list.append(mol_db_id)
        return moldb_id_list

    def _save_data_from_raw_ms_file(self):
        ms_file_type_config = SMConfig.get_ms_file_handler(self._wd_manager.local_dir.ms_file_path)
        acq_geometry_factory_module = ms_file_type_config['acq_geometry_factory']
        acq_geometry_factory = getattr(import_module(acq_geometry_factory_module['path']),
                                                acq_geometry_factory_module['name'])

        acq_geometry = acq_geometry_factory(self._wd_manager.local_dir.ms_file_path).create()
        self._ds.save_acq_geometry(self._db, acq_geometry)

        self._ds.save_ion_img_storage_type(self._db, ms_file_type_config['img_storage_type'])

    def run(self, ds):
        """ Entry point of the engine. Molecule search is completed in several steps:
            * Copying input data to the engine work dir
            * Conversion input mass spec files to plain text format. One line - one spectrum data
            * Generation and saving to the database theoretical peaks for all formulas from the molecule database
            * Molecules search. The most compute intensive part. Spark is used to run it in distributed manner.
            * Saving results (isotope images and their metrics of quality for each putative molecule) to the database

        Args
        ----
            ds : sm.engine.dataset_manager.Dataset
        """
        try:
            start = time.time()

            self._init_db()
            self._es = ESExporter(self._db)
            self._ds = ds

            if self._sm_config['rabbitmq']:
                self._status_queue = QueuePublisher(config=self._sm_config['rabbitmq'],
                                                    qdesc=SM_DS_STATUS,
                                                    logger=logger)
            else:
                self._status_queue = None
            ds.set_status(self._db, self._es, self._status_queue, DatasetStatus.STARTED)

            self._wd_manager = WorkDirManager(ds.id)
            self._configure_spark()

            if not self.no_clean:
                self._wd_manager.clean()

            self._ds_reader = DatasetReader(self._ds.input_path, self._sc, self._wd_manager)
            self._ds_reader.copy_convert_input_data()

            self._save_data_from_raw_ms_file()
            self._img_store.storage_type = self._ds.get_ion_img_storage_type(self._db)

            ds.set_status(self._db, self._es, self._status_queue, DatasetStatus.STARTED)

            logger.info('Dataset config:\n%s', pformat(self._ds.config))

            for mol_db_id in self.prepare_moldb_id_list():
                mol_db = MolecularDB(id=mol_db_id, iso_gen_config=self._ds.config['isotope_generation'], db=self._db)
                self._run_annotation_job(mol_db)

            ds.set_status(self._db, self._es, self._status_queue, DatasetStatus.FINISHED)

            logger.info("All done!")
            time_spent = time.time() - start
            logger.info('Time spent: %d mins %d secs', *divmod(int(round(time_spent)), 60))
        except Exception as e:
            if self._ds:
                ds.set_status(self._db, self._es, self._status_queue, DatasetStatus.FAILED)
            logger.error(e, exc_info=True)
            raise
        finally:
            if self._sc:
                self._sc.stop()
            if self._db:
                self._db.close()
            if self._wd_manager and not self.no_clean:
                self._wd_manager.clean()
            logger.info('*' * 150)
