from importlib import import_module
from .dataset import Dataset, DatasetStatus
from .dataset_reader import DatasetReader
from .dataset_manager import SMapiDatasetManager, SMDaemonDatasetManager, DatasetActionPriority
from .es_export import ESExporter, ESIndexManager
from .queue import QueueConsumer, QueuePublisher
from .db import DB
from .mol_db import MolecularDB
from .ms_txt_converter import MsTxtConverter
from .util import SMConfig
from ..rest.api import CONFIG_PATH

try:
    import pyspark
except ImportError:
    from .util import init_logger, logger
    init_logger()
    logger.warn('pyspark is not on PYTHONPATH')
else:
    from .search_job import SearchJob

SMConfig.set_path(CONFIG_PATH)

ms_parser_factory_module = SMConfig.get_conf()['ms_files']['parser_factory']
MsTxtConverter.parser_factory = getattr(import_module(ms_parser_factory_module['path']), ms_parser_factory_module['name'])

acq_geometry_factory_module = SMConfig.get_conf()['ms_files']['acq_geometry_factory']
Dataset.acq_geometry_factory = getattr(import_module(acq_geometry_factory_module['path']), acq_geometry_factory_module['name'])
