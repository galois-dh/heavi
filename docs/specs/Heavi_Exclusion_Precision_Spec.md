# HEAVI EXCLUSION PRECISION SPECIFICATION
# Investigating and Fixing False Exclusions of Real Solar Installations

## Problem

The weight adaptation validation (Test 1) found that 48% of EIA Form 860 solar installations (12 of 25 sampled) are flagged as Excluded by the current exclusion criteria. Since these are real, operating solar farms, the exclusion logic is either too aggressive, the data matching is imprecise, or both.

This matters because: if the platform excludes locations where solar was actually built, the product is giving wrong answers. An excluded location means "do not build here" — but someone DID build there. Every false exclusion is a false negative that undermines credibility.

## Investigation Steps

### Step 1: Diagnose Each Excluded EIA Installation

For every EIA installation that scored "Excluded" in the Test 1 results (docs/validation/raw/test1_solar_multistate.json), determine:

1. Which exclusion criterion fired (excl_protected, excl_wetlands, excl_flood, excl_steep, excl_urban)
2. What specific data triggered it:
   - For excl_protected: what PAD-US feature? What GAP status code? What designation name? (National park vs BLM land vs conservation easement vs state park)
   - For excl_urban: what NLCD class? (21 = Open Space, 22 = Low Intensity, 23 = Medium, 24 = High)
   - For excl_flood: what FEMA zone? (AE, A, VE, X)
   - For excl_steep: what was the computed slope? How many sample points exceeded 15%?
   - For excl_wetlands: which wetland source and classification?
3. The EIA plant name, capacity, and operator (from solar_eia_installations) — this provides context about what kind of installation it is

Report as a table:
| EIA Plant | State | Capacity MW | Exclusion Criterion | Specific Trigger | Assessment: True Exclusion or False Positive |

### Step 2: Categorize False Positives

Group the false positives by root cause:

**Category A: Coordinate precision.**
EIA Form 860 coordinates are self-reported plant centroids. A large solar farm (500+ acres) may have a centroid that falls in an adjacent parcel — the centroid might be in a protected area or urban land while the actual panels are on agricultural land next door. 
- Diagnostic: check if the EIA coordinate is within 500m of the PAD-US/urban boundary. If yes, likely a coordinate precision issue.
- Fix approach: buffer the query point by 200m and check if ANY non-excluded land exists within the buffer. If the point is on the edge of an exclusion zone, classify as "boundary proximity" rather than hard exclusion.

**Category B: Overly broad exclusion category.**
PAD-US includes multiple GAP status levels:
- GAP 1: Managed for biodiversity, disturbance events NOT permitted (wilderness areas, nature preserves) — HARD EXCLUSION
- GAP 2: Managed for biodiversity, disturbance events SUPPRESSED (national parks, most wildlife refuges) — HARD EXCLUSION  
- GAP 3: Managed for multiple uses, some extractive use allowed (national forests, BLM, state forests) — CONDITIONAL: some allow solar with permits
- GAP 4: No known mandate for protection (private land with conservation easement, DOD land) — CONDITIONAL: many allow solar

The current exclusion treats ALL PAD-US overlap as hard exclusion. This is too aggressive — GAP 3 and GAP 4 lands frequently allow solar development with appropriate permitting. Many of the largest US solar farms are on BLM land (GAP 3).
- Fix approach: Only hard-exclude GAP 1 and GAP 2. For GAP 3 and GAP 4, flag as "conditional — verify permitted use" rather than exclude.

For NLCD urban classes:
- Class 21 (Developed, Open Space): parks, golf courses, large-lot residential. Solar CAN be built here.
- Class 22 (Developed, Low Intensity): single-family housing, light commercial. Solar unlikely but not impossible (commercial rooftop, distributed).
- Class 23 (Developed, Medium Intensity): multi-family, commercial strips. Generally not suitable for utility-scale.
- Class 24 (Developed, High Intensity): CBD, industrial. Not suitable for utility-scale.

The current exclusion may treat all classes 21-24 as excluded. This is too aggressive — Class 21 (Open Space) should not be a hard exclusion.
- Fix approach: Only hard-exclude NLCD classes 23-24. Flag class 21-22 as "developed context — verify zoning" rather than exclude.

For FEMA flood zones:
Solar installations CAN operate in flood zones. Flood zone presence affects permitting and may increase insurance costs, but it is NOT a fatal flaw for solar development. Many real solar farms are in flood-prone areas.
- Fix approach: Downgrade from hard exclusion to a scored penalty. excl_flood becomes a scored criterion (deduction) rather than a binary exclusion. Or keep as exclusion only for V zones (coastal high hazard) and remove for A/AE zones.

**Category C: Threshold too aggressive.**
The steep slope threshold of 15% may be too low for some terrain types. Solar can be built on slopes up to 20-25% with appropriate racking systems (single-axis trackers on slopes are common).
- Fix approach: Raise default threshold from 15% to 20%. Or make it configurable with 15% as conservative and 20% as permissive.

### Step 3: Implement Fixes

Based on the diagnosis, implement the following changes to the exclusion logic in solar_scoring_v2.py:

