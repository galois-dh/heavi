# HEAVI GEOGRAPHIC WEIGHT ADAPTATION
# Constrained AHP Optimization Using EIA Ground Truth

## Purpose

The solar siting module uses a weighted linear combination (WLC) of scored criteria. The default weights were calibrated for Kern County, CA where transmission proximity dominates because solar irradiance is uniform. Multi-geography validation (Test 1) showed these weights achieve only 24% High rate nationally — the methodology is directionally correct (real installations score higher than random in all 5 states) but the absolute calibration doesn't generalize.

This spec defines a geographic weight adaptation layer that adjusts criterion weights based on regional characteristics, constrained to the ranges established in peer-reviewed literature. The approach is:

1. Deterministic — same location always gets the same weights
2. Academically grounded — constrained to published weight ranges
3. Validated against real data — optimized using EIA Form 860 installations
4. Documented — every scored output explains which weights were used and why

---

## Academic Grounding

### Weight Ranges from Literature

The methodology repository already stores weight_min and weight_max per criterion, derived from:

- Doorga et al. (2019): AHP weights for 9 criteria, Mauritius
- Al-Shammari et al. (2026): Fuzzy AHP, 10 criteria, CONUS at 90m
- Charabi & Gastli (2011): Continuous scoring, aspect inclusion
- Hernandez et al. (2015): Exclusion framework, infrastructure proximity zones
- The Southern India coastal study (2025): "adaptable weighting schemes that can be recalibrated through local expert consultation"
- The Kermanshah study (2025): sensitivity analysis showing results are "highly sensitive to the weighting criteria"

The literature consistently acknowledges that weights should vary by geography but provides no automated method for doing so. Every study either uses fixed expert-derived weights or recommends "local recalibration through expert consultation."

### What Heavi Adds (Novel Contribution)

Heavi has something no academic study has: 6,321 real EIA Form 860 solar installations nationally as ground truth. This enables data-driven calibration within the literature-supported range — constrained optimization, not unconstrained machine learning.

The approach is analogous to Bayesian updating: the literature provides the prior (weight ranges from AHP), and the EIA data provides the likelihood (what weights best explain where solar was actually built). The posterior is a calibrated weight profile for each region that is both academically grounded and empirically validated.

---

## Geographic Segmentation

### Why Segment

Different regions have different characteristics that affect which criteria differentiate good sites from bad:

- **Solar resource uniformity**: In the Desert Southwest (GHI 5.5-6.5 kWh/m²/day), irradiance is uniformly high and provides minimal differentiation — infrastructure criteria dominate. In the Pacific Northwest (GHI 3.5-5.0), irradiance varies significantly and should be weighted higher.
- **Grid topology**: The Eastern Interconnect has dense transmission networks where proximity differentiates less. WECC has sparse transmission where it differentiates more.
- **Terrain**: The Great Plains are flat (slope rarely differentiates). The Appalachians and Rockies have significant terrain variation (slope matters more).
- **Land cover**: The Midwest is predominantly cropland (land cover differentiates less). The Southeast mixes forest, cropland, and developed (land cover matters more).

### Segmentation Approach: NERC Regions

Use NERC reliability regions as the segmentation boundary. NERC regions align with grid topology (which drives interconnection economics) and roughly correlate with climate/terrain zones:

| NERC Region | States (approx) | Grid Character | Solar Resource | Terrain |
|---|---|---|---|---|
| WECC | CA, NV, AZ, CO, UT, NM, OR, WA, MT, WY, ID | Sparse transmission, long distances | High and uniform in south, variable in north | Highly variable |
| ERCOT | TX (most) | Dense within ERCOT, limited ties | High, moderately uniform | Flat to rolling |
| SPP | OK, KS, NE, parts of TX/NM/AR/LA/MO | Moderate density | Moderate, variable | Flat (Great Plains) |
| MISO | Upper Midwest (MN, WI, IA, IL, IN, MI, parts of others) | Dense | Moderate, seasonal variation | Flat |
| PJM | Mid-Atlantic (PA, NJ, OH, VA, WV, DC, MD, DE, parts of others) | Very dense | Moderate, variable | Rolling to mountainous |
| SERC | Southeast (NC, SC, GA, AL, TN, MS, FL, parts of others) | Moderate | Moderate to high, humid | Flat to rolling |
| NPCC | Northeast (NY, NE states) | Dense | Lower, seasonal | Rolling |

### Fallback: Default Weights

For regions with fewer than 20 EIA installations (unlikely given 6,321 nationally, but possible for NPCC), use the literature default weights without optimization.

---

## Optimization Method

### Objective Function

For each NERC region, find the weight vector W that maximizes the discrimination between EIA installation locations (positive examples) and non-installation locations (negative examples).

**Positive examples**: EIA Form 860 installations in the region. Score each using the solar scoring pipeline with weight vector W.

