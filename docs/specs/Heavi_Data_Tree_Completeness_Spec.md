# HEAVI DATA TREE COMPLETENESS AUDIT + GAP-FILL SPEC
# Ensuring Every Criterion Has a Proper Fallback Chain

## Problem

The wildfire module returned "$0/yr LOW risk" for Sonoma County because the wildfire criteria data trees have single nodes pointing to PostGIS-loaded rasters that only exist for limited geographies. When FSim and LANDFIRE aren't loaded, the selection engine correctly reports "no data" but the scoring pipeline treats that as zero rather than unknown.

The root cause isn't just the scoring pipeline — it's incomplete data trees. The architecture was designed so every criterion has a fallback chain. The wildfire trees were built with single nodes. This violates the architecture.

This spec audits EVERY data tree across all three workflows, identifies single-node trees where fallbacks exist, and adds the missing nodes.

## Audit Results

### SOLAR SITING (14 criteria)

| Criterion | Current Tree Depth | Status | Action Needed |
|---|---|---|---|
| solar_ghi | 2 (PVWatts, NSRDB) | ✅ OK | — |
| solar_slope | 1 (3DEP) | ✅ OK — 3DEP is national, always available | — |
| solar_aspect | 1 (3DEP) | ✅ OK — same | — |
| solar_transmission | 3 (HIFLD, OSM PostGIS, OSM Overpass) | ✅ OK | — |
| solar_road | 2 (TIGER, OSM Overpass) | ✅ OK | — |
| solar_land_cover | 1 (NLCD WMS) | ✅ OK — NLCD WMS is national, always available | — |
| solar_soil | 1 (SSURGO SDA) | ✅ OK — SDA is national, always available | — |
| solar_ej | 1 (EJScreen) | ⚠️ GENUINE GAP — EPA discontinued the tool, static 2024 data in PostGIS. No alternative source exists. | Document as permanent gap. Low-weight criterion (0.05). |
| excl_protected | 1 (PAD-US REST) | ✅ OK — national REST | — |
| excl_wetlands | 3 (NWI PostGIS, NWI REST, SSURGO proxy) | ✅ OK | — |
| excl_critical_habitat | 1 (USFWS REST) | ✅ OK — national REST | — |
| excl_flood | 1 (FEMA NFHL REST) | ✅ OK — national REST | — |
| excl_steep | 1 (3DEP) | ✅ OK | — |
| excl_urban | 1 (NLCD WMS) | ✅ OK | — |

**Solar verdict:** Trees are complete. Single-node trees exist only for national sources that are always available. solar_ej is a genuine gap (no alternative source) but low-weight.

---

### HAZARD ASSESSMENT — WILDFIRE (5 criteria)

| Criterion | Current Tree Depth | Status | Action Needed |
|---|---|---|---|
| wf_likelihood | 1 (FSim PostGIS) | ❌ INCOMPLETE — FSim only loaded for limited geographies | Add NIFC historical fire frequency as proxy |
| wf_fuel_proximity | 1 (LANDFIRE PostGIS) | ❌ INCOMPLETE — LANDFIRE only loaded for limited geographies | Add LANDFIRE WCS as national fallback |
| wf_canopy | 1 (LANDFIRE PostGIS) | ❌ INCOMPLETE — same | Add LANDFIRE WCS as national fallback |
| wf_slope | 1 (3DEP) | ✅ OK — national | — |
| wf_structure | 1 (NSI REST) | ✅ OK — national | — |

**Fix: wf_likelihood data tree**

```json
[
    {
        "source_id": "usfs_fsim",
        "relationship": "alternative",
        "quality": "authoritative",
        "confidence_value": 1.0,
        "provides": "Simulated annual burn probability at 270m from tens of thousands of fire season simulations",
        "provenance": "Finney et al. (2011). The gold standard for probabilistic wildfire hazard assessment."
    },
    {
        "source_id": "nifc_fire_perimeters",
        "relationship": "alternative",
        "quality": "proxy",
        "confidence_value": 0.5,
        "provides": "Historical fire frequency: number of times a location has burned in recorded history (perimeters through 2024). Computed as fire_count / years_of_record.",
        "provenance": "NIFC Interagency Fire Perimeter History. National coverage via ArcGIS REST. A proxy for burn probability: historical frequency underestimates true probability (fires that didn't reach this point aren't counted) but provides a real signal. Locations that have burned multiple times have demonstrably higher future burn probability."
    }
]
```