**PAD-US refinement:**
```python
# Query PAD-US and get GAP status
# GAP 1-2: hard exclusion (wilderness, nature preserve, national park)
# GAP 3-4: advisory only ("protected land — verify permitted use with managing agency")
if gap_status in (1, 2):
    excluded = True
    reason = f"GAP {gap_status} protected area: {designation_name} — biodiversity management, no development permitted"
elif gap_status in (3, 4):
    excluded = False  # NOT a hard exclusion
    advisory = f"GAP {gap_status} managed land: {designation_name} — solar may be permitted with appropriate approvals. Verify with {managing_agency}."
```

**NLCD refinement:**
```python
# Only hard-exclude high-intensity developed (23-24)
# Open space (21) and low-intensity (22) get advisory, not exclusion
if nlcd_class in (23, 24):
    excluded = True
    reason = f"NLCD class {nlcd_class} ({nlcd_description}) — dense development incompatible with utility-scale solar"
elif nlcd_class in (21, 22):
    excluded = False
    advisory = f"NLCD class {nlcd_class} ({nlcd_description}) — developed context, verify zoning permits solar"
```

**FEMA flood zone refinement:**
```python
# V zones (coastal high hazard): hard exclusion
# A/AE zones: scored penalty, not exclusion
# X zones: no constraint
if zone_prefix == 'V':
    excluded = True
    reason = f"FEMA Zone {zone} — coastal high hazard, wave action risk incompatible with ground-mount solar"
elif zone_prefix == 'A':
    excluded = False
    penalty = 0.15  # scored deduction applied to composite
    advisory = f"FEMA Zone {zone} — 100-year floodplain. Solar development possible with elevated mounting and appropriate permitting. Insurance costs may be higher."
```

**Slope threshold:**
```python
# Raise from 15% to 20% per literature review
# Many studies use 10° (~17.6%) or 20° (~36.4%)
SLOPE_EXCLUSION_THRESHOLD = 20.0  # percent, was 15.0
```

### Step 4: Update Methodology Documentation

For each exclusion refinement, update the methodology_criteria table:
- excl_protected: update exclusion_threshold from "any overlap" to "GAP 1-2 overlap only"
- excl_urban: update exclusion_threshold from "NLCD 21-24" to "NLCD 23-24"
- excl_flood: change criterion_type from "exclusion" to "scored" with weight 0.05 and negative scoring for A/AE zones
- excl_steep: update exclusion_threshold from ">15%" to ">20%"

Add academic rationale:
- PAD-US GAP refinement: "Per USGS PAD-US documentation, GAP 3-4 lands allow multiple uses including energy development with appropriate permitting. Major US solar installations exist on BLM (GAP 3) land."
- NLCD refinement: "Hernandez et al. (2015) excluded developed land but did not differentiate by intensity class. Class 21 (Open Space) includes land uses compatible with solar (parks, golf courses, institutional campuses)."
- Flood zone refinement: "Solar PV installations can operate in SFHA zones with elevated mounting. FEMA permits development in A/AE zones with appropriate floodplain development permits. Only V zones (coastal high hazard with wave action) are incompatible with ground-mount solar."
- Slope refinement: "Literature threshold ranges from 3% (Hernandez et al. 2015, conservative) to 20° (some international studies). 20% (11.3°) is moderate and accommodates single-axis tracker installations on rolling terrain."

### Step 5: Re-run Validation

After implementing fixes, re-run Test 1 (5 EIA + 5 random per state, 5 states, serial) with regional weights AND refined exclusions.

Report:
- How many EIA installations are still Excluded vs the previous 12/25
- % High among all EIA installations (was 40%, target ≥50%)
- % High among non-excluded EIA installations (was 77%)
- Whether EIA-vs-random separation is maintained or improved

### Step 6: Update Confidence Logic

If excl_flood changes from exclusion to scored criterion:
- Add it to the scored criteria with weight 0.05
- Update the confidence formula: one fewer exclusion criterion in the exclusion penalty denominator
- Re-verify the confidence tier distribution

## Acceptance Criteria

1. Diagnostic table produced for all excluded EIA installations with specific trigger data
2. Each false positive categorized by root cause (coordinate precision, broad category, aggressive threshold)
3. PAD-US exclusion refined to GAP 1-2 only, with GAP 3-4 as advisory
4. NLCD exclusion refined to classes 23-24 only, with 21-22 as advisory
5. Flood zone exclusion converted to scored penalty for A/AE zones, hard exclusion only for V zones
6. Slope threshold raised to 20%
7. Methodology documentation updated with academic rationale for each refinement
8. Test 1 re-run shows ≥50% High nationally with regional weights + refined exclusions
9. EIA-vs-random separation maintained or improved in all 5 states

## What This Is NOT

This is not weakening exclusions to pass a test. GAP 3-4 lands genuinely allow solar development — BLM solar farms are among the largest in the US. NLCD class 21 genuinely includes land compatible with solar. A/AE flood zones genuinely permit solar with elevated mounting. The refinements align the exclusion logic with real-world permitting practice, not with a desire to improve a metric.
