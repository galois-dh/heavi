# HEAVI MONTH-1 SPRINT — VALIDATION SUMMARY

**Date:** 2026-06-08
**Spec:** [`Heavi_Month1_Sprint_Spec.md`](../specs/Heavi_Month1_Sprint_Spec.md)

Four solar-product gaps that block design-partner demos. All acceptance criteria
verified (API + reportlab PDF rendering + headless-Chrome UI runs).

## Feature 1 — Address geocoding (6/6 PASS)

`GET /geocode?q=` (`app/geocoding.py`): Census Bureau geocoder first (single
confident match), Nominatim fallback for place names / city-state / POIs; raw
coords returned with no external call. Unified `GeocodeInput` on /energy,
/hazard, /locations.

1. "Bakersfield, CA" → 35.37,-119.02 · 2. "1600 Pennsylvania Ave, Washington DC"
→ White House 38.898,-77.037 · 3. "35.35,-119.05" detected as coords (no geocode
call) · 4. "asdfghjkl" → error · 5. all three pages unified · 6. resolved coords
shown before scoring.

## Feature 2 — Batch results on map with ranking (8/8 PASS)

`POST /solar/score-v2/batch` (cap 200). Energy page: CSV parser (lat/lng |
address | name), per-row scoring with a live progress bar, ranked sidebar list
(excluded grouped at bottom with reason), bidirectional map↔list select + pan.

10-row CSV scored + mapped; color-coded markers; sorted list; row→pan+detail;
marker→list highlight; progress indicator; address CSV geocoded; excluded last.

## Feature 3 — PDF export (6/6 PASS)

`app/solar_pdf.py` (reportlab). `GET /solar/score-v2/pdf` (single) and
`POST /solar/score-v2/batch/pdf` (portfolio: ranked summary + per-site pages).
Branded header/footer + date, KPI cards, exclusion + per-criterion tables,
weight profile, methodology page, disclaimer. "Export PDF" buttons in the UI.

Single Kern PDF; contains score/confidence/per-criterion/exclusions/weight
profile/methodology/disclaimer; clean tables (not a text dump); 5-site batch =
summary + 5 detail pages; Export button + download (200 application/pdf);
generation date + Heavi branding on every page.

## Feature 4 — Interconnection proximity intelligence (8/8 PASS)

`interconnection_queue` table + `load_interconnection_queue.py` +
`app/interconnection.py`. `get_interconnection_context()` adds nearest
substation, existing EIA-860 capacity, ISO queue activity (active solar
count/MW), a status breakdown, and the ISO to every `score-v2` output and the
PDF; queue projects are a togglable purple map layer.

1. all ISOs/utilities loaded (MISO/ERCOT/PJM/SPP/CAISO + FPL/Duke/BPA/NYISO/…) ·
2. score-v2 has interconnection_context · 3. Kern → 314 MW existing + 52 active
solar queue projects (13,169 MW) · 4. Houston → 4 active solar queue (994 MW) ·
5. UI detail section · 6. togglable queue map layer · 7. "informational, not an
interconnection study" note · 8. PDF includes the interconnection section.

### Data source (Feature 4) — UPDATED to live LBNL data

The `interconnection_queue` is now loaded from **LBNL "Queued Up" 2025** (Lawrence
Berkeley National Laboratory's aggregated national ISO/RTO + utility
interconnection queue, `data/interconnection/LBNL_Ix_Queue_Data_File_thru2025.xlsx`,
sheet "03. Complete Queue Data"), filtered to **active solar requests**
(`q_status='active'`, `type_clean ∈ {Solar, Solar+Battery}`): **4,426 projects,
794,818 MW**, flagged `data_source='lbnl_queued_up_2025'`.

The LBNL file has no coordinates, so each project is placed at its **county
centroid** (5-digit FIPS → Census 2024 county gazetteer); 32 rows without a usable
FIPS/geocode were skipped. County-centroid precision is appropriate for the 50 km
proximity context (which counts nearby queue activity) but is not a precise
project location — the API/PDF/UI state this explicitly. Existing capacity (EIA
Form 860) and the nearest-substation lookup use real loaded data. This replaces
the earlier representative dataset. (The loader, `load_interconnection_queue.py`,
auto-downloads the Census gazetteer and re-runs idempotently.)
