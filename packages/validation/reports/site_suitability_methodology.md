# Methodology — `site_suitability` v0.1.0

_Composite site-suitability score (0–100) for a point location, synthesizing flood risk, served demographics, transit access, environmental hazards, and competition density._


## Document identity

- **Module:** `site_suitability`
- **Module version:** `0.1.0`
- **Methodology hash (sha256):** `31ca405b9ca6259344eee7d7ec23aebd4544d95fd95334d3fc49c4425e9ff6b0`
- **Generated:** 2026-05-15T17:09:06.721413+00:00
- **Authors:** Heavi platform team

> This hash is computed over the canonical metadata (name, version, data sources, methodology steps, parameters, references, limitations). Any change to inputs that drive the score regenerates the hash; an audit consumer can verify they're reading the doc matched to a specific module version.

## Summary

The module evaluates a candidate site against five orthogonal factors, each scored 0–100 on a documented rubric, and returns an unweighted arithmetic mean as the composite score. Each factor is computed by a deterministic PostGIS query against an authoritative public dataset, evaluated within a configurable analysis radius (default 1 mile / 1609 m). The composite is intentionally simple and transparent: an auditor can independently reproduce any factor by running the documented SQL against the same data snapshot.

## Data sources & provenance

### FEMA National Flood Hazard Layer (NFHL)
- **Description:** Special Flood Hazard Areas (SFHA) — Zones A/AE/V/VE corresponding to the 1%-annual-chance flood (100-year floodplain).
- **Provenance:** FEMA Map Service Center, NFHL v2 (clipped to Alameda County)
- **License:** Public domain (U.S. Federal Government work)
- **URL:** https://msc.fema.gov/portal/advanceSearch
- **Backing table:** `catalog_fema_flood`

### U.S. Census ACS demographics
- **Description:** American Community Survey 5-year estimates at census-tract resolution.
- **Provenance:** U.S. Census Bureau, ACS 2019–2023 5-yr
- **License:** Public domain
- **URL:** https://www.census.gov/programs-surveys/acs
- **Backing table:** `catalog_census_demographics`

### GTFS transit stops
- **Description:** Public transit stop locations aggregated from regional GTFS feeds.
- **Provenance:** Bay Area transit operators (BART, AC Transit, etc.) via 511.org
- **License:** Open data, varies by operator
- **URL:** https://511.org/open-data
- **Backing table:** `catalog_transit_stops`

### EPA Facility Registry Service (FRS)
- **Description:** Regulated environmental facilities (TRI/RCRA/CERCLA/Brownfields).
- **Provenance:** EPA FRS, 2024
- **License:** Public domain
- **URL:** https://www.epa.gov/frs
- **Backing table:** `catalog_epa_facilities`

### CalFire Fire Hazard Severity Zones (FHSZ)
- **Description:** State-mapped Moderate / High / Very-High fire hazard severity zones.
- **Provenance:** CAL FIRE FRAP, 2022 FHSZ map
- **License:** Public domain
- **URL:** https://osfm.fire.ca.gov/divisions/community-wildfire-preparedness-and-mitigation/wildland-hazards-building-codes/fire-hazard-severity-zones-maps/
- **Backing table:** `catalog_calfire_fhsz`

### Overture Maps POIs
- **Description:** Points of interest used to estimate commercial competition density.
- **Provenance:** Overture Maps Foundation 2024-10 release
- **License:** ODbL / CDLA-Permissive (varies per feature)
- **URL:** https://overturemaps.org/
- **Backing table:** `catalog_overture_pois`

## Methodology

1. Geocode the request address to (lat, lng) if needed (Nominatim/OSM); otherwise use supplied coordinates directly.
2. Construct a circular analysis buffer of `radius_meters` (default 1609 m) around the point in EPSG:3857, transformed back to EPSG:4326.
3. **Flood:** `flood_risk = 0 if point ∈ FEMA SFHA polygon else 100`. Boolean containment, no soft margin.
4. **Transit:** count GTFS stops intersecting the buffer; `transit_access = min(100, round(count / 5 * 100))`. Saturates at ≥5 stops within the radius.
5. **Demographics:** `demographics = 75 if the point lies in a populated ACS tract else 40`. A coarse proxy for 'served area' coverage.
6. **Environmental:** start at 100, subtract 20 per EPA facility within the buffer, subtract 40 if the point lies in any CalFire FHSZ polygon; floor at 0.
7. **Competition:** count Overture POIs intersecting the buffer. 0 POIs → 40 (dead zone). 1–30 POIs → 40 + (count/30)*40 (linear ramp to a 'sweet spot' of 80). >30 POIs → 80 − (count − 30) / 3 (saturation penalty), floored at 20.
8. Composite = unweighted arithmetic mean of the five factor scores, rounded to the nearest integer.
9. Return the composite, the per-factor breakdown, raw counts, and the three nearest schools, transit stops, and EPA facilities.

