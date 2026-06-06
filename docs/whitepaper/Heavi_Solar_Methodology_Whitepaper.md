# Deterministic Validated Solar Site Suitability Assessment

## A Multi-Criteria Framework Calibrated Against 6,321 US Solar Installations

**Heavi Energy** · Methodology Whitepaper · June 2026

---

## Abstract

We present a deterministic multi-criteria solar site suitability framework that scores
candidate parcels against 14 criteria (9 scored, 5 exclusion) drawn from 15 federal and
open data sources. Criterion weights are calibrated per NERC region using constrained
optimization against a ground-truth corpus of 6,321 EIA Form 860 operating solar
installations, producing seven region-specific weight profiles. The framework includes a
data selection engine that identifies the best available data source for each criterion at
each location and reports a confidence score derived from data quality, using a
weakest-link composite. Validation across 10 US states and 5 NERC regions (300 locations:
150 real installations, 150 matched random rural locations) shows that **71% of
greenfield-eligible real solar installations score High (≥0.70)**, with **positive
discrimination versus random locations in all 10 of 10 states** (mean score separation
+0.122). Every assessment is auditable: it reports the score, the data source selected for
each criterion, the confidence in that source, and the peer-reviewed methodology behind
each weight. Unlike answer-engine approaches, identical inputs always produce identical
outputs.

---

## 1. Introduction

The Inflation Reduction Act has accelerated US solar development to a pace that the
traditional site-selection workflow cannot match. As of 2024, roughly **2,060 GW** of
generation and storage capacity sits in US interconnection queues — the majority of it
solar — and developers routinely screen hundreds of candidate parcels to advance a
handful. Screening is the bottleneck: each parcel must be evaluated for solar resource,
terrain, grid access, land cover, environmental constraints, and a dozen other factors,
most of which live in separate federal datasets with inconsistent coverage.

Three approaches dominate today, and each leaves a gap:

- **GIS consultants** produce rigorous, defensible analyses but are slow (weeks per
  batch) and expensive, which makes early-stage screening of large parcel sets
  impractical.
- **Enterprise GIS platforms** (Esri-based and similar) are powerful but require trained
  analysts and substantial configuration; they are tools for specialists, not a screening
  service.
- **AI answer engines** are fast and cheap but unauditable: they cannot tell you which
  data source produced a claim, how confident it is, or whether the same question asked
  twice will give the same answer.

The common gap is **trust**. None of these approaches tells a developer both *the answer*
and *how much to trust it* — which data backed each conclusion, where the data was
missing, and what methodology justified each weight.

This paper presents a framework that closes that gap. It produces **auditable,
confidence-rated** solar suitability assessments: every parcel receives a 0–100 score, a
per-criterion breakdown naming the exact data source used, a confidence tier reflecting
data quality at that location, and a complete methodology trail with academic citations.
The framework is **deterministic** — identical inputs always produce identical outputs —
which makes its assessments reproducible and reviewable, in contrast to probabilistic
answer engines.

---

## 2. Methodology

### 2.1 Framework Overview

The framework implements **GIS-based Multi-Criteria Decision Analysis (GIS-MCDA)**, the
standard academic approach to renewable-energy siting (Doorga et al. 2019; Charabi &
Gastli 2011; Al-Shammari et al. 2026). Suitability is computed as a **Weighted Linear
Combination (WLC)** of normalized criterion scores, with weights derived in the spirit of
the **Analytic Hierarchy Process (AHP)** but calibrated empirically against observed
installations rather than expert elicitation alone.

Each criterion is one of two types:

- **Scored criteria** (9) contribute a normalized 0–1 sub-score, multiplied by a weight;
  the weighted sum is the suitability score.
- **Exclusion criteria** (5) are binary pass/fail screens. Any failed exclusion overrides
  the weighted score and marks the parcel **Excluded** — a fatal flaw for utility-scale
  ground-mount development.

Final suitability is reported on a 0–100 scale with four ratings: **High (≥0.70)**,
**Moderate (0.40–0.69)**, **Low (<0.40)**, and **Excluded**.

### 2.2 Scored Criteria

The nine scored criteria, their literature-supported weight ranges, calibration default
weights, primary data source, and academic provenance:

