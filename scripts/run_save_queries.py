import numpy as np
from os import curdir, sep, path
import psycopg2, psycopg2.extras
import json
import argparse
import cPickle

ppm = 1.0
# tol = 0.01
adducts = ["H", "Na", "K"]

import sys
from os.path import dirname, realpath

engine_path = dirname(dirname(realpath(__file__)))
sys.path.append(engine_path)

from engine.metrics_db import *

parser = argparse.ArgumentParser(description='IMS webserver.')
parser.add_argument('--out', dest='fname', type=str, help='filename')
parser.add_argument('--config', dest='config', type=str, help='config file name')
parser.set_defaults(config='config.json', fname='queries.pkl')
args = parser.parse_args()

with open(args.config) as f:
    config_db = json.load(f)['db']

my_print("Reading formulas from DB...")

conn = psycopg2.connect(**config_db)
cur = conn.cursor()

# import pandas as pd
# ref_sf_adduct_df = pd.read_csv('/home/intsco/embl/SpatialMetabolomics/sm/data/ref_sf_adduct.csv')
# sf_adduct_filter = set(map(tuple, ref_sf_adduct_df.values))

sql = 'SELECT sf_id as id, adduct, peaks, ints FROM mz_peaks'
cur.execute(sql)
# formulas = filter(lambda row: (row[0], row[1]) in sf_adduct_filter, cur.fetchall())
formulas = cur.fetchall()
ids = [x[0] for x in formulas]
mzadducts = [x[1] for x in formulas]
mzpeaks = [x[2] for x in formulas]
intensities = [x[3] for x in formulas]
data = [[[float(x) - ppm*x/1e6, float(x) + ppm*x/1e6] for x in peaks] for peaks in mzpeaks]

if len(data) <= 0:
    raise Exception('{} returned empty result set'.format(sql))
else:
    print 'Fetched {} formulas from DB'.format(len(data))

res = {
    "ids": ids,
    "formulas": formulas,
    "mzadducts": mzadducts,
    "mzpeaks": mzpeaks,
    "intensities": intensities,
    "data": data
}

my_print("Saving queries to %s..." % args.fname)

with open(args.fname, "w") as outf:
    cPickle.dump(res, outf)

my_print("All done!")
