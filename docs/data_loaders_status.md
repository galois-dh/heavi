# Phase A — Data Loading Status

**Date:** 2026-06-05
**Scope:** 13-item data-source inventory for the deepened solar (8-stage) and flood (6-stage) modules.
**Architectural rule:** national-first. Kern County is validation; nothing is county-clipped except sources that are inherently single-state (CAL FIRE products).

---

## Summary

| Status | Count | Items |
|---|---|---|
| ✅ Verified live (on-demand API integration shipped) | 8 | PVWatts v8, USDA SDA, USFWS Critical Habitat, USGS PAD-US, USGS NHDPlus HR, USGS Peak-Flow, OpenFEMA Disasters + NFIP Claims |
| ✅ Loaded to PostGIS this pass | 1 | Google Inundation History (383 polygons) |
| ✅ Already loaded (verified via COUNT) | 3 | wildfire_dins (132,522), wildfire_frap_perimeters (22,810), catalog_calfire_fhsz (2,380) |
| ⚠️ Integration written, awaiting heavy-dep verification | 1 | Google GRRR Zarr (needs xarray + gcsfs in api venv) |
| ❌ Unavailable | 2 | EPA EJScreen, USGS StreamStats |
| ⏸ Deferred | 1 | National OSM substations (Overpass times out; needs Geofabrik PBF pipeline) |

**Total ready for module deepening:** 12 of 13 data sources usable. The two unavailable (EJScreen, StreamStats) have documented fallbacks below.

---

## Per-item detail

### Solar module data

#### 1. NREL PVWatts v8 — ✅ verified
- **Domain change confirmed:** the spec endpoint `developer.nrel.gov` returns NXDOMAIN from public DNS. The working host is `developer.nlr.gov` (per the build spec). Tested with the existing `NREL_API_KEY`.
- **Integration:** `packages/api/app/integrations/nrel_pvwatts.py` — async `pvwatts_v8(client, lat, lng, system_capacity_kw, …)` returning `ac_annual_kwh`, `capacity_factor_pct`, `solrad_annual`, `ac_monthly_kwh`, station metadata.
- **Test result (Kern, 1 MW fixed-tilt, 20° tilt, 180° azimuth):** ac_annual=1,688,855 kWh, capacity_factor=19.28%, solrad_annual=6.20 kWh/m²/d, version 8.5.0.

