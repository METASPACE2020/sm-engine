import pytest
import numpy as np
from mock import mock, MagicMock
from numpy.testing import assert_array_almost_equal
from engine.theor_peaks_gen import TheorPeaksGenerator, IsocalcWrapper
from engine.db import DB
from pyMS.mass_spectrum import MassSpectrum
from engine.test.util import spark_context, sm_config, ds_config


def get_spectrum_side_effect(source):
    if source == 'centroids':
        return np.array([100., 200.]), np.array([100., 10.])
    elif source == 'profile':
        return (np.array([0, 90., 95., 99., 100., 101., 105., 110.,
                          190., 195., 199., 200., 201., 205., 210., 100500.]),
                np.array([0, 10., 50., 90., 100., 90., 50., 10.,
                          1., 5., 9., 10., 9., 5., 1., 100500.]))


@mock.patch('engine.isocalc_wrapper.complete_isodist')
def test_isocalc_get_iso_peaks_correct_sf_adduct(isocalc_isodist, ds_config):
    mock_mass_sp = MagicMock(spec=MassSpectrum)
    mock_mass_sp.get_spectrum.side_effect = get_spectrum_side_effect
    isocalc_isodist.return_value = mock_mass_sp

    isocalc_wrapper = IsocalcWrapper(ds_config['isotope_generation'])
    isocalc_wrapper.max_mz_dist_to_centr = 5
    peak_dict = isocalc_wrapper.isotope_peaks('Au', '+H')

    for k in ['centr_mzs', 'centr_ints', 'profile_mzs', 'profile_ints']:
        assert k in peak_dict
        assert len(peak_dict[k]) > 0

    assert_array_almost_equal(peak_dict['centr_mzs'], get_spectrum_side_effect('centroids')[0])
    assert_array_almost_equal(peak_dict['centr_ints'], get_spectrum_side_effect('centroids')[1])

    assert_array_almost_equal(peak_dict['profile_mzs'], [95., 99., 100., 101., 105., 195., 199., 200., 201., 205.])
    assert_array_almost_equal(peak_dict['profile_ints'], [50., 90., 100., 90., 50., 5., 9., 10., 9., 5.])


@mock.patch('engine.theor_peaks_gen.IsocalcWrapper.isotope_peaks')
def test_formatted_iso_peaks_correct_input(iso_peaks_mock, ds_config):
    peak_dict = {'centr_mzs': [100.], 'centr_ints': [1000.],
                 'profile_mzs': [90., 100., 110.], 'profile_ints': [1., 1000., 1001.]}
    iso_peaks_mock.return_value = peak_dict

    isocalc_wrapper = IsocalcWrapper(ds_config['isotope_generation'])

    assert list(isocalc_wrapper.formatted_iso_peaks(0, 9, 'Au', '+H'))[0] == \
           ('0\t9\t+H\t0.010000\t1\t10000\t{100.000000}\t{1000.000000}\t'
            '{90.000000,100.000000,110.000000}\t'
            '{1.000000,1000.000000,1001.000000}')


@mock.patch('engine.theor_peaks_gen.DB')
def test_raises_exc_on_empty_formula_table(MockDB, ds_config):
    with pytest.raises(AssertionError):
        mock_db = MockDB.return_value
        mock_db.select.return_value = []

        gen = TheorPeaksGenerator(None, {'db': {}, 'fs': {'data_dir': ''}}, ds_config)
        gen.find_sf_adduct_cand([], {})


@mock.patch('engine.theor_peaks_gen.DB')
@mock.patch('engine.theor_peaks_gen.DECOY_ADDUCTS')
def test_find_sf_adduct_cand(DECOY_ADDUCTS_mock, MockDB, spark_context, sm_config, ds_config):
    DECOY_ADDUCTS_mock = []

    peaks_gen = TheorPeaksGenerator(spark_context, sm_config, ds_config)
    sf_adduct_cand = peaks_gen.find_sf_adduct_cand([(0, 'He'), (9, 'Au')], {('He', '+H'), ('Au', '+H')})

    assert sf_adduct_cand == [(0, 'He', '+Na'), (9, 'Au', '+Na')]


# @mock.patch('engine.theor_peaks_gen.DB')
# def test_find_sf_adduct_cand_invalid_sf_neg_adduct(MockDB, spark_context, sm_config, ds_config):
#     ds_config['isotope_generation']['adducts'] = ['-H']
#
#     peaks_gen = TheorPeaksGenerator(spark_context, sm_config, ds_config)
#     sf_adduct_cand = peaks_gen.find_sf_adduct_cand([(0, 'He'), (9, 'Au')], {})
#
#     assert sf_adduct_cand == []


@mock.patch('engine.theor_peaks_gen.DB')
def test_apply_database_filters_organic_filter(MockDB, spark_context, sm_config, ds_config):
    ds_config['isotope_generation']['adducts'] = ['+H']
    ds_config['database']['filters'] = ["Organic"]

    peaks_gen = TheorPeaksGenerator(spark_context, sm_config, ds_config)
    sf_adduct_cand = peaks_gen.apply_database_filters([(0, 'He'), (9, 'CO2')])

    assert sf_adduct_cand == [(9, 'CO2')]


@mock.patch('engine.theor_peaks_gen.DB')
@mock.patch('engine.theor_peaks_gen.TheorPeaksGenerator._import_theor_peaks_to_db')
def test_generate_theor_peaks(mock_import_theor_peaks_to_db, mockDB, spark_context, sm_config, ds_config):
    mock_db = mockDB.return_value
    mock_db.select_one.return_value = [0]

    peaks_gen = TheorPeaksGenerator(spark_context, sm_config, ds_config)
    peaks_gen.isocalc_wrapper.isotope_peaks = lambda *args: {'centr_mzs': [100.],
                                                             'centr_ints': [1000.],
                                                             'profile_mzs': [90., 100., 110.],
                                                             'profile_ints': [1., 1000., 1001.]}

    sf_adduct_cand = [(9, 'Au', '+Na')]
    peaks_gen.generate_theor_peaks(sf_adduct_cand)

    mock_import_theor_peaks_to_db.assert_called_with([('0\t9\t+Na\t0.010000\t1\t10000\t'
                                                       '{100.000000}\t{1000.000000}\t'
                                                       '{90.000000,100.000000,110.000000}\t'
                                                       '{1.000000,1000.000000,1001.000000}')])
