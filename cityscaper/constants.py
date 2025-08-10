import os
import pathlib

DATA_DIR = pathlib.Path(os.path.abspath(__file__)).parent.parent / "data"
OUTPUT_DIR = DATA_DIR / "output"
EXPORT_FIELDS = ['developed_height', 'lot_coverage_discount', 'ground_floor', 'ACRES', 'height', 'Historic', 'Residential_Dummy', 'ZONING', ]
REZONING_CODES = {"baseline": "D",
                  "fall_2023": "D",
                  # "feb_2024": "E",
                  "apr_2025": "F",
                  "builders_remedy": "BR",
                  }