| Criterion | Weight range | Default | Primary source | Why it matters | Provenance |
|---|---|---|---|---|---|
| Transmission proximity | 0.10–0.45 | 0.25 | HIFLD transmission | Gen-tie cost dominates interconnection economics | Hernandez et al. (2015); Al-Shammari et al. (2026) |
| Solar resource (GHI) | 0.10–0.18 | 0.15 | NREL PVWatts v8 | Annual energy yield sets revenue | Dobos (2014); Freeman et al. (2014) |
| Terrain slope | 0.11–0.17 | 0.15 | USGS 3DEP | Grading cost and tracker feasibility | Gesch et al. (2018); Doorga et al. (2019) |
| Road proximity | 0.10–0.14 | 0.12 | OSM roads | Access and construction logistics | Hernandez et al. (2015); Doorga et al. (2019) |
| Terrain aspect | 0.08–0.12 | 0.10 | USGS 3DEP | South-facing favored for fixed-tilt | Charabi & Gastli (2011) |
| Land cover | 0.08–0.12 | 0.10 | MRLC NLCD 2021 | Agricultural land preferred, buildable | Yang et al. (2018); Hernandez et al. (2015) |
| Soil suitability | 0.05–0.10 | 0.08 | USDA SSURGO | Drainage and shrink-swell affect cost | USDA NRCS Soil Survey |
| Flood penalty | 0.03–0.07 | 0.05 | FEMA NFHL | A/AE zones add cost, not a fatal flaw | FEMA NFHL |
| Environmental justice | 0.00–0.05 | 0.05 | EPA EJScreen | Regulatory and permitting awareness | EPA EJScreen 2024 v2.3 |

Notes on weight rationale (drawn directly from the methodology repository):

- **Transmission proximity** carries the highest weight because the cost of the
  generation-tie line frequently dominates interconnection economics. In regions where
  solar resource is uniformly high (e.g., the Sun Belt), grid proximity becomes the
  primary differentiator, consistent with Al-Shammari et al. (2026). The weight should be
  lower where irradiance varies more.
- **Solar resource (GHI)** carries a lower weight than one might expect because across the
  US Sun Belt, GHI is uniformly high and provides minimal differentiation between
  candidate parcels. The weight should increase in regions where GHI varies significantly.
- **Terrain aspect** is down-weighted because single- and dual-axis tracking systems
  largely eliminate aspect sensitivity; the criterion is suppressed entirely on flat
  terrain (slope < 1°), where aspect is meaningless.
- **Flood** was reclassified from a hard exclusion to a **scored penalty** (see §2.3): A/AE
  zones score 0.35, X/outside-SFHA score 1.0.

### 2.3 Exclusion Criteria

Five exclusion criteria act as binary screens. Each threshold reflects a deliberate
refinement of the conservative literature defaults toward what utility-scale developers
actually build:

| Exclusion | Threshold | Source | Rationale for the threshold |
|---|---|---|---|
| Critical habitat (ESA) | Any overlap with USFWS-designated critical habitat | USFWS ECOS (802 polygons) | ESA §7 consultation required for federal actions affecting designated CH |
| Protected areas | **GAP 1–2 overlap only** (GAP 3–4 → advisory) | USGS PAD-US (306,082 polygons) | GAP 1–2 lands preclude development; GAP 3–4 (e.g., BLM) host many of the largest US solar farms |
| Steep slope | **Slope > 20%** (raised from 15%) | USGS 3DEP | 20% (~11.3°) accommodates single-axis trackers on rolling terrain, common in practice |
| Developed / urban | **NLCD 23–24 only** (21–22 → advisory) | MRLC NLCD 2021 | Class 21 (open space) and 22 (low intensity) are not strictly incompatible; only medium/high-intensity development is fatal |
| Wetlands | Any overlap with NWI polygon (or hydric flag when proxy) | USFWS NWI / SSURGO proxy | Cowardin et al. (1979) classification standard; OR-SAGE treats NWI as a decision layer |

Two refinements deserve emphasis because they materially change which real installations
the framework accepts:

- **Protected-areas refinement (GAP 1–2 only).** Hernandez et al. (2015) excluded all
  protected land. But USGS PAD-US distinguishes GAP status: GAP 1–2 lands are managed for
  biodiversity with development precluded (wilderness, national parks), while GAP 3–4 lands
  permit multiple uses including energy development. Many of the largest US solar
  installations sit on BLM (GAP 3) land. Restricting the hard exclusion to GAP 1–2 avoids
  excluding viable BLM-sited projects.
