-- Data-tree completeness gap-fill (Heavi Data Tree Completeness Spec).
--
-- The wildfire criteria had single-node data trees pointing at PostGIS rasters
-- loaded only for limited geographies, so outside those geographies the
-- selection engine reported "no data" and scoring collapsed to $0. This adds the
-- missing national fallback nodes so every criterion has a real fallback chain.
--
-- Endpoint verification (2026-06-08) corrected several spec details, applied here:
--   * NIFC: field names are INCIDENT / FIRE_YEAR / GIS_ACRES (not the spec's
--     attr_* names); a 5 km local fire-shed buffer is used (the exact Sonoma
--     point is unburned at 0 m but TUBBS/C.HANLY/etc. lie within 5 km).
--   * LANDFIRE: the spec's coverage ids (LC23_F40_240/LC23_CC_240) and the
--     conus_sf canopy endpoint were outdated. Working full-CONUS coverages are
--     landfire_wcs:LF2023_FBFM40_CONUS (fuel) and LF2023_CC_CONUS (canopy),
--     queried via the geoserver WMS GetFeatureInfo (a lighter point-extraction
--     than full WCS GetCoverage). reliability=verified.

-- ─── New data sources ──────────────────────────────────────────────────────

INSERT INTO data_sources
    (source_id, name, provider, description, access_method, access_config,
     coverage_type, resolution, vintage, reliability, last_verified, known_gaps,
     license, source_url, citation, data_category, applicable_workflows)
VALUES
(
    'nifc_fire_perimeters',
    'NIFC Interagency Fire Perimeter History',
    'National Interagency Fire Center',
    $d$Historical wildfire perimeters for all known US wildfires. A spatial query returns fire perimeters near a location (name, year, acreage), enabling computation of historical burn frequency as a proxy for burn probability.$d$,
    'rest_api',
    $json${"endpoint": "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query", "buffer_m": 5000, "years_of_record": 45, "out_fields": "INCIDENT,FIRE_YEAR,FIRE_YEAR_INT,GIS_ACRES", "note": "5 km local fire-shed buffer; fire_frequency = distinct_fire_count / 45 (1980-2024)."}$json$::jsonb,
    'national', 'polygon (fire perimeter)', 'through 2024, updated annually',
    'verified', '2026-06-08 00:00:00+00',
    $d$Only fires with mapped perimeters; small fires and prescribed burns may be missing; pre-1980 record less complete.$d$,
    'public_domain',
    'https://data-nifc.opendata.arcgis.com/',
    'NIFC Wildland Fire Interagency Geospatial Services (WFIGS)',
    'hazard', ARRAY['hazard_assessment']
),
(
    'landfire_wcs_fuel',
    'LANDFIRE FBFM40 Fuel Model (on-demand)',
    'USGS/USFS LANDFIRE',
    $d$On-demand query for FBFM40 (Scott/Burgan Fire Behavior Fuel Model 40) at any CONUS coordinate. Returns the fuel-model code at the point.$d$,
    'wcs',
    $json${"endpoint": "https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/wms", "layer": "landfire_wcs:LF2023_FBFM40_CONUS", "access": "wms_getfeatureinfo", "value_field": "GRAY_INDEX", "note": "Point value via geoserver WMS GetFeatureInfo (EPSG:4326 bbox; lighter than WCS GetCoverage which needs Albers reprojection)."}$json$::jsonb,
    'national', '30m', 'LANDFIRE 2023',
    'verified', '2026-06-08 00:00:00+00',
    $d$Single-point query — does not support the multi-buffer (30/100/300m) analysis the pre-loaded raster supports. WMS may have latency.$d$,
    'public_domain',
    'https://landfire.gov/',
    'Rollins (2009)',
    'hazard', ARRAY['hazard_assessment']
),
(
    'landfire_wcs_canopy',
    'LANDFIRE Forest Canopy Cover (on-demand)',
    'USGS/USFS LANDFIRE',
    $d$On-demand query for forest canopy cover percentage (0-100) at any CONUS coordinate.$d$,
    'wcs',
    $json${"endpoint": "https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/wms", "layer": "landfire_wcs:LF2023_CC_CONUS", "access": "wms_getfeatureinfo", "value_field": "GRAY_INDEX", "note": "Canopy cover % via geoserver WMS GetFeatureInfo. The spec's conus_sf endpoint serves only fuel; canopy lives in the landfire_wcs workspace."}$json$::jsonb,
    'national', '30m', 'LANDFIRE 2023',
    'verified', '2026-06-08 00:00:00+00',
    $d$Single-point query — cannot do the multi-buffer defensible-space computation. WMS may have latency.$d$,
    'public_domain',
    'https://landfire.gov/',
    'Rollins (2009)',
    'hazard', ARRAY['hazard_assessment']
)
ON CONFLICT (source_id) DO UPDATE SET
    name = EXCLUDED.name, provider = EXCLUDED.provider,
    description = EXCLUDED.description, access_method = EXCLUDED.access_method,
    access_config = EXCLUDED.access_config, coverage_type = EXCLUDED.coverage_type,
    resolution = EXCLUDED.resolution, vintage = EXCLUDED.vintage,
    reliability = EXCLUDED.reliability, last_verified = EXCLUDED.last_verified,
    known_gaps = EXCLUDED.known_gaps, license = EXCLUDED.license,
    source_url = EXCLUDED.source_url, citation = EXCLUDED.citation,
    data_category = EXCLUDED.data_category,
    applicable_workflows = EXCLUDED.applicable_workflows,
    updated_at = NOW();

