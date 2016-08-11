import numpy as np
from mock import patch, MagicMock
from numpy.testing import assert_array_equal

from sm.engine.dataset import Dataset
from sm.engine.util import SMConfig
from sm.engine.work_dir import WorkDirManager
from sm.engine.tests.util import sm_config, ds_config, spark_context


def test_get_sample_area_mask_correctness(sm_config, ds_config, spark_context):
    work_dir_man_mock = MagicMock(WorkDirManager)
    work_dir_man_mock.ds_coord_path = '/ds_path'
    work_dir_man_mock.txt_path = '/txt_path'

    SMConfig._config_dict = sm_config

    with patch('sm.engine.tests.util.SparkContext.textFile') as m:
        m.return_value = spark_context.parallelize([
            '0,0,0\n',
            '2,1,1\n'])

        ds = Dataset(spark_context, 'ds_name', '', 'input_path', ds_config, work_dir_man_mock, None)

        #ds.norm_img_pixel_inds = np.array([0, 3])

        assert tuple(ds.get_sample_area_mask()) == (True, False, False, True)


# def test_get_dims_2by3(spark_context, sm_config):
#     with patch('engine.tests.util.SparkContext.textFile') as m:
#         m.return_value = spark_context.parallelize([
#             '0,0,1\n',
#             '1,2,2\n',
#             '2,2,1\n',
#             '3,0,2\n',
#             '4,1,2\n'])
#         work_dir_mock = MagicMock(WorkDir)
#         work_dir_mock.coord_path = '/fn'
#
#         SMConfig._config_dict = sm_config
#         ds = Dataset(spark_context, '', '', {}, work_dir_mock, None)
#
#         m.assert_called_once_with('file:///fn')
#         assert ds.get_dims() == (2, 3)
#
#
# def test_get_norm_img_pixel_inds_2by3(spark_context, sm_config):
#     with patch('engine.tests.util.SparkContext.textFile') as m:
#         m.return_value = spark_context.parallelize([
#             '0,0,1\n',
#             '1,2,2\n',
#             '2,2,1\n',
#             '3,0,2\n',
#             '4,1,2\n'])
#         work_dir_mock = MagicMock(WorkDir)
#         work_dir_mock.coord_path = '/fn'
#
#         SMConfig._config_dict = sm_config
#         ds = Dataset(spark_context, '', 0, {}, work_dir_mock, None)
#
#         m.assert_called_once_with('file:///fn')
#         assert_array_equal(ds.get_norm_img_pixel_inds(), [0, 5, 2, 3, 4])
#
#
# def test_get_spectra_2by3(spark_context, sm_config):
#     with patch('engine.tests.util.SparkContext.textFile') as m:
#         m.return_value = spark_context.parallelize([
#             '0|100|100\n',
#             '1|101|0\n',
#             '2|102|0\n',
#             '3|103|0\n',
#             '4|200|10\n'])
#         work_dir_mock = MagicMock(WorkDir)
#         work_dir_mock.coord_path = '/coord_path'
#         work_dir_mock.txt_path = '/txt_path'
#
#         with patch('engine.tests.test_dataset.Dataset._define_pixels_order'):
#             SMConfig._config_dict = sm_config
#             ds = Dataset(spark_context, '', 0, {}, work_dir_mock, None)
#             res = ds.get_spectra().collect()
#             exp_res = [(0, np.array([100.]), np.array([100.])),
#                        (1, np.array([101.]), np.array([0.])),
#                        (2, np.array([102.]), np.array([0.])),
#                        (3, np.array([103.]), np.array([0.])),
#                        (4, np.array([200.]), np.array([10.]))]
#
#             m.assert_called_once_with('file:///txt_path', minPartitions=8)
#             assert len(res) == len(exp_res)
#
#             for r, exp_r in zip(res, exp_res):
#                 assert len(r) == len(exp_r)
#                 assert r[0] == r[0]
#                 assert_array_equal(r[1], exp_r[1])
#                 assert_array_equal(r[2], exp_r[2])
