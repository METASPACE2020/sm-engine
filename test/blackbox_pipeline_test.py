__author__ = 'intsco'

from os.path import join
import psycopg2
import json
import cPickle
from luigi import interface, scheduler, worker
from os import environ
from scripts.sm_pipeline import RunPipeline
from fabric.api import env
from fabric.api import put, local, run
import pandas as pd
from pandas.util.testing import assert_frame_equal
import argparse


class BlackboxPipelineTest:

    def __init__(self, project_dir, clear=False):
        self._clear = clear
        self._project_dir = project_dir
        self._ds_s3_dir = 's3://embl-sm-testing'
        self._ds_name = '20150730_ANB_spheroid_control_65x65_15um'
        self._input_fn = self._ds_name + '.zip'
        self._data_dir = join(project_dir, 'data', self._ds_name)
        self._test_dir = join(project_dir, 'test/data/blackbox_pipeline_test', self._ds_name)
        # self._tmp_dir = join(self._data_dir, 'tmp')
        self._master_data_dir = '/root/sm/data'
        self._rows = 65
        self._cols = 65
        self._config_path = join(project_dir, 'conf/config.json')
        # self._sf_fn = 'result_sfs.txt'
        self._queries_fn = 'queries.pkl'
        # self._test_queries_fn = 'test_queries.pkl'
        # self._sf_set = set()
        # self._sf_id_set = set()

    # def _load_sf(self):
    #     with open(join(self._test_data_dir, self._sf_fn)) as f:
    #         self._sf_set = set(f.read().split('\n'))

    def _get_db_config(self):
        with open(self._config_path) as f:
            config = json.load(f)['db']
        return config

    def _run_query(self, sql):
        conn = psycopg2.connect(**self._get_db_config())
        cur = conn.cursor()
        cur.execute(sql)
        return cur

    # def _collect_sf_ids(self):
    #     sql = 'select distinct p.sf_id, sf from mz_peaks p join formulas f on p.sf_id=f.sf_id'
    #     cur = self._run_query(sql)
    #     self._sf_id_set = set(sf_id for sf_id, sf in cur.fetchall() if sf in self._sf_set)

    def _get_master_host(self):
        with open(join(self._project_dir, 'conf/SPARK_MASTER')) as f:
            return f.readline().strip('\n')

    def setup(self):
        print "Setting up testing environment..."
        if self._clear:
            local('rm -r {}'.format(self._data_dir))
            local('mkdir {}'.format(self._data_dir))
        else:
            local('rm {}'.format(join(self._data_dir, 'AnnotationInsertStatus')))

        # self._load_sf()
        # self._collect_sf_ids()

        print "Preparing test queries file..."

        local('python {}/scripts/run_save_queries.py --out {} --config {} --sf-filter-file {}'.
              format(self._project_dir,
                     join(self._data_dir, self._queries_fn),
                     self._config_path,
                     join(self._test_dir, 'ref_sf_adduct.csv')))

        # # queries = {}
        # with open(join(self._test_data_dir, self._queries_fn)) as f:
        #     queries = cPickle.load(f)
        #
        # test_queries_inds = set(i for (i, sf_id) in enumerate(queries['ids']) if sf_id in self._sf_id_set)
        # if len(test_queries_inds) == 0:
        #     raise Exception("Empty test queries!")
        # test_queries = {}
        # for name, coll in queries.iteritems():
        #     test_queries[name] = [x for (i, x) in enumerate(queries[name]) if i in test_queries_inds]
        #
        # with open(join(self._test_data_dir, self._test_queries_fn), 'wb') as f:
        #     cPickle.dump(test_queries, f)
        #
        # env.host_string = 'root@' + self._get_master_host()
        # env.key_filename = '~/.ssh/sm_spark_cluster.pem'
        # put(local_path=join(self._test_data_dir, self._test_queries_fn),
        #     remote_path=join(self._master_data_dir, self._test_queries_fn))

    def _run_pipeline(self):
        print "Starting test pipeline..."
        cmd = ['python', self._project_dir + '/scripts/sm_pipeline.py',
               '--s3-dir', self._ds_s3_dir,
               '--input-fn', self._input_fn,
               '--queries-fn', self._queries_fn,
               '--rows', str(self._rows),
               '--cols', str(self._cols)]
        local(' '.join(cmd))

    def _compare_results(self):
        print "Comparing test results..."
        sql = 'select max(id) from jobs'
        curs = self._run_query(sql)
        job_id = curs.fetchall()[0][0]

        sql = 'select f.sf, adduct, stats from job_result_stats jrs join formulas f \
        on jrs.formula_id = f.sf_id where jrs.job_id = {}'.format(job_id)
        curs = self._run_query(sql)
        res_df = pd.DataFrame([(sf, adduct, stats['chaos'], stats['corr_int'], stats['corr_images'])
                              for sf, adduct, stats in curs.fetchall()],
                              columns=['sf', 'adduct', 'moc', 'spec', 'spat'])
        # res_df.drop_duplicates(inplace=True)
        res_df.to_csv(join(self._data_dir, 'result_sf_metrics.csv'), sep='\t', index=False)

        ref_df = pd.read_csv(join(self._test_dir, 'ref_result_sf_metrics.csv'),
                             sep='\t',
                             names=['sf', 'adduct', 'mz', 'moc', 'spec', 'spat'])
        ref_df.drop('mz', axis=1, inplace=True)

        assert_frame_equal(res_df, ref_df)

    def test(self):
        self._run_pipeline()
        self._compare_results()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pipeline integration test')
    parser.add_argument('--proj-dir', dest='proj_dir', type=str, help='Project dir path')
    parser.add_argument('--clear', dest='clear', help='Clear all tmp results', action='store_true', default=False)
    args = parser.parse_args()

    test = BlackboxPipelineTest(args.proj_dir, clear=args.clear)
    test.setup()
    test.test()