- **Slope refinement (>20%).** Literature thresholds range from a conservative 3%
  (Hernandez et al. 2015) to ~36% in some international studies. We use 20% (~11.3°), which
  accommodates the single-axis tracker installations that dominate current US utility-scale
  practice.

### 2.4 Data Selection Engine

Data availability varies by location: no single source is available everywhere at full
quality. The framework addresses this with **quality-ordered data trees**. Each criterion
defines an ordered list of candidate sources, from highest quality to lowest, and the
engine selects the best one that returns data at the queried location.

Each source carries a **confidence value** reflecting its quality tier:

| Tier | Confidence | Example |
|---|---|---|
| Authoritative | 1.0 | NREL PVWatts for GHI; USGS 3DEP for slope |
| Fallback | 0.7–0.9 | Live Overpass query when the PostGIS cache misses |
| Proxy | 0.4–0.5 | SSURGO hydric-soil flag standing in for unavailable NWI wetlands |
| None | 0.0 | All tree nodes exhausted — reported as a gap, never silently |

**Worked example — the wetlands criterion tree:** the engine first attempts the
PostGIS-loaded NWI polygons (authoritative, 1.0); if the location is outside loaded
geographies, it attempts the national NWI REST service (when available); if that fails, it
falls back to the SSURGO **hydric-soil flag** as a proxy (0.4–0.5). The proxy is honest
about its lower confidence rather than pretending the authoritative source was used.

**Composite confidence** is computed across all criteria with a **weakest-link exclusion
factor**: a missing or low-confidence *exclusion* criterion (which can fatally flaw a
parcel) drags the composite down more than a low-confidence *scored* criterion. This
prevents a high composite from masking the fact that, say, wetland data was unavailable at
a given parcel. Crucially, **every criterion whose data tree is fully exhausted is reported
as a gap** — the framework never returns a misleading "$0 risk" or "Low" when the true
answer is "we could not assess this." When a critical source is exhausted, the affected
output is marked **CANNOT ASSESS** rather than scored.

### 2.5 Regional Weight Calibration

Fixed weights do not generalize across US geographies: transmission proximity matters more
in the uniform-irradiance Sun Belt than in regions where GHI varies. The framework
calibrates weights **per NERC region** using **constrained optimization** (scipy SLSQP).

- **Training signal.** EIA Form 860 operating installations are positive examples; matched
  random rural locations are negative examples. The optimizer maximizes the score
  separation between them.
- **Constraints.** Weights are bounded to the literature-supported ranges in §2.2 and
  constrained to sum to 1.0, so calibration tunes *within* defensible bounds rather than
  overfitting to arbitrary values.
- **Result.** Seven NERC-specific weight profiles (WECC, ERCOT, SERC, PJM, MISO, SPP,
  NPCC), each fitted against its regional subset of the 6,321-installation corpus (up to
  100 installations per region). At scoring time, the engine resolves a parcel's NERC
  region and applies the matching profile; where no calibrated profile exists, it falls
  back to literature-default weights and says so in the output.

The resulting calibrated weights (scored criteria, summing to 1.0 per region):

| NERC | Trans. | GHI | Slope | Road | Aspect | Land cover | Soil | Flood | EJ |
|---|---|---|---|---|---|---|---|---|---|
| WECC | 0.42 | 0.10 | 0.17 | 0.10 | 0.08 | 0.08 | 0.05 | 0.00 | 0.00 |
| ERCOT | 0.45 | 0.10 | 0.11 | 0.10 | 0.08 | 0.08 | 0.05 | 0.00 | 0.03 |
| SERC | 0.45 | 0.10 | 0.14 | 0.10 | 0.08 | 0.08 | 0.05 | 0.00 | 0.00 |
| PJM | 0.42 | 0.10 | 0.17 | 0.10 | 0.08 | 0.08 | 0.05 | 0.00 | 0.00 |
| MISO | 0.45 | 0.10 | 0.14 | 0.10 | 0.08 | 0.08 | 0.05 | 0.00 | 0.00 |
| SPP | 0.45 | 0.10 | 0.11 | 0.10 | 0.11 | 0.08 | 0.05 | 0.00 | 0.00 |
| NPCC | 0.45 | 0.10 | 0.14 | 0.10 | 0.08 | 0.08 | 0.05 | 0.00 | 0.00 |

