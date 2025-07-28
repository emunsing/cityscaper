import os
import numpy as np
import pandas as pd
from cityscaper.utils import  latlon_filter, read_rds_to_df
from cityscaper.constants import DATA_DIR, REZONING_CODES
import logging

logger = logging.getLogger(__name__)

def pdev_model(geom_select: tuple[float, float, float, float] = (-122.43270, 37.76874, -122.43060, 37.77047),
               simulation_years: int = 50,
               random_seed: int = None,
               pdev_metric: str = 'pdev_1yr',
               rezoning_scenario: str = 'apr_2025',
               override_csv: os.PathLike | None = None,
               ) -> pd.DataFrame:

    height_estimator_func = lambda df: (df['height'] * (np.random.rand(df.shape[0]) * 0.5 + 0.5)) // 5 * 5

    assert rezoning_scenario in REZONING_CODES.keys(), f"Rezoning scenario must be one of {REZONING_CODES.keys()}"
    rezoning_fname = f"rezoning_{REZONING_CODES[rezoning_scenario]}_output.RDS"
    rezoning_scenario_data = read_rds_to_df(DATA_DIR / rezoning_fname, index_cols='mapblklot')
    assert 'height' in rezoning_scenario_data.columns
    assert 'pdev' in rezoning_scenario_data.columns

    if rezoning_scenario == 'baseline':
        rezoning_scenario_data['pdev'] = rezoning_scenario_data['pdev_baseline']
        rezoning_scenario_data['height'] = rezoning_scenario_data['ex_height2024']

    rezoning_scenario_data['pdev_1yr'] = 1 - (
            1 - rezoning_scenario_data['pdev']) ** 0.1  # Assume 10-year generating scenario

    if random_seed:
        np.random.seed(random_seed)

    lots_in_region = latlon_filter(rezoning_scenario_data, *geom_select)
    development_candidates = lots_in_region[lots_in_region['ZONING'].notnull()].copy()
    development_candidates['developed_height'] = height_estimator_func(development_candidates)

    developed_site_years = {}

    # TODO: Handle lot mergers in the override csv
    if override_csv:
        skipped_overrides = []
        override_lots = pd.read_csv(override_csv)
        assert 'mapblklot' in override_lots.columns and 'height' in override_lots.columns, "Overrides must contain mapblklot and heights"
        override_lots = override_lots.set_index('mapblklot')
        for mapblklot, s in override_lots.iterrows():
            if mapblklot not in development_candidates.index:
                continue
            developed_site_years[mapblklot] = 0
            development_candidates.loc[mapblklot, 'developed_height'] = s['height']
            development_candidates.loc[mapblklot, 'height'] = s['height']
        if skipped_overrides:
            logger.warning(f"Skipped the following mapblklot override as they are not in study area: {', '.join(skipped_overrides)}")

    for mapblklot, pdev in development_candidates[pdev_metric].items():
        if mapblklot in developed_site_years:
            continue
        for yr in range(simulation_years):
            if np.random.rand() < pdev:
                developed_site_years[mapblklot] = yr
                break
    developed_site_years = pd.Series(developed_site_years, name='development_study_year')

    developed_site_data = development_candidates.join(developed_site_years, how='right')
    developed_site_data['developed_height'] = height_estimator_func(developed_site_data)
    return developed_site_data