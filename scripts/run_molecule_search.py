"""
Script for running molecule search
"""
import argparse
import sys
from logging.config import dictConfig
from datetime import datetime as dt

from sm.engine.util import SMConfig, logger, sm_log_config
from sm.engine.search_job import SearchJob


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SM process dataset at a remote spark location.')
    parser.add_argument('input_path', type=str, help='Path to a dataset location')
    parser.add_argument('--ds-name', dest='ds_name', type=str, help='Dataset name')
    parser.add_argument('--ds-config', dest='ds_config_path', type=str, help='Path to a dataset config file')
    parser.add_argument('--config', dest='sm_config_path', type=str, help='SM config path')

    args = parser.parse_args()

    dictConfig(sm_log_config)

    ds_id = dt.now().strftime("%Y-%m-%d_%Hh%Mm")
    job = SearchJob(ds_id, args.ds_name, args.input_path, args.sm_config_path)
    job.run(args.ds_config_path)

    sys.exit()
