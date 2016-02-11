from os import makedirs
from os.path import join, exists
from traceback import format_exc

import numpy as np

from engine.db import DB
from engine.util import logger
from pyMS.pyisocalc.canopy.sum_formula_actions import InvalidFormulaError, ParseError
from pyMS.pyisocalc.pyisocalc import complete_isodist, parseSumFormula


def list_of_floats_to_str(l):
    return ','.join(map(lambda x: '{:.6f}'.format(x), l))


class IsocalcWrapper(object):
    """ Wrapper around pyMS.pyisocalc.pyisocalc used for getting theoretical isotope peaks'
    centroids and profiles for a sum formula.

    Args
    ----------
    isocalc_config : dict
        Dictionary representing isotope_generation section of a dataset config file
    """
    def __init__(self, isocalc_config):
        self.charge = 0
        if 'polarity' in isocalc_config['charge']:
            polarity = isocalc_config['charge']['polarity']
            self.charge = (-1 if polarity == '-' else 1) * isocalc_config['charge']['n_charges']
        self.sigma = isocalc_config['isocalc_sigma']
        self.pts_per_mz = isocalc_config['isocalc_pts_per_mz']
        self.prof_pts_per_centr = 6
        self.max_mz_dist_to_centr = 0.15

    def _isodist(self, sf_adduct):
        sf_adduct_obj = parseSumFormula(sf_adduct)
        return complete_isodist(sf_adduct_obj, sigma=self.sigma, charge=self.charge, pts_per_mz=self.pts_per_mz,
                                centroid_kwargs={'weighted_bins': 5})

    def isotope_peaks(self, sf, adduct):
        """
        Args
        ----
        sf : str
            Sum formula
        adduct : str
            Molecule adduct. One of isotope_generation.adducts from a dataset config file

        Returns
        -------
        : dict
            A dict with keys:
             - centroid mzs
             - centroid intensities
             - profile mzs
             - profile intensities
            In case of any errors returns a dict of empty lists.
        """
        res_dict = {'centr_mzs': [], 'centr_ints': [], 'profile_mzs': [], 'profile_ints': []}
        try:
            isotope_ms = self._isodist(sf + adduct)

            centr_mzs, centr_ints = isotope_ms.get_spectrum(source='centroids')
            res_dict['centr_mzs'] = centr_mzs
            res_dict['centr_ints'] = centr_ints

            profile_mzs, profile_ints = isotope_ms.get_spectrum(source='profile')
            res_dict['profile_mzs'], res_dict['profile_ints'] = \
                self._sample_profiles(centr_mzs, profile_mzs, profile_ints)
        except (InvalidFormulaError, ParseError) as e:
            logger.warning('(%s, %s) - %s', sf, adduct, e)
        except Exception as e:
            logger.error('(%s, %s) - %s', sf, adduct, e)
            logger.error(format_exc())
        finally:
            return res_dict

    @staticmethod
    def slice_array(mzs, lower, upper):
        return np.hstack(map(lambda (l, u): mzs[l:u], zip(lower, upper)))

    def _sample_profiles(self, centr_mzs, profile_mzs, profile_ints):
        sampled_prof_mz_list, sampled_prof_int_list = [], []

        for cmz in centr_mzs:
            centr_mask = np.abs(profile_mzs - cmz) <= self.max_mz_dist_to_centr
            sample_step = max(1, len(profile_mzs[centr_mask]) / self.prof_pts_per_centr)

            # take only N mz points for each centroid
            sampled_prof_mz_list.append(profile_mzs[centr_mask][::sample_step])
            sampled_prof_int_list.append(profile_ints[centr_mask][::sample_step])

        return np.hstack(sampled_prof_mz_list), np.hstack(sampled_prof_int_list)

    def _format_peak_str(self, db_id, sf_id, adduct, peak_dict):
        return '%d\t%d\t%s\t%.6f\t%d\t%d\t{%s}\t{%s}\t{%s}\t{%s}' % (
            db_id, sf_id, adduct,
            round(self.sigma, 6), self.charge, self.pts_per_mz,
            list_of_floats_to_str(peak_dict['centr_mzs']),
            list_of_floats_to_str(peak_dict['centr_ints']),
            list_of_floats_to_str(peak_dict['profile_mzs']),
            list_of_floats_to_str(peak_dict['profile_ints'])
        )

    def formatted_iso_peaks(self, db_id, sf_id, sf, adduct):
        """
        Args
        ----
        db_id : int
            Database id
        sf_id : int
            Sum formula id
        sf : str
            Sum formula
        adduct : str
            Sum formula adduct

        Returns
        -------
        : str
            A one line string with tab separated lists. Every list is a comma separated string.
        """
        peak_dict = self.isotope_peaks(sf, adduct)
        if np.all([len(v) > 0 for v in peak_dict.values()]):
            yield self._format_peak_str(db_id, sf_id, adduct, peak_dict)


DB_ID_SEL = 'SELECT id FROM formula_db WHERE name = %s'
AGG_FORMULA_SEL = 'SELECT id, sf FROM agg_formula where db_id = %s'
# TODO: sigma precision to take into account?
SF_ADDUCT_SEL = ('SELECT sf, adduct FROM theor_peaks p '
                 'JOIN agg_formula f on p.sf_id = f.id and p.db_id = f.db_id '
                 'WHERE p.db_id = %s AND ROUND(sigma::numeric, 6) = %s AND charge = %s AND pts_per_mz = %s')


