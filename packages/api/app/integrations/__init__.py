"""On-demand federal/national data service clients.

Each module in this package wraps a single external service used by one or
more scoring modules. They share three conventions:

  - Functions take a single point (lat, lng) or a single ID; geometry is
    serialized internally.
  - The async clients accept an ``httpx.AsyncClient`` (e.g. a
    ``RequestContext.http_client()``) so HTTP calls are captured in the
    decision trail without per-integration plumbing.
  - Returned dicts have the smallest contract the scoring stage needs —
    not the raw service response.

Verification status (smoke-tested 2026-06-05):

  ✓ nrel_pvwatts             developer.nlr.gov (domain changed from nrel.gov)
  ✓ usda_ssurgo              sdmdataaccess.sc.egov.usda.gov SDA Tabular
  ✓ usfws_critical_habitat   services.arcgis.com FeatureServer (802 polygons)
  ✓ usgs_padus               services.arcgis.com PADUS_Protected_Areas_National (306,082)
  ✓ usgs_nhdplus             hydro.nationalmap.gov NHDPlus_HR MapServer
  ✓ usgs_peak_flow           nwis.waterdata.usgs.gov/nwis/peak (RDB)
  ✓ openfema                 www.fema.gov/api/open/v2 (Disasters + NFIP claims)
  ⚠ google_grrr              gs://flood-forecasting/hydrologic_predictions (Zarr; lazy import)

Known unavailable as of 2026-06-05:

  ✗ EPA EJScreen — service discontinued Feb 2025; gaftp.epa.gov/EJScreen also 404.
  ✗ USGS StreamStats — all documented /streamstatsservices/* endpoints 404.
"""

from .epa_ejscreen import ejscreen_at_point, geocode_block_group
from .google_grrr import grrr_return_periods
from .landfire_wcs import (
    query_landfire_canopy,
    query_landfire_fuel,
    query_landfire_value,
)
from .mrlc_nlcd import nlcd_class_at_point
from .nifc_fire import query_nifc_perimeters
from .nrel_pvwatts import pvwatts_v8
from .openfema import disaster_declarations, nfip_claims_by_zip
from .usda_ssurgo import sda_point
from .usfws_critical_habitat import (
    critical_habitat_at_point,
    critical_habitat_in_envelope,
)
from .usgs_3dep import elev_multipoint_m, ground_elev_m, slope_aspect_from_grid
from .usgs_nhdplus import nhdplus_at_point
from .usgs_padus import padus_at_point, padus_in_envelope
from .usgs_peak_flow import peak_flows_for_site

__all__ = [
    "critical_habitat_at_point",
    "critical_habitat_in_envelope",
    "disaster_declarations",
    "ejscreen_at_point",
    "elev_multipoint_m",
    "geocode_block_group",
    "grrr_return_periods",
    "ground_elev_m",
    "nfip_claims_by_zip",
    "nhdplus_at_point",
    "nlcd_class_at_point",
    "padus_at_point",
    "padus_in_envelope",
    "peak_flows_for_site",
    "query_landfire_canopy",
    "query_landfire_fuel",
    "query_landfire_value",
    "query_nifc_perimeters",
    "pvwatts_v8",
    "sda_point",
    "slope_aspect_from_grid",
]
