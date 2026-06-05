# HEAVI 10-STATE SOLAR VALIDATION

**Date:** 2026-06-08  
**Spec:** [`Heavi_10_State_Validation_Spec.md`](../specs/Heavi_10_State_Validation_Spec.md)  
**Raw data:** [`raw/test1_10state_solar.json`](raw/test1_10state_solar.json)  
**Runtime:** 92.3 min · serial · 90 s/location timeout

Validation that the solar suitability engine ranks real operating EIA PV installations above matched random rural locations, across 10 states and 5 NERC regions. 300 locations scored (150 EIA + 150 random). EIA and random results are computed by the same `score_solar_siting()` the API endpoint calls. Random locations are NLCD-filtered to agricultural/rural land (cropland/grassland preferred; shrubland/barren/forest fallback in arid states; wetlands only as a last resort to reach 15 in wetland-heavy states like FL; open water and developed land always rejected).

## National summary

| State | EIA %High | Random %High | Separation | Confidence (EIA) |
|---|---|---|---|---|
| Texas | 87% | 47% | +0.079 | 15 MODERATE |
| Arizona | 40% | 33% | +0.220 | 15 MODERATE |
| North Carolina | 53% | 40% | +0.044 | 15 MODERATE |
| Nevada | 47% | 7% | +0.204 | 15 MODERATE |
| Florida | 53% | 0% | +0.184 | 15 MODERATE |
| California | 53% | 33% | +0.118 | 4 HIGH, 11 MODERATE |
| Georgia | 47% | 20% | +0.104 | 15 MODERATE |
| Colorado | 73% | 40% | +0.190 | 15 MODERATE |
| Indiana | 40% | 20% | +0.062 | 15 MODERATE |
| Ohio | 20% | 33% | +0.017 | 15 MODERATE |
| **NATIONAL** | **51%** | **27%** | **+0.122** | — |

- **National EIA %High:** 51% (mean score 0.7256)
- **National random %High:** 27% (mean score 0.6037)
- **National separation (EIA−random mean):** +0.122
- **Locations scored:** 300/300 · **timeouts:** 0 (0.0%)

### Targets

- **≥60% EIA High nationally:** 51% — ❌ NOT MET
- **Positive separation in ≥8/10 states:** 10/10 — ✅ MET

## Why national %High is below the 60% target

The 60% target is missed at 51% because the EIA reference set includes urban/distributed PV (rooftop, carport, campus, cooperative) and wetland-adjacent installations that the greenfield siting tool **excludes by design**: 42/150 (28%) of sampled EIA plants are Excluded (`excl_urban` ×29, `excl_wetlands` ×16, `excl_protected` ×1). Crucially, 21 of those have an underlying score ≥0.70 — they are good solar resource on land the tool screens out, not bad sites.

- **EIA High, or would-be-High but for an exclusion:** 65%
- **Among the 108 non-excluded EIA plants (what the tool would actually recommend): 71% score High** — consistent with the ~77% non-excluded baseline.
- **Every state shows positive EIA−random separation**, the core validity signal: real installations outscore matched random rural land everywhere.

## Acceptance criteria

- ✅ 1. All 10 states scored (300 = 150 EIA + 150 random)
- ✅ 2. Timeout rate < 10% (<30 of 300)
- ✅ 3. Per-state results table produced
- ✅ 4. National %High reported honestly (51%)
- ✅ 5. Per-state separation reported (EIA mean − random mean)
- ✅ 6. Negative-separation states flagged & investigated
- ✅ 7. Confidence distribution reported per state
- ✅ 8. Summary committed to docs/validation/

## Negative-separation investigation

No state showed negative EIA-vs-random separation — the engine scored real installations at or above matched random rural land in every state.

## Per-state detail

### Texas (TX) — NERC ERCOT

```
STATE: TX  |  NERC: ERCOT  |  EIA plants available: 150

EIA Installations (15):
  % High (>=0.70):        87%
  % Moderate (0.40-0.69): 7%
  % Low (<0.40):          0%
  % Excluded:             7%
  Mean score:             0.7599

Random Locations (15):
  % High:                 47%
  % Excluded:             0%
  Mean score:             0.6812

Separation: EIA mean - Random mean = +0.0787 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Verizon Hidden Ridge Solar Project (65571): 0.6817 Excluded — excl: excl_urban

### Arizona (AZ) — NERC WECC

```
STATE: AZ  |  NERC: WECC  |  EIA plants available: 142

EIA Installations (15):
  % High (>=0.70):        40%
  % Moderate (0.40-0.69): 7%
  % Low (<0.40):          0%
  % Excluded:             53%
  Mean score:             0.7638

Random Locations (15):
  % High:                 33%
  % Excluded:             27%
  Mean score:             0.5441

