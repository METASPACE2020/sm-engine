from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk, BulkIndexError
from elasticsearch.client import IndicesClient

from sm.engine.util import logger


COLUMNS = ["db_name", "ds_id", "ds_name", "sf", "comp_names", "comp_ids", "chaos", "image_corr", "pattern_match", "msm",
           "adduct", "job_id", "sf_id", "peaks", "db_id", "fdr", "mz"]

RESULTS_TABLE_SQL = '''
SELECT
    sf_db.name AS db_name,
    ds.id as ds_id,
    ds.name AS ds_name,
    f.sf,
    f.names AS comp_names,
    f.subst_ids AS comp_ids,
    COALESCE(((m.stats -> 'chaos'::text)::text)::real, 0::real) AS chaos,
    COALESCE(((m.stats -> 'spatial'::text)::text)::real, 0::real) AS image_corr,
    COALESCE(((m.stats -> 'spectral'::text)::text)::real, 0::real) AS pattern_match,
    COALESCE(m.msm, 0::real) AS msm,
    m.adduct,
    j.id AS job_id,
    f.id AS sf_id,
    m.peaks_n AS peaks,
    sf_db.id AS db_id,
    m.fdr as pass_fdr,
    tp.centr_mzs[1] AS mz
FROM iso_image_metrics m
JOIN formula_db sf_db ON sf_db.id = m.db_id
JOIN agg_formula f ON m.db_id = f.db_id AND f.id = m.sf_id
JOIN job j ON j.id = m.job_id
JOIN dataset ds ON ds.id = j.ds_id
JOIN theor_peaks tp ON tp.db_id = sf_db.id AND tp.sf_id = m.sf_id AND tp.adduct = m.adduct
	AND tp.sigma::real = (ds.config->'isotope_generation'->>'isocalc_sigma')::real
	AND tp.charge = (CASE WHEN ds.config->'isotope_generation'->'charge'->>'polarity' = '+' THEN 1 ELSE -1 END)
	AND tp.pts_per_mz = (ds.config->'isotope_generation'->>'isocalc_pts_per_mz')::int
WHERE ds.id = %s
ORDER BY COALESCE(m.msm, 0::real) DESC
'''


class ESExporter:
    def __init__(self, sm_config):
        self.es = Elasticsearch(hosts=[{"host": sm_config['elasticsearch']['host']}])
        self.ind_client = IndicesClient(self.es)
        self.index = sm_config['elasticsearch']['index']

    def _index(self, annotations):
        to_index = []
        for r in annotations:
            d = dict(zip(COLUMNS, r))
            d['comp_names'] = u'|'.join(d['comp_names']).replace(u'"', u'')
            d['comp_ids'] = u'|'.join(d['comp_ids'])
            d['mz'] = '{:010.4f}'.format(d['mz']) if d['mz'] else ''

            to_index.append({
                '_index': self.index,
                '_type': 'annotation',
                '_id': '{}_{}_{}'.format(d['ds_id'], d['sf'], d['adduct']),
                '_source': d
            })

        bulk(self.es, actions=to_index, timeout='60s')

    def _delete(self, annotations):
        to_delete = []
        for r in annotations:
            d = dict(zip(COLUMNS, r))
            to_delete.append({
                '_op_type': 'delete',
                '_index': self.index,
                '_type': 'annotation',
                '_id': '{}_{}_{}_{}'.format(d['ds_id'], d['db_name'], d['sf'], d['adduct']),
            })
        try:
            bulk(self.es, to_delete)
        except BulkIndexError as e:
            logger.warn('{} - {}'.format(e.args[0], e.args[1][1]))

    def index_ds(self, db, ds_id):
        annotations = db.select(RESULTS_TABLE_SQL, ds_id)

        logger.info('Deleting documents from the index: {}'.format(ds_id))
        self._delete(annotations)

        logger.info('Indexing documents: {}'.format(ds_id))
        self._index(annotations)

    def create_index(self):
        body = {
            "settings": {
                "index": {
                    "max_result_window": 2147483647,
                    "analysis": {
                        "analyzer": {
                            "analyzer_keyword": {
                                "tokenizer": "keyword",
                                "filter": "lowercase"
                            }
                        }
                    }
                }
            },
            "mappings": {
                "annotation": {
                    "properties": {
                        "db_name": {"type": "string", "index": "not_analyzed"},
                        "ds_id": {"type": "string", "index": "not_analyzed"},
                        "ds_name": {"type": "string", "index": "not_analyzed"},
                        "sf": {"type": "string", "index": "not_analyzed"},
                        "comp_names": {
                            "type": "string",
                            "analyzer": "analyzer_keyword",
                        },
                        "comp_ids": {"type": "string", "index": "not_analyzed"},
                        "chaos": {"type": "float", "index": "not_analyzed"},
                        "image_corr": {"type": "float", "index": "not_analyzed"},
                        "pattern_match": {"type": "float", "index": "not_analyzed"},
                        "msm": {"type": "float", "index": "not_analyzed"},
                        "adduct": {"type": "string", "index": "not_analyzed"},
                        "fdr": {"type": "float", "index": "not_analyzed"},
                        "mz": {"type": "string", "index": "not_analyzed"}
                    }
                }
            }
        }
        if not self.ind_client.exists(self.index):
            out = self.ind_client.create(index=self.index, body=body)
            logger.info('Index {} created\n{}'.format(self.index, out))
        else:
            logger.info('Index {} already exists'.format(self.index))

    def delete_index(self):
        if self.ind_client.exists(self.index):
            out = self.ind_client.delete(self.index)
            logger.info('Index {} deleted\n{}'.format(self.index, out))