**New data source: nifc_fire_perimeters**
```
source_id: nifc_fire_perimeters
name: NIFC Interagency Fire Perimeter History
provider: National Interagency Fire Center
description: Historical wildfire perimeters for all known US wildfires. Spatial query returns all fire perimeters that intersect a location, with fire name, year, and acreage. Enables computation of historical burn frequency.
access_method: rest_api
access_config: {
    "endpoint": "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query",
    "params": {
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "attr_FireName,attr_IncidentName,irwin_FireDiscoveryDateTime,poly_GISAcres",
        "f": "json"
    }
}
coverage_type: national
resolution: polygon (fire perimeter)
vintage: through 2024, updated annually
reliability: verified (need to verify endpoint)
known_gaps: Only includes fires with mapped perimeters. Small fires and prescribed burns may be missing. Historical record is less complete before ~1980.
license: public_domain
data_category: hazard
applicable_workflows: ['hazard_assessment']
citation: NIFC Wildland Fire Interagency Geospatial Services (WFIGS)
```

**Fix: wf_fuel_proximity data tree**

```json
[
    {
        "source_id": "landfire_fuels_canopy",
        "relationship": "alternative",
        "quality": "authoritative",
        "confidence_value": 1.0,
        "provides": "Pre-loaded LANDFIRE raster: FBFM40 fuel model classification. Distance to nearest burnable fuel computed from fuel model at 30m.",
        "provenance": "Rollins (2009). Pre-loaded for faster query; same data as WCS."
    },
    {
        "source_id": "landfire_wcs_fuel",
        "relationship": "alternative",
        "quality": "authoritative",
        "confidence_value": 0.9,
        "provides": "Same LANDFIRE fuel model data queried on-demand via WCS at any CONUS coordinate. Returns FBFM40 value at the point.",
        "provenance": "Rollins (2009). Same dataset, different access path. On-demand WCS has slight latency but same data quality. Confidence 0.9 (not 1.0) because single-point query vs. pre-loaded multi-point analysis."
    }
]
```

**Fix: wf_canopy data tree**

```json
[
    {
        "source_id": "landfire_fuels_canopy",
        "relationship": "alternative",
        "quality": "authoritative",
        "confidence_value": 1.0,
        "provides": "Pre-loaded LANDFIRE raster: canopy cover percentage at 30m. Multi-buffer analysis (30/100/300m) pre-computed.",
        "provenance": "Rollins (2009). Pre-loaded for multi-buffer defensible space analysis."
    },
    {
        "source_id": "landfire_wcs_canopy",
        "relationship": "alternative",
        "quality": "authoritative",
        "confidence_value": 0.9,
        "provides": "Same LANDFIRE canopy cover data queried on-demand via WCS. Returns canopy cover percentage at a point. Single-point query — does not support the multi-buffer defensible space computation (30/100/300m).",
        "provenance": "Rollins (2009). Same data, on-demand access. Limited to point query — multi-buffer requires multiple WCS calls or local raster."
    },
    {
        "source_id": "nlcd_land_cover",
        "relationship": "alternative",
        "quality": "proxy",
        "confidence_value": 0.4,
        "provides": "NLCD land cover class as proxy for canopy: forest classes (41-43) indicate high canopy, shrub (52) moderate, grassland (71) low, developed/barren minimal. Coarser than LANDFIRE (30m, categorical vs continuous).",
        "provenance": "Yang et al. (2018). NLCD is a land cover classification, not a canopy measurement. Provides directional signal (forested vs not) but not the continuous canopy cover percentage that LANDFIRE provides."
    }
]
```