class TheorPeaksGenerator(object):
    """ Generator of theoretical isotope peaks for all molecules in a database.

    Args
    ----------
    sc : pyspark.SparkContext
    sm_config : dict
        SM engine config
    ds_config : dict
        Dataset config
    """
    def __init__(self, sc, sm_config, ds_config):  # TODO: replace sm_config with db
        self.sc = sc
        self.sm_config = sm_config
        self.ds_config = ds_config

        self.theor_peaks_tmp_dir = join(sm_config['fs']['data_dir'], 'theor_peaks_gen')
        self.db = DB(sm_config['db'])

        self.adducts = self.ds_config['isotope_generation']['adducts']

        self.isocalc_wrapper = IsocalcWrapper(self.ds_config['isotope_generation'])

    @staticmethod
    def _sf_elements(sf):
        return [seg.element().name() for seg in parseSumFormula(sf).get_segments()]

    @classmethod
    def _valid_sf_adduct(cls, sf, adduct):
        if sf is None or adduct is None or sf == 'None' or adduct == 'None':
            logger.warning('Invalid sum formula or adduct: sf=%s, adduct=%s', sf, adduct)
            return False

        if '-' in adduct and adduct.strip('-') not in cls._sf_elements(sf):
            logger.info('No negative adduct element in the sum formula: sf=%s, adduct=%s', sf, adduct)
            return False

        return True

    def run(self):
        """ Starts peaks generation. Checks all formula peaks saved in the database and
        generates peaks only for new ones"""
        logger.info('Running theoretical peaks generation')

        db_id = self.db.select_one(DB_ID_SEL, self.ds_config['database']['name'])[0]
        formula_list = self.apply_database_filters(self.db.select(AGG_FORMULA_SEL, db_id))

        stored_sf_adduct = self.db.select(SF_ADDUCT_SEL, db_id,
                                          self.isocalc_wrapper.sigma,
                                          self.isocalc_wrapper.charge,
                                          self.isocalc_wrapper.pts_per_mz)

        sf_adduct_cand = self.find_sf_adduct_cand(formula_list, set(stored_sf_adduct))
        logger.info('%d saved (sf, adduct)s, %s not saved (sf, adduct)s', len(stored_sf_adduct), len(sf_adduct_cand))

        if sf_adduct_cand:
            peak_lines = self.generate_theor_peaks(sf_adduct_cand)
            self._import_theor_peaks_to_db(peak_lines)

    def apply_database_filters(self, formula_list):
        """ Filters according to settings in dataset config

        Args
        ----
        formula_list : list
            List of pairs (id, sum formula) to search through

        Returns
        -------
        : list
            Filtered list of pairs (id, sum formula)
        """
        if 'organic' in map(lambda s: s.lower(), self.ds_config['database'].get('filters', [])):
            logger.info('Organic sum formula filter has been applied')
            return filter(lambda (_, sf): 'C' in self._sf_elements(sf), formula_list)
        return formula_list

    def find_sf_adduct_cand(self, formula_list, stored_sf_adduct):
        """
        Args
        ----
        formula_list : list
            List of pairs (id, sum formula) to search through
        stored_sf_adduct : set
            Set of (formula, adduct) pairs which have theoretical patterns saved in the database

        Returns
        -------
        : list
            List of (formula id, formula, adduct) triples which don't have theoretical patterns saved in the database
        """
        assert formula_list, 'Emtpy agg_formula table!'
        cand = [sf_row + (adduct,) for sf_row in formula_list for adduct in self.adducts]
        valid_cand = filter(lambda (_, sf, adduct): self._valid_sf_adduct(sf, adduct), cand)
        return filter(lambda (sf_id, sf, adduct): (sf, adduct) not in stored_sf_adduct, valid_cand)

    def generate_theor_peaks(self, sf_adduct_cand):
        """
        Args
        ----
        sf_adduct_cand : list
            List of (formula id, formula, adduct) triples which don't have theoretical patterns saved in the database

        Returns
        -------
        : list
            List of strings with formatted theoretical peaks data
        """
        logger.info('Generating missing peaks')
        formatted_iso_peaks = self.isocalc_wrapper.formatted_iso_peaks
        db_id = self.db.select_one(DB_ID_SEL, self.ds_config['database']['name'])[0]
        sf_adduct_cand_rdd = self.sc.parallelize(sf_adduct_cand)
        peak_lines = (sf_adduct_cand_rdd
                      .flatMap(lambda (sf_id, sf, adduct): formatted_iso_peaks(db_id, sf_id, sf, adduct))
                      .collect())
        return peak_lines

    def _import_theor_peaks_to_db(self, peak_lines):
        logger.info('Saving new peaks to the DB')
        if not exists(self.theor_peaks_tmp_dir):
            makedirs(self.theor_peaks_tmp_dir)

        peak_lines_path = join(self.theor_peaks_tmp_dir, 'peak_lines.csv')
        with open(peak_lines_path, 'w') as f:
            f.write('\n'.join(peak_lines))

        with open(peak_lines_path) as peaks_file:
            self.db.copy(peaks_file, 'theor_peaks')