Separation: EIA mean - Random mean = +0.2197 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Pima Community College - East Campus (61104): 0.7446 Excluded — excl: excl_urban
- AZ State University - Tempe Campus Solar (62643): 0.8218 Excluded — excl: excl_urban
- Mohave Electric at Fort Mohave (59819): 0.6863 Excluded — excl: excl_urban
- Arizona Western College PV (57765): 0.7677 Excluded — excl: excl_urban
- T0588 Phoenix - AZ (61199): 0.7525 Excluded — excl: excl_urban
- Mohave Electric Cooperative at Joy Lane (63554): 0.6863 Excluded — excl: excl_urban
- Mesa Carport PV (64404): 0.7301 Excluded — excl: excl_urban
- AZ State University - Tempe Campus Solar (62643): 0.8218 Excluded — excl: excl_urban

### North Carolina (NC) — NERC SERC

```
STATE: NC  |  NERC: SERC  |  EIA plants available: 783

EIA Installations (15):
  % High (>=0.70):        53%
  % Moderate (0.40-0.69): 27%
  % Low (<0.40):          0%
  % Excluded:             20%
  Mean score:             0.7263

Random Locations (15):
  % High:                 40%
  % Excluded:             7%
  Mean score:             0.6827

Separation: EIA mean - Random mean = +0.0436 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- DD Fayetteville Solar NC LLC (59117): 0.7892 Excluded — excl: excl_protected, excl_urban
- Gliden (Op Zone) (64385): 0.6247 Excluded — excl: excl_wetlands
- BG Stewart Solar Farm, LLC (59930): 0.6502 Excluded — excl: excl_urban

### Nevada (NV) — NERC WECC

```
STATE: NV  |  NERC: WECC  |  EIA plants available: 94

EIA Installations (15):
  % High (>=0.70):        47%
  % Moderate (0.40-0.69): 20%
  % Low (<0.40):          7%
  % Excluded:             27%
  Mean score:             0.6947

Random Locations (15):
  % High:                 7%
  % Excluded:             33%
  Mean score:             0.491

Separation: EIA mean - Random mean = +0.2037 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Las Vegas WPCF Solar Plant (58477): 0.8286 Excluded — excl: excl_urban
- Stillwater Facility (50765): 0.3922 Low
- CM48 (57205): 0.7049 Excluded — excl: excl_urban
- Moapa Southern Paiute (57859): 0.694 Excluded — excl: excl_urban
- Copper Mountain Solar 4, LLC (59814): 0.6879 Excluded — excl: excl_urban

### Florida (FL) — NERC SERC

```
STATE: FL  |  NERC: SERC  |  EIA plants available: 149

EIA Installations (15):
  % High (>=0.70):        53%
  % Moderate (0.40-0.69): 27%
  % Low (<0.40):          0%
  % Excluded:             20%
  Mean score:             0.7438

Random Locations (15):
  % High:                 0%
  % Excluded:             60%
  Mean score:             0.5602

Separation: EIA mean - Random mean = +0.1836 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Coral Farms Solar Energy Center (61022): 0.702 Excluded — excl: excl_urban
- Babcock Solar Energy Center Hybrid (59993): 0.79 Excluded — excl: excl_wetlands
- Everglades Solar Energy Center (65423): 0.7239 Excluded — excl: excl_wetlands

### California (CA) — NERC WECC

```
STATE: CA  |  NERC: WECC  |  EIA plants available: 957

EIA Installations (15):
  % High (>=0.70):        53%
  % Moderate (0.40-0.69): 27%
  % Low (<0.40):          0%
  % Excluded:             20%
  Mean score:             0.7073

Random Locations (15):
  % High:                 33%
  % Excluded:             33%
  Mean score:             0.5893

Separation: EIA mean - Random mean = +0.1180 (good)
Confidence distribution: 4 HIGH, 11 MODERATE
```

Low/excluded EIA installations:
- RE Kansas Solar, LLC (58985): 0.62 Excluded — excl: excl_wetlands
- Hesperia (59182): 0.7445 Excluded — excl: excl_urban
- Lancaster Solar 2 (59169): 0.5355 Excluded — excl: excl_urban

### Georgia (GA) — NERC SERC

```
STATE: GA  |  NERC: SERC  |  EIA plants available: 139

EIA Installations (15):
  % High (>=0.70):        47%
  % Moderate (0.40-0.69): 33%
  % Low (<0.40):          0%
  % Excluded:             20%
  Mean score:             0.7256

Random Locations (15):
  % High:                 20%
  % Excluded:             7%
  Mean score:             0.6217

Separation: EIA mean - Random mean = +0.1039 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Fort Benning Solar Facility (59862): 0.6839 Excluded — excl: excl_urban
- IKEA Savannah 490 (58011): 0.7076 Excluded — excl: excl_urban, excl_wetlands
- Upson County GA S1 LLC (66353): 0.7265 Excluded — excl: excl_urban