**New data sources for LANDFIRE WCS:**

```
source_id: landfire_wcs_fuel
name: LANDFIRE FBFM40 Fuel Model (WCS On-Demand)
provider: USGS/USFS LANDFIRE
description: On-demand WCS query for FBFM40 (Fire Behavior Fuel Model 40) at any CONUS coordinate. Returns the Scott/Burgan fuel model classification.
access_method: wcs
access_config: {
    "endpoint": "https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/conus_sf/wcs",
    "coverage": "LC23_F40_240",
    "note": "WCS GetCoverage with point geometry. Returns raster value at coordinate."
}
coverage_type: national
resolution: 30m
vintage: 2023 (LANDFIRE 2023)
reliability: unverified (needs endpoint testing)
known_gaps: WCS endpoint may have latency. Needs coordinate reprojection (LANDFIRE uses Albers Equal Area).
license: public_domain
data_category: hazard
applicable_workflows: ['hazard_assessment']
```

```
source_id: landfire_wcs_canopy
name: LANDFIRE Canopy Cover (WCS On-Demand)
provider: USGS/USFS LANDFIRE
description: On-demand WCS query for canopy cover percentage at any CONUS coordinate.
access_method: wcs
access_config: {
    "endpoint": "https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/conus_sf/wcs",
    "coverage": "LC23_CC_240",
    "note": "WCS GetCoverage returns continuous 0-100% canopy cover."
}
coverage_type: national
resolution: 30m
vintage: 2023 (LANDFIRE 2023)
reliability: unverified (needs endpoint testing)
known_gaps: Same as fuel — latency, reprojection.
license: public_domain
data_category: hazard
applicable_workflows: ['hazard_assessment']
```

---

### HAZARD ASSESSMENT — FLOOD (5 criteria)

| Criterion | Current Tree Depth | Status | Action Needed |
|---|---|---|---|
| fl_zone | 1 (NFHL REST) | ✅ OK — national | — |
| fl_depth | 4 (NFHL + 3DEP + NSI components, inundation supplementary) | ✅ OK | — |
| fl_historical | 2 (OpenFEMA, USGS peak flow) | ✅ OK | — |
| fl_hydrology | 3 (GRRR, NHDPlus, peak flow) | ✅ OK | — |
| fl_building | 2 (NSI + HAZUS DDFs components) | ✅ OK | — |

**Flood verdict:** Trees are complete. All sources are national.

---

### TRADE AREA (7 criteria)

| Criterion | Current Tree Depth | Status | Action Needed |
|---|---|---|---|
| ta_population | 1 (Census ACS) | ✅ OK — national API | — |
| ta_competitive_gap | 2 (OSM PostGIS, Overpass) | ✅ OK | — |
| ta_income | 1 (Census ACS) | ✅ OK | — |
| ta_daytime | 2 (LEHD, ACS commuter) | ✅ OK | — |
| ta_accessibility | 1 (ORS isochrones) | ⚠️ RISK — ORS free tier is 500 req/day. If exhausted, no fallback. | Add Euclidean buffer as low-confidence proxy |
| ta_complementary | 2 (OSM PostGIS, Overpass) | ✅ OK | — |
| ta_flood | 1 (FEMA NFHL) | ✅ OK | — |

**Fix: ta_accessibility data tree**

```json
[
    {
        "source_id": "ors_isochrones",
        "relationship": "alternative",
        "quality": "authoritative",
        "confidence_value": 1.0,
        "provides": "Drive-time catchment polygons (5/10/15 min) from OSM road network. The standard for trade area delineation.",
        "provenance": "Huff (1963). ORS uses Dijkstra's algorithm on the OSM road network."
    },
    {
        "source_id": "euclidean_buffer",
        "relationship": "alternative",
        "quality": "proxy",
        "confidence_value": 0.3,
        "provides": "Simple circular buffer as proxy for drive-time catchment. Uses approximate radii: 5 min ≈ 3 km, 10 min ≈ 7 km, 15 min ≈ 12 km. Does not account for road network, traffic, or terrain.",
        "provenance": "Euclidean distance is the simplest proxy for accessibility. Significantly overestimates catchment in dense urban areas (road network is slower than straight-line) and underestimates in areas with limited road access. Confidence 0.3 reflects the low quality of this proxy."
    }
]
```

