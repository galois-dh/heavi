# HEAVI WORKFLOW INTEGRATION SPEC
# Wire Hazard Assessment and Trade Area Through the Platform Architecture

## Context

The platform architecture (Phases 1-4) was built and validated for the solar_siting workflow:
- Phase 1: Data Repository (31 sources with availability checking)
- Phase 2: Methodology Repository (31 criteria across 3 workflows with data trees and academic citations)
- Phase 3: Data Selection Engine (tree traversal, confidence scoring, quality propagation)
- Phase 4: Solar Scoring Pipeline v2 (consumes selection engine, produces scored output with confidence + methodology)

The methodology_criteria table already has criteria seeded for hazard_assessment (10 criteria) and trade_area (7 criteria). The data_sources table has all sources referenced by those criteria. The select_data() function accepts any workflow_type.

What's missing: the actual scoring functions for hazard and trade area don't consume the data selection engine. They use hardcoded data source lookups without confidence scoring, data quality reporting, or methodology documentation from the platform architecture.

## What Needs to Change

### Reference Implementation

solar_scoring_v2.py is the reference. Every workflow refactor should follow the same pattern:

```python
async def score_[workflow](pool, latitude, longitude, **config):
    # 1. Call data selection engine
    selection = await select_data(pool, "[workflow_type]", latitude, longitude)
    
    # 2. Load methodology
    methodology = get_methodology_doc("[workflow_type]")
    
    # 3. Score each criterion using selected data from source_cache
    criterion_scores = {}
    for criterion in selection.criteria:
        if criterion.confidence > 0:
            score = compute_criterion_score(criterion, selection.source_cache)
            criterion_scores[criterion.criterion_id] = score
    
    # 4. Check exclusions (if applicable)
    exclusions = check_exclusions(selection)
    
    # 5. Compute composite score with methodology weights
    composite = weighted_composite(criterion_scores, methodology.weights)
    
    # 6. Return scored result with confidence + methodology
    return {
        "score": composite,
        "rating": rating_from_score(composite),
        "criteria_scores": criterion_scores,
        "exclusions": exclusions,
        "confidence": {
            "tier": selection.confidence_tier,
            "composite": selection.composite_confidence,
            "statement": selection.confidence_statement,
            "per_criterion": selection.criteria,
            "gaps": selection.gaps,
            "strongest_data": selection.strongest_data,
            "weakest_data": selection.weakest_data
        },
        "methodology": methodology
    }
```

---

## WORKFLOW 1: HAZARD ASSESSMENT

### Current State

Two separate scoring functions:
- wildfire_loss.py: assess_wildfire_loss() — logistic regression vulnerability model, queries FSim, LANDFIRE, 3DEP, NSI, DINS/FRAP directly
- flood_scoring.py: assess_flood_risk() — FEMA zone lookup → NSI match → HAZUS DDF → annualized loss, queries NFHL, NSI, 3DEP, HAZUS directly

Both bypass the data selection engine, produce no confidence scoring, and attach minimal methodology documentation.

### Target State

A new hazard_scoring_v2.py that:
1. Calls select_data("hazard_assessment", lat, lng) to determine available data and confidence
2. Runs wildfire scoring using data from the selection engine's source_cache
3. Runs flood scoring using data from the selection engine's source_cache
4. Produces a combined hazard assessment with per-peril scores and a composite confidence

### Criteria (from methodology_criteria, already seeded)

**Wildfire criteria (5):**
- wf_likelihood: USFS FSim burn probability → data tree: [usfs_fsim]
- wf_fuel_proximity: LANDFIRE distance to fuel → data tree: [landfire_fuels_canopy]
- wf_canopy: LANDFIRE canopy cover at buffer scales → data tree: [landfire_fuels_canopy]
- wf_slope: 3DEP slope → data tree: [usgs_3dep]
- wf_structure: NSI building type → data tree: [usace_nsi]

