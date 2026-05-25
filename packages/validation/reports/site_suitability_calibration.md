# Calibration Report — `site_suitability` v0.1.0
- **Run ID:** `0ed7a8ac-bc28-4856-a20d-f819468cc982`
- **Started:** 2026-05-15T17:08:47.013877+00:00
- **Finished:** 2026-05-15T17:09:06.711260+00:00
- **Total wall time:** 19.70 s
- **Cases:** 10

## Summary
- **In-range rate:** 4/10 (40.0%)
- **MAE:** 11.0  (95% CI: 6.2 – 16.6, bootstrap n=2000)
- **RMSE:** 13.78
- **Bias (signed mean error):** +2.80  (positive ⇒ module over-scores vs expectation)
- **Max |error|:** 29.0

### Latency per case
- min 1653.51 ms · p50 1969.53 ms · mean 1969.63 ms · max 2554.2 ms

### Error distribution
| Abs error band | Count | Share |
|----------------|------:|------:|
| 0-5 | 3 | 30.0% |
| 5-10 | 1 | 10.0% |
| 10-20 | 5 | 50.0% |
| 20-30 | 1 | 10.0% |
| 30+ | 0 | 0.0% |

## Per-case results
| ID | Scenario | Expected | Predicted | Δ | Range | Status | Latency (ms) |
|----|----------|---------:|----------:|--:|-------|--------|-------------:|
| H1 | Rockridge BART, Oakland | 82.0 | 71.0 | -11.0 | [75, 92] | FAIL | 2554.2 |
| H2 | North Berkeley BART / Solano Ave | 82.0 | 71.0 | -11.0 | [75, 92] | FAIL | 1653.5 |
| H3 | Downtown Alameda — Park Street | 78.0 | 59.0 | -19.0 | [70, 88] | FAIL | 1930.3 |
| M1 | Downtown Oakland — 12th St BART | 66.0 | 79.0 | +13.0 | [55, 78] | FAIL | 2046.1 |
| M2 | Downtown Hayward — Hayward BART | 66.0 | 67.0 | +1.0 | [55, 78] | PASS | 2050.7 |
| M3 | San Leandro residential | 62.0 | 71.0 | +9.0 | [50, 72] | PASS | 1959.5 |
| M4 | Pleasanton residential | 56.0 | 59.0 | +3.0 | [45, 68] | PASS | 1703.3 |
| L1 | Oakland Coliseum / Doolittle industrial — SFHA | 42.0 | 71.0 | +29.0 | [28, 55] | FAIL | 1969.5 |
| L2 | Bay Farm Island shoreline, Alameda — SFHA | 48.0 | 48.0 | +0.0 | [35, 60] | PASS | 1975.3 |
| L3 | Niles Canyon / Sunol unincorporated | 50.0 | 64.0 | +14.0 | [35, 62] | FAIL | 1853.9 |

## Per-factor breakdown
| ID | flood_risk | demographics | transit_access | environmental | competition | violations |
|----|---:|---:|---:|---:|---:|------------|
| H1 | 100 | 75 | 60 | 100 | 20 | — |
| H2 | 100 | 75 | 60 | 100 | 20 | — |
| H3 | 100 | 75 | 0 | 100 | 20 | transit_access=0 outside [40, 100] |
| M1 | 100 | 75 | 100 | 100 | 20 | — |
| M2 | 100 | 75 | 60 | 80 | 20 | transit_access=60 outside [80, 100] |
| M3 | 100 | 75 | 60 | 100 | 20 | — |
| M4 | 100 | 75 | 0 | 100 | 20 | — |
| L1 | 100 | 75 | 80 | 80 | 20 | flood_risk=100 outside [0, 0]; environmental=80 outside [0, 60] |
| L2 | 0 | 75 | 0 | 100 | 65 | — |
| L3 | 100 | 75 | 0 | 100 | 44 | environmental=100 outside [40, 80] |

## Notes
- A case passes when the predicted composite score falls within the test case's accepted range. The expected midpoint is used for error metrics; the range is used for pass/fail.
- The MAE confidence interval uses percentile bootstrap (n=2000, seed=42).
- Latency includes the full module call (geocoding skipped — coordinates are supplied directly).
