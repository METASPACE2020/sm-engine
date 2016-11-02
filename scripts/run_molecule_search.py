#!/usr/bin/env python
"""
Script for running molecule search
"""
import argparse
import sys
from datetime import datetime as dt

from sm.engine.util import SMConfig, logger, sm_log_config, init_logger
from sm.engine.search_job import SearchJob


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SM process dataset at a remote spark location.')
    parser.add_argument('--input-path', type=str, help='Path to a dataset location')
    parser.add_argument('--ds-name', dest='ds_name', type=str, help='Dataset name')
    parser.add_argument('--drop', action='store_true', help='Drop all datasets with ds_name first')
    parser.add_argument('--no-clean', dest='no_clean', action='store_true', help="Don't clean dataset txt files after job is finished")
    parser.add_argument('--ds-id', dest='ds_id', type=str, help='Dataset id')
    parser.add_argument('--ds-config', dest='ds_config_path', type=str, help='Path to a dataset config file')
    parser.add_argument('--config', dest='sm_config_path', type=str, help='SM config path')

    args = parser.parse_args()

    init_logger()

    ds_id = args.ds_id or dt.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")
    job = SearchJob(ds_id, args.ds_name, args.drop, args.input_path, args.sm_config_path, args.no_clean)
    try:
        job.run(args.ds_config_path)
    except:
        sys.exit(1)

    sys.exit()
