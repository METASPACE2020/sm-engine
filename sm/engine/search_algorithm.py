
class SearchAlgorithm(object):

    def __init__(self, sc, ds, formulas, fdr, ds_config):
        self.sc = sc
        self.ds = ds
        self.formulas = formulas
        self.fdr = fdr
        self.ds_config = ds_config
        self.metrics = []

    def search(self):
        pass

    def calc_metrics(self, sf_images):
        pass

    def estimate_fdr(self, all_sf_metrics_df):
        pass

    def filter_sf_metrics(self, sf_metrics_df):
        return sf_metrics_df[sf_metrics_df.msm > 0]

    def filter_sf_images(self, sf_images, sf_metrics_df):
        return sf_images.filter(lambda (sf_i, _): sf_i in sf_metrics_df.index)
