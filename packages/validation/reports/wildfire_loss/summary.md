# Wildfire Loss Estimation — Sonoma County Summary

_Run ID:_ `3b8b4377-8496-4066-b721-1b9ce45dbc2c`  
_Methodology hash:_ `89caa222b6b059ffb2d64aa66df6259f43fbe0fea8ba290fa894c99046004881`  
_Vulnerability model:_ run `ca43038e…` AUC = 0.760  
_Generated:_ 2026-05-15T22:31:33.584369+00:00

## Portfolio totals

- **Structures scored:** 185,300
- **Total expected annual loss:** $47,586,439
- **Mean EAL / structure:** $256.81
- **Median EAL / structure:** $6.16

## EAL distribution

| Bucket | n | share | total EAL in bucket |
|--------|--:|------:|--------------------:|
| $0 | 69,488 | 37.5% | $0 |
| $0-10 | 27,165 | 14.7% | $72,241 |
| $10-100 | 24,398 | 13.2% | $1,079,819 |
| $100-500 | 37,065 | 20.0% | $9,786,564 |
| $500-1000 | 16,124 | 8.7% | $11,458,715 |
| $1000+ | 11,060 | 6.0% | $25,189,100 |

## EAL by occupancy class (first three NSI occtype chars)

| Class | n | total EAL | mean EAL | share | total exposure |
|-------|--:|----------:|---------:|------:|---------------:|
| RES | 166,924 | $34,783,367 | $208.38 | 73.1% | $49,421,482,850 |
| COM | 12,033 | $4,952,528 | $411.58 | 10.4% | $14,253,921,594 |
| IND | 3,795 | $3,480,747 | $917.19 | 7.3% | $5,821,705,835 |
| AGR | 1,309 | $2,568,817 | $1,962.43 | 5.4% | $1,211,389,832 |
| EDU | 357 | $1,045,423 | $2,928.36 | 2.2% | $2,674,407,091 |
| REL | 567 | $383,584 | $676.52 | 0.8% | $871,591,183 |
| GOV | 315 | $371,971 | $1,180.86 | 0.8% | $571,337,896 |

## Top 20 areas by aggregate EAL

_Aggregated by census tract; ZIP attached via Nominatim reverse-geocoding of the tract centroid (see limitations)._

| Rank | Tract FIPS | ZIP | n_structures | Total EAL | Mean EAL |
|----:|-----------|----:|------------:|----------:|---------:|
| 1 | `06097151100` | nan | 2,678 | $4,525,188 | $1,689.76 |
| 2 | `06097151201` | 94931 | 3,321 | $2,224,979 | $669.97 |
| 3 | `06097150612` | 94954 | 2,167 | $2,196,379 | $1,013.56 |
| 4 | `06097153501` | nan | 1,978 | $2,189,381 | $1,106.87 |
| 5 | `06097150500` | 95442 | 2,107 | $1,935,606 | $918.65 |
| 6 | `06097152600` | 95409 | 3,074 | $1,706,409 | $555.11 |
| 7 | `06097151000` | 94999 | 1,676 | $1,581,103 | $943.38 |
| 8 | `06097154100` | 95441 | 1,749 | $1,571,248 | $898.37 |
| 9 | `06097153502` | 95472 | 1,601 | $1,499,181 | $936.40 |
| 10 | `06097150303` | 95476 | 2,499 | $1,486,907 | $595.00 |
| 11 | `06097151309` | 95404 | 2,377 | $1,253,989 | $527.55 |
| 12 | `06097151602` | 95409 | 2,088 | $1,046,038 | $500.98 |
| 13 | `06097150702` | 94952 | 2,110 | $1,033,428 | $489.78 |
| 14 | `06097153600` | 95444 | 2,110 | $1,024,732 | $485.66 |
| 15 | `06097154302` | 94922 | 2,490 | $889,120 | $357.08 |
| 16 | `06097150100` | 95476 | 1,559 | $871,518 | $559.02 |
| 17 | `06097151502` | 95405 | 2,578 | $854,046 | $331.28 |
| 18 | `06097153706` | 95436 | 1,961 | $801,766 | $408.86 |
| 19 | `06097150800` | 94952 | 1,897 | $797,557 | $420.43 |
| 20 | `06097153404` | 95472 | 1,553 | $791,796 | $509.85 |