**Negative examples**: Random locations in the region (agricultural/rural land, same acreage distribution as positives). Score each using the same pipeline with weight vector W.

**Objective**: Maximize the mean score difference between positives and negatives:

```
maximize: mean(score(EIA_locations, W)) - mean(score(random_locations, W))
```

Subject to: W_min[i] <= W[i] <= W_max[i] for all criteria i, and sum(W) = 1.0

**Alternative objective** (may produce better results): Maximize the percentage of EIA installations scoring above a threshold (e.g., >= 0.60):

```
maximize: count(score(EIA, W) >= 0.60) / count(EIA)
```

This directly targets the key recall metric ("what percentage of real solar farms does your model identify as suitable?").

### Optimization Algorithm

Use scipy.optimize.minimize with method='SLSQP' (Sequential Least Squares Programming), which supports bounds and equality constraints:

```python
from scipy.optimize import minimize

def objective(weights, eia_scores_func, random_scores_func):
    """Negative mean separation (minimize negative = maximize positive)."""
    eia_scores = eia_scores_func(weights)
    random_scores = random_scores_func(weights)
    return -(np.mean(eia_scores) - np.mean(random_scores))

bounds = [(w_min_i, w_max_i) for each criterion i]
constraints = [{'type': 'eq', 'fun': lambda w: sum(w) - 1.0}]

result = minimize(
    objective,
    x0=default_weights,  # literature defaults as starting point
    bounds=bounds,
    constraints=constraints,
    method='SLSQP'
)

optimized_weights = result.x
```

### Scoring Function for Optimization

The scoring function used during optimization should be FAST — it's called hundreds of times during optimization. This means:

1. Pre-compute all criterion values for all locations ONCE before optimization starts
2. During optimization, only the weight multiplication and summation change — no API calls
3. The criterion values matrix is: rows = locations, columns = criteria, values = normalized scores (0-1)

```python
# Pre-compute once
criterion_matrix = np.array([
    [criterion_score(location, criterion) for criterion in scored_criteria]
    for location in all_locations
])

# During optimization (fast — just matrix multiplication)
def compute_scores(weights):
    return criterion_matrix @ weights
```

This means each optimization run (200-500 iterations × matrix multiply) takes seconds, not hours.

### Sample Generation

For each NERC region:

**Positive samples (EIA installations):**
- Query solar_eia_installations WHERE state IN (region states)
- Sample up to 50 installations (or all if fewer than 50)
- For each, pre-compute all criterion scores using the data selection engine

**Negative samples (random non-installation locations):**
- Generate random lat/lng within the region's bounding box
- Filter to rural/agricultural locations (NLCD classes 81, 82 — cropland/pasture)
- Match the acreage distribution of the positive samples
- Sample same count as positives (matched sample)
- For each, pre-compute all criterion scores

**Pre-computation budget**: 100 locations per region × 7 regions = 700 score-v2 calls. At ~10s each (post-optimization fix) = ~2 hours one-time computation. The results are cached — optimization runs against the cached matrix.

---

## Output: Regional Weight Profiles

The optimization produces a weight profile per NERC region:

```json
{
    "region": "ERCOT",
    "method": "constrained_optimization",
    "n_eia_installations": 245,
    "n_random_comparisons": 245,
    "optimized_weights": {
        "solar_ghi": 0.12,
        "solar_slope": 0.14,
        "solar_aspect": 0.08,
        "solar_transmission": 0.22,
        "solar_road": 0.13,
        "solar_land_cover": 0.11,
        "solar_soil": 0.10,
        "solar_ej": 0.10
    },
    "default_weights": {
        "solar_ghi": 0.15,
        "solar_slope": 0.15,
        "solar_aspect": 0.10,
        "solar_transmission": 0.25,
        "solar_road": 0.12,
        "solar_land_cover": 0.10,
        "solar_soil": 0.08,
        "solar_ej": 0.05
    },
    "weight_changes": {
        "solar_transmission": {"from": 0.25, "to": 0.22, "reason": "ERCOT has dense grid — transmission proximity provides less differentiation than in WECC"},
        "solar_soil": {"from": 0.08, "to": 0.10, "reason": "Gulf Coast expansive clays create meaningful cost differentiation"},
        "solar_ej": {"from": 0.05, "to": 0.10, "reason": "Texas permitting increasingly considers EJ factors"}
    },
    "validation": {
        "pct_eia_high_default_weights": 0.467,
        "pct_eia_high_optimized_weights": 0.72,
        "mean_separation_default": 0.25,
        "mean_separation_optimized": 0.41
    },
    "academic_basis": "Weights constrained to ranges from Doorga et al. (2019), Al-Shammari et al. (2026). Optimization against EIA Form 860 installations within constrained range.",
    "calibrated_at": "2026-06-07"
}
```

