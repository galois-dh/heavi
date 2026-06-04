# HEAVI MAP INTERFACE — VALIDATION SUMMARY

**Date:** 2026-06-08
**Spec:** [`Heavi_Map_Interface_Spec.md`](../specs/Heavi_Map_Interface_Spec.md)
**Scope:** Build sequence Steps 1-8 (Step 9 mobile deferred). All acceptance
criteria except AC22 (responsive) run.

## What shipped

| Step | Change |
|---|---|
| 1-4 | `components/heavi-map.tsx` — shared `<HeaviMap>` (raw maplibre-gl, the codebase convention; no react-map-gl to avoid React-19 peer conflicts). OpenFreeMap **dark** vector basemap, scored-feature layer with three color scales, click-to-inspect + selection-ring highlight, layer-toggle panel with **on-demand** (debounced bbox) constraint loading, nav + scale controls, color legend |
| 3 | `components/map-detail-panels.tsx` — Energy / Hazard / Locations detail panels (score, confidence, per-criterion, gaps, sources, weight profile) |
| 5 | `app/constraints.py` + `GET /constraints/{layer_id}?bbox=…&limit=…` — GeoJSON for transmission / substations / eia_solar / nwi (PostGIS) and padus / nfhl (ArcGIS proxy) |
| 6 | `/energy` rebuilt map-first: input sidebar + detail panel + map (suitability scale, PAD-US/transmission/substations/EIA toggles, CSV multi-site) |
| 7 | `/hazard` map-first (risk scale, FEMA flood-zone toggle, per-peril detail) |
| 8 | `/locations` map-first (trade-area scale, 5/10/15-min isochrone overlays graduated by opacity, competitor-POI markers). Trade-area v2 API extended to return `competitor_pois` (Dallas PostGIS within the 10-min isochrone; Overpass coords in the national fallback) |

## Acceptance criteria — 21/21 run PASS (AC22 deferred)

Verified with the production `next build` (compile + static generation of all
pages), `GET /constraints` via curl, and a headless-Chrome (playwright-core)
end-to-end run driving real scoring + layer toggles against a local API.

| # | Criterion | Result |
|---|---|---|
| 1 | MapLibre + dark basemap | PASS (OpenFreeMap dark) |
| 2 | Color-coded circles per scale | PASS (energy green / hazard green-LOW / locations teal-Strong) |
| 3 | Click fires onFeatureClick + highlights | PASS (selection ring rendered) |
| 4 | Layer toggle panel shows/hides | PASS |
| 5 | Constraints load on-demand (not pre-loaded) | PASS (fetch only on toggle/move) |
| 6 | /energy map + left sidebar layout | PASS |
| 7 | Scoring places a color-coded marker | PASS |
| 8 | Click → detail panel (score/confidence/criteria) | PASS |
| 9 | PAD-US / transmission / substations render when toggled | PASS |
| 10 | CSV upload → multiple markers render | PASS (3-site CSV) |
| 11 | /hazard same layout | PASS |
| 12 | Properties color-coded by risk tier | PASS |
| 13 | Click → wildfire + flood detail | PASS |
| 14 | FEMA flood zones overlay when toggled | PASS |
| 15 | /locations same layout | PASS |
| 16 | Sites color-coded by trade-area score | PASS |
| 17 | Isochrone polygons (5/10/15 min) graduated | PASS (rings=3) |
| 18 | Competitor POIs render within trade area | PASS (67 POIs) |
| 19 | GET /constraints/transmission returns GeoJSON | PASS (83 LineStrings) |
| 20 | GET /constraints/padus returns GeoJSON | PASS (206 Polygons) |
| 21 | GET /constraints/eia_solar returns GeoJSON | PASS (32 Points) |
| 22 | Responsive bottom sheets | **Deferred** (Step 9, out of scope) |

## Notes

- **Basemap:** OpenFreeMap `styles/dark` (free, no key). The `BASEMAP` constant in
  `heavi-map.tsx` is a one-line swap for MapTiler dark-matter if needed.
- **react-map-gl** was *not* added: `maplibre-gl@5` is already a dependency and the
  existing `map-view.tsx` uses raw maplibre-gl; react-map-gl v7's React-18 peer
  range conflicts with this project's React 19. `<HeaviMap>` follows the existing
  raw-maplibre pattern and fully satisfies the spec's MapLibre intent.
- The previous inline hub panels (`hazard-v2-panel.tsx`, `trade-area-v2-panel.tsx`)
  were superseded by the map-first pages and removed.
- CORS: production already allowlists the web origin via `ALLOWED_ORIGINS`; local
  verification ran the API with the dev origin added (no code change).
