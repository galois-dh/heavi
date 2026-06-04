# HEAVI INSUFFICIENT DATA HANDLING SPEC
# Stop Producing Misleading Outputs When Critical Data Is Missing

## Problem

The hazard module returns "$0/yr" and "LOW" risk for a Sonoma County wildfire assessment because FSim (burn probability) data isn't loaded nationally. The system computes: annual_risk = FSim_probability × damage × value = 0 × 100% × $X = $0. This is mathematically correct but factually wrong — Sonoma County is high wildfire risk. The $0 and LOW rating actively mislead the user.

This same problem can occur anywhere in the platform: when a critical data source is missing, the scoring pipeline fills in zero or a default, computes a result, and presents it as if the assessment was completed. The confidence system correctly flags the gap (MODERATE 65%, 3 data gaps listed), but the headline number ($0/yr LOW) contradicts the confidence warning.

The rule: **if the data necessary to compute a reliable estimate is missing, do NOT produce a numeric estimate.** Show "Cannot assess" instead of a misleading number.

## Where This Can Occur

### Hazard — Wildfire
**Critical sources:** usfs_fsim (burn probability), landfire_fuels_canopy (fuel proximity, canopy cover)
**Current behavior when missing:** annual_risk = $0, risk_tier = "LOW", damage_probability = computed from building features alone
**Correct behavior:** wildfire_available = false, annual_risk = null, risk_tier = "CANNOT ASSESS", message = "Wildfire likelihood data (FSim) is not available at this location. Wildfire risk cannot be estimated without burn probability data."

### Hazard — Flood
**Critical sources:** fema_nfhl (flood zone + BFE), usgs_3dep (ground elevation), usace_nsi (building data)
**When missing:** If NFHL returns no zone or Zone D ("undetermined"), the flood risk should NOT be reported as $0/LOW. It should report "Flood zone undetermined — FEMA has not mapped this area."
**If 3DEP is missing:** depth cannot be computed. Report "Ground elevation unavailable — flood depth cannot be estimated."
**If NSI is missing:** building characteristics unknown. Report "Building data unavailable — damage estimate cannot be computed."

### Energy — Solar
**Critical sources:** nrel_pvwatts_v8 (solar resource — if this is down, the entire solar assessment is invalid)
**When missing:** If PVWatts fails, do NOT report a score based on the remaining criteria. Report "Solar resource data unavailable — suitability cannot be scored."
**For exclusion criteria:** If a critical exclusion source is unavailable (e.g., NWI wetlands), the current behavior (proxy + confidence degradation) is correct — the assessment IS produced but with reduced confidence. This is different from a scored criterion being completely missing.

### Trade Area
**Critical sources:** ors_isochrones (drive-time polygons — without this, the trade area cannot be delineated)
**When missing:** If ORS fails (rate limit, timeout), do NOT report a trade area score. Report "Drive-time isochrone unavailable — trade area cannot be delineated."
**For demographic sources:** If Census ACS is down, population and income cannot be scored. If LEHD is unavailable, the proxy (ACS commuter) is acceptable with confidence degradation — this case is already handled correctly.

## Implementation

### Define Critical Sources Per Workflow

Each workflow has a set of data sources without which the assessment cannot be meaningfully computed. These are distinct from "nice to have" sources where proxy or degraded data is acceptable.

```python
CRITICAL_SOURCES = {
    "solar_siting": {
        # PVWatts is THE solar resource assessment. Without it, there's no energy estimate.
        "nrel_pvwatts_v8": {
            "criterion": "solar_ghi",
            "message": "Solar resource data (NREL PVWatts) unavailable. Suitability cannot be scored."
        }
    },
    "hazard_assessment": {
        # FSim is THE wildfire hazard layer. Without burn probability, wildfire risk is unknowable.
        "usfs_fsim": {
            "criterion": "wf_likelihood",
            "peril": "wildfire",
            "message": "Wildfire burn probability data (USFS FSim) unavailable at this location. Wildfire risk cannot be estimated."
        },
        # LANDFIRE provides fuel and canopy — secondary but important. If FSim AND LANDFIRE are both missing,
        # the wildfire assessment has no inputs at all.
        "landfire_fuels_canopy": {
            "criterion": ["wf_fuel_proximity", "wf_canopy"],
            "peril": "wildfire",
            "message": "Fuel and canopy data (LANDFIRE) unavailable at this location."
        },
        # NFHL is THE flood hazard source. Without it, flood zone is unknown.
        "fema_nfhl": {
            "criterion": "fl_zone",
            "peril": "flood",
            "message": "FEMA flood zone data unavailable at this location. Flood risk cannot be determined."
        },
        # 3DEP is needed for depth computation. Without ground elevation, depth is unknowable.
        "usgs_3dep": {
            "criterion": "fl_depth",
            "peril": "flood",
            "message": "Ground elevation data (USGS 3DEP) unavailable. Flood depth cannot be estimated."
        }
    },
    "trade_area": {
        # ORS isochrones define the trade area boundary. Without them, there is no trade area.
        "ors_isochrones": {
            "criterion": "ta_accessibility",
            "message": "Drive-time isochrone service unavailable. Trade area cannot be delineated."
        }
    }
}
```

### Scoring Pipeline Changes