The euclidean_buffer is not a real data source — it's a computed fallback that requires no external API. It's just `ST_Buffer(point, radius_m)` in PostGIS. Implement as a built-in fallback in the scoring logic rather than a data_sources entry.

---

## Summary of Changes Needed

### New Data Sources (add to data_sources table)

1. **nifc_fire_perimeters** — NIFC historical fire perimeters via ArcGIS REST. National. Proxy for burn probability.
2. **landfire_wcs_fuel** — LANDFIRE FBFM40 fuel model via WCS. National on-demand.
3. **landfire_wcs_canopy** — LANDFIRE canopy cover via WCS. National on-demand.

### Updated Data Trees (update methodology_criteria table)

1. **wf_likelihood** — add nifc_fire_perimeters as proxy node (confidence 0.5)
2. **wf_fuel_proximity** — add landfire_wcs_fuel as fallback node (confidence 0.9)
3. **wf_canopy** — add landfire_wcs_canopy as fallback (confidence 0.9), add nlcd_land_cover as proxy (confidence 0.4)
4. **ta_accessibility** — add euclidean_buffer as proxy node (confidence 0.3)

### New Source Implementations

For each new data source, implement the actual query logic:

**nifc_fire_perimeters:**
```python
async def query_nifc_perimeters(lat, lng, buffer_m=1000):
    """Query NIFC for historical fire perimeters that intersect a buffer around the point.
    Returns: list of fires with name, year, acreage.
    Computed metric: fire_frequency = count / years_of_record (assume 45 years, 1980-2024)
    """
    endpoint = "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query"
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "attr_FireName,irwin_FireDiscoveryDateTime,poly_GISAcres",
        "returnGeometry": "false",
        "f": "json"
    }
    # Returns features → count fires → fire_frequency = count / 45
```

**landfire_wcs_fuel and landfire_wcs_canopy:**
```python
async def query_landfire_wcs(lat, lng, coverage="LC23_F40_240"):
    """Query LANDFIRE WCS for a raster value at a point.
    coverage options:
      LC23_F40_240 = FBFM40 fuel model
      LC23_CC_240 = canopy cover percentage
    Note: LANDFIRE uses Albers Equal Area projection. Need to either:
      - Reproject the query point to Albers
      - Or use the WCS reprojection capability
    """
    endpoint = "https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/conus_sf/wcs"
    # WCS GetCoverage request with point subset
```

**euclidean_buffer (no external source):**
```python
def compute_euclidean_buffer(lat, lng, minutes=[5, 10, 15]):
    """Approximate drive-time catchment with circular buffers.
    Assumes average speed 40 km/h in suburban areas.
    5 min ≈ 3.3 km, 10 min ≈ 6.7 km, 15 min ≈ 10 km
    Returns GeoJSON polygons.
    """
    # ST_Buffer in PostGIS or shapely
```

### Endpoint Verification

Before implementing, verify the new endpoints work:
1. NIFC fire perimeters: query for Sonoma County (38.44, -122.71) — should return multiple historical fires
2. LANDFIRE WCS fuel: query for any CONUS point — should return an FBFM40 value
3. LANDFIRE WCS canopy: query for a forested location — should return canopy cover percentage

If any endpoint doesn't work or has changed, document it honestly and set reliability='degraded'.

### Scoring Pipeline Updates

With the data trees completed, the scoring pipeline changes:

**Wildfire scoring with NIFC proxy:**
When FSim is unavailable and NIFC fire perimeters are used:
- fire_frequency = count_of_perimeters / 45 (years 1980-2024)
- This is a CRUDE proxy for annual burn probability — FSim simulates thousands of fire seasons; NIFC just counts historical occurrences
- Use fire_frequency directly as the wf_likelihood score (scaled 0-1)
- Confidence = 0.5 (proxy, not authoritative simulation)

