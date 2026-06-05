# HEAVI 10-STATE SOLAR VALIDATION
# Expanding Validation from 5 States to 10

## Purpose

Current solar validation covers 5 states (TX, AZ, NC, NV, FL) with regional weights and refined exclusions: 52% High nationally, 77% among non-excluded parcels. Expanding to 10 states strengthens the investor claim and reveals state-specific issues before design partner outreach.

## New States to Add

| State | Why | NERC Region | Solar Market Rank |
|---|---|---|---|
| California | Home market, Kern County already validated. Largest US solar market. | WECC | #1 |
| Georgia | Fast-growing southeast solar market. Different grid topology (SERC). | SERC | Top 10 |
| Colorado | Mountain West, terrain variation, different environmental constraints. | WECC | Top 15 |
| Indiana | Midwest, flat terrain, MISO grid. Tests agricultural land scoring. | MISO | Emerging |
| Ohio | PJM grid, Midwest/Appalachian transition zone. | PJM | Emerging |

## Protocol

For each of the 10 states (5 existing + 5 new):

1. Query solar_eia_installations for operating PV plants in that state
2. Sample 15 installations (random seed 42, or all if fewer than 15)
3. Generate 15 matched random rural locations in the same state:
   - Random lat/lng within the state bounding box
   - Filter to NLCD agricultural/rural classes (cropland, pasture, grassland) where possible
   - Exclude obviously unsuitable random points (water, dense urban)
4. Score all 30 locations using POST /solar/score-v2
5. Record: score, rating, confidence_tier, exclusions, weight_profile region

## Per-Location Timeout

90 seconds per location. If a location times out, record as TIMEOUT and continue. Do not let one stuck location block the entire state.

## Concurrency

Serial (concurrency=1) to avoid API contention. At ~10s per location, 30 locations per state, 10 states = ~50 minutes total.

## Report Format

Per-state table:

```
STATE: [XX]  |  NERC: [region]  |  EIA plants available: [N]

EIA Installations (15):
  % High (≥0.70):        [X]%
  % Moderate (0.40-0.69): [X]%
  % Low (<0.40):          [X]%
  % Excluded:             [X]%
  Mean score:             [X]
  
Random Locations (15):
  % High:                 [X]%
  Mean score:             [X]

Separation: EIA mean - Random mean = [X] (positive = good)
Confidence distribution: [N] HIGH, [N] MODERATE, [N] LOW
```

National summary:

```
10-STATE VALIDATION SUMMARY

                  EIA %High   Random %High   Separation   Confidence
Texas              [X]%        [X]%           +[X]         [distribution]
Arizona            [X]%        [X]%           +[X]         [distribution]
North Carolina     [X]%        [X]%           +[X]         [distribution]
Nevada             [X]%        [X]%           +[X]         [distribution]
Florida            [X]%        [X]%           +[X]         [distribution]
California         [X]%        [X]%           +[X]         [distribution]
Georgia            [X]%        [X]%           +[X]         [distribution]
Colorado           [X]%        [X]%           +[X]         [distribution]
Indiana            [X]%        [X]%           +[X]         [distribution]
Ohio               [X]%        [X]%           +[X]         [distribution]
─────────────────────────────────────────────────────────
NATIONAL            [X]%        [X]%          +[X]

Target: ≥60% EIA High nationally
Target: Positive EIA-vs-random separation in ≥8 of 10 states
```

## Output

Write results to docs/validation/Heavi_10_State_Solar_Validation.md

Write raw data to docs/validation/raw/test1_10state_solar.json

## Acceptance Criteria

1. All 10 states scored (300 total locations: 150 EIA + 150 random)
2. Timeout rate < 10% (fewer than 30 timeouts out of 300)
3. Results table produced per the format above
4. National % High reported honestly
5. Per-state separation reported (EIA mean - random mean)
6. Any state with negative separation flagged and investigated
7. Confidence distribution reported per state
8. Summary committed to docs/validation/
