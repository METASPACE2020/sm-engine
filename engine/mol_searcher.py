__author__ = 'intsco'
"""
.. module:: computing_fast_spark
    :synopsis: Functions for running spark jobs.

.. moduleauthor:: Vitaly Kovalev <intscorpio@gmail.com>
"""

import numpy as np
import scipy.sparse
from itertools import izip, repeat
from pyspark import SparkContext, SparkConf

from engine.pyIMS.image_measures.level_sets_measure import measure_of_chaos
from engine.pyIMS.image_measures.isotope_pattern_match import isotope_pattern_match
from engine.pyIMS.image_measures.isotope_image_correlation import isotope_image_correlation


def txt_to_spectrum(s):
    """Converts a text string in the format to a spectrum in the form of two arrays:
    array of m/z values and array of partial sums of intensities.

    :param s: string id|mz1 mz2 ... mzN|int1 int2 ... intN
    :returns: triple spectrum_id, mzs, cumulative sum of intensities
    """
    arr = s.strip().split("|")
    intensities = np.fromstring("0 " + arr[2], sep=' ')
    return int(arr[0]), np.fromstring(arr[1], sep=' '), np.cumsum(intensities)


def eval_sf(img_m, theor_int):
    relevant = False
    if img_m.nnz > 0:
        img_dense = img_m.toarray()
        relevant = (isotope_image_correlation(img_dense, theor_int[1:]) > 0.4) and \
                   (isotope_pattern_match(img_dense, theor_int) > 0.7)
    return relevant


def get_nonzero_ints(sp, lower, upper):
    sp_i, mzs, cum_ints = sp
    ints = cum_ints[mzs.searchsorted(upper, 'r')] - cum_ints[mzs.searchsorted(lower, 'l')]
    peak_inds = np.arange(len(lower))
    return sp_i, peak_inds[ints > 0.001], ints[ints > 0.001]


def find_candidates(spectra, peak_bounds, sf_peak_inds, theor_peak_ints):
    """Run multiple queries on a spectrum.
    :param sp: tuple (spectrum id, m/z values, partial sums of ints_slice)
    :param peak_bounds: two arrays providing lower and upper bounds of the m/z intervals
    :returns: tuple (peak_i, (spectrum_id, intensity))
    """
    lower, upper = peak_bounds
    spectra_list = list(spectra)
    peak_sp_ints = scipy.sparse.dok_matrix((len(lower), len(spectra_list)))

    for i, sp in enumerate(spectra_list):
        sp_i, non_zero_int_inds, non_zero_ints = get_nonzero_ints(sp, lower, upper)
        peak_sp_ints[non_zero_int_inds, i] = non_zero_ints.reshape(-1, 1)

    sf_peak_bounds = zip(sf_peak_inds[:-1], sf_peak_inds[1:])
    sf_inds = np.arange(len(sf_peak_bounds))

    peak_sp_ints_csr = peak_sp_ints.tocsr()
    candadate_mask = map(lambda (sf_i, (l, u), theor_int): eval_sf(peak_sp_ints_csr[l:u], theor_int),
                         izip(sf_inds, sf_peak_bounds, theor_peak_ints))

    return sf_inds[np.array(candadate_mask)]


def sample_spectrum(sp, peak_bounds, sf_peak_map):
    """Run multiple queries on a spectrum.

    :param sp: tuple (spectrum id, m/z values, partial sums of ints_slice)
    :param peak_bounds: two arrays providing lower and upper bounds of the m/z intervals
    :returns: tuple (peak_i, (spectrum_id, intensity))
    """
    lower, upper = peak_bounds
    sp_i, non_zero_int_inds, non_zero_ints = get_nonzero_ints(sp, lower, upper)
    sf_inds = sf_peak_map[:, 0][non_zero_int_inds]
    peak_inds = sf_peak_map[:, 1][non_zero_int_inds]

    return zip(izip(sf_inds, peak_inds),
               izip(repeat(sp_i), non_zero_ints))