## Parameter selection

| Parameter | Value | Justification |
|-----------|-------|---------------|
| `radius_meters` | 1609 m | 1 statute mile — the de-facto pedestrian catchment used in U.S. transit-oriented-development literature (Cervero & Kockelman, 1997). Lets transit-access and competition factors compare like-for-like with TOD studies and standard retail trade-area analyses. |
| `transit_saturation` | 5 stops | Five stops within 1 mile is the empirical inflection point above which marginal accessibility gains diminish in NCHRP Report 684 transit-access scoring. |
| `competition_sweet_spot` | 30 POIs | Roughly the mid-point of the commercial-cluster density observed in Glaeser & Gottlieb (2009) urban-agglomeration data — sufficient co-location to drive foot-traffic spillover without saturation. |
| `environmental_per_facility_penalty` | 20 points | Calibrated so five EPA facilities within the radius reduces the factor score to zero, matching the OEHHA CalEnviroScreen 4.0 convention of using facility density as a categorical risk indicator. |
| `fire_hazard_penalty` | 40 points | FHSZ containment is a binary regulatory designation in CA Public Resources Code §4201–4204; a 40-point penalty makes a fire-zone site uncompetitive on the environmental factor unless EPA hazards are absent. Threshold chosen so a fire-zone-only site still scores 60/100, reflecting that mitigation (defensible space, materials) is feasible. |
| `composite_aggregation` | unweighted_mean | Equal weighting is the most defensible default in the absence of a domain-specific weight elicitation (Saaty, 1980, AHP). Re-weighting should be done explicitly in a downstream module rather than baked into the base score. |

## Academic & regulatory basis

- _peer-reviewed_ — Cervero, R. & Kockelman, K. (1997). Travel demand and the 3Ds: Density, Diversity, and Design. Transportation Research Part D.
- _peer-reviewed_ — Glaeser, E. L. & Gottlieb, J. D. (2009). The Wealth of Cities: Agglomeration Economies and Spatial Equilibrium in the United States. Journal of Economic Literature.
- _framework_ — Saaty, T. L. (1980). The Analytic Hierarchy Process. McGraw-Hill.
- _framework_ — [OEHHA (2021). CalEnviroScreen 4.0 — methodology for cumulative environmental risk scoring.](https://oehha.ca.gov/calenviroscreen)
- _standard_ — [FEMA (2020). Guidelines and Standards for Flood Risk Analysis and Mapping — Special Flood Hazard Area determination.](https://www.fema.gov/flood-maps/guidance-partners)
- _standard_ — California Public Resources Code §4201–4204 — Fire Hazard Severity Zone designation.
- _report_ — TRB (2013). NCHRP Report 684 — Estimating Demand and Benefits of Vibrant Walkable Mixed-Use Centers.

## Validation

Calibration evidence: [`site_suitability_calibration.md`](site_suitability_calibration.md)

Most recent calibration summary:

- Cases: 10
- In-range rate: 0.4
- MAE: 11.0 (95% CI [6.2, 16.6])
- RMSE: 13.78
- Bias: 2.8

## Known limitations

- **[high]** Boolean flood containment ignores SFHA proximity. A site 5 m outside the SFHA polygon scores identically to one 5 km away. — _mitigation:_ Adopt a distance-decay penalty (e.g. linear 0→100 across the 0–200 m buffer) once we ingest FEMA depth grids.
- **[high]** Demographics factor only checks census-tract presence, not tract-level income, age, or population density. — _mitigation:_ Replace with multi-variable scoring once ACS variables are joined onto catalog_census_demographics.
- **[medium]** Transit count is unweighted by mode (a bus stop counts the same as a BART station) and ignores service frequency. — _mitigation:_ Ingest GTFS schedules; weight by trips-per-peak-hour.
- **[medium]** Competition POI curve is a heuristic; it has not been calibrated against revealed-preference retail location data. — _mitigation:_ Calibrate against historical site-success outcomes once we have a labelled training set.
- **[medium]** EPA facility count is uniform-weighted; a Superfund site counts the same as a small dry-cleaner. — _mitigation:_ Weight by EPA program (CERCLA > RCRA > TRI > FRS-only).
- **[medium]** Unweighted-mean aggregation lets a single strong factor mask another critical one (e.g. an SFHA site can still score 60+ if the other four factors are high). — _mitigation:_ Expose a `hard_disqualifier` flag (SFHA or VH-FHSZ) to downstream consumers.
- **[low]** Geocoding uses Nominatim with rate-limited public endpoint; high-volume callers should pre-resolve coordinates.

---

_This document is generated from structured metadata; do not edit by hand. Regenerate via `scripts/generate_methodology.py` when the module's data sources, parameters, references, or limitations change._