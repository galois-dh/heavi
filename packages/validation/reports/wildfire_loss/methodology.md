# Methodology — `wildfire_loss` v0.1.0

_Property-level expected annual loss (EAL) for Sonoma County, derived from a frequency-severity decomposition: annual burn probability (hazard) × P(destroyed | features) (vulnerability) × NSI replacement value (exposure)._


## Document identity

- **Module:** `wildfire_loss`
- **Module version:** `0.1.0`
- **Methodology hash (sha256):** `89caa222b6b059ffb2d64aa66df6259f43fbe0fea8ba290fa894c99046004881`
- **Generated:** 2026-05-15T22:31:33.584218+00:00
- **Authors:** Heavi platform team

> This hash is computed over the canonical metadata (name, version, data sources, methodology steps, parameters, references, limitations). Any change to inputs that drive the score regenerates the hash; an audit consumer can verify they're reading the doc matched to a specific module version.

## Summary

We use the classical actuarial decomposition of expected loss into frequency × severity (Klugman, Panjer & Willmot, *Loss Models* §6). Each structure's annual destruction is treated as an independent Bernoulli trial with success probability λ = P(burn) × P(destroyed | burned). The hazard term P(burn) is the per-cell USFS WRC FSim long-run annual burn probability (frozen at LANDFIRE 2014 fuels). The vulnerability term P(destroyed | burned) is the in-perimeter destruction probability from the calibrated logistic model ([[wildfire_vulnerability]]). Severity is taken as the full NSI replacement value (total loss given destruction). The portfolio Occurrence Exceedance Probability (OEP) curve is the per-structure frequency cumulated in descending loss-amount order, converted to return period via T = 1 / λ.

## Data sources & provenance

### Enriched NSI structures
- **Description:** All 185,572 Sonoma County structures with the six raster-derived enrichment fields and replacement value (val_struct).
- **Provenance:** Heavi Stage 1+2 ingest of USACE NSI v2 + Stage 2 raster enrichment.
- **Backing table:** `wildfire_nsi_structures`

### Fitted vulnerability model
- **Description:** Coefficient bundle written by the Stage 3 trainer; supplies the P(destroyed | features) term.
- **Provenance:** packages/validation/modules/wildfire_vulnerability/fitted_model.json
- **Backing table:** `(JSON file, not a DB table)`

## Methodology

1. Pull every NSI structure with val_struct > 0 and all four vulnerability predictors non-null.
2. Score P(destroyed | features) via the closed-form logistic function using coefficients loaded from the wildfire_vulnerability fitted bundle (no inference call — vectorised numpy).
3. Compute λ_i = burn_probability_i × P(destroyed)_i for each structure.
4. Compute property-level EAL_i = λ_i × val_struct_i.
5. Persist EAL_i as `expected_annual_loss` on wildfire_nsi_structures via temp-table bulk UPDATE.
6. Aggregate: portfolio total (Σ EAL), by census tract (cbfips[:11]) → top 20 tracts with Nominatim-reverse-geocoded representative ZIP, by occupancy first-three-chars (RES/COM/IND/PUB/AGR/GOV/EDU), and a per-property EAL histogram (six buckets).
7. Build the county-level Occurrence Exceedance Probability (OEP) curve: sort (val_struct, λ) pairs by descending val_struct, cumulate λ, and report return period T = 1 / cum_λ at standard insurance return periods (10, 25, 50, 100, 250, 500, 1000 yr).

## Parameter selection

| Parameter | Value | Justification |
|-----------|-------|---------------|
| `loss_amount_given_destruction` | val_struct | Total replacement-value loss given destruction (>50 %). The DINS destruction threshold of 50 % aligns with insurance industry total-loss convention; partial losses are absorbed into the 'No Damage' arm by the vulnerability model's class filter. A more realistic mean damage ratio per state would scale every EAL by ~0.6-0.8. |
| `bernoulli_independence_assumption` | True | Per-structure annual destruction events are treated as mutually independent for the OEP construction. This is conservative for the right tail (real fire events destroy spatially-clustered structures simultaneously, so individual events are far more expensive than independence implies). |
| `ep_curve_standard_return_periods_years` | [10, 25, 50, 100, 250, 500, 1000] | Insurance-industry standard return periods for catastrophe models. PML at 250-yr is the typical reinsurance attachment reference point. |
| `aggregation_geography` | census_tract (cbfips[:11]) + Nominatim ZIP label | NSI v2 carries cbfips (census block FIPS, 15 chars) but no ZIP. Aggregating by tract gives the right granularity for Sonoma (~120 tracts ≈ ~30 ZCTAs) and we reverse-geocode the centroid of each top-20 tract through Nominatim to attach a representative ZIP for the report. Loading the Census ZCTA boundaries would let us aggregate natively by ZIP — recommended once we add more counties. |