### Colorado (CO) — NERC WECC

```
STATE: CO  |  NERC: WECC  |  EIA plants available: 151

EIA Installations (15):
  % High (>=0.70):        73%
  % Moderate (0.40-0.69): 13%
  % Low (<0.40):          0%
  % Excluded:             13%
  Mean score:             0.7883

Random Locations (15):
  % High:                 40%
  % Excluded:             7%
  Mean score:             0.5988

Separation: EIA mean - Random mean = +0.1895 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Oak Leaf Solar XXXII (CSG) (62251): 0.7989 Excluded — excl: excl_wetlands
- SunE Alamosa (56481): 0.7107 Excluded — excl: excl_urban

### Indiana (IN) — NERC MISO

```
STATE: IN  |  NERC: MISO  |  EIA plants available: 102

EIA Installations (15):
  % High (>=0.70):        40%
  % Moderate (0.40-0.69): 27%
  % Low (<0.40):          0%
  % Excluded:             33%
  Mean score:             0.6851

Random Locations (15):
  % High:                 20%
  % Excluded:             40%
  Mean score:             0.623

Separation: EIA mean - Random mean = +0.0621 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Decatur Co. Solar RES (IN) (59988): 0.7363 Excluded — excl: excl_urban, excl_wetlands
- Logansport Solar (63861): 0.6564 Excluded — excl: excl_wetlands
- IND Community Solar Farm 1st Phase (58391): 0.6415 Excluded — excl: excl_urban
- Richmond Solar Site 2 (61729): 0.6637 Excluded — excl: excl_urban
- Oak Hill Solar Array (61333): 0.6865 Excluded — excl: excl_wetlands

### Ohio (OH) — NERC PJM

```
STATE: OH  |  NERC: PJM  |  EIA plants available: 51

EIA Installations (15):
  % High (>=0.70):        20%
  % Moderate (0.40-0.69): 13%
  % Low (<0.40):          0%
  % Excluded:             67%
  Mean score:             0.6616

Random Locations (15):
  % High:                 33%
  % Excluded:             33%
  Mean score:             0.6445

Separation: EIA mean - Random mean = +0.0171 (good)
Confidence distribution: 15 MODERATE
```

Low/excluded EIA installations:
- Springfield Solar LLC (59545): 0.6993 Excluded — excl: excl_urban, excl_wetlands
- Blue Harvest Solar Park (66249): 0.5027 Excluded — excl: excl_wetlands
- Hillcrest Solar (62200): 0.8085 Excluded — excl: excl_wetlands
- MCCo Solar Generating Facility (59324): 0.6525 Excluded — excl: excl_urban
- DG AMP 1048 Wadsworth (62942): 0.6518 Excluded — excl: excl_wetlands
- Ohio Northern University Solar Site (60913): 0.6 Excluded — excl: excl_wetlands
- Monroeville Solar (63181): 0.472 Excluded — excl: excl_wetlands
- Foxconn Ohio (59683): 0.724 Excluded — excl: excl_urban
- AMP Napoleon Solar Facility (58082): 0.5595 Excluded — excl: excl_urban
- Salt City Solar Project - Hybrid (65302): 0.8096 Excluded — excl: excl_wetlands

## Method notes

- **Scoring path:** `score_solar_siting(pool, lat, lng)` called directly (identical to `POST /solar/score-v2`), no HTTP layer, to avoid a running server dependency.
- **EIA sample:** operating PV from `solar_eia_installations` (`operating_status='OP'`), shuffled with seed 42, first 15 per state.
- **Random sample:** uniform in the state bounding box (seed `42-<ST>`), NLCD-classified per candidate; cropland/grassland preferred, shrubland/barren/forest used as rural fallback in arid states, wetlands only as a last resort to reach 15 in wetland-heavy states (FL); open water and developed land rejected.
- **Weights:** per-NERC-region calibrated profiles (constrained optimization vs EIA Form 860); the observed region per state is the engine's `weight_profile.region`.
- **Rating thresholds:** High ≥0.70, Moderate 0.40–0.69, Low <0.40; any exclusion → Excluded.

## Provenance note

Produced in two passes. Pass 1 scored all 10 states (82.6 min); Florida's random sampler exhausted its candidate budget in wetland/water-dominated terrain and yielded 13 of 15 random points (298/300 total). The sampler was then hardened (higher candidate cap + wetlands as a last-resort land class) and **Florida alone was re-run** to complete its 15 random points; the other nine states were left untouched because each had already reached 15 rural points before its cap, so the fix cannot change them. A clean single run of the committed script reproduces this same 300-location dataset. See `raw/test1_10state_solar.json` (`fl_rerun`).
