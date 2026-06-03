# HEAVI MULTI-GEOGRAPHY VALIDATION SPEC
# Pre-Investor Testing Protocol

## Purpose

Every validation metric in the platform is currently single-geography:
- Solar: 97.7% in Kern County only
- Wildfire: AUC 0.76 in Sonoma County only
- Flood: 16× discrimination in Lee County only
- Trade area: 96.7% in Dallas County only

Before showing investors, we need to know whether the methodologies generalize beyond their validation geographies. This spec defines exactly what to test, against what ground truth, and what the pass criteria are.

This is NOT about achieving perfect scores everywhere. It IS about knowing honestly where the methodology works, where it degrades, and why. An investor who asks "does this work in Texas?" deserves a grounded answer.

---

## TEST 1: SOLAR SITING — Multi-State EIA Validation

### Ground Truth
EIA Form 860 solar installations are already loaded nationally (6,321 operating PV plants in solar_eia_installations). These are real solar farms that were actually built — the strongest possible validation target.

### Test Protocol

Score EIA solar installations in 5 states outside California using POST /solar/score-v2:

| State | Why | Expected EIA Count (approx) |
|---|---|---|
| Texas | Largest US solar market outside CA. Different terrain, different grid. | 200+ |
| Arizona | High GHI, desert terrain, different environmental constraints. | 100+ |
| North Carolina | East coast, different land cover (forest/agriculture), different grid. | 150+ |
| Nevada | Desert, high GHI, BLM land issues, different grid topology. | 50+ |
| Florida | Flat, different soil (sandy/limestone), hurricane zone, different constraints. | 100+ |

For each state:
1. Query solar_eia_installations for all operating PV plants in that state (filter by state from the loaded data)
2. Sample 30 installations per state (random seed 42, or all if fewer than 30)
3. Score each installation using POST /solar/score-v2
4. Also score 30 random non-installation locations in the same state for comparison (random agricultural/rural land)
5. Report:
   - Percentage of EIA installations scoring High (≥0.70)
   - Mean score for EIA installations vs mean score for random locations
   - Score separation (do real installations score meaningfully higher than random?)
   - Confidence tier distribution (how many HIGH vs MODERATE vs LOW?)
   - Which criteria drive the scores (is it still transmission-dominant, or do different states have different drivers?)
   - Any installations scoring Low — why? (these reveal methodology problems)

### Pass Criteria
- ≥60% of EIA installations score High across all 5 states (lower bar than Kern's 97.7% because weights were calibrated for Kern)
- EIA installations score higher than random locations on average in every state (mean separation > 0)
- At least 3 of 5 states show ≥70% High rate
- If a state shows <50% High rate, investigate: is it a weight calibration issue (e.g., transmission weight too high for states with distributed grid) or a data gap?

### What This Tells Investors
"We validated solar siting against real EIA installations across 5 states. [X]% score High nationally. The methodology generalizes from Kern County with [these caveats]."

If the methodology DOESN'T generalize (e.g., Texas installations score poorly because the transmission weight is wrong for ERCOT's grid structure), that's a finding too — it means the weights need to be geography-adaptive, which is a product feature (customer configuration profiles).

---

## TEST 2: WILDFIRE RISK — Multi-County CAL FIRE Validation

### Ground Truth
CAL FIRE DINS (Damage Inspection) records are loaded for Sonoma County. For multi-geography validation, we need DINS or equivalent damage records from other fire events.

### Available Ground Truth
- CAL FIRE DINS covers all California fires. The existing pipeline matched DINS to NSI structures within fire perimeters (FRAP).
- Other California counties with significant WUI fire events: San Diego (2003 Cedar, 2007 Witch Creek), Los Angeles (2018 Woolsey), Butte (2018 Camp Fire), Ventura (2017 Thomas).

### Test Protocol

For each additional fire event:
1. Download DINS records for the fire (if not already loaded — DINS is statewide)
2. Download FRAP perimeter for the fire
3. Match DINS to NSI structures within the perimeter (same pipeline as Sonoma)
4. Score each structure using the existing wildfire vulnerability model
5. Compute AUC-ROC on the held-out fire

| Fire | County | Year | Expected Structures | Notes |
|---|---|---|---|---|
| Camp Fire | Butte | 2018 | 10,000+ | Near-total destruction of Paradise — extreme event |
| Woolsey Fire | LA/Ventura | 2018 | 3,000+ | Coastal WUI, different terrain than Sonoma |
| Cedar Fire | San Diego | 2003 | 2,000+ | Older event, different era of development |
| Thomas Fire | Ventura | 2017 | 1,000+ | Largest CA fire at the time |