-- ─── Updated data trees ────────────────────────────────────────────────────

UPDATE methodology_criteria SET data_tree = $json$[
    {"source_id": "usfs_fsim", "relationship": "alternative", "quality": "authoritative", "confidence_value": 1.0, "provides": "Simulated annual burn probability at 270m from tens of thousands of fire-season simulations.", "provenance": "Finney et al. (2011). The gold standard for probabilistic wildfire hazard assessment."},
    {"source_id": "nifc_fire_perimeters", "relationship": "alternative", "quality": "proxy", "confidence_value": 0.5, "provides": "Historical fire frequency near the location (perimeters through 2024). Computed as fire_count / years_of_record.", "provenance": "NIFC Interagency Fire Perimeter History. National coverage via ArcGIS REST. A proxy for burn probability: historical frequency underestimates true probability but provides a real signal. Locations that have burned multiple times have demonstrably higher future burn probability."}
]$json$::jsonb WHERE criterion_id = 'wf_likelihood';

UPDATE methodology_criteria SET data_tree = $json$[
    {"source_id": "landfire_fuels_canopy", "relationship": "alternative", "quality": "authoritative", "confidence_value": 1.0, "provides": "Pre-loaded LANDFIRE raster: FBFM40 fuel model classification. Distance to nearest burnable fuel computed at 30m.", "provenance": "Rollins (2009). Pre-loaded for faster query; same data as WCS."},
    {"source_id": "landfire_wcs_fuel", "relationship": "alternative", "quality": "authoritative", "confidence_value": 0.9, "provides": "Same LANDFIRE fuel-model data queried on-demand at any CONUS coordinate. Returns the FBFM40 value at the point.", "provenance": "Rollins (2009). Same dataset, on-demand access path. Confidence 0.9 (not 1.0) because single-point query vs. pre-loaded multi-point analysis."}
]$json$::jsonb WHERE criterion_id = 'wf_fuel_proximity';

UPDATE methodology_criteria SET data_tree = $json$[
    {"source_id": "landfire_fuels_canopy", "relationship": "alternative", "quality": "authoritative", "confidence_value": 1.0, "provides": "Pre-loaded LANDFIRE raster: canopy cover percentage at 30m. Multi-buffer analysis (30/100/300m) pre-computed.", "provenance": "Rollins (2009). Pre-loaded for multi-buffer defensible-space analysis."},
    {"source_id": "landfire_wcs_canopy", "relationship": "alternative", "quality": "authoritative", "confidence_value": 0.9, "provides": "Same LANDFIRE canopy-cover data queried on-demand. Returns canopy cover percentage at a point. Single-point query — does not support the multi-buffer defensible-space computation.", "provenance": "Rollins (2009). Same data, on-demand access. Limited to point query."},
    {"source_id": "nlcd_land_cover", "relationship": "alternative", "quality": "proxy", "confidence_value": 0.4, "provides": "NLCD land-cover class as proxy for canopy: forest (41-43) high, shrub (52) moderate, grassland (71) low, developed/barren minimal.", "provenance": "Yang et al. (2018). NLCD is a land-cover classification, not a canopy measurement. Provides a directional signal (forested vs not) but not continuous canopy cover percentage."}
]$json$::jsonb WHERE criterion_id = 'wf_canopy';

UPDATE methodology_criteria SET data_tree = $json$[
    {"source_id": "ors_isochrones", "relationship": "alternative", "quality": "authoritative", "confidence_value": 1.0, "provides": "Drive-time catchment polygons (5/10/15 min) from the OSM road network. The standard for trade-area delineation.", "provenance": "Huff (1963). ORS uses Dijkstra shortest paths on the OSM road network."},
    {"source_id": "euclidean_buffer", "relationship": "alternative", "quality": "proxy", "confidence_value": 0.3, "provides": "Circular buffer as a proxy for drive-time catchment (5 min ~3 km, 10 min ~7 km, 15 min ~12 km). Ignores road network, traffic, terrain.", "provenance": "Euclidean distance is the simplest accessibility proxy. Overestimates catchment in dense urban areas and underestimates where road access is limited. Confidence 0.3 reflects the low quality. Computed in-process (no external API)."}
]$json$::jsonb WHERE criterion_id = 'ta_accessibility';
