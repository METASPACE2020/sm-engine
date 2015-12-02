DROP TABLE IF EXISTS formula_db;
CREATE TABLE formula_db (
	id		int,
	version	date,
    name	text,
	CONSTRAINT id_version_ind PRIMARY KEY(id, version)
);
CREATE INDEX ind_formula_db_name ON formula_db (name);
INSERT INTO formula_db VALUES (0, '2015-01-01', 'HMDB'), (1, '2015-01-01', 'apple_db');

DROP TABLE IF EXISTS formula;
CREATE TABLE formula (
	db_id	int,
	id		text,
	sf_id 	int,
	name	text,
	sf 		text,
	CONSTRAINT formula_dbid_id PRIMARY KEY(db_id, id)
);

DROP TABLE IF EXISTS agg_formula;
CREATE TABLE agg_formula (
    db_id 		int,
	id 		    int,
	sf 		    text,
	subst_ids 	text[],
	names 		text[],
	CONSTRAINT db_id_id_ind PRIMARY KEY(db_id, id)
);

;
CREATE INDEX ind_agg_formulas_1 ON agg_formula (sf);
CREATE INDEX ind_agg_formulas_2 ON agg_formula (id);
CREATE INDEX ind_agg_formulas_3 ON agg_formula (id, sf);
CREATE INDEX ind_agg_formulas_4 ON agg_formula (db_id, id, sf);

DROP TABLE IF EXISTS dataset;
CREATE TABLE dataset (
	id	        int,
	name		text,
	file_path   text,
	img_bounds	json,
	CONSTRAINT dataset_id_ind PRIMARY KEY(id)
);
CREATE INDEX ind_dataset_name ON dataset (name);

DROP TABLE IF EXISTS coordinates;
CREATE TABLE coordinates (
	ds_id 	int,
	xs       int[],
	ys       int[],
	CONSTRAINT coord_ds_id_ind PRIMARY KEY(ds_id)
);
CREATE INDEX ind_coordinates_2 ON coordinates (ds_id);

DROP TABLE IF EXISTS job;
CREATE TABLE job (
	id 			int,
	db_id       int,
	ds_id	    int,
	status		text,
	tasks_done	int,
	tasks_total	int,
	start       timestamp,
	finish      timestamp,
	CONSTRAINT job_id_ind PRIMARY KEY(id)
);

DROP TABLE IF EXISTS iso_image;
CREATE TABLE iso_image (
	job_id		int,
	db_id		int,
	sf_id		int,
	adduct 		text,
	peak		int,
	pixel_inds  int[],
	intensities	real[],
	min_int		real,
	max_int		real,
	CONSTRAINT iso_image_id_ind PRIMARY KEY(job_id, db_id, sf_id, adduct, peak)
);

DROP TABLE IF EXISTS iso_image_metrics;
CREATE TABLE iso_image_metrics (
	job_id		int,
	db_id		int,
	sf_id		int,
	adduct 		text,
	peaks_n		int,
	stats 		json,
	CONSTRAINT iso_image_metrics_id_ind PRIMARY KEY(job_id, db_id, sf_id, adduct)
);

DROP TABLE IF EXISTS theor_peaks;
CREATE TABLE theor_peaks (
    db_id           int,
	sf_id			int,
	adduct			text,
	centr_mzs		double precision[],
	centr_ints		double precision[],
	prof_mzs		double precision[],
	prof_ints		double precision[],
	CONSTRAINT sf_id_adduct PRIMARY KEY(db_id, sf_id, adduct)
);
CREATE INDEX ind_theor_peaks_2 ON theor_peaks(db_id, sf_id);
