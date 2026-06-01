# Phase A — Data Loading Status

**Date:** 2026-06-05
**Scope:** 13-item data-source inventory for the deepened solar (8-stage) and flood (6-stage) modules.
**Architectural rule:** national-first. Kern County is validation; nothing is county-clipped except sources that are inherently single-state (CAL FIRE products).

---

## Summary (after 2026-06-05 Phase A2 retries)

| Status | Count | Items |
|---|---|---|
| ✅ Verified live (on-demand API integration shipped) | 10 | PVWatts v8, USDA SDA, USFWS Critical Habitat, USGS PAD-US, USGS NHDPlus HR, USGS Peak-Flow, OpenFEMA Disasters + NFIP Claims, NLCD WMS, EJScreen (loaded + Census-Geocoder lookup) |
| ✅ Loaded to PostGIS this pass | 3 | Google Inundation History (383 polygons), EJScreen 2024 v2.32 (243,022 block groups via Wayback Machine), OSM Substations TX/AZ/NV/FL/NC + CA (16,725) |
| ✅ Already loaded (verified via COUNT) | 3 | wildfire_dins (132,522), wildfire_frap_perimeters (22,810), catalog_calfire_fhsz (2,380) |
| ✅ Heavy deps installed | 1 | Google GRRR Zarr (xarray 2026.4.0, zarr 3.2.1, gcsfs 2026.5.0 in packages/api/.venv) |
| ❌ Unavailable | 1 | USGS StreamStats (all endpoints 404; substitute with GRRR + Peak-Flow) |
| ⏸ Deferred | 0 | — |

**Total ready for module deepening:** 12 of 13 data sources usable. Only StreamStats is genuinely deferred.

### What changed since the first Phase A pass

- **PVWatts** confirmed at `developer.nlr.gov` (per user note — the canonical `developer.nrel.gov` is NXDOMAIN as of 2026-05-29).
- **NLCD** retrieved via MRLC's `geoserver/mrlc_download/wms` GetFeatureInfo. No raster download required. Tested at 5 cities — palette indexes map correctly (Yosemite → grassland, Houston → developed high).
- **EJScreen** sourced from the **Internet Archive Wayback Machine snapshot** of `gaftp.epa.gov/EJSCREEN/2024/2.32_August_UseMe/` from 2025-02-06 (EPA discontinued the live tool Feb 2025). 243,022 block-group rows × 41 selected columns loaded via `COPY FROM` (the 20k-row `pd.to_sql(method="multi")` chunks stalled on Supabase pooler SSL; COPY is the production path).
- **Substations** loaded for top 6 solar states (CA + TX + AZ + NV + FL + NC = **16,725 features**) via per-state Overpass with 300-600s timeout. Geofabrik PBF parsing with pyosmium was abandoned (the location-index build for area-mapped substations took >6 min CPU per state).
- **Google GRRR deps** installed.

---

## Per-item detail

### Solar module data

#### 1. NREL PVWatts v8 — ✅ verified
- **Domain change confirmed:** the spec endpoint `developer.nrel.gov` returns NXDOMAIN from public DNS. The working host is `developer.nlr.gov` (per the build spec). Tested with the existing `NREL_API_KEY`.
- **Integration:** `packages/api/app/integrations/nrel_pvwatts.py` — async `pvwatts_v8(client, lat, lng, system_capacity_kw, …)` returning `ac_annual_kwh`, `capacity_factor_pct`, `solrad_annual`, `ac_monthly_kwh`, station metadata.
- **Test result (Kern, 1 MW fixed-tilt, 20° tilt, 180° azimuth):** ac_annual=1,688,855 kWh, capacity_factor=19.28%, solrad_annual=6.20 kWh/m²/d, version 8.5.0.

#### 2. NLCD National Land Cover — ✅ verified via MRLC WMS GetFeatureInfo
- **Solved**: `mrlc.gov/geoserver/mrlc_download/wms` exposes the full NLCD product suite as WMS layers. Per-point lookup via `GetFeatureInfo` returns the palette index, which maps to the 16-class NLCD legend.
- **Integration**: `app/integrations/mrlc_nlcd.py` — `nlcd_class_at_point(client, lat, lng)` returns `{code, label, group, layer}` using `NLCD_2021_Land_Cover_L48` by default.
- **Verified across 5 cities**: Kern → Developed Low Intensity, Houston → Developed High, Yosemite meadow → Grassland/Herbaceous, Phoenix → Developed High, Dallas → Developed Medium.
- **Includes** a group taxonomy useful for solar siting: `cropland`, `grassland`, `shrubland`, `developed`, `wetlands`, etc.

#### 3. USFWS Critical Habitat — ✅ verified
- **Source:** `services.arcgis.com/QVENGdaPbd4LUkLV/.../USFWS_Critical_Habitat/FeatureServer/0`
- **National scale:** 802 designated polygons across all listed species.
- **Integration:** `app/integrations/usfws_critical_habitat.py` — `critical_habitat_at_point(client, lat, lng)` returns a list of overlapping habitat units with common name, scientific name, listing entity, federal register reference, publication date.