## Loss exceedance probability (OEP curve)

| Return period (yr) | Annual freq. of exceedance | Loss amount |
|------------------:|---------------------------:|------------:|
| 10 | 0.1000 | $10,377,838 |
| 25 | 0.0400 | $13,752,258 |
| 50 | 0.0200 | $16,858,049 |
| 100 | 0.0100 | $20,944,229 |
| 250 | 0.0040 | $27,979,502 |
| 500 | 0.0020 | $42,388,006 |
| 1000 | 0.0010 | $44,322,035 |

_The OEP curve gives the expected annual frequency of ANY single-property loss exceeding the listed amount. Return period = 1 / frequency. Built on the Bernoulli-independence assumption — see limitations._

## Documented limitations

- **[HIGH]** **Conditioning caveat (CRITICAL).** burn_probability appears in both the hazard term (λ_burn) and as a *predictor* in the vulnerability model. In the calibration cohort the vulnerability model assigned a negative coefficient to burn_probability (β = −130.76), because conditional on a structure being inside a fire perimeter, high-BP locations are wildland-residential with lower destruction rates than dense urban WUI. The two terms consequently cancel partially: EAL = BP × P(destroy | BP) compresses the spread of EAL across structures. This is a known property of the decomposition we chose, not a calculation error. Treat absolute EAL magnitudes as ordinal, not cardinal. *Mitigation:* Drop burn_probability from the vulnerability-model predictor set and refit, OR move to a copula formulation that handles the dependence explicitly.

- **[HIGH]** **Tubbs dominance.** Tubbs (2017) supplied 4,320 of 5,797 destroyed records (75 %) in the training cohort. Its dense urban-edge (Coffey Park) ember-storm signature dominates the vulnerability coefficients, so structures resembling Coffey Park geometry will score highly even outside that fuel/wind regime. *Mitigation:* Add fire-fixed effects or refit with sample weights that down-weight Tubbs.

- **[MEDIUM]** **Bernoulli independence in OEP.** The portfolio OEP cumulates per-structure frequencies as if losses were independent. Real wildfires destroy clusters of structures simultaneously, so the AEP (Aggregate Exceedance Probability) is significantly fatter-tailed than the OEP we report. *Mitigation:* Run Monte Carlo at the fire-event level using FSim stochastic catalogs, or apply a cluster-shock multiplier (×2-4 for ~100-yr return).

- **[MEDIUM]** **NSI pseudo-locations.** NSI v2 places structures at a synthesized centroid that may be offset 20-100 m from the true building footprint. Where the synthesized location lands on a different raster cell from the real structure, the BP / fuel / canopy / slope features carry that error into EAL. *Mitigation:* Re-snap NSI points to the matched Microsoft Building Footprint when a high-confidence pair exists.

- **[MEDIUM]** **Temporal mismatch.** BP is a stationary surface (LANDFIRE 2014 fuels). Fuels are LANDFIRE 2022. NSI replacement values are 2023 dollars. DINS labels span 2017-2020. Each layer is a snapshot from a different year. EAL implicitly assumes the future looks like an average of these snapshots. *Mitigation:* Refresh BP via a re-run of FSim against LANDFIRE 2022 fuels, and reflate val_struct to a consistent target year.

- **[LOW]** **Total-loss severity.** We treat severity as 100 % of val_struct given destruction. Insurance industry-typical mean damage ratios for total-loss claims are ~0.7-0.85 (salvage + foundation, ALE costs net out). EAL is therefore biased high by ~15-30 %. *Mitigation:* Multiply per-structure EAL by an industry-typical mean damage ratio (e.g. 0.75) before reporting absolute dollars.

- **[LOW]** **ZIP via reverse geocoding.** NSI has census-block FIPS but no ZIP. Top-20 tract centroids are reverse-geocoded through Nominatim's public API to attach a representative ZIP, which may not match the USPS ZIP that contains every individual structure in that tract. *Mitigation:* Load the Census ZCTA boundaries and aggregate natively.


_For full methodology, references, and parameter justifications see `methodology.md` in this folder._