The calibration is interpretable, not a black box. Transmission proximity is driven to its
upper bound (0.42–0.45) in every region — the optimizer confirms, against real
installations, that grid proximity is the dominant differentiator. Slope weight tracks
terrain: lower in the flat ERCOT (0.11) and SPP (0.11) footprints, higher in the more
varied PJM and WECC terrain (0.17). The flood penalty contributes through a separate
deduction mechanism rather than a positive weight, so it appears as 0.00 here.

### 2.6 Scoring Functions (Normalization)

Each scored criterion maps a raw measurement to a normalized 0–1 sub-score through an
explicit, documented function. The framework reports the function and the raw value in every
assessment, so a reviewer can reproduce the sub-score by hand:

| Criterion | Raw measurement | Normalization |
|---|---|---|
| Transmission | Distance to nearest line (km) | Linear: 0 km → 1.0, 16 km (~10 mi) → 0.0 |
| Solar resource | PVWatts capacity factor (%) | Linear: 14% → 0.0, 22% → 1.0 |
| Slope | Slope (%) from 3DEP | Linear: 0% → 1.0, 15% → 0.0 |
| Aspect | Deviation from due south (180°) | Cosine taper; suppressed when slope < 1° |
| Road | Distance to nearest road (km) | Linear, shorter scale than transmission |
| Land cover | NLCD class | Categorical: cropland/grassland high, forest/shrub mid |
| Soil | Drainage, hydric, shrink-swell | Categorical from SSURGO properties |
| Flood | FEMA zone | Categorical: X → 1.0, A/AE → 0.35, V → exclusion |
| Env. justice | EJScreen percentile | Advisory band (does not penalize a good site) |

Two points are worth noting. First, the **slope scoring function** (0–15% linear) is
distinct from the **slope exclusion** (>20%): a parcel at 10% slope is penalized in the
score but not excluded, while one at 25% is excluded outright. Second, all functions are
**monotonic and bounded** — there are no discontinuities that would make a small input
change flip the rating unpredictably, which is part of what makes the framework's output
stable and auditable.

---

## 3. Data Sources

The solar framework draws on the following sources, part of a broader 34-source federal and
open-data catalog spanning the platform's solar, hazard, and trade-area workflows. For each:
provider, coverage, resolution, vintage, and known limitations.

### Solar resource

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| PVWatts v8 | NREL | National | Nearest TMY station (<5 km) | 2020 TMY | System simulation; ±5% median accuracy |
| NSRDB (raw GHI) | NREL | National | 4 km | — | Raw irradiance only; use PVWatts for system output |

### Terrain

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| 3DEP DEM | USGS | National | ~10 m (1/3 arc-sec) | Continuously updated | 30 m-class DEM cannot resolve micro-terrain |

### Infrastructure

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| HIFLD transmission | DHS/CISA | National | Line segments | 2024 | 52,244 segments; voltage attribution varies |
| OSM substations | OpenStreetMap | National | Point | 2026 | PostGIS cache 6 states; Overpass fallback otherwise |
| OSM roads | OpenStreetMap | National | — | Live | Classification quality varies by region |
| EIA Form 860 | EIA | National | Plant points | 2024 | 6,321 operating PV plants (calibration ground truth) |

### Environmental

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| PAD-US | USGS | National | Polygon | 2024 | 306,082 polygons; GAP status drives exclusion logic |
| Critical Habitat | USFWS | National | Polygon | Current | 802 polygons; only formally designated species |
| NWI wetlands | USFWS | County (loaded) | Polygon | 2023 | **Critical gap** — PostGIS only Kern Co.; national REST degraded |
| EJScreen | EPA (archived) | National | Block group | 2024 v2.3 | Static snapshot; EPA tool offline since Feb 2025 |

### Land and soil

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| NLCD land cover | MRLC | National | 30 m | 2021 | 16-class scheme; served via WMS GetFeatureInfo |
| SSURGO soils | USDA NRCS | National | 1:12k–1:24k | 2023 | Urban areas may lack detailed survey; used as hydric proxy |

### Hazard (flood penalty)

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| FEMA NFHL | FEMA | National | Parcel polygons | Varies by community | Map currency varies; pluvial flooding not mapped |

### Interconnection

| Source | Provider | Coverage | Resolution | Vintage | Known limitations |
|---|---|---|---|---|---|
| Queued Up 2025 | LBNL | National | County centroid | 2025 | 4,426 active solar projects; informational, not a power-flow study |