**Wildfire scoring with LANDFIRE WCS:**
When LANDFIRE PostGIS is unavailable and WCS is used:
- Query WCS for fuel model value at the point
- Compute distance_to_fuel = 0 if the point itself has a burnable fuel model, otherwise query surrounding points
- Note: single-point WCS queries can't do the multi-buffer analysis (30/100/300m) that the PostGIS raster supports. The WCS fallback provides point-level data, not buffer analysis.
- Confidence = 0.9 (same data, less spatial analysis capability)

**Trade area scoring with Euclidean buffer:**
When ORS is unavailable:
- Use circular buffers instead of drive-time isochrones
- Census demographics still intersected with the buffer polygons
- POI competitive analysis still runs within the buffer
- Confidence = 0.3 (Euclidean distance is a poor proxy for drive-time accessibility)

### Insufficient Data Handling (from previous spec)

After completing the data trees, the CANNOT ASSESS logic still applies but should fire less often. It fires ONLY when ALL nodes in a tree are unavailable — not just the primary source. With the completed trees:

- wf_likelihood: FSim unavailable → try NIFC perimeters. If NIFC ALSO unavailable → CANNOT ASSESS
- wf_fuel_proximity: LANDFIRE PostGIS unavailable → try LANDFIRE WCS. If WCS ALSO unavailable → CANNOT ASSESS
- wf_canopy: LANDFIRE PostGIS → LANDFIRE WCS → NLCD proxy. All three down → CANNOT ASSESS

CANNOT ASSESS should be RARE with completed trees, not the default for most of the country.

---

## Acceptance Criteria

### New Sources
1. nifc_fire_perimeters source entry added to data_sources table
2. landfire_wcs_fuel source entry added to data_sources table
3. landfire_wcs_canopy source entry added to data_sources table
4. Endpoint verification: NIFC perimeters returns results for Sonoma County (38.44, -122.71)
5. Endpoint verification: LANDFIRE WCS fuel returns a value for Kern County (35.35, -119.05)
6. Endpoint verification: LANDFIRE WCS canopy returns a value for a forested location (e.g., 38.44, -122.71)

### Updated Trees
7. wf_likelihood data tree has 2 nodes (FSim + NIFC)
8. wf_fuel_proximity data tree has 2 nodes (LANDFIRE PostGIS + LANDFIRE WCS)
9. wf_canopy data tree has 3 nodes (LANDFIRE PostGIS + LANDFIRE WCS + NLCD proxy)
10. ta_accessibility data tree has 2 nodes (ORS + Euclidean buffer)

### Selection Engine Behavior
11. select_data("hazard_assessment", 38.44, -122.71) — wf_likelihood selects nifc_fire_perimeters (proxy) instead of reporting NONE
12. select_data("hazard_assessment", 38.44, -122.71) — wf_fuel_proximity selects landfire_wcs_fuel (fallback) instead of reporting NONE
13. select_data("hazard_assessment", 38.44, -122.71) — wf_canopy selects landfire_wcs_canopy (fallback) instead of reporting NONE

### Scoring Results
14. Sonoma County wildfire: returns a NON-ZERO annual risk estimate using NIFC frequency + LANDFIRE WCS data — NOT "$0/yr LOW"
15. Sonoma County wildfire: confidence is MODERATE or LOW (not HIGH — using proxy/fallback data) — but NOT "CANNOT ASSESS"
16. Sonoma County wildfire: risk_tier reflects actual risk level, not "LOW" from missing data

### CANNOT ASSESS
17. CANNOT ASSESS only fires when ALL nodes in a data tree are exhausted — not when the primary source is missing
18. Existing assessments with full primary data (Kern County solar, Dallas trade area) continue to work with no regression

### Cross-Module
19. No single-node data trees remain for criteria where fallback sources exist (verified by querying methodology_criteria)