### Pass Criteria
- AUC-ROC ≥ 0.65 for at least 3 of 4 additional fires (lower than Sonoma's 0.76 because the model was trained on Sonoma fires)
- If AUC drops below 0.60 for any fire, investigate: is it a terrain/vegetation difference, a construction era difference, or a model limitation?
- Discrimination ratio (predicted risk in damaged vs undamaged structures) ≥ 3× for all fires

### What This Tells Investors
"The wildfire model trained on Sonoma County fires achieves AUC [X] when tested against [N] additional California fires. The methodology generalizes [with these caveats]."

### Limitation
This validation is California-only. CAL FIRE DINS doesn't exist outside California. National wildfire validation would require FEMA Individual Assistance records or NIFC damage data — a future enhancement.

---

## TEST 3: FLOOD RISK — Multi-Event NFIP Validation

### Ground Truth
OpenFEMA NFIP claims (already loaded and verified in Phase A). We validated against Hurricane Ian (Lee County, FL). Additional validation events:

### Test Protocol

| Event | Geography | Year | Why |
|---|---|---|---|
| Hurricane Harvey | Harris County, TX | 2017 | Already tested — showed 0.13 discrimination (pluvial limitation). RE-TEST to confirm the pluvial mismatch is properly documented. |
| Hurricane Sandy | NY/NJ coast | 2012 | Coastal flood event. Different from riverine. Tests V-zone performance. |
| Hurricane Florence | Robeson County, NC | 2018 | Riverine flooding. Should perform better than Harvey. |
| 2016 Louisiana Flood | East Baton Rouge, LA | 2016 | Extreme rainfall + riverine. Partial pluvial. |

For each event:
1. Query OpenFEMA NFIP claims for the county during the event period
2. Identify tracts with high claim density vs tracts with low/no claims
3. Score NSI structures in both claim-heavy and claim-light tracts using the flood module
4. Compute discrimination ratio (mean predicted risk in claim-heavy vs claim-light tracts)
5. Compute Spearman rank correlation between predicted risk and actual claims by tract

### Pass Criteria
- Discrimination ratio ≥ 5× for at least 2 of 4 events
- Hurricane Harvey: discrimination ratio remains low (<2×) — confirming the documented pluvial limitation
- Hurricane Sandy: discrimination ratio ≥ 5× (coastal flood, NFHL V-zones should discriminate well)
- Spearman correlation ≥ 0.3 for at least 2 events

### What This Tells Investors
"The flood model discriminates well for riverine and coastal flooding (Sandy: [X]×, Florence: [X]×). It does not capture pluvial flooding (Harvey: [X]×), which is documented in every output. [X]% of US flood risk is fluvial/coastal, so the model covers the majority of events."

---

## TEST 4: TRADE AREA — Multi-Metro Starbucks Validation

### Ground Truth
OSM POIs contain Starbucks locations nationally (name ILIKE '%starbucks%'). Professional site selection teams chose these locations.

### Test Protocol

Score Starbucks locations in 4 metros outside Dallas:

| Metro | Why |
|---|---|
| Chicago, IL | Dense urban, different competitive landscape |
| Phoenix, AZ | Suburban sprawl, different demographics |
| Atlanta, GA | Southeast, different growth patterns |
| Seattle, WA | Starbucks HQ market, saturated |

For each metro:
1. Query OSM POIs via Overpass for Starbucks locations in the metro county
2. Sample 20 Starbucks + 20 random locations (seed 42)
3. Score each using the trade area module with business_category="coffee_shop"
4. Report: % of Starbucks scoring Strong, mean Starbucks score vs mean random score

### Pass Criteria
- ≥70% of Starbucks score Strong in at least 3 of 4 metros
- Starbucks mean score > random mean score in every metro (positive separation)
- If a metro shows <50% Strong, investigate: is it a competitive density issue (too many coffee shops = lower competitive gap score)?

### Note on Data Availability
Trade area analysis requires ORS isochrone API calls (3 per location × 40 locations × 4 metros = 480 calls). Free tier is 500/day. This test consumes most of a day's ORS budget. Batch across 2 days if needed.

---

## TEST 5: DATA SELECTION ENGINE — National Behavior Verification

### Purpose
Verify that the data selection engine correctly identifies available data and computes accurate confidence levels across diverse US geographies.

### Test Protocol

Run select_data("solar_siting", lat, lng) for 50 locations (seed 42) spread across all US climate zones and land types:

```python
import random
random.seed(42)
test_locations = []
# 50 points across CONUS
for i in range(50):
    lat = round(random.uniform(26.0, 47.5), 4)
    lng = round(random.uniform(-123.0, -70.0), 4)
    test_locations.append({"id": f"VAL-{i:03d}", "lat": lat, "lng": lng})
```

For each location report:
- State (reverse geocode)
- Composite confidence + tier
- Which source was selected for each criterion
- Whether any PostGIS-cached sources were found (NWI, substations, POIs)
- Overpass fallback usage count
- Any API failures or timeouts

### Pass Criteria
- ≥45 of 50 locations return a valid selection result (some will be in water)
- Confidence varies across locations (not all the same value)
- PostGIS cache hits occur for locations in loaded states (CA for NWI, 6 states for substations)
- Overpass fallback fires for locations outside loaded states
- No silent failures — every unavailable source is explicitly logged in the selection result
- API timeout rate < 10% across all 50 locations

### What This Tells Investors
"The data selection engine works nationally. It correctly identifies the best available data at each location and honestly reports confidence based on data quality. [X]% of US locations get MODERATE confidence due to NWI wetland data limitations, which we surface transparently."

---

## TEST 6: END-TO-END PRODUCT WORKFLOW

### Purpose
Verify the full user workflow works for each product entry.

### Test Protocol

**Heavi Energy (/energy):**
1. Upload a CSV with 10 coordinates across 5 states (2 per state: TX, AZ, NC, NV, FL)
2. Verify all 10 are scored with the v2 pipeline
3. Verify each result includes: score, rating, confidence tier, per-criterion breakdown, methodology documentation, data gaps
4. Verify at least some results are Excluded (environmental or terrain constraints)
5. Verify the confidence statement names specific degraded criteria

**Heavi Hazard (/hazard):**
1. Enter 5 addresses (one per hazard profile): coastal FL, WUI CA, floodplain TX, urban NY, rural KS
2. Verify wildfire + flood scores returned for each
3. Verify methodology documentation attached
4. Verify risk factors are plausible (coastal FL = high flood, WUI CA = high wildfire)

**Heavi Locations (/locations):**
1. Enter 3 addresses in different metros
2. Verify trade area scores returned with competitive analysis
3. Verify methodology documentation attached

### Pass Criteria
- All three product entries load and accept input
- Scored results display with confidence tier at same visual weight as score
- Data gaps displayed as first-class output
- Methodology documentation accessible from every result
- No insurance language visible anywhere in the UI

---

## REPORTING

After all tests complete, produce a validation summary document:

```
HEAVI MULTI-GEOGRAPHY VALIDATION SUMMARY
Date: [date]

SOLAR SITING
  Kern County (original):  97.7% High, 130 EIA installations
  Texas:                   [X]% High, [N] EIA installations
  Arizona:                 [X]% High, [N] EIA installations
  North Carolina:          [X]% High, [N] EIA installations
  Nevada:                  [X]% High, [N] EIA installations
  Florida:                 [X]% High, [N] EIA installations
  National aggregate:      [X]% High across [N] total installations
  
  Weight sensitivity: [notes on whether transmission dominance holds outside CA]
  
WILDFIRE RISK
  Sonoma County (original): AUC 0.76, 1,420 held-out structures
  Camp Fire (Butte):        AUC [X], [N] structures
  Woolsey Fire (LA/Vent):   AUC [X], [N] structures
  Cedar Fire (San Diego):   AUC [X], [N] structures
  Thomas Fire (Ventura):    AUC [X], [N] structures
  
FLOOD RISK
  Hurricane Ian (original): 16× discrimination, Lee County FL
  Hurricane Harvey:         [X]× discrimination, Harris County TX [expected low — pluvial]
  Hurricane Sandy:          [X]× discrimination, NY/NJ coast
  Hurricane Florence:       [X]× discrimination, Robeson County NC
  Louisiana 2016:           [X]× discrimination, East Baton Rouge LA

TRADE AREA
  Dallas (original):    96.7% Starbucks Strong
  Chicago:              [X]% Starbucks Strong
  Phoenix:              [X]% Starbucks Strong
  Atlanta:              [X]% Starbucks Strong
  Seattle:              [X]% Starbucks Strong

DATA SELECTION ENGINE
  50 random locations: [X]/50 valid, [X] distinct confidence values
  Mean composite confidence: [X]
  PostGIS cache hit rate: [X]%
  Overpass fallback rate: [X]%
  API failure rate: [X]%

KNOWN LIMITATIONS (updated post-validation)
  [List any new limitations discovered during multi-geography testing]
  [Update severity ratings if findings change the assessment]
```

This summary becomes part of the technical diligence package and informs how validation metrics are presented to investors.

---

## EXECUTION NOTES

### ORS API Budget
Trade area validation consumes ~480 ORS isochrone requests. Free tier = 500/day. Run trade area tests on a dedicated day or across 2 days.

### PVWatts API Budget
Solar validation: 5 states × 60 locations = 300 PVWatts calls. No rate limit concern (PVWatts is generous).

### Compute Time
Each solar score-v2 call takes 5-15 seconds (multiple API calls + PostGIS queries). 300 solar locations ≈ 25-75 minutes.
Each flood assessment takes 3-5 seconds. 200 flood locations ≈ 10-17 minutes.
Each wildfire assessment requires pre-loading DINS + FRAP for the fire event. Loading is the slow step; scoring is fast once loaded.

### Data Loading Requirements
- Wildfire multi-geography: need to load DINS records for Butte, LA/Ventura, San Diego, Ventura counties. DINS is statewide — may already be partially loaded. FRAP perimeters for each fire event.
- Everything else uses nationally available data or on-demand APIs.