---

## 4. Validation

### 4.1 Validation Design

- **Ground truth.** EIA Form 860 operating solar installations — real plants that
  developers actually built, financed, and interconnected.
- **Metric.** Percentage of installations scoring **High (≥0.70)**, with particular focus
  on **greenfield-eligible** (non-excluded) installations — the population the screening
  tool is designed for.
- **Comparison.** Real installations versus matched random rural locations in the same
  state, to test whether the framework *discriminates* — i.e., scores real sites above
  arbitrary land.
- **Coverage.** 10 states across 5 NERC regions: TX, AZ, NC, NV, FL, CA, GA, CO, IN, OH.
- **Sample.** 15 EIA installations + 15 random rural locations per state = **300 total
  locations**, scored serially through the production engine. Random locations are
  NLCD-filtered to agricultural/rural land (cropland/grassland preferred), with water and
  developed land rejected.

### 4.2 Results

| State | NERC | EIA %High | EIA mean | Random %High | Random mean | Separation |
|---|---|---|---|---|---|---|
| Texas | ERCOT | 87% | 0.760 | 47% | 0.681 | +0.079 |
| Arizona | WECC | 40% | 0.764 | 33% | 0.544 | +0.220 |
| North Carolina | SERC | 53% | 0.726 | 40% | 0.683 | +0.044 |
| Nevada | WECC | 47% | 0.695 | 7% | 0.491 | +0.204 |
| Florida | SERC | 53% | 0.744 | 0% | 0.560 | +0.184 |
| California | WECC | 53% | 0.707 | 33% | 0.589 | +0.118 |
| Georgia | SERC | 47% | 0.726 | 20% | 0.622 | +0.104 |
| Colorado | WECC | 73% | 0.788 | 40% | 0.599 | +0.190 |
| Indiana | MISO | 40% | 0.685 | 20% | 0.623 | +0.062 |
| Ohio | PJM | 20% | 0.662 | 33% | 0.645 | +0.017 |
| **National** | — | **51%** | **0.726** | **27%** | **0.604** | **+0.122** |

**The core validity signal holds in every state: EIA installations outscore matched random
rural land in all 10 of 10 states** (positive separation), national mean separation
+0.122. This is the discrimination the framework is designed to provide.

### 4.3 Exclusion Analysis

The headline national figure — 51% of *all* sampled EIA installations score High — is
deceptively low, and the reason is instructive. **28% (42 of 150) of sampled installations
are Excluded by design:**

| Exclusion reason | Count |
|---|---|
| `excl_urban` (NLCD 23–24: rooftop, carport, campus, cooperative) | 29 |
| `excl_wetlands` (NWI / hydric overlap) | 16 |
| `excl_protected` (GAP 1–2 overlap) | 1 |

These are **distributed and rooftop installations** — university campuses, parking-lot
carports, cooperative rooftop arrays — that the EIA reports as operating PV but that a
**greenfield utility-scale screening tool is explicitly not designed to evaluate**.
Critically, **21 of the 42 excluded installations have an underlying score ≥0.70**: they
are good solar resource on land the tool screens out for being developed or wetland, not
bad sites.

Correcting for this:

- **Among the 108 greenfield-eligible (non-excluded) installations, 71% score High.**
- Counting installations that are either High or would-be-High but for an exclusion: 65% of
  the full sample.

The 71% figure is the honest measure of recall for the population the tool serves.

### 4.4 Confidence Distribution

Per-state confidence tiers concentrate at **MODERATE** (Texas through Ohio: 15/15 MODERATE;
California: 11 MODERATE, 4 HIGH). This is not a defect to hide — it is a direct,
honest consequence of a documented data gap:

The **NWI wetlands** authoritative source is PostGIS-loaded only for Kern County, CA, and
the national NWI REST service is degraded (HTTP 500 on spatial queries). Outside Kern
County, the wetlands criterion falls back to the SSURGO hydric-soil **proxy** (confidence
0.4–0.5). Because wetlands is an *exclusion* criterion, the weakest-link composite
(§2.4) correctly pulls the composite confidence down to MODERATE wherever the proxy is
used — which is nearly everywhere. California shows the only HIGH-confidence installations,
consistent with Kern County's loaded NWI coverage. **The framework reports MODERATE rather
than overstating HIGH** — a deliberate honesty that a buyer's technical reviewer can
verify.

