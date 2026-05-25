"""Shared configuration for the Sonoma wildfire raster pipeline."""

from __future__ import annotations

from pathlib import Path

# Sonoma County study extent (lon_min, lat_min, lon_max, lat_max), EPSG:4326.
# Slightly larger than the user-supplied bbox so canopy-buffer convolutions and
# distance-transform edge effects don't bias structures near the county edge.
SONOMA_BBOX_4326 = (-123.55, 38.05, -122.35, 38.86)

# Working projected CRS. EPSG:3310 (California Albers, NAD83) is the standard
# California-wide equal-area projection; metres are correct and the projection
# is supported everywhere we'll resample/derive.
WORKING_CRS = "EPSG:3310"

# Output raster grid resolution in metres. 30 m matches LANDFIRE native and
# keeps the Sonoma extent at ~3000 x 3000 px — comfortable for in-memory
# scipy convolutions and FFT-based circular-buffer means.
TARGET_PIX_M = 30.0

# Filesystem layout.
PKG_ROOT = Path(__file__).resolve().parents[2]
RASTER_ROOT = PKG_ROOT / "rasters" / "sonoma"
RAW_DIR = RASTER_ROOT / "raw"
DERIVED_DIR = RASTER_ROOT / "derived"

# Cached source downloads.
WRC_CA_ZIP = RAW_DIR / "wrc_california.zip"
WRC_BP_TIF = RAW_DIR / "wrc_bp_sonoma.tif"
DEM_TIF = RAW_DIR / "dem_sonoma.tif"
FBFM40_TIF = RAW_DIR / "fbfm40_sonoma.tif"
CC_TIF = RAW_DIR / "cc_sonoma.tif"
LANDFIRE_ZIP = RAW_DIR / "landfire_sonoma.zip"

# Derived outputs.
SLOPE_TIF = DERIVED_DIR / "slope_deg.tif"
DIST_TO_FUEL_TIF = DERIVED_DIR / "dist_to_burnable_m.tif"
CC_30_TIF = DERIVED_DIR / "cc_30m.tif"
CC_100_TIF = DERIVED_DIR / "cc_100m.tif"
CC_300_TIF = DERIVED_DIR / "cc_300m.tif"

# FBFM40 non-burnable codes (LANDFIRE FBFM40 v2.0.0 conventions):
#   91 = NB1 urban
#   92 = NB2 snow/ice
#   93 = NB3 agriculture
#   98 = NB8 open water
#   99 = NB9 bare ground
# Treat 0/255 (nodata) as non-burnable for distance-transform purposes.
NB_FBFM40_CODES = {0, 91, 92, 93, 98, 99, -9999, 255}

# Source URLs.
# WRC Burn Probability lives in the Short et al. (2020) FSim publication
# RDS-2016-0034-2 — a CONUS-wide 270 m raster derived from LANDFIRE 2014. The
# 30 m upsampled version in RDS-2020-0016 is only delivered via Box per-state
# zips, and those Box share URLs are intermittently 404'd; the 270 m parent is
# a reliable HTTPS download direct from fs.usda.gov.
WRC_CA_URL = (
    "https://www.fs.usda.gov/rds/archive/products/RDS-2016-0034-2/"
    "RDS-2016-0034-2.zip"
)
# LFPS migrated off the legacy ArcGIS GP-service in 2025; the current JSON
# API takes JSON-body POSTs with an Email field and polls via JobId query.
LANDFIRE_SUBMIT_URL = "https://lfps.usgs.gov/api/job/submit"
LANDFIRE_STATUS_URL = "https://lfps.usgs.gov/api/job/status"
LANDFIRE_EMAIL = "dhazarik@gmail.com"  # required by the new API
# Valid LFPS product codes are "LFyyyy_<acronym>" — see /api/products.
LANDFIRE_LAYER_LIST = "LF2022_FBFM40;LF2022_CC"
DEM_IMAGESERVER_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/exportImage"
)


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