In each scoring v2 function, BEFORE computing a result, check if critical sources are available:

```python
async def score_hazard_v2(pool, latitude, longitude):
    selection = await select_data(pool, "hazard_assessment", latitude, longitude)
    
    # Check critical sources for each peril
    wildfire_assessable = True
    flood_assessable = True
    critical_gaps = []
    
    for source_id, config in CRITICAL_SOURCES["hazard_assessment"].items():
        criterion_ids = config["criterion"] if isinstance(config["criterion"], list) else [config["criterion"]]
        for crit_id in criterion_ids:
            crit_selection = find_criterion(selection, crit_id)
            if crit_selection and crit_selection.confidence == 0.0:
                peril = config.get("peril")
                if peril == "wildfire":
                    wildfire_assessable = False
                elif peril == "flood":
                    flood_assessable = False
                critical_gaps.append({
                    "source": source_id,
                    "criterion": crit_id,
                    "message": config["message"]
                })
    
    # Compute wildfire ONLY if assessable
    if wildfire_assessable:
        wildfire_result = compute_wildfire(selection.source_cache, ...)
    else:
        wildfire_result = {
            "available": False,
            "annual_risk_usd": None,  # NOT $0 — null means "cannot assess"
            "risk_tier": "CANNOT ASSESS",  # NOT "LOW"
            "damage_probability": None,
            "message": "Wildfire risk cannot be assessed at this location due to missing data.",
            "missing_sources": [g for g in critical_gaps if g.get("source") in ("usfs_fsim", "landfire_fuels_canopy")]
        }
    
    # Same for flood
    if flood_assessable:
        flood_result = compute_flood(selection.source_cache, ...)
    else:
        flood_result = {
            "available": False,
            "annual_risk_usd": None,
            "risk_tier": "CANNOT ASSESS",
            "flood_zone": None,
            "depth_ft": None,
            "message": "Flood risk cannot be assessed at this location due to missing data.",
            "missing_sources": [g for g in critical_gaps if g.get("source") in ("fema_nfhl", "usgs_3dep")]
        }
    
    return {
        "wildfire": wildfire_result,
        "flood": flood_result,
        "confidence": selection.confidence_tier,
        ...
    }
```

### Web UI Changes

When a peril or assessment returns `available: false`:

**Instead of:**
```
Wildfire    LOW
$0/yr
damage prob 100%
```

**Show:**
```
Wildfire    CANNOT ASSESS
─────────────────────────
Wildfire risk cannot be assessed 
at this location. Critical data 
sources are unavailable:

• FSim burn probability (usfs_fsim)
• LANDFIRE fuel/canopy data

This does NOT mean the property 
has low wildfire risk.
```

The "CANNOT ASSESS" badge should be visually distinct — not green (LOW), not red (HIGH), but a neutral color (gray or muted amber) with an info icon.

### For Solar (Energy)

If PVWatts is unavailable:
```
SITE SCORE    CANNOT ASSESS
─────────────────────────────
Solar resource data unavailable. 
Suitability cannot be scored 
without energy production estimates.
```

Do NOT show a partial score based on terrain/transmission/exclusions only — those criteria alone don't tell you if a site is suitable for solar.

### For Trade Area (Locations)

If ORS isochrones fail:
```
TRADE AREA    CANNOT ASSESS
─────────────────────────────
Drive-time isochrone service 
unavailable. Trade area cannot 
be delineated without catchment 
boundary.
```

## Confidence Tier Update

Add a new confidence tier below INSUFFICIENT:

| Composite Confidence | Tier | Output Language |
|---|---|---|
| ≥ 0.85 | HIGH | "Based on authoritative data for all major criteria." |
| 0.65 – 0.84 | MODERATE | "Uses proxy or partial data for [N] criteria." |
| 0.40 – 0.64 | LOW | "Significant data gaps affecting [N] criteria." |
| 0.01 – 0.39 | INSUFFICIENT | "Insufficient data for a reliable assessment." |
| 0.0 (critical source missing) | CANNOT ASSESS | "Critical data sources unavailable. Assessment cannot be produced." |

When confidence = CANNOT ASSESS, the scoring pipeline should NOT produce numeric outputs. The entire response structure changes from "scored result with quality caveats" to "cannot assess with explanation."

## Acceptance Criteria

1. Sonoma County wildfire (38.4405, -122.7144): returns wildfire.available=false, wildfire.risk_tier="CANNOT ASSESS", wildfire.annual_risk_usd=null (NOT $0)
2. Sonoma County flood: returns flood results normally (NFHL IS available there — zone X is a real answer)
3. Web UI for CANNOT ASSESS perils shows the explanatory message, NOT $0 or LOW
4. CANNOT ASSESS badge is visually distinct (gray/amber, not green or red)
5. Houston flood (if NFHL is available): returns normal flood assessment, not CANNOT ASSESS
6. Solar scoring: if PVWatts were to fail, returns CANNOT ASSESS instead of a partial score (test by temporarily disabling the PVWatts call)
7. Trade area: if ORS were to fail, returns CANNOT ASSESS instead of a partial score
8. The confidence_statement for CANNOT ASSESS results says "Critical data sources unavailable" and names which sources are missing
9. Existing assessments that DO have all critical data continue to work exactly as before — no regression
