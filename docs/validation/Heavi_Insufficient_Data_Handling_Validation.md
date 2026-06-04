# HEAVI INSUFFICIENT DATA HANDLING — VALIDATION SUMMARY

**Date:** 2026-06-08
**Spec:** [`Heavi_Insufficient_Data_Handling_Spec.md`](../specs/Heavi_Insufficient_Data_Handling_Spec.md)

Stops the platform from producing misleading $0/LOW outputs when critical data is
missing — it returns **CANNOT ASSESS** instead.

## Key interaction with the data-tree completeness work

CANNOT ASSESS now fires only when a criterion's **entire data tree is exhausted**
(selection confidence 0.0 = no tree node available), or when the critical value is
genuinely unobtainable at scoring time — NOT merely when the primary source is
missing. Two of the spec's literal expectations are therefore **superseded** by
the completed fallback chains (this is the correct, intended behavior):

- **AC1** (Sonoma wildfire): FSim is missing, but the **NIFC fallback** makes
  wf_likelihood assessable → returns a real HIGH estimate, *not* CANNOT ASSESS.
- **AC7** (ORS down): the **euclidean_buffer fallback** delineates the trade area
  → degraded result (confidence 0.3), *not* CANNOT ASSESS.

The CANNOT ASSESS mechanism is verified to fire when a tree IS truly exhausted.

## Acceptance criteria

| # | Criterion | Result |
|---|---|---|
| 1 | Sonoma wildfire → CANNOT ASSESS, null risk | **Superseded** — now assessable via NIFC (HIGH, non-null). Mechanism verified: NIFC-API-failure → wildfire CANNOT ASSESS, risk_tier="CANNOT ASSESS", annual_risk=null, missing_sources=["nifc_fire_perimeters"]. |
| 2 | Sonoma flood returns normally (zone X) | **PASS** (available, LOW, zone X) |
| 3 | Web UI shows the explanatory message, not $0/LOW | **PASS** (browser: message + named sources + "does NOT mean low risk", no $0) |
| 4 | CANNOT ASSESS badge visually distinct (gray/amber) | **PASS** (browser: gray badge + ⓘ icon, not green/red; map markers gray via `#9ca3af`) |
| 5 | Houston flood returns normally | **PASS** (available, LOW, zone X) |
| 6 | Solar → CANNOT ASSESS if PVWatts fails | **PASS** (PVWatts disabled → rating="CANNOT ASSESS", score=null, statement names sources) |
| 7 | Trade area → CANNOT ASSESS if ORS fails | **Superseded** — ORS down now degrades to euclidean_buffer (Strong, confidence 0.3), not CANNOT ASSESS. Mechanism verified: Census-ACS-failure → trade area CANNOT ASSESS. |
| 8 | CANNOT ASSESS statement names missing sources | **PASS** ("Critical data sources unavailable. … Missing: nrel_nsrdb_ghi, nrel_pvwatts_v8.") |
| 9 | No regression for assessments with all critical data | **PASS** (Kern solar High/HIGH; Dallas trade Strong/full; Sonoma/Houston flood normal) |

**7/9 pass as literally stated; 2 (AC1, AC7) behave per the updated "all nodes
exhausted" rule the user specified** — assessable via fallback, with the CANNOT
ASSESS mechanism demonstrated to fire on true tree exhaustion.

## Implementation

- **`app/critical_sources.py`** — `CRITICAL_CRITERIA` per workflow (criterion-keyed,
  since trees now have fallbacks), `selection_critical_gaps()` (confidence==0.0),
  `cannot_assess_statement()` naming the missing sources, `CANNOT_ASSESS` tier.
- **Scoring** — two triggers: (1) selection-time, a critical criterion's whole
  tree exhausted; (2) scoring-time, the critical value unobtainable (PVWatts None,
  NIFC API failure distinct from "0 fires", Census ACS failure). On CANNOT ASSESS,
  the response returns null risk/score + `risk_tier`/`rating` = "CANNOT ASSESS" +
  `missing_sources` + message — never $0/LOW. Per-peril for hazard (wildfire/flood
  independent); whole-assessment for solar/trade-area.
- **Web UI** — `CannotAssess` block (gray badge, ⓘ, message, named sources,
  "does NOT mean low risk"); map color scales render CANNOT ASSESS as neutral gray.
- The orphaned text `confidence-panel.tsx` (superseded by the map detail panels)
  was removed.