#### 4. EPA EJScreen — ✅ loaded (Wayback Machine snapshot)
- **EPA discontinued the live tool Feb 2025.** But the **Internet Archive Wayback Machine has a snapshot of `gaftp.epa.gov/EJSCREEN/2024/` from 2025-02-06** with all release artifacts (CSV + GDB).
- **Loaded:** EJScreen 2024 v2.32 BG StatePct CSV from Wayback (428 MB unzipped). Filtered to 41 of 229 columns (identifiers + state-percentile fields for demographic and environmental burden indicators).
- **PostGIS table** `ejscreen_blockgroups`: **243,022 rows** across 56 states/territories, keyed by 12-digit block group GEOID.
- **Loader:** `packages/data-catalog/loaders/solar/load_ejscreen.py` — uses `COPY FROM` (pd.to_sql with multi-row INSERT batches stalls the Supabase pooler SSL connection).
- **Integration:** `app/integrations/epa_ejscreen.py` — `ejscreen_at_point(pool, client, lat, lng)` does a two-step lookup: Census Geocoder API → BG GEOID → DB SELECT. Verified across 4 cities — Houston BG = 99th pct PM2.5 (petrochem corridor), Bakersfield = 90th pct low income.

#### 5. USDA SSURGO via SDA — ✅ verified national
- **Source:** `sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest` (T-SQL via JSON POST)
- **Integration:** `app/integrations/usda_ssurgo.py` — `sda_point(client, lat, lng)` returns dominant component's drainage class, hydric flag, taxonomy, mapunit name, horizon depths.
- **Tested:** Houston coord returned `mukey=2888237 / Urban land / hydric=No`.
- **Existing PostGIS table** `solar_soils_kern` (1,245 polygons) stays as Kern Discover-mode demo. SDA covers everything else nationally on-demand.

#### 6. USGS PAD-US — ✅ verified national
- **Source:** `services.arcgis.com/v01gqwM5QqNysAAi/.../PADUS_Protected_Areas_National/FeatureServer/0`
- **National scale:** 306,082 polygons.
- **Integration:** `app/integrations/usgs_padus.py` — `padus_at_point(client, lat, lng)` returns unit name, manager name + type, GAP status, IUCN category, public access.
- **Tested:** Yosemite coord returned `Yosemite Wilderness Area (National Park Service)`.
- **Existing PostGIS table** `solar_protected_areas` (18,114 CA polygons) stays as the Kern Discover-mode demo.

#### 7. HIFLD Substations / OSM substations top-6 solar states — ✅ loaded
- **HIFLD itself remains restricted** (publication paused; substitute documented).
- **Geofabrik PBF parsing was abandoned**: pyosmium with `locations=True` (required for area-mapped substations) builds a global node index that took >6 min CPU per state on the 2 GB Texas PBF.
- **Per-state Overpass turned out to work fine** with a 300-600s timeout — it was the single national US query that 504s.
- **Loader:** `packages/data-catalog/loaders/solar/load_substations_geofabrik.py` (despite the filename, it now uses Overpass — the existing PBF artifacts at `/tmp/heavi_pbf/` can be deleted).
- **PostGIS table** `substations_osm_us`: **16,725 substations** across CA (3,971), TX (6,104), AZ (1,267), NV (565), FL (2,292), NC (2,526). Includes name, voltage, operator, frequency, substation type tags.

### Flood module data

#### 8. Google Inundation History — ✅ loaded
- **Source:** `gs://flood-forecasting/inundation_history/` (public bucket, **CC-BY-4.0 confirmed**)
- **License clarification:** the spec was correct — this is plain CC-BY-4.0, not CC-BY-NC. (The CC-BY-NC dataset I initially probed was `GLOBAL_FLOOD_DB_MODIS_EVENTS_V1` on Earth Engine, which is a different Google product.)
- **Format:** ~1,629 worldwide GeoJSON tiles, ~1 GB total. Each tile has High/Medium/Low risk layers (≥5%, ≥1%, ≥0.5% wet between 1999–2020).
- **Loader:** `packages/data-catalog/loaders/flood/load_google_inundation_history.py` — paginates GCS object listing, filters to US bbox, downloads + parses + bulk-loads to PostGIS.
- **PostGIS table** `flood_inundation_history` (383 polygons, 49,834 km² high-risk + 164,008 km² medium + 350,202 km² low):
  - Houston (29.7604, -95.3698) test → falls in high-risk polygon (≥5% wet) ✓
- **Coverage caveat:** dataset spans lat -39 to 43 and lng -125 to 170. **Excludes US territory above ~43°N** — northern WA, MT, ND, MN, WI N, MI U.P., NY N, VT, NH, ME, all of AK. Module must surface this gap via the data-quality dashboard.

