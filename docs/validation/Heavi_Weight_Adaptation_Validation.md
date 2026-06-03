# HEAVI GEOGRAPHIC WEIGHT ADAPTATION — VALIDATION SUMMARY

**Date:** 2026-06-07
**Spec:** [`Heavi_Weight_Adaptation_Spec.md`](../specs/Heavi_Weight_Adaptation_Spec.md)
**Approach run:** sampling — up to 100 EIA + matched random per NERC region, concurrency = 2.
**Raw artifacts:** [`raw/weight_profiles.json`](raw/weight_profiles.json) (the 7 calibrated profiles),
[`raw/test1_solar_multistate.json`](raw/test1_solar_multistate.json) (Test 1 with regional weights),
[`raw/test1_solar_multistate.default-weights.json`](raw/test1_solar_multistate.default-weights.json) (default-weights baseline for the AC6 comparison).

---

## Build sequence — what ran

| Step | What | Result |
|---|---|---|
| 1 | NERC region boundaries → PostGIS | 7 regions dissolved from US state polygons (`nerc_us_states.geojson`); `ST_Contains` lookup verified |
| 2 | Pre-compute criterion scores (the bottleneck) | 1,282 locations scored, **0 errors**, 166.8 min wall at concurrency 2; cached per region |
| 3 | Matched random samples per region | `ST_GeneratePoints(geom, n, seed=42)` — deterministic, strictly in-region |
| 4 | Constrained optimization per region | scipy SLSQP, bounds + Σ=1, ~seconds on cached matrices |
| 5 | Store regional weight profiles | 7 rows in `regional_weight_profiles` |
| 6 | Consume regional profiles in scoring | `score_solar_siting` resolves region → profile → weights; adds `weight_profile` section |
| 7 | Re-run Test 1 with regional weights | 10.8 min, 0 errors |

Per the spec, weight optimization is **constrained AHP, not machine learning**: criteria and their
weight bounds are fixed by the literature (Doorga 2019, Al-Shammari 2026); only the weights move, only
within published ranges, deterministically.

---

## Acceptance criteria

| # | Criterion | Result |
|---|---|---|
| 1 | NERC boundaries in PostGIS; any US lat/lng maps to a region | **PASS** — 7 MultiPolygons; CONUS point checks resolve correctly |
| 2 | Profiles for ≥5 of 7 regions | **PASS** — **7/7** (all regions had ≥41 EIA, above the 20 threshold) |
| 3 | Optimized weights within literature bounds | **PASS** — every weight within `[weight_min, weight_max]` |
| 4 | Σ weights = 1.0 per profile | **PASS** — all 7 sum to 1.000000 |
| 5 | ≥50% High nationally (up from 24%) | **FAIL (improved 24% → 40%)** — capped by exclusions; see below |
| 6 | EIA-vs-random separation improves in ≥4/5 test states | **PASS** — **5/5** improved |
| 7 | Every scored output documents its weight profile | **PASS** — `weight_profile` section present (region, method, n, note) |
| 8 | Profiles table documents academic_basis, weight_changes w/ reasons, metadata | **PASS** — all present in `regional_weight_profiles.metadata` |

**7 of 8 pass.** AC5 is a characterized near-miss (below).

### AC6 — separation improvement (default → regional)

| State | Region | default | regional | |
|---|---|---|---|---|
| TX | ERCOT | +0.314 | +0.406 | improved |
| AZ | WECC  | +0.086 | +0.182 | improved |
| NC | SERC  | +0.176 | +0.221 | improved |
| NV | WECC  | +0.170 | +0.246 | improved |
| FL | SERC  | +0.285 | +0.356 | improved |

### AC5 — % High is gated by exclusions, not weights

National EIA % High rose **24% → 40%**, short of the 50% target. The ceiling is structural:

- **12 of 25 EIA sites (48%) are rated *Excluded*** (protected-area, urban, flood, wetland gates firing
  on real solar-farm coordinates). An excluded site is never "High" regardless of weights, so the maximum
  achievable national % High is **52%**.
- Among the 13 *non-excludable* EIA sites, the calibration lifted High from **6/13 → 10/13 (77%)**, mean
  composite 0.765. Weight adaptation captured nearly all the headroom available to it.

Weight optimization only moves the **scored composite**; it cannot change exclusion gates. Closing the
remaining gap to 50% requires improving exclusion-check precision (e.g., a small parcel buffer so a plant
centroid landing on an access road or NLCD-developed pixel isn't excluded) — out of scope for this spec
and **not modified here**. This is the same exclusion-precision issue noted in the Phase-5 Test 1 report.

---

## Calibrated weights (observation)

The EIA ground truth shows **transmission proximity is the dominant discriminator in every region**, and
`solar_transmission` has the widest literature bound (0.10–0.45). So all seven profiles push transmission
toward its upper bound (0.42–0.45) and trim the narrow-bound criteria toward their minimums. Regional
differentiation is real but subtle — chiefly in `solar_slope` (WECC/PJM 0.17, MISO/SERC/NPCC 0.14,
ERCOT/SPP 0.11), reflecting terrain variability. The weights remain interpretable, bounded, and
deterministic; the convergence toward transmission is a property of the data, not a modeling artifact.

| Region | n_eia (excl) | transmission | slope | ghi | notable |
|---|---|---|---|---|---|
| WECC  | 100 (49) | 0.25→0.42 | 0.15→0.17 | 0.15→0.10 | high terrain variability |
| ERCOT | 100 (22) | 0.25→0.45 | 0.15→0.11 | 0.15→0.10 | flat, uniform resource |
| SPP   | 41 (18)  | 0.25→0.45 | 0.15→0.11 | 0.15→0.10 | flat Great Plains |
| MISO  | 100 (36) | 0.25→0.45 | 0.15→0.14 | 0.15→0.10 | flat cropland |
| PJM   | 100 (51) | 0.25→0.42 | 0.15→0.17 | 0.15→0.10 | rolling/mountainous |
| SERC  | 100 (27) | 0.25→0.45 | 0.15→0.14 | 0.15→0.10 | moderate terrain |
| NPCC  | 100 (36) | 0.25→0.45 | 0.15→0.14 | 0.15→0.10 | seasonal resource |

---

## Reproduce

```bash
cd packages/api && source .venv/bin/activate
python load_nerc_regions.py            # Step 1 — NERC polygons (idempotent)
python precompute_weight_matrix.py     # Steps 2-3 — ~2.8h, caches weight_cache/<region>.json
python run_weight_adaptation.py        # Steps 4-5 — optimize + store profiles (seconds)
python validate_phase5_multigeo.py --test 1   # Step 7 — Test 1 with regional weights
```

The criterion matrices (`weight_cache/`) are git-ignored intermediate artifacts (regenerable by
`precompute_weight_matrix.py`); the committed evidence is `weight_profiles.json` plus the two Test 1 runs.
