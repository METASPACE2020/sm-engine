"""
Script for running molecule search
"""
import argparse
import time
from pprint import pformat
from logging import Formatter, FileHandler, DEBUG

from sm.engine.util import SMConfig, logger, sm_log_formatters
from sm.engine.search_job import SearchJob


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='SM process dataset at a remote spark location.')
    parser.add_argument('ds_name', type=str, help='Dataset name')
    parser.add_argument('input_path', type=str, help='Path to a dataset location')
    parser.add_argument('--ds-config', dest='ds_config_path', type=str, help='Path to a dataset config file')
    parser.add_argument('--config', dest='sm_config_path', type=str, help='SM config path')
    parser.add_argument('--no-clean', dest='no_clean', action='store_true', help='do not clean interim files')

    start = time.time()
    args = parser.parse_args()

    SMConfig.set_path(args.sm_config_path)

    fileHandler = FileHandler(filename='logs/jobs/{}.log'.format(args.ds_name.replace('/', '_')))
    fileHandler.setLevel(DEBUG)
    fileHandler.setFormatter(Formatter(sm_log_formatters['SM']['format']))
    logger.addHandler(fileHandler)

    logger.debug('Using SM config:\n%s', pformat(SMConfig.get_conf()))

    logger.info("Processing...")

    job = SearchJob(None, args.ds_name)
    job.run(args.input_path, args.ds_config_path, clean=not args.no_clean)

    logger.info("All done!")
    time_spent = time.time() - start
    logger.info('Time spent: %d mins %d secs', *divmod(int(round(time_spent)), 60))
