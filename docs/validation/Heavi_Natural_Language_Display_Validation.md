# HEAVI NATURAL LANGUAGE DISPLAY — VALIDATION SUMMARY

**Date:** 2026-06-09
**Spec:** [`Heavi_Natural_Language_Display_Spec.md`](../specs/Heavi_Natural_Language_Display_Spec.md)

Replace internal criterion/source IDs with human-readable labels everywhere a buyer
sees them — across the three product pages, the PDF export, and the API responses.

## Implementation

- **`app/display_names.py`** (server registry): `CRITERION_DISPLAY` (31 criteria across
  solar/hazard/trade), `SOURCE_DISPLAY` (32 sources), `GAP_MESSAGES` (14 context-specific
  messages), plus `criterion_name`/`source_name`/`gap_message`/`make_gap` helpers and an
  `enrich_result()` that adds `display_name` + `source_display` to every ID-keyed map in a
  scoring result.
- **`src/lib/display-names.ts`** (frontend mirror): same registry + `criterionName`/
  `sourceName`, with the trade-area short-key fallback (`population` → `ta_population`).
- **`data_selection.py`**: confidence statements now name criteria by display name; data
  gaps are structured `{criterion, display_name, message, tried}` objects with the
  buyer-facing message.
- **`critical_sources.py`**: CANNOT-ASSESS statement names missing sources by display name.
- **Three scoring engines** (solar/hazard/trade): each return is passed through
  `enrich_result()`; CANNOT-ASSESS gaps are structured.
- **`solar_pdf.py`**: criterion, source, exclusion, and gap text all use display names.
- **`map-detail-panels.tsx`**: per-criterion, exclusion, gap, and data-source rendering use
  display names; hazard gained a per-peril criteria list; trade-area gained a criteria
  section and source-name labels.

## Acceptance criteria — 10/10 PASS

Verified via headless Chrome (playwright) against the live product, the rendered PDF, and
direct API inspection.

1. ✅ **Kern solar per-criterion labels** — "Transmission proximity", "Solar resource (GHI)",
   "Terrain slope", "Road access" (not `solar_transmission`, `solar_ghi`).
2. ✅ **Kern data gaps** — "Environmental Justice screening data is unavailable at this
   location. The EPA EJScreen tool has been discontinued." (not `solar_ej: No data…`).
3. ✅ **Exclusion labels** — "Protected areas · Protected Areas Database (PAD-US)",
   "Developed land · National Land Cover Database 2021" (not `protected · usgs_padus`).
4. ✅ **Sonoma hazard wildfire criteria** — "Wildfire burn probability", "Distance to
   burnable fuel" (not `wf_likelihood`, `wf_fuel_proximity`).
5. ✅ **Dallas trade-area criteria** — "Population density", "Competitive density",
   "Drive-time accessibility" (not `ta_population`, `ta_competitive_gap`).
6. ✅ **PDF export** — gaps, exclusion screening, and scored-criteria tables all use display
   names (e.g. "Transmission proximity · HIFLD Transmission Lines").
7. ✅ **Confidence statements** — reference display names ("Proxy or partial data was used
   for Wildfire burn probability."), no IDs.
8. ✅ **API responses** — `criteria_scores`/`exclusion_results`/`per_criterion` entries carry
   `display_name` + `source_display`; `gaps` are `{criterion, display_name, message, tried}`.
9. ✅ **All three modules** — /energy, /hazard, /locations updated.
10. ✅ **No technical IDs in the UI** — playwright assertions confirm no `solar_*`, `wf_*`,
    `ta_*`, `usgs_padus`, `epa_ejscreen`, `osm_pois`, or `census_acs` strings render in the
    energy or locations panels.

## Notes

- The ID fields remain in the API response for programmatic use; display fields are added
  alongside them (per spec §7).
- Trade-area `criteria_scores` use short keys (`population`) and plain numbers — the frontend
  registry maps these via a `ta_` prefix fallback, so the UI shows full names without an API
  shape change.
- `tsc --noEmit` clean; `ruff` clean on all changed files (one pre-existing E501 in
  `solar_scoring_v2.py:384`, unrelated to this change, left as-is).