#### 2. NLCD National Land Cover — ⏸ deferred
- **MRLC bucket structure changed**: every documented S3/MRLC URL for the 2021 CONUS raster returns 403 or 404 from this host. Per-point WMS access is theoretically possible but `www.mrlc.gov/geoserver/...` returns the homepage at every reasonable path.
- **Substitute for now:** USDA SDA (#5) returns enough land-use information (urban land detection, agricultural classification via component descriptions) to cover the most common screening cases. Land-cover-driven gating can run off USFWS Critical Habitat + USGS PAD-US + SDA for v1.
- **Action item:** open a follow-up ticket — likely the URL is `https://www.mrlc.gov/data/nlcd-2023-land-cover-conus` and MRLC restructured. Not blocking module deepening; flagged for the data-quality dashboard.

#### 3. USFWS Critical Habitat — ✅ verified
- **Source:** `services.arcgis.com/QVENGdaPbd4LUkLV/.../USFWS_Critical_Habitat/FeatureServer/0`
- **National scale:** 802 designated polygons across all listed species.
- **Integration:** `app/integrations/usfws_critical_habitat.py` — `critical_habitat_at_point(client, lat, lng)` returns a list of overlapping habitat units with common name, scientific name, listing entity, federal register reference, publication date.

#### 4. EPA EJScreen — ❌ UNAVAILABLE
- **EPA discontinued the public tool Feb 2025.** Spec-suggested `gaftp.epa.gov/EJScreen/` returns 404. `ejscreen.epa.gov` is NXDOMAIN.
- **No public-mirror confirmed working.** Listed "screening-tools.com" and "PEDP copy" were not located.
- **Substitute:** social-vulnerability + demographic context can be pulled from Census ACS (already loaded via trade_area_acs_dallas for one geography; can be expanded). Document as a known module limitation in the data quality dashboard.

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

#### 7. HIFLD Substations — ⏸ deferred (national OSM via Overpass timed out)
- **HIFLD itself is restricted** (publication paused; confirmed by absence of a public download).
- **OSM Overpass national query times out at 90s and 180s.** The OSM data exists but Overpass cannot serve it in a single query at this scale.
- **Recommended path forward:** download a Geofabrik US PBF (`download.geofabrik.de/north-america/us-latest.osm.pbf`, ~10 GB) and parse offline with `osmosis` or `pyrosm`. This is a one-time job, not a per-request integration. Out of scope for Phase A.
- **Current PostGIS state:** `solar_substations_osm` has 3,970 rows (CA only). Sufficient for Kern Discover-mode demo; national interconnection analysis is degraded until the Geofabrik load runs.

### Flood module data

#### 8. Google Inundation History — ✅ loaded
- **Source:** `gs://flood-forecasting/inundation_history/` (public bucket, **CC-BY-4.0 confirmed**)
- **License clarification:** the spec was correct — this is plain CC-BY-4.0, not CC-BY-NC. (The CC-BY-NC dataset I initially probed was `GLOBAL_FLOOD_DB_MODIS_EVENTS_V1` on Earth Engine, which is a different Google product.)
- **Format:** ~1,629 worldwide GeoJSON tiles, ~1 GB total. Each tile has High/Medium/Low risk layers (≥5%, ≥1%, ≥0.5% wet between 1999–2020).
- **Loader:** `packages/data-catalog/loaders/flood/load_google_inundation_history.py` — paginates GCS object listing, filters to US bbox, downloads + parses + bulk-loads to PostGIS.
- **PostGIS table** `flood_inundation_history` (383 polygons, 49,834 km² high-risk + 164,008 km² medium + 350,202 km² low):
  - Houston (29.7604, -95.3698) test → falls in high-risk polygon (≥5% wet) ✓
- **Coverage caveat:** dataset spans lat -39 to 43 and lng -125 to 170. **Excludes US territory above ~43°N** — northern WA, MT, ND, MN, WI N, MI U.P., NY N, VT, NH, ME, all of AK. Module must surface this gap via the data-quality dashboard.

#### 9. Google GRRR — ⚠️ integration written, lazy deps
- **Source:** `gs://flood-forecasting/hydrologic_predictions/model_id_8583a5c2_v0/` (Zarr format, public)
- **Data discovery:** found by parsing the user-provided Colab notebook. Contains `reanalysis/streamflow.zarr/`, `reforecast/streamflow.zarr/`, `return_periods.zarr/`.
- **Coverage:** ~1M global HydroBASINS reaches, daily resolution, 1980–2023.
- **Integration:** `app/integrations/google_grrr.py` — `grrr_return_periods(catchment_id)` returns `{10: cfs, 50, 100, 500}`. Synchronous (Zarr/GCSFS use blocking IO); module must call from a threadpool.
- **Heavy deps:** requires `xarray`, `zarr`, `gcsfs` — lazy-imported. **Not yet installed in `packages/api/.venv`**; flood module stage 2 will need to either install them or move GRRR access to a cloud worker.
- **Open question:** also need a way to map a (lat, lng) to a HydroBASINS catchment ID. Two paths: load HydroBASINS PFAF level-12 polygons to PostGIS (~1 GB shapefile), or query their REST service. Defer to flood module Phase C planning.

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

## What changed in PostGIS this pass

| Table | Before | After | Notes |
|---|---|---|---|
| `flood_inundation_history` | did not exist | **383 polygons** | NEW — Google CC-BY-4.0 |
| `wildfire_dins` | 0 (stat estimate) | 132,522 | Was already loaded; pg_stat was stale |
| `wildfire_frap_perimeters` | 0 (stat estimate) | 22,810 | Was already loaded; pg_stat was stale |
| `catalog_calfire_fhsz` | 0 (stat estimate) | 2,380 | Was already loaded; pg_stat was stale |
| `catalog_layers` | 4 | 28 | Many tables registered themselves during the pass |

---

## What needs your decision before Phase B (module deepening)

1. **EJScreen substitute** — accept module ships without it (with a documented limitation in the data quality dashboard), or invest time hunting a mirror?
2. **StreamStats substitute** — same question. Google GRRR + Peak-Flow may be sufficient.
3. **NLCD URL discovery** — should I keep hunting MRLC's current structure, or punt to a follow-up loader pass?
4. **National OSM substations** — accept CA-only for v1 (with a documented gap), or build the Geofabrik PBF pipeline?
5. **GRRR heavy deps** — install xarray/zarr/gcsfs in the api venv (~150 MB), or run GRRR queries from a separate worker process?

None of these block starting Phase B (solar + flood module deepening with the verified inventory). They are quality-of-coverage upgrades the data-quality dashboard will surface.