def coord_list_to_matrix(sp_iter, norm_img_pixel_inds, nrows, ncols):
    sp_intens_arr = np.array(list(sp_iter), dtype=[('sp', int), ('intens', float)])
    # inds, vals = zip(*map(lambda (sp_i, intens): (pixels_order[sp_i], intens), sp_intens_arr))
    img_array = np.zeros(nrows*ncols)
    pixel_inds = norm_img_pixel_inds[sp_intens_arr['sp']]
    img_array[pixel_inds] = sp_intens_arr['intens']
    return scipy.sparse.csr_matrix(img_array.reshape(nrows, ncols))

    # inds, vals = zip(*map(lambda (sp_i, intens): (pixels_order[sp_i], intens), sp_intens_pairs))
    # array = np.bincount(inds, weights=vals, minlength=max_y * max_x)
    # img = np.reshape(array, (max_y, max_x))
    # return scipy.sparse.csr_matrix(img)


def img_pairs_to_list(pairs):
    if not pairs:
        return None
    length = max([i for i, img in pairs]) + 1
    res = np.ndarray(length, dtype=object)
    for i, img in pairs:
        res[i] = img
    return res.tolist()


def correct_peak_intens_distribution(iso_imgs_flat):
    first_peak_ints = np.sum(map(np.sum, iso_imgs_flat[0:1]))
    second_peak_ints = np.sum(map(np.sum, iso_imgs_flat[1:2]))
    rest_peak_ints = np.sum(map(np.sum, iso_imgs_flat[2:]))
    if (first_peak_ints < second_peak_ints + rest_peak_ints) or (second_peak_ints < rest_peak_ints):
        return False
    else:
        return True