### Storage

Store regional weight profiles in a new table:

```sql
CREATE TABLE regional_weight_profiles (
    region TEXT PRIMARY KEY,
    workflow_type TEXT NOT NULL DEFAULT 'solar_siting',
    weights JSONB NOT NULL,
    metadata JSONB NOT NULL,  -- n_eia, n_random, validation metrics, weight_changes, academic_basis
    calibrated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### NERC Region Lookup

To determine which region a location falls in, use a simple lookup table or bounding boxes. NERC region boundaries are published and relatively stable. Store as polygons in PostGIS:

```sql
CREATE TABLE nerc_regions (
    region TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    geometry GEOMETRY(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX idx_nerc_regions_geom ON nerc_regions USING GIST (geometry);
```

Query: `SELECT region FROM nerc_regions WHERE ST_Contains(geometry, ST_Point(lng, lat))`

---

## Integration with Scoring Pipeline

The solar scoring pipeline (solar_scoring_v2.py) currently uses default weights from the methodology repository. Update to:

1. Determine the location's NERC region
2. Look up the regional weight profile
3. If a profile exists for this region, use the optimized weights
4. If no profile exists (sparse data region), use the literature defaults
5. Document in the output which weight profile was used and why

The confidence report already shows per-criterion quality. Add a weight_profile section:

```json
{
    "weight_profile": {
        "region": "ERCOT",
        "method": "calibrated",
        "n_installations_in_calibration": 245,
        "note": "Weights calibrated against 245 EIA Form 860 installations in ERCOT region, constrained to ranges from Doorga et al. (2019) and Al-Shammari et al. (2026)."
    }
}
```

For regions using defaults:
```json
{
    "weight_profile": {
        "region": "NPCC",
        "method": "literature_default",
        "note": "Fewer than 20 EIA installations in this region. Using literature default weights from Doorga et al. (2019)."
    }
}
```

---

## Build Sequence

| Step | What | Time Estimate |
|---|---|---|
| 1 | Load NERC region boundaries into PostGIS | 30 min |
| 2 | Pre-compute criterion scores for all EIA installations (6,321 × 8 criteria) | 2-3 hours (one-time, cached) |
| 3 | Generate matched random samples per region | 30 min |
| 4 | Run constrained optimization per region | 10 min (fast — matrix operations on cached data) |
| 5 | Store regional weight profiles | 15 min |
| 6 | Update scoring pipeline to consume regional profiles | 30 min |
| 7 | Re-run Test 1 validation with regional weights | 30 min |

Step 2 is the bottleneck — scoring 6,321 EIA locations through the full pipeline. At ~10s per location serial, that's ~17 hours. Optimizations:
- Parallelize with asyncio (4 concurrent) = ~4-5 hours
- Use the criterion matrix approach: compute raw criterion values (not full score-v2) which avoids the composite scoring overhead. Each criterion value requires 1-2 API calls, not the full pipeline. Estimated: 3-5s per location × 6,321 = ~6-9 hours serial, ~2 hours with concurrency.
- Alternatively: sample 200 per region (up to 1,400 total) instead of all 6,321. This is statistically sufficient for optimization and takes ~4 hours serial.

### Recommended Approach for Step 2

Sample 100 EIA installations per region (up to 700 total) + 100 random per region (up to 700 total) = 1,400 locations. At 10s each serial = ~4 hours. With concurrency=2 (conservative to avoid API contention) = ~2 hours.

Pre-compute once, cache the criterion matrix, run optimization in seconds.

---

## Acceptance Criteria

1. NERC region boundaries loaded into PostGIS. Any US lat/lng maps to a NERC region.
2. Regional weight profiles generated for at least 5 of 7 NERC regions (WECC, ERCOT, SPP, MISO, SERC should all have >20 EIA installations).
3. Optimized weights are within the literature-supported bounds (weight_min <= w <= weight_max for every criterion).
4. Sum of weights = 1.0 for every regional profile.
5. Re-run Test 1 (5 EIA + 5 random per state, serial) with regional weights. Target: ≥50% High nationally (up from 24% with fixed weights).
6. EIA-vs-random mean separation improves in at least 4 of 5 test states.
7. Every scored output includes the weight_profile section documenting which weights were used and why.
8. Documentation: the regional weight profiles table includes academic_basis, weight_changes with reasons, and calibration metadata.

---

## What This Is NOT

This is not machine learning. The criteria are fixed by the academic literature. The weight ranges are fixed by the literature. The optimization finds the best weights WITHIN those fixed ranges using observed data. The output is interpretable (8 named weights), constrained (bounded by published research), and deterministic (same location always gets the same weights).

This is the equivalent of a surveyor adjusting their instrument calibration for local conditions using known reference points. The instrument (methodology) doesn't change. The calibration (weights) adapts to local conditions using ground truth (EIA installations).
