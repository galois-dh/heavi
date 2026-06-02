"""Seed data for the data_sources table — Heavi Platform Refactor Phase 1.

Every row is transcribed from Heavi_Platform_Refactor_Spec.md verbatim. The
metadata (coverage_type, reliability, access_config, known_gaps) reflects what
was actually verified during Phase A data loading — see docs/data_loaders_
status.md (commits 2a0029c and c6a2c55) for the verification log.

Note: the spec narrative says "22 sources"; the spec body lists 25 source
blocks, so 25 are seeded here. The discrepancy was flagged in the Phase 1
delivery message.

Run `python -m app.data_repository_seed` to upsert. Idempotent — safe to
re-run after schema changes.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime

# Load .env from monorepo root so a direct `python -m` works.
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _ds(**kw: Any) -> dict[str, Any]:
    """Default optional fields to None so the INSERT-binding doesn't need to
    branch on which fields each row supplies."""
    return {
        "source_id":            kw["source_id"],
        "name":                 kw["name"],
        "provider":             kw["provider"],
        "description":          kw.get("description"),
        "access_method":        kw["access_method"],
        "access_config":        kw["access_config"],
        "coverage_type":        kw["coverage_type"],
        "coverage_states":      kw.get("coverage_states"),
        "coverage_notes":       kw.get("coverage_notes"),
        "resolution":           kw.get("resolution"),
        "vintage":              kw.get("vintage"),
        "update_frequency":     kw.get("update_frequency"),
        "reliability":          kw["reliability"],
        "last_verified":        kw.get("last_verified"),
        "known_gaps":           kw.get("known_gaps"),
        "license":              kw.get("license"),
        "source_url":           kw.get("source_url"),
        "citation":             kw.get("citation"),
        "data_category":        kw["data_category"],
        "applicable_workflows": kw.get("applicable_workflows"),
    }


# Verification timestamp for the Phase A inventory pass.
_PHASE_A_TS = datetime(2026, 6, 5, tzinfo=UTC)


SEED: list[dict[str, Any]] = [
    _ds(
        source_id="nrel_pvwatts_v8",
        name="NREL PVWatts v8",
        provider="National Renewable Energy Laboratory",
        description=("Hourly PV system simulation using TMY weather data. Returns annual "
                     "energy production, capacity factor, monthly profile."),
        access_method="rest_api",
        access_config={"endpoint": "https://developer.nlr.gov/api/pvwatts/v8.json",
                       "auth": "api_key", "key_env_var": "NREL_API_KEY"},
        coverage_type="national",
        coverage_notes="CONUS + Hawaii. Uses nearest NSRDB TMY station.",
        resolution="site-specific (nearest TMY station, typically <5km)",
        vintage="2020 TMY",
        update_frequency="periodic (NSRDB updates)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="Domain changed from developer.nrel.gov to developer.nlr.gov on May 29, 2026.",
        license="public_domain",
        source_url="https://developer.nlr.gov/docs/solar/pvwatts/v8/",
        data_category="solar_resource",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="usgs_3dep",
        name="USGS 3DEP Digital Elevation Model",
        provider="U.S. Geological Survey",
        description=("Ground elevation at any US coordinate. Used for slope, aspect, "
                     "terrain analysis."),
        access_method="rest_api",
        access_config={"endpoint": "https://epqs.nationalmap.gov/v1/json",
                       "params": {"units": "Meters", "wkid": "4326"}},
        coverage_type="national",
        resolution="~10m (1/3 arc-second)",
        vintage="current (continuously updated)",
        update_frequency="continuous",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="None documented.",
        license="public_domain",
        source_url="https://apps.nationalmap.gov/3depdem/",
        data_category="terrain",
        applicable_workflows=["solar_siting", "hazard_assessment"],
    ),
    _ds(
        source_id="fema_nfhl",
        name="FEMA National Flood Hazard Layer",
        provider="Federal Emergency Management Agency",
        description=("Flood zones and Base Flood Elevations. Used for flood risk "
                     "and as solar/hazard exclusion constraint."),
        access_method="rest_api",
        access_config={"endpoint": "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query",
                       "format": "esriGeometryEnvelope"},
        coverage_type="national",
        coverage_notes="Coverage varies by community. Some rural areas unmapped.",
        resolution="parcel-level polygons",
        vintage="varies by community (some maps 10-20 years old)",
        update_frequency="community-by-community updates",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Map currency varies. Pluvial flooding not mapped. Some rural areas "
                    "have no NFHL coverage."),
        license="public_domain",
        source_url="https://www.fema.gov/flood-maps/national-flood-hazard-layer",
        data_category="hazard",
        applicable_workflows=["solar_siting", "hazard_assessment"],
    ),
    _ds(
        source_id="usace_nsi",
        name="USACE National Structure Inventory v2",
        provider="U.S. Army Corps of Engineers",
        description=("Building characteristics for every US structure. Occupancy, "
                     "foundation, stories, replacement value, first floor height."),
        access_method="rest_api",
        access_config={"endpoint": "https://nsi.sec.usace.army.mil/nsiapi/structures",
                       "method": "POST", "format": "geojson_polygon"},
        coverage_type="national",
        resolution="point (structure-level, synthesized centroids)",
        vintage="2023",
        update_frequency="periodic",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Positions are synthesized centroids (20-100m error). First floor "
                    "heights are estimated, not surveyed."),
        license="public_domain",
        source_url="https://nsi.sec.usace.army.mil",
        data_category="building",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="usda_sda_ssurgo",
        name="USDA Soil Data Access (SSURGO)",
        provider="USDA Natural Resources Conservation Service",
        description=("Soil properties via national SQL API. Drainage class, hydric "
                     "rating, hydrologic group, depth to water table, shrink-swell."),
        access_method="rest_api",
        access_config={"endpoint": "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest",
                       "method": "POST", "format": "json+tsql"},
        coverage_type="national",
        coverage_notes="Coverage varies. Some areas have STATSGO (coarser) instead of SSURGO.",
        resolution="soil map unit polygons (varies, typically 1:12,000 to 1:24,000)",
        vintage="2023",
        update_frequency="annual",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="Urban areas may lack detailed survey. STATSGO fallback is much coarser.",
        license="public_domain",
        source_url="https://sdmdataaccess.sc.egov.usda.gov",
        data_category="soil",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="hifld_transmission",
        name="HIFLD Electric Power Transmission Lines",
        provider="Homeland Infrastructure Foundation-Level Data",
        description=("National transmission line network. Voltage, owner, distance "
                     "calculations for interconnection analysis."),
        access_method="postgis_table",
        access_config={"table": "solar_transmission_lines",
                       "geometry_column": "geometry", "srid": 4326},
        coverage_type="national",
        resolution="line segments",
        vintage="2024",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="None documented. 52,244 segments loaded.",
        license="public_domain",
        data_category="infrastructure",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="osm_substations",
        name="OpenStreetMap Power Substations",
        provider="OpenStreetMap contributors",
        description=("Electrical substations. PostGIS cache for 6 states + Overpass "
                     "on-demand fallback for national coverage."),
        access_method="postgis_table",
        access_config={
            "table": "substations_osm_us", "geometry_column": "geometry", "srid": 4326,
            "fallback": {
                "method": "overpass_api",
                "endpoint": "https://overpass-api.de/api/interpreter",
                "query_template": (
                    "[out:json][timeout:30];(node[\"power\"=\"substation\"]"
                    "(around:50000,{lat},{lng});way[\"power\"=\"substation\"]"
                    "(around:50000,{lat},{lng}););out center;"
                ),
            },
        },
        coverage_type="national",
        coverage_states=["CA", "TX", "AZ", "NV", "FL", "NC"],
        coverage_notes=("16,725 substations cached for 6 states. Overpass API fallback "
                        "works nationally but adds latency (2-5s) and can timeout."),
        resolution="point",
        vintage="2026-06-05",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Cache coverage limited to 6 states. Overpass fallback is functional "
                    "but fragile under load."),
        license="ODbL",
        source_url="https://www.openstreetmap.org",
        data_category="infrastructure",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="eia_form860",
        name="EIA Form 860 Operating Solar Plants",
        provider="U.S. Energy Information Administration",
        description=("All operating solar PV plants in the US. Used for congestion "
                     "assessment and validation."),
        access_method="postgis_table",
        access_config={"table": "solar_eia_installations",
                       "geometry_column": "geometry", "srid": 4326},
        coverage_type="national",
        resolution="plant-level points",
        vintage="2024",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="None documented. 6,321 operating PV plants loaded.",
        license="public_domain",
        source_url="https://www.eia.gov/electricity/data/eia860/",
        data_category="infrastructure",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="usfws_critical_habitat",
        name="USFWS Critical Habitat Designations",
        provider="U.S. Fish and Wildlife Service",
        description=("Designated critical habitat for threatened and endangered species. "
                     "Environmental exclusion constraint."),
        access_method="rest_api",
        access_config={
            "endpoint": ("https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/"
                         "USFWS_Critical_Habitat/FeatureServer/2/query"),
            "format": "geojson", "spatial_rel": "esriSpatialRelIntersects",
        },
        coverage_type="national",
        resolution="polygon",
        vintage="current (updated with new designations)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("802 polygons nationally. Coverage reflects only species with formal "
                    "critical habitat designations."),
        license="public_domain",
        source_url="https://ecos.fws.gov/ecp/report/critical-habitat",
        data_category="environmental",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="usgs_padus",
        name="USGS Protected Areas Database (PAD-US)",
        provider="U.S. Geological Survey",
        description=("National parks, wilderness areas, conservation easements, and other "
                     "protected lands."),
        access_method="rest_api",
        access_config={"endpoint": "https://mapservices.nps.gov/arcgis/rest/services/padus/FeatureServer/0/query",
                       "format": "geojson"},
        coverage_type="national",
        resolution="polygon",
        vintage="2024",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="306,082 polygons loaded nationally.",
        license="public_domain",
        source_url="https://maps.usgs.gov/padus/",
        data_category="environmental",
        applicable_workflows=["solar_siting", "hazard_assessment"],
    ),
    _ds(
        source_id="nlcd_land_cover",
        name="NLCD Land Cover",
        provider="Multi-Resolution Land Characteristics Consortium (MRLC)",
        description=("Land cover classification at any US coordinate. Cropland, forest, "
                     "developed, wetland, etc."),
        access_method="wms",
        access_config={
            "endpoint": "https://www.mrlc.gov/geoserver/mrlc_display/NLCD_2021_Land_Cover_L48/wms",
            "service": "WMS", "request": "GetFeatureInfo", "layers": "NLCD_2021_Land_Cover_L48",
        },
        coverage_type="national",
        resolution="30m",
        vintage="2021",
        update_frequency="every 2-3 years",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="MRLC bucket URLs may change. WMS GetFeatureInfo verified working.",
        license="public_domain",
        source_url="https://www.mrlc.gov/data/nlcd-2021-land-cover-conus",
        data_category="land_cover",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="epa_ejscreen",
        name="EPA EJScreen Block Group Data",
        provider="U.S. Environmental Protection Agency (archived)",
        description=("Environmental justice screening indicators at census block group "
                     "level. EJ index percentiles, demographic index, environmental burden."),
        access_method="postgis_table",
        access_config={"table": "ejscreen_blockgroups", "join_field": "geoid",
                       "lookup": "census_block_group_geocoder"},
        coverage_type="national",
        resolution="census block group",
        vintage="2024 (v2.3, archived from Wayback Machine 2025-02-06 snapshot)",
        update_frequency="discontinued (EPA tool taken offline Feb 2025)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Static snapshot. Will not be updated unless EPA restores the tool. "
                    "243,022 block groups loaded."),
        license="public_domain",
        data_category="environmental",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="nwi_wetlands",
        name="USFWS National Wetlands Inventory",
        provider="U.S. Fish and Wildlife Service",
        description=("Wetland boundaries and classifications. Environmental exclusion "
                     "constraint for solar siting."),
        access_method="postgis_table",
        access_config={
            "table": "solar_wetlands_ca", "geometry_column": "geometry", "srid": 4326,
            "fallback": {
                "method": "rest_api",
                "endpoint": "https://fwsprimary.wim.usgs.gov/server/rest/services/Wetlands/MapServer/0/query",
                "status": "UNVERIFIED — national REST endpoint needs testing",
            },
        },
        coverage_type="county",
        coverage_states=["CA"],
        coverage_notes=("44,573 polygons loaded for Kern County CA only. National REST "
                        "endpoint exists but was flagged as degraded. NOT YET VERIFIED "
                        "for national on-demand use."),
        resolution="polygon",
        vintage="2023",
        reliability="degraded",
        last_verified=_PHASE_A_TS,
        known_gaps=("CRITICAL GAP — only Kern County loaded. Re-tested 2026-06-05 at "
                    "Houston + Portland: layer-info probe returns empty service metadata "
                    "and envelope queries fail with HTTP 500 'Error performing query "
                    "operation'. National service remains degraded. SSURGO hydric flag "
                    "is a partial proxy but not a substitute."),
        license="public_domain",
        source_url="https://www.fws.gov/program/national-wetlands-inventory",
        data_category="environmental",
        applicable_workflows=["solar_siting"],
    ),
    _ds(
        source_id="google_inundation_history",
        name="Google Inundation History",
        provider="Google Research",
        description=("Satellite-derived flood frequency at 128m resolution. How often "
                     "each pixel was wet between 1999-2020."),
        access_method="postgis_table",
        access_config={"table": "flood_inundation_history",
                       "geometry_column": "geometry", "srid": 4326},
        coverage_type="regional",
        coverage_notes=("Excludes US territory above ~43°N (no data for northern "
                        "WA/MT/ND/MN/WI/MI/NY/VT/NH/ME/AK)."),
        resolution="128m",
        vintage="1999-2020",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="Northern US excluded. 383 polygons loaded.",
        license="CC-BY-4.0",
        source_url="https://sites.research.google/gr/floodforecasting/resources/",
        citation="Google Flood Forecasting team",
        data_category="hydrology",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="google_grrr",
        name="Google Runoff Reanalysis & Reforecast (GRRR)",
        provider="Google Research",
        description=("Global river discharge estimates at daily resolution on "
                     "HydroBasins framework (1980-2023). AI-derived hydrologic predictions."),
        access_method="file",
        access_config={
            "format": "zarr",
            "location": "gs://flood-forecasting/hydrologic_predictions/",
            "deps": ["xarray", "zarr", "gcsfs"],
        },
        coverage_type="national",
        resolution="HydroBasins catchments (PFAF-12)",
        vintage="1980-2023",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Requires xarray/zarr/gcsfs. HydroBASINS catchment-ID lookup needed "
                    "for point queries (PFAF-12 polygons or REST wrapper)."),
        license="CC-BY-4.0",
        source_url="https://sites.research.google/gr/floodforecasting/resources/",
        data_category="hydrology",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="usgs_nhdplus",
        name="USGS NHDPlus High Resolution",
        provider="U.S. Geological Survey",
        description=("Flowlines, HUC-12 watershed boundaries, stream order. For "
                     "watershed identification and stream proximity."),
        access_method="rest_api",
        access_config={"endpoint": "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer",
                       "layers": {"flowlines": 2, "huc12": 8}},
        coverage_type="national",
        resolution="1:24,000",
        vintage="current",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="On-demand REST avoids 22 GB national download. Query response times vary.",
        license="public_domain",
        source_url="https://www.usgs.gov/national-hydrography/nhdplus-high-resolution",
        data_category="hydrology",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="openfema_disasters",
        name="OpenFEMA Disaster Declarations",
        provider="Federal Emergency Management Agency",
        description=("FEMA disaster declarations by county. Also NFIP claims by zip code. "
                     "Historical flood context."),
        access_method="rest_api",
        access_config={"endpoint": "https://www.fema.gov/api/open/v2/DisasterDeclarations",
                       "claims_endpoint": "https://www.fema.gov/api/open/v2/FimaNfipClaims"},
        coverage_type="national",
        resolution="county (declarations), zip code (claims)",
        vintage="current (continuously updated)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="NFIP claims data has coordinate redaction (~0.1 degree).",
        license="public_domain",
        source_url="https://www.fema.gov/about/openfema/data-sets",
        data_category="hazard",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="usgs_peak_flow",
        name="USGS Peak Flow Data",
        provider="U.S. Geological Survey",
        description=("Annual peak streamflow values at USGS gauge stations. Historical "
                     "flood magnitude data."),
        access_method="rest_api",
        access_config={"endpoint": "https://waterservices.usgs.gov/nwis/peak/", "format": "rdb"},
        coverage_type="national",
        resolution="gauge-level (point)",
        vintage="current (continuously updated)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="Coverage depends on gauge density. Rural areas may have distant gauges.",
        license="public_domain",
        source_url="https://waterservices.usgs.gov",
        data_category="hydrology",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="hazus_ddfs",
        name="HAZUS Depth-Damage Functions",
        provider="FEMA / USACE Institute for Water Resources",
        description=("Damage percentage as a function of flood depth by building type. "
                     "174 rows covering 6 occupancy classes."),
        access_method="postgis_table",
        access_config={"table": "hazus_ddfs",
                       "lookup": "occupancy_class + foundation_type + depth"},
        coverage_type="national",
        resolution="lookup table (not spatial)",
        vintage="2024 (reconciled against FEMA HAZUS database)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="Stillwater assumption. Velocity and wave action not separately modeled.",
        license="public_domain",
        data_category="hazard",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="usfs_fsim",
        name="USFS Fire Simulation (FSim) Wildfire Likelihood",
        provider="USDA Forest Service",
        description=("Probabilistic annual burn probability at 270m resolution from "
                     "thousands of simulated fire seasons."),
        access_method="postgis_table",
        access_config={"table": "wildfire_fsim_likelihood", "format": "raster_extracted_to_points"},
        coverage_type="national",
        resolution="270m",
        vintage="LANDFIRE 2014 fuels",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Uses LANDFIRE 2014 fuels — temporal mismatch with current conditions. "
                    "Dataset ID: RDS-2016-0034-2."),
        license="public_domain",
        source_url="https://www.fs.usda.gov/rds/archive/catalog/RDS-2016-0034-2",
        citation="Finney et al. (2011)",
        data_category="hazard",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="landfire_fuels_canopy",
        name="LANDFIRE Fuel Models and Canopy Cover",
        provider="USGS / USFS",
        description=("30m fuel model classification and canopy cover percentage. Used "
                     "for wildfire exposure enrichment."),
        access_method="postgis_table",
        access_config={"table": "wildfire_exposure_enrichment",
                       "format": "raster_extracted_to_structures"},
        coverage_type="national",
        resolution="30m",
        vintage="2022",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="None documented.",
        license="public_domain",
        source_url="https://landfire.gov",
        citation="Rollins (2009)",
        data_category="hazard",
        applicable_workflows=["hazard_assessment"],
    ),
    _ds(
        source_id="census_acs",
        name="Census American Community Survey (ACS) 5-Year",
        provider="U.S. Census Bureau",
        description=("Demographics at tract and block group level. Population, "
                     "households, income, age, commute patterns."),
        access_method="rest_api",
        access_config={"endpoint": "https://api.census.gov/data/2022/acs/acs5",
                       "auth": "api_key", "key_env_var": "CENSUS_API_KEY"},
        coverage_type="national",
        resolution="census tract / block group",
        vintage="2022 (5-year estimates, 2018-2022)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="5-year rolling average lags reality by 1-3 years.",
        license="public_domain",
        source_url="https://www.census.gov/programs-surveys/acs",
        data_category="demographic",
        applicable_workflows=["trade_area"],
    ),
    _ds(
        source_id="census_lehd",
        name="Census LEHD/LODES Workplace Data",
        provider="U.S. Census Bureau",
        description=("Workplace area characteristics — daytime employment by census "
                     "block. Commute flows."),
        access_method="postgis_table",
        access_config={"table": "trade_area_lehd_dallas",
                       "note": "currently Dallas County only — needs expansion for national"},
        coverage_type="county",
        coverage_states=["TX"],
        coverage_notes=("Currently loaded for Dallas County only (13,208 blocks, 1.72M "
                        "jobs). National LODES data available for download."),
        resolution="census block",
        vintage="2021",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("CRITICAL GAP — only Dallas County loaded. National download "
                    "available but not loaded."),
        license="public_domain",
        data_category="demographic",
        applicable_workflows=["trade_area"],
    ),
    _ds(
        source_id="osm_pois",
        name="OpenStreetMap Points of Interest",
        provider="OpenStreetMap contributors",
        description=("Business and amenity locations with category classification. "
                     "Competitor and complementary POI data for trade area analysis."),
        access_method="postgis_table",
        access_config={"table": "trade_area_pois_dallas",
                       "note": ("currently Dallas County only — "
                                "Overpass on-demand for other locations")},
        coverage_type="county",
        coverage_states=["TX"],
        coverage_notes=("45,840 POIs loaded for Dallas County. Overpass API can query "
                        "other locations on-demand."),
        resolution="point",
        vintage="2026",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps=("Only Dallas County pre-loaded. Overpass on-demand for other "
                    "locations adds latency."),
        license="ODbL",
        data_category="demographic",
        applicable_workflows=["trade_area"],
    ),
    _ds(
        source_id="ors_isochrones",
        name="OpenRouteService Drive-Time Isochrones",
        provider="OpenRouteService (HeiGIT)",
        description=("Drive-time catchment area polygons. Used for trade area "
                     "delineation."),
        access_method="rest_api",
        access_config={"endpoint": "https://api.openrouteservice.org/v2/isochrones/driving-car",
                       "auth": "api_key", "key_env_var": "ORS_API_KEY"},
        coverage_type="national",
        coverage_notes=("Free tier limited to 500 requests/day. Each scored location uses "
                        "3 requests (5/10/15 min)."),
        resolution="polygon (drive-time based)",
        vintage="current (OSM road network)",
        reliability="verified",
        last_verified=_PHASE_A_TS,
        known_gaps="Rate limited. OSM road data completeness varies.",
        license="ODbL (data), free tier API",
        source_url="https://openrouteservice.org",
        data_category="infrastructure",
        applicable_workflows=["trade_area"],
    ),
]


UPSERT_SQL = """
INSERT INTO data_sources (
    source_id, name, provider, description, access_method, access_config,
    coverage_type, coverage_states, coverage_notes, resolution, vintage,
    update_frequency, reliability, last_verified, known_gaps, license,
    source_url, citation, data_category, applicable_workflows, updated_at
) VALUES (
    $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12, $13, $14, $15,
    $16, $17, $18, $19, $20, now()
)
ON CONFLICT (source_id) DO UPDATE SET
    name = EXCLUDED.name,
    provider = EXCLUDED.provider,
    description = EXCLUDED.description,
    access_method = EXCLUDED.access_method,
    access_config = EXCLUDED.access_config,
    coverage_type = EXCLUDED.coverage_type,
    coverage_states = EXCLUDED.coverage_states,
    coverage_notes = EXCLUDED.coverage_notes,
    resolution = EXCLUDED.resolution,
    vintage = EXCLUDED.vintage,
    update_frequency = EXCLUDED.update_frequency,
    reliability = EXCLUDED.reliability,
    last_verified = EXCLUDED.last_verified,
    known_gaps = EXCLUDED.known_gaps,
    license = EXCLUDED.license,
    source_url = EXCLUDED.source_url,
    citation = EXCLUDED.citation,
    data_category = EXCLUDED.data_category,
    applicable_workflows = EXCLUDED.applicable_workflows,
    updated_at = now()
"""


async def seed() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    conn = await asyncpg.connect(url, ssl="require")
    try:
        for row in SEED:
            await conn.execute(
                UPSERT_SQL,
                row["source_id"], row["name"], row["provider"], row["description"],
                row["access_method"], json.dumps(row["access_config"]),
                row["coverage_type"], row["coverage_states"], row["coverage_notes"],
                row["resolution"], row["vintage"], row["update_frequency"],
                row["reliability"], row["last_verified"], row["known_gaps"],
                row["license"], row["source_url"], row["citation"],
                row["data_category"], row["applicable_workflows"],
            )
        n = await conn.fetchval("SELECT COUNT(*) FROM data_sources")
        print(f"  upserted {len(SEED)} rows; data_sources now has {n} rows")
        cats = await conn.fetch(
            "SELECT data_category, COUNT(*) AS n FROM data_sources "
            "GROUP BY data_category ORDER BY 1"
        )
        for c in cats:
            print(f"    {c['data_category']:20s} {c['n']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