class MolSearcher(object):

    def __init__(self, ds_path, ds_coords_path, sf_mz_intervals, theor_peak_intens, ds_config):
        self.ds_path = ds_path
        self.ds_coord_path = ds_coords_path
        self.ds_config = ds_config
        self.max_x, self.max_y = None, None
        self.sf_mz_intervals = np.array(sf_mz_intervals)
        self.sf_peak_inds = np.insert(np.cumsum(map(len, self.sf_mz_intervals)), 0, 0)  # 0 - extra index
        self.theor_peak_intens = theor_peak_intens
        self.minPartitions = 8
        self.measures_thr = np.array([self.ds_config['image_measure_thresholds']['measure_of_chaos'],
                                      self.ds_config['image_measure_thresholds']['image_corr'],
                                      self.ds_config['image_measure_thresholds']['pattern_match']])

        self.sconf = SparkConf().set('spark.python.profile', True).set("spark.executor.memory", "1g")
        self.sc = SparkContext(conf=self.sconf)

        self._define_pixels_order()

    def _get_peak_bounds(self, sf_filter=None):
        sf_peak_bounds = self.sf_mz_intervals[sf_filter] if sf_filter else self.sf_mz_intervals
        peak_bounds = [np.array([s[0] for _q in sf_peak_bounds for s in _q]),
                       np.array([s[1] for _q in sf_peak_bounds for s in _q])]
        return peak_bounds

    def _get_sf_peak_map(self, sf_filer=None):
        return np.array([(i, j)
                         for i, sf_peaks in enumerate(self.sf_mz_intervals)
                         for j, p in enumerate(sf_peaks)])

    def run(self):
        # convert strings to numpy arrays for each spectra
        ds_rdd = self.sc.textFile(self.ds_path, minPartitions=self.minPartitions)
        spectra = ds_rdd.map(txt_to_spectrum)

        sf_images = self._compute_sf_images(spectra)
        sf_iso_images_map, sf_metrics_map = self._filter_search_results(sf_images)
        return sf_iso_images_map, sf_metrics_map

    def _define_pixels_order(self):
        # this function maps coords onto pixel indicies (assuming a grid defined by bounding box and transform type)
        # -implement methods such as interp onto grid spaced over coords
        # -currently treats coords as grid positions,

        # pixel_indices = np.zeros(len(self.coords))
        with open(self.ds_coord_path) as f:
            coords = map(lambda s: map(int, s.strip('\n').split(',')[1:]), f.readlines())
        _coord = np.asarray(coords)
        _coord = np.around(_coord, 5)  # correct for numerical precision
        _coord -= np.amin(_coord, axis=0)

        step = np.zeros((2, 1))
        for ii in range(0, 2):
            step[ii] = np.mean(np.diff(np.unique(_coord[:, ii])))

        # coordinate to pixels
        _coord /= np.reshape(step, (2,))
        self.min_x, self.min_y = np.amin(_coord, axis=0)
        self.max_x, self.max_y = np.amax(_coord, axis=0)

        pixel_indices = _coord[:, 1] * (self.max_x+1) + _coord[:, 0]
        pixel_indices = pixel_indices.astype(np.int32)
        self.norm_img_pixel_inds = pixel_indices

    def _get_dims(self):
        return (self.max_y - self.min_y + 1,
                self.max_x - self.min_x + 1)

    def _compute_sf_images(self, spectra):
        mz_bounds_cand_brcast = self.sc.broadcast(self._get_peak_bounds())
        sf_peak_map_brcast = self.sc.broadcast(self._get_sf_peak_map())
        nrows, ncols = self._get_dims()
        norm_img_pixel_inds = self.norm_img_pixel_inds

        sf_images = (spectra
                     .flatMap(lambda sp: sample_spectrum(sp, mz_bounds_cand_brcast.value, sf_peak_map_brcast.value))
                     .groupByKey()
                     .map(lambda ((sf_i, p_i), spectrum_it):
                          (sf_i, (p_i, coord_list_to_matrix(spectrum_it, norm_img_pixel_inds, nrows, ncols))))
                     .groupByKey()
                     .mapValues(lambda img_pairs_it: img_pairs_to_list(list(img_pairs_it))))

        return sf_images

    def _get_compute_img_measures_func(self):
        nrows, ncols = self._get_dims()
        empty_matrix = np.zeros((nrows, ncols))
        nlevels = self.ds_config['image_generation']['nlevels']
        q = self.ds_config['image_generation']['q']
        preprocessing = self.ds_config['image_generation']['do_preprocessing']

        def compute_img_measures(iso_images_sparse, sf_intensity):
            diff = len(sf_intensity) - len(iso_images_sparse)
            iso_imgs = [empty_matrix if img is None else img.toarray()
                        for img in iso_images_sparse + [None] * diff]
            iso_imgs_flat = [img.flat[:] for img in iso_imgs]

            measures = 0, 0, 0
            if (len(iso_imgs) > 0) and correct_peak_intens_distribution(iso_imgs_flat):
                pattern_match = isotope_pattern_match(iso_imgs_flat, sf_intensity)

                if pattern_match:
                    image_corr = isotope_image_correlation(iso_imgs_flat, weights=sf_intensity[1:])

                    if image_corr:
                        chaos = measure_of_chaos(iso_imgs[0].copy(), nlevels=nlevels, interp=preprocessing, q_val=q)[0]
                        if np.isnan(chaos):
                            chaos = 0
                        inv_chaos = 1 - chaos
                        if np.allclose(inv_chaos, 1.0, atol=1e-6):
                            inv_chaos = 0
                        measures = (inv_chaos, image_corr, pattern_match)
            return measures

        return compute_img_measures

    def _filter_search_results(self, sf_images):
        theor_peak_intens_brcast = self.sc.broadcast(self.theor_peak_intens)
        thr = self.measures_thr
        compute_img_measures = self._get_compute_img_measures_func()

        sf_metrics_map = (sf_images
                          .map(lambda (sf_i, imgs):
                               (sf_i, compute_img_measures(imgs, theor_peak_intens_brcast.value[sf_i])))
                          .filter(lambda (_, metrics): np.all(np.array(metrics) > thr))
                          ).collectAsMap()

        sf_iso_images_map = sf_images.filter(lambda (sf_i, _): sf_i in sf_metrics_map).collectAsMap()
        return sf_iso_images_map, sf_metrics_map