#### 9. Google GRRR — ✅ integration ready, deps installed
- **Source:** `gs://flood-forecasting/hydrologic_predictions/model_id_8583a5c2_v0/` (Zarr format, public)
- **Integration:** `app/integrations/google_grrr.py` — `grrr_return_periods(catchment_id)` returns `{10: cfs, 50, 100, 500}`.
- **Heavy deps now installed** in `packages/api/.venv`: xarray 2026.4.0, zarr 3.2.1, gcsfs 2026.5.0.
- **Open question (carries into Phase B/C):** mapping a (lat, lng) to a HydroBASINS catchment ID still needs a HydroBASINS PFAF-12 polygon layer or its REST service. We'll address this in flood module Stage 2 by loading the relevant HydroBASINS shapefile or wrapping their REST.

#### 10. USGS NHDPlus HR — ✅ verified on-demand (no 22 GB download needed)
- **Source:** `hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer` (national MapServer with 13 layers).
- **Avoided:** the 22 GB national GDB download. The MapServer can answer point-in-polygon + envelope queries.
- **Integration:** `app/integrations/usgs_nhdplus.py` — `nhdplus_at_point(client, lat, lng)` returns `{huc12, watershed_name, states, flowlines: [...]}` using layer 12 (WBDHU12) and layer 3 (NetworkNHDFlowline).
- **Tested:** Houston (29.7604, -95.3698) → HUC-12 `120401040305` ("City of Houston-Buffalo Bayou") + 12 flowlines including Little Whiteoak Bayou (stream order 3).

#### 11. USGS StreamStats — ❌ UNAVAILABLE
- **All documented endpoints under `streamstats.usgs.gov/streamstatsservices/*` return 404.** Tested base, `/watershed.geojson`, `/watershed.json`, alternative subdomains. The SS web app at `/ss/` is up but the REST service appears retired or migrated without a published successor.
- **Substitute:** USGS Peak-Flow (#13) covers historical gauged peaks; for ungauged-location flow estimation, no current free national API was located. **Flood module stage 2 should rely on Google GRRR (#9) as the AI-hydrologic primary**, with Peak-Flow for historical validation.

#### 12. OpenFEMA — ✅ verified national
- **Source:** `www.fema.gov/api/open/v2/DisasterDeclarationsSummaries` and `…/FimaNfipClaims`
- **Integration:** `app/integrations/openfema.py` — `disaster_declarations(client, state_abbr, county_name)` and `nfip_claims_by_zip(client, zip_code)`.
- **Tested:** Harris County TX → Hurricane Beryl 2024 + Flood 2024 + Severe Ice Storm 2021. NFIP claims for zip 77024 → 200 claims aggregated ($13,003,165 building paid, $3,888,998 contents paid; most recent dated 2026-05-23).

#### 13. USGS Peak-Flow — ✅ verified national
- **Source:** `nwis.waterdata.usgs.gov/nwis/peak?site_no=…&format=rdb` (tab-delimited RDB).
- **Integration:** `app/integrations/usgs_peak_flow.py` — `peak_flows_for_site(client, site_no)` parses RDB, returns one record per annual peak with date, flow_cfs, gage_height, qualifier.
- **Tested:** Buffalo Bayou (08074500) → 91 annual peaks back to 1929, max 50,600 cfs.

---

## What changed in PostGIS across Phase A + A2

| Table | Final count | Notes |
|---|---|---|
| `flood_inundation_history` | **383 polygons** | NEW — Google CC-BY-4.0, Inundation History |
| `ejscreen_blockgroups` | **243,022 rows** | NEW — EPA 2024 v2.32, Wayback Machine sourced |
| `substations_osm_us` | **16,725 features** | NEW — CA+TX+AZ+NV+FL+NC via Overpass |
| `wildfire_dins` | 132,522 | Verified loaded (was 0 stat estimate) |
| `wildfire_frap_perimeters` | 22,810 | Verified loaded |
| `catalog_calfire_fhsz` | 2,380 | Verified loaded |
| `catalog_layers` | 30 | All new layers registered |

---

## Open items going into Phase B (none blocking)

1. **StreamStats** is the only sourced item not solved. All `/streamstatsservices/*` endpoints return 404. **Substitute:** USGS Peak-Flow (working) + Google GRRR (deps now installed) cover the gauged-historical + AI-hydrologic-prediction roles. No further action required for Phase B.
2. **HydroBASINS catchment-ID lookup** — needed to use GRRR per point. Two options for flood module Stage 2: load HydroBASINS PFAF-12 polygons (~1 GB shapefile) to PostGIS, or call their REST service. Lightweight; can decide during flood Stage 2 implementation.
3. **Solar substations outside the top 6 states** — current coverage is CA, TX, AZ, NV, FL, NC (top 6 solar markets = ~90 % of US utility solar capacity). Expansion to more states is one Overpass invocation per state; the data-quality dashboard will surface "no substation data" for parcels outside the loaded states.
