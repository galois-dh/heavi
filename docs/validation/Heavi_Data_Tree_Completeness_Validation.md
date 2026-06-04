# HEAVI DATA TREE COMPLETENESS — VALIDATION SUMMARY

**Date:** 2026-06-08
**Spec:** [`Heavi_Data_Tree_Completeness_Spec.md`](../specs/Heavi_Data_Tree_Completeness_Spec.md)

Completes the single-node wildfire (and ta_accessibility) data trees with real
national fallback nodes, so the selection engine picks a fallback instead of
reporting "no data" and scoring no longer collapses to $0.

## Endpoint verification (Step 1) — honest corrections

The spec's source details were partly stale; verified and corrected:

| Source | Spec | Verified reality (2026-06-08) |
|---|---|---|
| NIFC perimeters | `attr_FireName`, `irwin_*`, point-intersect | Fields are `INCIDENT` / `FIRE_YEAR` / `GIS_ACRES`; the exact Sonoma point is unburned (0 at 0 m) so a **5 km local fire-shed buffer** is used → TUBBS (2017), C. HANLY (1964), TAYLOR (2020). **Works.** |
| LANDFIRE fuel | `conus_sf/wcs`, coverage `LC23_F40_240` | Coverage renamed; working full-CONUS layer is `landfire_wcs:LF2023_FBFM40_CONUS`. Kern → FBFM40 **91**. Queried via geoserver **WMS GetFeatureInfo** (lighter than WCS GetCoverage; no Albers reprojection / GeoTIFF parsing). **Works.** |
| LANDFIRE canopy | `conus_sf/wcs`, coverage `LC23_CC_240` | `conus_sf` serves **only fuel**; canopy is `landfire_wcs:LF2023_CC_CONUS`. Forested Sonoma hills (38.49,-122.61) → **45%** (the spec's example point 38.44,-122.71 is agricultural → 0%). **Works.** |

reliability set to `verified` for all three (they work with the corrections).

## Acceptance criteria — 19/19 PASS

| # | Criterion | Result |
|---|---|---|
| 1-3 | nifc_fire_perimeters / landfire_wcs_fuel / landfire_wcs_canopy added to data_sources | PASS |
| 4 | NIFC returns results for Sonoma | PASS (TUBBS/C.HANLY/TAYLOR within 5 km) |
| 5 | LANDFIRE WCS fuel returns a value for Kern | PASS (FBFM40 = 91) |
| 6 | LANDFIRE WCS canopy returns a value for a forested location | PASS (Sonoma hills = 45%) |
| 7 | wf_likelihood has 2 nodes | PASS (FSim + NIFC) |
| 8 | wf_fuel_proximity has 2 nodes | PASS (LANDFIRE PostGIS + WCS) |
| 9 | wf_canopy has 3 nodes | PASS (LANDFIRE PostGIS + WCS + NLCD proxy) |
| 10 | ta_accessibility has 2 nodes | PASS (ORS + euclidean_buffer) |
| 11 | select_data Sonoma → wf_likelihood selects NIFC (not NONE) | PASS |
| 12 | … wf_fuel_proximity selects landfire_wcs_fuel | PASS |
| 13 | … wf_canopy selects landfire_wcs_canopy | PASS |
| 14 | Sonoma wildfire returns NON-ZERO risk (not $0) | PASS — **$518,179/yr** (was $0) |
| 15 | Sonoma wildfire confidence MODERATE/LOW, not CANNOT ASSESS | PASS (wildfire confidence 0.5 → LOW; available) |
| 16 | Sonoma risk_tier reflects actual risk | PASS (HIGH) |
| 17 | CANNOT ASSESS only when ALL nodes exhausted | PASS (Sonoma: FSim missing but NIFC used → not CANNOT ASSESS) |
| 18 | No regression for Kern solar / Dallas trade area | PASS (Kern High/HIGH; Dallas Strong, LEHD HIGH) |
| 19 | No single-node trees where fallback sources exist | PASS — see below |

### AC19 detail

Remaining single-node trees all point to a national-always-available source or a
documented gap with **no alternative source in the catalog**, so there is no
fallback to add:

- national-always-available: `solar_slope`/`solar_aspect`/`excl_steep`/`wf_slope` (3DEP),
  `solar_land_cover`/`excl_urban` (NLCD), `solar_soil` (SSURGO), `excl_protected` (PAD-US),
  `excl_critical_habitat` (USFWS), `fl_zone`/`excl_flood`/`ta_flood` (NFHL),
  `ta_population`/`ta_income` (Census ACS), `wf_structure` (NSI).
- documented gaps with no alternative: `solar_ej` (EPA EJScreen discontinued),
  `solar_road` (only `osm_roads_overpass` exists — no TIGER source in the catalog;
  the spec's audit "2 nodes" was inaccurate).

## Implementation notes

- **Selection engine:** added a `wcs` availability handler (verified → available,
  like WMS) and a built-in `euclidean_buffer` availability (always available,
  not a `data_sources` row, per spec).
- **Scoring:** wildfire is now selection-driven — FSim pre-loaded path when
  available, else NIFC fire-frequency (burn-probability proxy) × LANDFIRE WCS
  fuel/canopy damage factor × NSI replacement value, with a national exposure
  floor so a real fire-shed isn't reported as $0 for lack of an NSI match.
  Houston correctly stays $0 (no historical fires — accurate, not the bug).
- **Trade area:** `euclidean_buffer` wired as a built-in ORS-failure fallback
  (circular buffers, ta_accessibility confidence 0.3); only triggers on ORS
  RuntimeError, so the ORS happy path (and AC18b) is untouched.