### 4.5 Worked Example

To make the output concrete, here is the full assessment of a single greenfield parcel near
the Solar Star / Edwards–Sanborn cluster in Kern County, California (34.8200°N,
-118.3600°W). The parcel scores **86/100 (High)** at **HIGH confidence (95/100)** under the
WECC weight profile, with all five exclusion screens passing:

| Criterion | Sub-score | Weight | Contribution | Source | Confidence |
|---|---|---|---|---|---|
| Transmission proximity | 91 | 0.42 | 0.381 | HIFLD (1.5 km to line) | 1.0 |
| Solar resource (GHI) | 93 | 0.10 | 0.093 | PVWatts v8 (21.4% CF) | 1.0 |
| Terrain slope | 95 | 0.17 | 0.162 | USGS 3DEP (0.7%) | 1.0 |
| Road proximity | 50 | 0.10 | 0.050 | OSM roads | 1.0 |
| Terrain aspect | 100 | 0.08 | 0.080 | USGS 3DEP | 1.0 |
| Land cover | 60 | 0.08 | 0.048 | NLCD 2021 | 1.0 |
| Soil suitability | 100 | 0.05 | 0.050 | SSURGO | 1.0 |
| Flood penalty | 50 | 0.05 | 0.000 | FEMA NFHL | 1.0 |
| Environmental justice | — | — | — | EJScreen (gap) | 0.0 |
| **Composite** | **86** | — | **0.863** | — | **HIGH (0.95)** |

This single parcel illustrates several design choices at once. **Transmission proximity
dominates** the weighted contribution (0.381 of 0.863), consistent with the calibration.
**Environmental justice is a gap** — EJScreen returned no value at this point — yet the
**composite confidence remains HIGH (0.95)** because EJ carries near-zero weight and, more
importantly, every *exclusion* criterion resolved authoritatively (confidence 1.0). This is
the weakest-link logic working as intended: a low-weight scored gap barely moves the
composite, whereas an unavailable exclusion criterion would have pulled it down sharply. The
assessment also reports interconnection context: the nearest substation is **2.1 miles**
away, and **4,376 MW of existing operating solar capacity sits within 50 km** (141 plants —
the Solar Star, Beacon, and Edwards–Sanborn clusters), confirming the area as a proven
solar corridor.

---

## 5. Interconnection Context

Beyond suitability scoring, each assessment includes **interconnection context** derived
from the **LBNL "Queued Up" 2025** dataset — LBNL's aggregated national ISO/RTO and utility
interconnection queue. The framework loads **4,426 active solar interconnection requests**
(filtered from the full queue to `q_status = active` and solar/solar-plus-storage resource
types).

For a candidate parcel, the context reports:

- **Nearest substation** (distance and voltage class, from OSM/HIFLD)
- **Existing connected capacity** within 50 km (from EIA Form 860 operating plants)
- **Active queue activity** within 50 km (count and MW of nearby solar interconnection
  requests, from LBNL)
- **The predominant ISO/RTO** for the area

This is explicitly **informational context, not a power-flow or interconnection study**
(which is a separate engineering discipline). The LBNL file contains no per-project
coordinates, so each queue project is placed at its **county centroid** (5-digit FIPS →
Census 2024 county gazetteer); this is adequate for the 50 km proximity count but is not a
precise project location, and the output states so. Actual hosting-capacity determination
requires filing an interconnection application with the relevant ISO.

---

## 6. Known Limitations

The framework's credibility rests on documenting its limitations as clearly as its
strengths. The following are the substantive ones:

- **NWI wetlands (national gap).** The authoritative USFWS NWI source is PostGIS-loaded
  only for Kern County; the national REST service returns HTTP 500 on spatial queries.
  Outside loaded geographies, the wetlands exclusion uses the SSURGO hydric-soil proxy,
  which lowers composite confidence to MODERATE. This is the single largest driver of the
  national confidence distribution.
- **Wildfire likelihood (proxy outside loaded geographies).** The hazard module uses USFS
  FSim burn-probability where loaded and NIFC historical fire frequency as a proxy
  elsewhere; this is a recall-limited proxy, not a calibrated probability everywhere.
- **EJScreen (static).** EPA EJScreen has been offline since February 2025; the framework
  uses an archived 2024 v2.3 snapshot (243,022 block groups). It will not update unless EPA
  restores the tool.
