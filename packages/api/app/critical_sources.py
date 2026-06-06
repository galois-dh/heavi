"""Critical-source / CANNOT ASSESS logic (Heavi Insufficient Data Handling Spec).

The rule: if the data necessary to compute a reliable estimate is missing, do
NOT produce a numeric estimate — return CANNOT ASSESS instead of a misleading
$0/LOW.

After the data-tree completeness work, a criterion is "missing" only when its
ENTIRE data tree is exhausted — i.e. the selection engine reports per-criterion
confidence 0.0 (no tree node available), NOT merely when the primary source is
missing. So CANNOT ASSESS fires far less often: a wildfire assessment with the
FSim primary missing but the NIFC fallback available is ASSESSABLE.

A criterion can also be unobtainable at scoring time even when the selection
engine declared its source "available" — e.g. the PVWatts API is down, or the
NIFC query errors. Scorers signal that with a ``critical_unavailable`` flag in
the per-criterion basis; this module aggregates both signals.
"""

from __future__ import annotations

from typing import Any

CANNOT_ASSESS = "CANNOT ASSESS"

# Per-workflow critical criteria: if the criterion's whole tree is exhausted (or
# its value is unobtainable at scoring time), the peril/assessment cannot be
# produced. Keyed by criterion (not source) because trees have fallbacks now.
CRITICAL_CRITERIA: dict[str, dict[str, dict[str, Any]]] = {
    "solar_siting": {
        "solar_ghi": {
            "sources": ["nrel_pvwatts_v8", "nrel_nsrdb_ghi"],
            "message": (
                "Solar resource data (NREL PVWatts) unavailable. Suitability "
                "cannot be scored without energy-production estimates."
            ),
        },
    },
    "hazard_assessment": {
        "wf_likelihood": {
            "peril": "wildfire",
            "sources": ["usfs_fsim", "nifc_fire_perimeters"],
            "message": (
                "Wildfire burn-probability data (USFS FSim / NIFC fire history) "
                "unavailable at this location. Wildfire risk cannot be estimated."
            ),
        },
        "fl_zone": {
            "peril": "flood",
            "sources": ["fema_nfhl"],
            "message": (
                "FEMA flood-zone data unavailable at this location. Flood risk "
                "cannot be determined."
            ),
        },
    },
    "trade_area": {
        "ta_population": {
            "sources": ["census_acs"],
            "message": (
                "Census demographic data unavailable. Trade area cannot be "
                "scored without resident population."
            ),
        },
    },
}


def selection_critical_gaps(selection: Any, workflow: str) -> list[dict[str, Any]]:
    """Critical criteria whose ENTIRE data tree is exhausted (selection
    confidence == 0.0). This is the "all nodes exhausted" trigger."""
    cfg = CRITICAL_CRITERIA.get(workflow, {})
    by_id = {c.criterion_id: c for c in selection.criteria}
    gaps: list[dict[str, Any]] = []
    for crit_id, meta in cfg.items():
        sel = by_id.get(crit_id)
        if sel is not None and sel.confidence == 0.0:
            gaps.append({
                "criterion": crit_id,
                "sources": meta["sources"],
                "message": meta["message"],
                "peril": meta.get("peril"),
            })
    return gaps


def scoring_critical_gap(workflow: str, criterion_id: str) -> dict[str, Any]:
    """Build a critical-gap record for a criterion that was unobtainable at
    scoring time (e.g. the critical API call failed despite being 'available')."""
    meta = CRITICAL_CRITERIA.get(workflow, {}).get(criterion_id, {})
    return {
        "criterion": criterion_id,
        "sources": meta.get("sources", []),
        "message": meta.get("message", f"Critical data for {criterion_id} unavailable."),
        "peril": meta.get("peril"),
    }


def cannot_assess_statement(gaps: list[dict[str, Any]]) -> str:
    """Confidence statement naming the missing critical sources, by display name."""
    from .display_names import source_name
    srcs = sorted({s for g in gaps for s in g.get("sources", [])})
    names = sorted({source_name(s) for s in srcs})
    detail = (" Missing: " + ", ".join(names) + ".") if names else ""
    return "Critical data sources unavailable. Assessment cannot be produced." + detail
