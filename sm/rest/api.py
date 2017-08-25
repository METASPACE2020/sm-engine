import json
from datetime import datetime
import logging
from bottle import post, run
from bottle import request as req
from bottle import response as resp

from sm.engine import DB, ESExporter
from sm.engine import Dataset, SMapiDatasetManager, DatasetActionPriority
from sm.engine.queue import QueuePublisher, SM_ANNOTATE
from sm.engine.util import SMConfig
from sm.engine.util import init_logger
from sm.engine.errors import UnknownDSID


CONFIG_PATH = 'conf/config.json'

OK = {
    'status': 200,
    'title': 'OK'
}

ERR_OBJECT_NOT_EXISTS = {
    'status': 404,
    'title': 'Object Not Exists'
}


def _read_config():
    SMConfig.set_path(CONFIG_PATH)
    config = SMConfig.get_conf()
    return config


def _create_db_conn():
    config = _read_config()
    return DB(config['db'])


def _json_params(req):
    b = req.body.getvalue()
    return json.loads(b.decode('utf-8'))


def _create_queue_publisher():
    config = _read_config()
    return QueuePublisher(config['rabbitmq'])


def _create_dataset_manager(db):
    return SMapiDatasetManager(SM_ANNOTATE, db, ESExporter(db),
                               mode='queue', queue_publisher=_create_queue_publisher())


@post('/v1/datasets/add')
def add_ds():
    params = _json_params(req)
    logger.info('Received ADD request: %s', params)
    now = datetime.now()
    ds = Dataset(params.get('id', None) or now.strftime("%Y-%m-%d_%Hh%Mm%Ss"),
                 params.get('name', None),
                 params.get('input_path'),
                 params.get('upload_dt', now),
                 params.get('metadata', None),
                 params.get('config'))
    db = _create_db_conn()
    ds_man = _create_dataset_manager(db)
    ds_man.add(ds, del_first=params.get('del_first', False),
               priority=params.get('priority', DatasetActionPriority.DEFAULT))
    db.close()
    return OK['title']


@post('/v1/datasets/<ds_id>/update')
def update_ds(ds_id):
    try:
        params = _json_params(req)
        logger.info('Received UPDATE request: %s', params)
        db = _create_db_conn()
        ds = Dataset.load(db=db, ds_id=ds_id)
        ds.name = params.get('name', ds.name)
        ds.input_path = params.get('input_path', ds.input_path)
        ds.meta = params.get('metadata', ds.meta)
        ds.config = params.get('config', ds.config)

        ds_man = _create_dataset_manager(db)
        ds_man.update(ds, priority=params.get('priority', DatasetActionPriority.DEFAULT))
        db.close()
        return OK['title']
    except UnknownDSID:
        resp.status = ERR_OBJECT_NOT_EXISTS['status']
        return ERR_OBJECT_NOT_EXISTS['title']


@post('/v1/datasets/<ds_id>/delete')
def delete_ds(ds_id):
    try:
        params = _json_params(req)
        logger.info('Received DELETE request: %s', params)
        del_raw = params.get('del_raw', False)

        db = _create_db_conn()
        ds = Dataset.load(db=db, ds_id=ds_id)

        ds_man = _create_dataset_manager(db)
        ds_man.delete(ds, del_raw_data=del_raw)
        db.close()
        return OK['title']
    except UnknownDSID:
        resp.status = ERR_OBJECT_NOT_EXISTS['status']
        return ERR_OBJECT_NOT_EXISTS['title']

if __name__ == '__main__':
    init_logger()
    logger = logging.getLogger(name='sm-api')
    run(host='localhost', port=5123)
