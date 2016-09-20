import argparse
from os.path import abspath
import json
from logging.config import dictConfig

from sm.engine.util import sm_log_config
from sm.engine.es_export import ESExporter


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create ElasticSearch indices')
    parser.add_argument('--conf', default='conf/config.json', help="SM config path")
    parser.add_argument('--drop', action='store_true', help='Delete index if exists')

    args = parser.parse_args()

    dictConfig(sm_log_config)

    with open(abspath(args.conf)) as f:
        es_exp = ESExporter(json.load(f))
        if args.drop:
            es_exp.delete_index()
        es_exp.create_index()