**Flood criteria (5):**
- fl_zone: FEMA NFHL flood zone → data tree: [fema_nfhl]
- fl_depth: multi-source computation (BFE + ground elev + FFH) → data tree: [fema_nfhl (component), usgs_3dep (component), usace_nsi (component), google_inundation_history (supplementary)]
- fl_historical: OpenFEMA + peak flow → data tree: [openfema_disasters, usgs_peak_flow]
- fl_hydrology: Google GRRR + NHDPlus + peak flow → data tree: [google_grrr, usgs_nhdplus, usgs_peak_flow]
- fl_building: NSI + HAZUS DDFs → data tree: [usace_nsi (component), hazus_ddfs (component)]

### Scoring Logic

**Wildfire scoring:** The existing logistic regression model (wildfire_loss.py) computes a damage probability from the 5 features. The refactored version should:
- Get the raw feature values from the source_cache (FSim likelihood, fuel distance, canopy cover, slope, building type)
- Apply the same logistic model: P(damage) = logistic(intercept + Σ beta_i × x_i)
- Compute annual risk = FSim_likelihood × P(damage) × replacement_value
- Use the same coefficients as the existing model (these were calibrated against DINS data)

**Flood scoring:** The existing HAZUS pipeline (flood_scoring.py) computes depth → damage → annualized loss. The refactored version should:
- Get flood zone + BFE from source_cache (NFHL)
- Get ground elevation from source_cache (3DEP)
- Get building data from source_cache (NSI)
- Compute depth = BFE - ground_elevation - first_floor_height
- Look up damage from HAZUS DDFs
- Compute annual loss = damage × annual_probability

**Combined hazard score:** Normalize wildfire and flood scores to 0-1 ranges and report both. Do NOT combine into a single number — they are independent perils. Report:
```json
{
    "wildfire": {"annual_risk_usd": 1234, "risk_tier": "High", "damage_probability": 0.67},
    "flood": {"annual_risk_usd": 567, "risk_tier": "Moderate", "flood_zone": "AE", "depth_ft": 2.3},
    "confidence": { ... per-criterion confidence from selection engine ... },
    "methodology": { ... from methodology repository ... }
}
```

### New Endpoint

POST /hazard/score-v2
- Accepts: latitude, longitude (or address)
- Returns: combined wildfire + flood assessment with confidence and methodology

Keep existing POST /wildfire-loss and POST /flood/risk endpoints for backward compatibility. The v2 endpoint is the new primary.

### Confidence Behavior

The hazard workflow's data trees include component relationships (fl_depth needs NFHL + 3DEP + NSI). The confidence computation should correctly handle:
- All components available → HIGH
- BFE missing (zone A without published BFE) → confidence drops per missing_confidence in the data tree
- NSI unavailable → cannot compute damage → fl_building and fl_depth degrade
- Google Inundation History (supplementary) → present enhances corroboration but absence doesn't degrade

For wildfire: if the location is outside Sonoma County (where the model was calibrated), the methodology documentation should note: "Wildfire vulnerability model calibrated on Sonoma County CAL FIRE DINS data. Application outside Sonoma County uses the same coefficients without local calibration."

---

## WORKFLOW 2: TRADE AREA

### Current State

trade_area_scoring.py: score_trade_area() — computes isochrones via ORS, intersects with Census ACS, counts POIs, applies Huff model. Queries Census API, ORS API, PostGIS POIs directly. No confidence scoring, no data selection engine.

### Target State

A new trade_area_scoring_v2.py that:
1. Calls select_data("trade_area", lat, lng) to determine available data and confidence
2. Computes trade area metrics using data from the selection engine's source_cache
3. Produces scored output with confidence and methodology

### Criteria (from methodology_criteria, already seeded)

- ta_population: Census ACS demographics → data tree: [census_acs]
- ta_competitive_gap: OSM POIs → data tree: [osm_pois, osm_pois_overpass]
- ta_income: Census ACS income → data tree: [census_acs]
- ta_daytime: LEHD daytime employment → data tree: [census_lehd, census_acs_commuter]
- ta_accessibility: ORS isochrones → data tree: [ors_isochrones]
- ta_complementary: OSM POIs → data tree: [osm_pois, osm_pois_overpass]
- ta_flood: FEMA NFHL → data tree: [fema_nfhl]