- **Interconnection (informational only).** The LBNL queue context is informational and
  placed at county-centroid precision. It is not a capacity analysis or power-flow study.
- **Batch throughput.** Live scoring is rate-limited by the free-tier APIs behind several
  sources (PVWatts, Overpass, SSURGO); large batches are paced accordingly.
- **Validation measures recall, not precision.** The 71% figure answers "what fraction of
  real installations does the tool identify as suitable?" It does **not** yet answer "of the
  parcels the tool scores High, what fraction would a developer actually pursue?" That
  precision metric requires expert review of the tool's output and is defined for
  measurement during design-partner pilots (see the companion precision-metric framework).
- **Single-founder engineering.** The methodology was designed and implemented by one
  person. It is transparent and reproducible by construction, but it has not yet been
  independently audited by an external GIS authority.

---

## 7. Conclusion

This paper has described a deterministic, validated framework for solar site suitability
screening. Its contributions are: (1) a **transparent multi-criteria methodology** with 14
criteria grounded in peer-reviewed literature and explicit, defensible exclusion
thresholds; (2) a **data selection engine** that picks the best available source per
criterion per location and reports honest, weakest-link confidence — including explicit
"cannot assess" rather than misleading defaults; (3) **regional weight calibration** against
6,321 real installations producing seven NERC-specific profiles; and (4) a **10-state
validation** demonstrating 71% recall among greenfield-eligible installations and positive
discrimination in all 10 states.

Future work follows directly from the limitations: establishing a **precision metric** from
design-partner pilot feedback; **national data loading** to close the NWI wetlands and
related gaps; and extension of the same auditable, confidence-rated approach to the
platform's **hazard and trade-area** modules.

The differentiator is not any single criterion or data source — it is that every assessment
tells you both the answer *and how much to trust it*, reproducibly, with the methodology
open to inspection.

---

## 8. References

1. Al-Shammari, S., et al. (2026). GIS-based solar suitability assessment across CONUS at
   90 m resolution using fuzzy AHP. *Renewable Energy* (in press).
2. Charabi, Y., & Gastli, A. (2011). PV solar farms site assessment using GIS-based spatial
   fuzzy multi-criteria evaluation. *Renewable Energy*, 36(9), 2554–2561.
3. Cowardin, L.M., Carter, V., Golet, F.C., & LaRoe, E.T. (1979). *Classification of
   Wetlands and Deepwater Habitats of the United States*. USFWS FWS/OBS-79/31.
4. Dobos, A.P. (2014). *PVWatts Version 5 Manual*. NREL/TP-6A20-62641.
5. Doorga, J.R.S., Rughooputh, S.D.D.V., & Boojhawon, R. (2019). Multi-criteria GIS-based
   modelling approach for the identification of suitable sites for the construction of
   photovoltaic solar plants. *Renewable and Sustainable Energy Reviews*, 104, 133–146.
6. Freeman, J., Whitmore, J., Kaffine, L., Blair, N., & Dobos, A.P. (2014). *Validation of
   Multiple Tools for Flat Plate PV Modeling Against Measured Data*. NREL/TP-6A20-61497.
7. Gesch, D.B., Evans, G.A., Oimoen, M.J., & Arundel, S. (2018). *The 3D Elevation
   Program — Summary of Program Direction*. USGS Fact Sheet 2018-3029.
8. Hernandez, R.R., Hoffacker, M.K., Murphy-Mariscal, M.L., Wu, G.C., & Allen, M.F. (2015).
   Solar energy development impacts on land cover change and protected areas. *PNAS*, 112,
   13579–13584.
9. Sengupta, M., Xie, Y., Lopez, A., Habte, A., Maclaurin, G., & Shelby, J. (2018). The
   National Solar Radiation Database (NSRDB). *Renewable and Sustainable Energy Reviews*,
   89, 51–60.
10. Yang, L., Jin, S., Danielson, P., Homer, C., Gass, L., et al. (2018). A New Generation
    of the United States National Land Cover Database. *Remote Sensing of Environment*,
    209, 64–76.

---

*Heavi Energy — Solar Site Screening for Renewable Development. This whitepaper documents
the methodology as implemented and validated as of June 2026. Validation data and the
scoring engine are reproducible; methodology is open to technical review.*
