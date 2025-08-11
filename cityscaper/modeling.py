import os
import numpy as np
import pandas as pd
from cityscaper.utils import  latlon_filter, read_rds_to_df, geojson_rds_to_json, geojson_to_parcel_bound_latlon
from cityscaper.constants import DATA_DIR, REZONING_CODES
import logging

logger = logging.getLogger(__name__)
UNFILTERED_REZONING_DATA = DATA_DIR / "five_rezonings_nongeo_unfiltered.rds"
GEOM_DATA_UNFILTERED = DATA_DIR / "sf_map_unfiltered.rds"
ZONING_OVERRIDE_STRING = "Override"

def get_site_data(geom_select: tuple[float, float, float, float] = (-122.43270, 37.76874, -122.43060, 37.77047),
                  rezoning_scenario: str = 'apr_2025',
                  override_csv: os.PathLike | None = None,
                  random_seed: int | None = None,
                  unfilterered_rezoning_data_rds: os.PathLike = UNFILTERED_REZONING_DATA,
                  geom_data_rds: os.PathLike = GEOM_DATA_UNFILTERED,
                  ) -> pd.DataFrame:

    if random_seed:
        np.random.seed(random_seed)
    height_estimator_func = lambda df: (df['height'] * (np.random.rand(df.shape[0]) * 0.3 + 0.7)) // 5 * 5

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
    rezoning_scenario_data['developed_height'] = height_estimator_func(rezoning_scenario_data)

    if override_csv:
        # TODO: Handle lot mergers in the override csv
        override_lots = pd.read_csv(override_csv, index_col='mapblklot')
        assert 'height' in override_lots.columns, "Overrides must contain mapblklot and heights"
        lots_needing_data = override_lots.index.difference(rezoning_scenario_data.index)
        if len(lots_needing_data) > 0:
            logger.warning(
                f"Override lots {', '.join(lots_needing_data)} are not in rezoning scenario data, loading unfiltered data- are they in the Pipeline?")
            unfiltered_rezoning_data = read_rds_to_df(unfilterered_rezoning_data_rds, index_cols='mapblklot')
            auxiliary_lots = lots_needing_data.intersection(unfiltered_rezoning_data.index)
            raw_geom_geojson = geojson_to_parcel_bound_latlon(geojson_rds_to_json(geom_data_rds))
            auxiliary_lots = [mapblklot for mapblklot in auxiliary_lots if mapblklot in raw_geom_geojson]
            auxiliary_data = unfiltered_rezoning_data.loc[auxiliary_lots, :].copy()
            rezoning_scenario_data = pd.concat([rezoning_scenario_data, auxiliary_data], axis=0)
            missing_data = lots_needing_data.difference(auxiliary_lots)
            if len(missing_data) > 0:
                print(f"Skipped overrides for {', '.join(missing_data)} as they are not present in the data.")
        lots_with_overrides = override_lots.index.intersection(rezoning_scenario_data.index)
        rezoning_scenario_data.loc[lots_with_overrides, 'pdev_1yr'] = 1
        rezoning_scenario_data.loc[lots_with_overrides, 'ZONING'] = ZONING_OVERRIDE_STRING
        rezoning_scenario_data.loc[lots_with_overrides, 'height'] = override_lots.loc[lots_with_overrides, 'height']
        rezoning_scenario_data.loc[lots_with_overrides, 'developed_height'] = override_lots.loc[
            lots_with_overrides, 'height']

    lots_in_region = latlon_filter(rezoning_scenario_data, *geom_select)
    development_candidates = lots_in_region[lots_in_region['ZONING'].notnull()].copy()
    development_candidates = development_candidates.groupby(level='mapblklot').first()
    return development_candidates

def lotwise_pdev_sim(development_candidates: pd.DataFrame,
                     simulation_years: int = 50,
                     random_seed: int = None,
                     pdev_metric: str = 'pdev_1yr',
                     pdev_correction_factor: float = 1.0,
                     ) -> pd.DataFrame:
    if random_seed:
        np.random.seed(random_seed)

    developed_site_years = {}
    for mapblklot, pdev in development_candidates[pdev_metric].items():
        if development_candidates.loc[mapblklot, 'ZONING'] == ZONING_OVERRIDE_STRING:
            developed_site_years[mapblklot] = 0  # Override lots are considered developed in year 0
            continue
        for yr in range(1, simulation_years+1):
            if np.random.rand() <= pdev / pdev_correction_factor:
                developed_site_years[mapblklot] = yr
                break
    developed_site_years = pd.Series(developed_site_years, name='development_study_year')

    developed_site_data = development_candidates.join(developed_site_years, how='right')
    return developed_site_data

def pdev_model(geom_select: tuple[float, float, float, float] = (-122.43270, 37.76874, -122.43060, 37.77047),
               simulation_years: int = 50,
               random_seed: int = None,
               pdev_metric: str = 'pdev_1yr',
               pdev_correction_factor: float = 1.0,
               rezoning_scenario: str = 'apr_2025',
               override_csv: os.PathLike | None = None,
               exclude_csv: os.PathLike | None = None,
               unfilterered_rezoning_data_rds: os.PathLike = UNFILTERED_REZONING_DATA,
               geom_data_rds: os.PathLike = GEOM_DATA_UNFILTERED,
               ) -> pd.DataFrame:

    development_candidates = get_site_data(
        geom_select=geom_select,
        rezoning_scenario=rezoning_scenario,
        override_csv=override_csv,
        random_seed=random_seed,
        unfilterered_rezoning_data_rds=unfilterered_rezoning_data_rds,
        geom_data_rds=geom_data_rds
    )

    if exclude_csv:
        exclude_lots = pd.read_csv(exclude_csv, dtype={'mapblklot': str}, index_col='mapblklot')
        exclude_lots = exclude_lots.index.intersection(development_candidates.index)
        if exclude_lots.empty:
            logger.warning(f"Exclude_lots csv was specified, but no eligible lots in the study area! Double-check study zone and file format?")
        development_candidates = development_candidates.drop(index=exclude_lots, errors='ignore')

    developed_site_data = lotwise_pdev_sim(
        development_candidates=development_candidates,
        simulation_years=simulation_years,
        random_seed=random_seed,
        pdev_metric=pdev_metric,
        pdev_correction_factor=pdev_correction_factor
    )

    return developed_site_data