# HEAVI WORKFLOW INTEGRATION — VALIDATION SUMMARY

**Date:** 2026-06-07
**Spec:** [`Heavi_Workflow_Integration_Spec.md`](../specs/Heavi_Workflow_Integration_Spec.md)
**Reference pattern:** `solar_scoring_v2.py` (Phase 4)

Wires the **hazard_assessment** and **trade_area** workflows through the Phase 1-4
platform architecture (data repository → methodology repository → selection
engine → scoring) so both produce confidence scoring, per-criterion data quality,
and methodology documentation — matching the solar workflow.

## What shipped

| Layer | Change |
|---|---|
| Selection engine | Fixed the `census_lehd` availability probe (geometry-less table → tract-join containment), so LEHD resolves where loaded (Dallas) and falls back to the ACS commuter proxy elsewhere |
| Scoring | `hazard_scoring_v2.py` (combined wildfire + flood, per-peril, not merged) and `trade_area_scoring_v2.py` (full Huff pipeline in loaded geography; on-demand Overpass + NFHL fallback elsewhere) |
| API | `POST /hazard/score-v2`, `POST /trade-area/score-v2` (legacy `/wildfire-loss`, `/flood/risk`, `/trade-area/score` unchanged) |
| MCP | `wildfire_risk_assessment`, `flood_risk_assessment` → `/hazard/score-v2`; `trade_area_analysis` → `/trade-area/score-v2`; all now return `confidence_tier` + `data_gaps` |
| Web | `/hazard` and `/locations` pages gained inline v2 panels showing per-peril/score, confidence tier, source provenance, and data gaps |

## Acceptance criteria — 17/17 PASS

| # | Criterion | Result |
|---|---|---|
| 1 | `/hazard/score-v2` wildfire+flood for Sonoma | PASS (wildfire available; flood scored) |
| 2 | `/hazard/score-v2` wildfire+flood for Houston | PASS (flood scored; wildfire reports no-coverage honestly) |
| 3 | Confidence report, per-criterion quality for all 10 hazard criteria | PASS (10/10) |
| 4 | Component confidence for `fl_depth` (3 components) | PASS (1.0 HIGH with NFHL+3DEP+NSI) |
| 5 | Data gaps surfaced when sources unavailable | PASS (wf_likelihood, wf_fuel_proximity, wf_canopy) |
| 6 | Methodology with citations (Finney, Scawthorn) | PASS |
| 7 | `/trade-area/score-v2` Dallas → LEHD → HIGH `ta_daytime` | PASS (census_lehd, HIGH) |
| 8 | `/trade-area/score-v2` Chicago → proxy `ta_daytime` | PASS (census_acs_commuter, LOW) |
| 9 | Confidence shows POI source (PostGIS vs Overpass) | PASS (Dallas osm_pois / Chicago osm_pois_overpass) |
| 10 | Methodology with citations (Huff, Suárez-Vega) | PASS |
| 11 | `GET /data-selection?workflow=hazard_assessment` valid | PASS (10 criteria) |
| 12 | `GET /data-selection?workflow=trade_area` valid | PASS (7 criteria) |
| 13 | `GET /methodology/hazard_assessment` full doc | PASS (10 criteria, 5 citations) |
| 14 | `GET /methodology/trade_area` full doc | PASS (7 criteria, Huff + Suárez-Vega) |
| 15 | `/hazard` page displays confidence tier | PASS (HazardV2Panel; production build succeeds) |
| 16 | `/locations` page displays confidence tier | PASS (TradeAreaV2Panel; production build succeeds) |
| 17 | MCP tools return confidence tier | PASS (flood MODERATE, wildfire MODERATE, trade_area HIGH) |

## Design notes (honest scope)

- **Wildfire** is scored with the validated Sonoma vulnerability model
  (pre-computed FSim/LANDFIRE/3DEP structure features). National FSim/LANDFIRE
  rasters are not loaded, so `wf_likelihood` / `wf_fuel_proximity` / `wf_canopy`
  honestly appear as confidence gaps everywhere, and wildfire reports
  `available: false` outside loaded coverage (e.g. Houston) rather than
  fabricating a score. The methodology note flags the Sonoma calibration.
- **Trade area** demographic ring-aggregation requires loaded Census tract
  geometries (Dallas only). Outside that geography the v2 falls back to on-demand
  Overpass competitive analysis + FEMA NFHL flood, scoring over the computable
  criteria and reporting population/income/daytime as explicit coverage gaps with
  the selection engine's confidence (proxy/MODERATE) — never overstating coverage.
- **Flood** scoring reuses `flood_scoring.py`'s pure NFHL/NSI/3DEP/HAZUS query and
  lookup helpers, so v2 and the legacy endpoint share the same validated math.
