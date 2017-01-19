from sm.engine.msm_basic.formula_imager_segm import compute_sf_images
from sm.engine.msm_basic.formula_img_validator import sf_image_metrics, sf_image_metrics_est_fdr
from sm.engine.search_algorithm import SearchAlgorithm
from sm.engine.png_generator import PngGenerator

import logging
logger = logging.getLogger('sm-engine')


class MSMBasicSearch(SearchAlgorithm):

    def __init__(self, sc, ds, formulas, fdr, ds_config):
        super(MSMBasicSearch, self).__init__(sc, ds, formulas, fdr, ds_config)
        self.metrics = ['chaos', 'spatial', 'spectral']
        self.max_fdr = 0.5

    def search(self):
        """ Search for molecules in the dataset

        Returns
        -------
        : tuple
            (ion metrics DataFrame, ion image urls dict)
        """
        logger.info('Running molecule search')
        ion_images = compute_sf_images(self.sc, self.ds, self.formulas.get_sf_peak_df(),
                                      self.ds_config['image_generation']['ppm'])
        all_sf_metrics_df = self.calc_metrics(ion_images)
        sf_metrics_fdr_df = self.estimate_fdr(all_sf_metrics_df)
        sf_metrics_fdr_df = self.filter_sf_metrics(sf_metrics_fdr_df)
        ion_images = self.filter_sf_images(ion_images, sf_metrics_fdr_df)

        png_generator = PngGenerator(self.ds.coords)
        ion_img_urls = dict(ion_images.mapValues(
            lambda imgs: png_generator.save_imgs_as_png(imgs)).collect())

        return sf_metrics_fdr_df, ion_img_urls

    def calc_metrics(self, sf_images):
        all_sf_metrics_df = sf_image_metrics(sf_images, self.sc, self.formulas, self.ds, self.ds_config)
        return all_sf_metrics_df

    def estimate_fdr(self, all_sf_metrics_df):
        sf_metrics_fdr_df = sf_image_metrics_est_fdr(all_sf_metrics_df, self.formulas, self.fdr)
        return sf_metrics_fdr_df

    def filter_sf_metrics(self, sf_metrics_df):
        return sf_metrics_df[sf_metrics_df.fdr <= self.max_fdr]
