# HEAVI MONTH-2 SPRINT — VALIDATION SUMMARY

**Date:** 2026-06-09
**Spec:** [`Heavi_Month2_Sprint_Spec.md`](../specs/Heavi_Month2_Sprint_Spec.md)

Three deliverables: a methodology whitepaper, a precision-metric framework + pilot
template, and a sample output package for design-partner outreach. All built from the
live system's real data (criteria, weights, validation, scored parcels) — no invented
numbers.

## Deliverable 1 — Methodology whitepaper (7/7 PASS)

`docs/whitepaper/Heavi_Solar_Methodology_Whitepaper.md` → `….pdf` (rendered by the new
`app/whitepaper_pdf.py` reportlab Markdown→PDF pipeline).

1. ✅ PDF generated, **12 pages** (target 12–15).
2. ✅ All 10-state validation results with per-state table (§4.2) + national row.
3. ✅ All 14 criteria documented with academic citations — 9 scored (§2.2) + 5 exclusion
   (§2.3), each with weight range, default, source, and provenance; plus the calibrated
   per-NERC weight table (§2.5) and scoring functions (§2.6).
4. ✅ Data selection engine + weakest-link confidence explained with a worked wetlands
   tree (§2.4) and a full worked single-parcel example (§4.5).
5. ✅ Known-limitations section is honest and specific (§6): NWI gap, FSim proxy,
   EJScreen static, interconnection county-centroid, recall-not-precision, single-founder.
6. ✅ References section: all 10 cited papers in academic format (§8).
7. ✅ Visually professional — cover page, branded header/footer, navy-header tables,
   alternating rows (not a markdown dump).

Key reconciliation: the system has **14 criteria = 9 scored + 5 exclusion** (the spec's
abstract said "8 scored, 6 exclusion"; the whitepaper documents the accurate 9+5, matching
the product's own methodology repository and PDF). The platform catalogs **34 data sources**
and **31 criteria** across solar/hazard/trade workflows; the solar framework uses **15** of
those sources. EIA corpus = **6,321** installations (matches the title).

## Deliverable 2 — Precision metric framework + pilot template (3/3 PASS)

1. ✅ `docs/Heavi_Precision_Metric_Framework.md` — precision defined as
   (would-pursue + already-known) / High-scored; recall-vs-precision distinction; 50→15
   measurement protocol; ≥70% target; failure-reason logging; coverage as a secondary
   metric. (+ `.pdf`)
2. ✅ `docs/Heavi_Design_Partner_Pilot_Template.md` — 90-day free pilot; what each side
   provides; jointly-defined success criteria; timeline; data handling; $25–50K/yr
   conversion; signature block. Convertible to PDF (`.pdf` rendered). 
3. ✅ Both committed under `docs/`.

## Deliverable 3 — Sample output package (5/5 PASS)

Scored 10 parcels in Kern County, CA via the production engine — 5 greenfield parcels in
the Solar Star / Edwards–Sanborn corridor (all High, 78–90; ~4,500 MW existing solar
within 50 km) + 5 random agricultural parcels in the San Joaquin Valley farm belt (3 High,
2 Excluded on `excl_urban`).

1. ✅ 10-location batch scored near Solar Star, Kern County.
2. ✅ Batch portfolio PDF (`docs/sales/Heavi_Sample_Batch_Portfolio.pdf`) — ranked summary
   + per-site detail pages; plus a single-site PDF
   (`Heavi_Sample_Single_Site_Assessment.pdf`).
3. ✅ Map screenshot (`docs/sales/Heavi_Sample_Batch_Map.png`) — 10 color-coded results on
   the live energy-product map (High green / Excluded gray), background EIA layer toggled
   off for clarity, with the rating legend.
4. ✅ One-page product overview PDF (`docs/sales/Heavi_Product_Overview.pdf`).
5. ✅ All materials under `docs/sales/`.

## Method notes

- The whitepaper, precision framework, pilot template, and product overview PDFs are all
  produced by `app/whitepaper_pdf.py` (a reportlab Markdown renderer: headings, pipe
  tables, lists, bold/italic/code, cover or inline title). The single-site and batch
  assessment PDFs use the existing `app/solar_pdf.py` product pipeline.
- The map screenshot was captured with headless system Chrome (playwright-core) driving the
  live Next.js energy page against the local API, uploading a 10-row CSV and screenshotting
  after scoring completed.
- Scores carry minor run-to-run variance from live data APIs (PVWatts/Overpass/SSURGO); the
  batch PDF and the map screenshot are independent scoring runs, so a parcel may differ by a
  point or two between them. All are valid production outputs.