## Academic & regulatory basis

- _framework_ — Klugman, S. A., Panjer, H. H., Willmot, G. E. (2019). *Loss Models: From Data to Decisions* (5th ed.). Wiley. Chapter 6 — Frequency-severity model and aggregate losses.
- _framework_ — Grossi, P. & Kunreuther, H. (eds.) (2005). *Catastrophe Modeling: A New Approach to Managing Risk*. Springer. Chapters 2-3 — hazard, vulnerability, exposure decomposition.
- _peer-reviewed_ — [Short, K. C., Finney, M. A., Vogler, K. C., Scott, J. H., Gilbertson-Day, J. W., Grenfell, I. C. (2020). Spatial dataset of probabilistic wildfire risk components for the United States (270 m). RDS-2016-0034-2.](https://doi.org/10.2737/RDS-2016-0034-2)
- _standard_ — [Insurance Information Institute (2024). Fundamentals of catastrophe modeling and the OEP/AEP distinction.](https://www.iii.org/)

## Validation

Calibration evidence: [`summary.md`](summary.md)

Most recent calibration summary:

- Cases: None
- In-range rate: None
- MAE: None (95% CI None)
- RMSE: None
- Bias: None

## Known limitations

- **[high]** **Conditioning caveat (CRITICAL).** burn_probability appears in both the hazard term (λ_burn) and as a *predictor* in the vulnerability model. In the calibration cohort the vulnerability model assigned a negative coefficient to burn_probability (β = −130.76), because conditional on a structure being inside a fire perimeter, high-BP locations are wildland-residential with lower destruction rates than dense urban WUI. The two terms consequently cancel partially: EAL = BP × P(destroy | BP) compresses the spread of EAL across structures. This is a known property of the decomposition we chose, not a calculation error. Treat absolute EAL magnitudes as ordinal, not cardinal. — _mitigation:_ Drop burn_probability from the vulnerability-model predictor set and refit, OR move to a copula formulation that handles the dependence explicitly.
- **[high]** **Tubbs dominance.** Tubbs (2017) supplied 4,320 of 5,797 destroyed records (75 %) in the training cohort. Its dense urban-edge (Coffey Park) ember-storm signature dominates the vulnerability coefficients, so structures resembling Coffey Park geometry will score highly even outside that fuel/wind regime. — _mitigation:_ Add fire-fixed effects or refit with sample weights that down-weight Tubbs.
- **[medium]** **Bernoulli independence in OEP.** The portfolio OEP cumulates per-structure frequencies as if losses were independent. Real wildfires destroy clusters of structures simultaneously, so the AEP (Aggregate Exceedance Probability) is significantly fatter-tailed than the OEP we report. — _mitigation:_ Run Monte Carlo at the fire-event level using FSim stochastic catalogs, or apply a cluster-shock multiplier (×2-4 for ~100-yr return).
- **[medium]** **NSI pseudo-locations.** NSI v2 places structures at a synthesized centroid that may be offset 20-100 m from the true building footprint. Where the synthesized location lands on a different raster cell from the real structure, the BP / fuel / canopy / slope features carry that error into EAL. — _mitigation:_ Re-snap NSI points to the matched Microsoft Building Footprint when a high-confidence pair exists.
- **[medium]** **Temporal mismatch.** BP is a stationary surface (LANDFIRE 2014 fuels). Fuels are LANDFIRE 2022. NSI replacement values are 2023 dollars. DINS labels span 2017-2020. Each layer is a snapshot from a different year. EAL implicitly assumes the future looks like an average of these snapshots. — _mitigation:_ Refresh BP via a re-run of FSim against LANDFIRE 2022 fuels, and reflate val_struct to a consistent target year.
- **[low]** **Total-loss severity.** We treat severity as 100 % of val_struct given destruction. Insurance industry-typical mean damage ratios for total-loss claims are ~0.7-0.85 (salvage + foundation, ALE costs net out). EAL is therefore biased high by ~15-30 %. — _mitigation:_ Multiply per-structure EAL by an industry-typical mean damage ratio (e.g. 0.75) before reporting absolute dollars.
- **[low]** **ZIP via reverse geocoding.** NSI has census-block FIPS but no ZIP. Top-20 tract centroids are reverse-geocoded through Nominatim's public API to attach a representative ZIP, which may not match the USPS ZIP that contains every individual structure in that tract. — _mitigation:_ Load the Census ZCTA boundaries and aggregate natively.

---

_This document is generated from structured metadata; do not edit by hand. Regenerate via `scripts/generate_methodology.py` when the module's data sources, parameters, references, or limitations change._