### Scoring Logic

The existing trade area scoring logic is sound — Huff gravity model, isochrone-based demographics, competitive density. The refactored version should:
- Use the data selection engine to determine which POI source to use (PostGIS cache vs Overpass on-demand)
- Use the data selection engine to determine which daytime population source to use (LEHD vs ACS commuter proxy)
- Apply the same Huff model and demographic aggregation
- Report confidence based on which data sources were actually used

### Confidence Behavior

Trade area confidence is primarily affected by:
- ta_daytime: LEHD (confidence 1.0) vs ACS commuter proxy (confidence 0.4) — major differentiation
- ta_competitive_gap / ta_complementary: PostGIS cache (confidence 1.0) vs Overpass on-demand (confidence 0.7)
- ta_accessibility: ORS isochrones are always available but rate-limited (500/day free tier)

For locations with LEHD loaded (currently Dallas only), daytime population uses authoritative block-level employment data. Everywhere else, it falls back to ACS commuter counts as a proxy. The confidence report should clearly show this distinction.

### New Endpoint

POST /trade-area/score-v2
- Accepts: latitude, longitude (or address), business_category, existing_locations (optional)
- Returns: trade area score with demographic profile, competitive analysis, confidence, and methodology

Keep existing POST /trade-area/score for backward compatibility.

---

## Web UI Updates

### /hazard page
Update to call POST /hazard/score-v2 instead of separate wildfire and flood endpoints.
Display:
- Wildfire risk tier + annual risk estimate
- Flood risk tier + annual risk estimate + flood zone
- Combined confidence tier (from data selection engine)
- Per-criterion quality breakdown (same format as /energy page)
- Data gaps prominently displayed
- Methodology documentation accessible

### /locations page
Update to call POST /trade-area/score-v2.
Display:
- Trade area score + rating
- Confidence tier
- Per-criterion quality showing which POI source and daytime source were used
- Data gaps
- Methodology documentation

---

## MCP Tool Updates

Update the MCP tools to use the v2 endpoints:
- wildfire_risk_assessment → calls POST /hazard/score-v2
- flood_risk_assessment → calls POST /hazard/score-v2
- trade_area_analysis → calls POST /trade-area/score-v2

The MCP tool responses should include the confidence tier and any data gaps so the AI agent can present them to the user.

---

## Acceptance Criteria

### Hazard
1. POST /hazard/score-v2 returns wildfire + flood scores for a Sonoma County address (wildfire-relevant)
2. POST /hazard/score-v2 returns wildfire + flood scores for a Houston address (flood-relevant)
3. Confidence report present with per-criterion quality for all 10 hazard criteria
4. Component confidence correctly computed for fl_depth (3 components)
5. Data gaps surfaced when sources are unavailable
6. Methodology documentation attached with academic citations (Finney, Scawthorn, etc.)

### Trade Area
7. POST /trade-area/score-v2 returns trade area score for a Dallas address (LEHD loaded → HIGH confidence for ta_daytime)
8. POST /trade-area/score-v2 returns trade area score for a Chicago address (LEHD not loaded → proxy used, MODERATE confidence for ta_daytime)
9. Confidence report shows which POI source was used (PostGIS vs Overpass)
10. Methodology documentation attached with citations (Huff, Suárez-Vega, etc.)

### Cross-workflow
11. GET /data-selection?workflow=hazard_assessment&lat=35.35&lng=-119.05 returns valid selection result
12. GET /data-selection?workflow=trade_area&lat=32.78&lng=-96.80 returns valid selection result
13. GET /methodology/hazard_assessment returns full methodology doc
14. GET /methodology/trade_area returns full methodology doc
15. /hazard web page displays results with confidence tier
16. /locations web page displays results with confidence tier
17. MCP tools return confidence tier in responses
