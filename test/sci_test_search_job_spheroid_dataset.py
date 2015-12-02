from __future__ import division
from os.path import join, dirname
from subprocess import check_call
import argparse
import json
import numpy as np
from fabric.api import local
from fabric.context_managers import warn_only

from engine.db import DB
from engine.util import proj_root, hdfs


def sm_config():
    with open(join(proj_root(), 'conf/config.json')) as f:
        return json.load(f)


ds_name = 'spheroid_12h'
data_dir_path = join(sm_config()['fs']['data_dir'], ds_name)
test_dir_path = join(proj_root(), 'test/data/sci_test_search_job_spheroid_dataset')

search_res_select = ("select sf, adduct, stats "
                     "from iso_image_metrics s "
                     "join formula_db db on db.id = s.db_id "
                     "join agg_formula f on f.id = s.sf_id "
                     "join job j on j.id = s.job_id "
                     "join dataset ds on ds.id = j.ds_id "
                     "where ds.name = %s and db.name = %s "
                     "ORDER BY sf, adduct ")


def compare_search_results(base_search_res, search_res):
    missed_sf_adduct = set(base_search_res.keys()).difference(set(search_res.keys()))
    print 'Missed formulas: {:.1f}%'.format(len(missed_sf_adduct) / len(base_search_res) * 100)
    print list(missed_sf_adduct)

    new_sf_adduct = set(search_res.keys()).difference(set(base_search_res.keys()))
    print 'False discovery: {:.1f}%'.format(len(new_sf_adduct) / len(base_search_res) * 100)
    print list(new_sf_adduct)

    print 'Differences in metrics'
    for b_sf_add, b_metr in base_search_res.iteritems():
        if b_sf_add in search_res.keys():
            metr = search_res[b_sf_add]
            diff = np.abs(b_metr - metr)
            if np.any(diff > 1e-6):
                print '{} metrics diff = {}'.format(b_sf_add, diff)


def zip_engine():
    local('cd {}; zip -rq engine.zip engine'.format(proj_root()))


def run_search():
    cmd = ['python', join(proj_root(), 'scripts/run_molecule_search.py'), test_dir_path]
    check_call(cmd)


def clear_data_dirs():
    with warn_only():
        local('rm -r {}'.format(data_dir_path))
        local(hdfs('-rmr {}'.format(data_dir_path)))


class SciTester(object):

    def __init__(self):
        db_config = {
            "host": "localhost",
            "database": "sm",
            "user": "sm",
            "password": "1321"
        }
        self.db = DB(db_config)
        self.base_search_res_path = join(proj_root(), 'test/reports', 'spheroid_12h_search_res.csv')
        self.metrics = ['chaos', 'img_corr', 'pat_match']

    def metr_dict_to_array(self, metr_d):
        return np.array([metr_d[m] for m in self.metrics])

    def read_base_search_res(self):
        with open(self.base_search_res_path) as f:
            rows = map(lambda line: line.strip('\n').split('\t'), f.readlines()[1:])
            return {(r[0], r[1]): np.array(r[2:], dtype=float) for r in rows}

    def fetch_search_res(self):
        rows = self.db.select(search_res_select, (ds_name, 'HMDB'))
        return {(r[0], r[1]): self.metr_dict_to_array(r[2]) for r in rows}

    def run_sci_test(self):
        compare_search_results(self.read_base_search_res(), self.fetch_search_res())

    def save_sci_test_report(self):
        with open(self.base_search_res_path, 'w') as f:
            f.write('\t'.join(['sf', 'adduct'] + self.metrics) + '\n')
            for (sf, adduct), metrics in self.fetch_search_res().iteritems():
                f.write('\t'.join([sf, adduct] + metrics.astype(str).tolist()) + '\n')

        print 'Successfully saved sample dataset search report'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scientific test runner')
    parser.add_argument('-r', '--run', action='store_true', help='compare current search results with previous')
    parser.add_argument('-s', '--save', action='store_true', help='store current search results')
    args = parser.parse_args()

    sci_tester = SciTester()

    if args.run:
        try:
            zip_engine()
            run_search()
            sci_tester.run_sci_test()
        finally:
            clear_data_dirs()
    elif args.save:
        resp = raw_input('You are going to replace the reference values. Are you sure? (y/n): ')
        if resp == 'y':
            sci_tester.save_sci_test_report()
    else:
        print 'Dry run'
