"""Hazard assessment scoring v2 — Workflow Integration Spec.

Wires the hazard_assessment workflow through the Phase 1-4 platform architecture,
following solar_scoring_v2.py as the reference pattern:

  1. select_data("hazard_assessment", lat, lng) establishes which sources are
     available and the per-criterion + composite confidence.
  2. Wildfire is scored with the validated Sonoma vulnerability model
     (wildfire_loss.score_property — logistic model over pre-computed FSim /
     LANDFIRE / 3DEP structure features).
  3. Flood is scored with the national HAZUS pipeline (FEMA NFHL zone + BFE,
     USACE NSI exposure, USGS 3DEP elevation, HAZUS depth-damage) — reusing the
     pure query/lookup functions from flood_scoring.py.
  4. The two perils are reported SEPARATELY (independent perils — not combined
     into one number) alongside the selection engine's confidence report and the
     methodology documentation.

Existing /wildfire-loss and /flood/risk endpoints are unchanged; this is the new
combined primary.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import httpx

from . import wildfire_loss
from .data_selection import select_data
from .flood_scoring import (
    DEFAULT_FIRST_FLOOR_HEIGHT_FT,
    DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT,
    classify_zone,
    ddf_lookup,
    map_occupancy_class,
    query_3dep_ground_ft,
    query_nfhl,
    query_nsi,
)
from .methodology_repository import get_methodology_doc

MODULE_NAME = "hazard_assessment_scoring_v2"
MODULE_VERSION = "0.1.0"

WILDFIRE_CRITERIA = {
    "wf_likelihood", "wf_fuel_proximity", "wf_canopy", "wf_slope", "wf_structure",
}
FLOOD_CRITERIA = {
    "fl_zone", "fl_depth", "fl_historical", "fl_hydrology", "fl_building",
}

_WILDFIRE_CALIBRATION_NOTE = (
    "Wildfire vulnerability model calibrated on Sonoma County CAL FIRE DINS data "
    "(AUC 0.76). Application outside Sonoma County uses the same coefficients "
    "without local calibration, and requires pre-computed FSim/LANDFIRE/3DEP "
    "structure features (currently loaded for Sonoma County)."
)


def _tier(annual_risk: float | None) -> str | None:
    """Shared HIGH/MODERATE/LOW risk tiering used by both perils."""
    if annual_risk is None:
        return None
    return "HIGH" if annual_risk > 500 else "MODERATE" if annual_risk >= 50 else "LOW"


# ─── Wildfire peril ────────────────────────────────────────────────────────


async def _wildfire_block(
    pool: asyncpg.Pool, latitude: float, longitude: float,
) -> dict[str, Any]:
    """Score wildfire via the Sonoma vulnerability model. When no NSI structure
    with pre-computed features is within range (i.e. outside loaded coverage),
    report the peril as unavailable rather than fabricating a score."""
    res = await wildfire_loss.score_property(pool, latitude, longitude)
    if res.get("match") is None:
        return {
            "available": False,
            "annual_risk_usd": None,
            "risk_tier": None,
            "damage_probability": None,
            "note": (
                "No structure with pre-computed wildfire features within range. "
                + _WILDFIRE_CALIBRATION_NOTE
            ),
        }
    pv = res["property_vulnerability"]
    risk = res["risk_estimate"]
    annual = (
        risk.get("annual_risk_estimate_usd_persisted")
        if risk.get("annual_risk_estimate_usd_persisted") is not None
        else risk.get("annual_risk_estimate_usd")
    )
    return {
        "available": True,
        "annual_risk_usd": annual,
        "risk_tier": _tier(annual),
        "damage_probability": pv.get("damage_probability"),
        "exceeds_risk_threshold": pv.get("exceeds_risk_threshold"),
        "features": res.get("features"),
        "match": res.get("match"),
        "validation_auc_roc": pv.get("validation_auc_roc"),
        "note": _WILDFIRE_CALIBRATION_NOTE,
    }


# ─── Flood peril ───────────────────────────────────────────────────────────


async def _flood_block(
    pool: asyncpg.Pool, latitude: float, longitude: float,
) -> dict[str, Any]:
    """Score flood via the national HAZUS pipeline, reusing flood_scoring's pure
    query/lookup helpers (depth → damage → annual loss)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        nfhl = await query_nfhl(client, longitude, latitude)
        nsi = await query_nsi(client, longitude, latitude)
        ground_ft = await query_3dep_ground_ft(client, longitude, latitude)

    zone = nfhl["flood_zone"]
    zinfo = classify_zone(zone, nfhl["zone_subtype"])
    bfe = nfhl["static_bfe"]

    # First-floor height (NSI) with national default; 3DEP ground with NSI fallback.
    ffh = (
        float(nsi["found_ht"])
        if nsi and nsi.get("found_ht") is not None
        else DEFAULT_FIRST_FLOOR_HEIGHT_FT
    )
    if ground_ft is None and nsi and nsi.get("ground_elv_ft") is not None:
        ground_ft = float(nsi["ground_elv_ft"])

    # Depth above first floor (positive = water above first floor).
    if zinfo["is_sfha"] and bfe is not None and ground_ft is not None:
        depth_ft = bfe - ground_ft - ffh
        depth_basis = "NFHL static BFE − ground elevation − first-floor height"
    elif zinfo["is_sfha"]:
        depth_ft = DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT - ffh
        depth_basis = (
            f"nominal {DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT:.0f} ft 100-yr depth above "
            "grade (no published static BFE) − first-floor height"
        )
    else:
        depth_ft = None
        depth_basis = "outside the Special Flood Hazard Area — no modeled inundation"

    occupancy_class = (
        map_occupancy_class(nsi.get("occtype"), nsi.get("num_story"), nsi.get("found_type"))
        if nsi else "RES1-1SNB"
    )
    val_struct = float(nsi["val_struct"]) if nsi and nsi.get("val_struct") is not None else 0.0
    val_cont = float(nsi["val_cont"]) if nsi and nsi.get("val_cont") is not None else 0.0

    struct_pct = cont_pct = 0.0
    if depth_ft is not None:
        ddf = await ddf_lookup(pool, occupancy_class, depth_ft)
        if ddf:
            struct_pct = float(ddf["structural_damage_pct"])
            cont_pct = float(ddf["contents_damage_pct"])

    structural_loss = round(val_struct * struct_pct / 100.0, 2)
    contents_loss = round(val_cont * cont_pct / 100.0, 2)
    total_loss = round(structural_loss + contents_loss, 2)
    annual_risk = round(total_loss * zinfo["annual_probability"], 2)

    return {
        "available": zone is not None or nsi is not None,
        "annual_risk_usd": annual_risk,
        "risk_tier": _tier(annual_risk),
        "flood_zone": zone,
        "in_special_flood_hazard_area": zinfo["is_sfha"],
        "depth_ft": round(depth_ft, 2) if depth_ft is not None else None,
        "depth_basis": depth_basis,
        "static_bfe_ft": bfe,
        "ground_elevation_ft": round(ground_ft, 2) if ground_ft is not None else None,
        "annual_exceedance_probability": zinfo["annual_probability"],
        "return_period_years": zinfo["return_period_years"],
        "damage": {
            "hazus_occupancy_class": occupancy_class,
            "structural_damage_pct": struct_pct,
            "contents_damage_pct": cont_pct,
            "structural_loss_usd": structural_loss,
            "contents_loss_usd": contents_loss,
            "total_loss_usd": total_loss,
        },
        "structure_matched": nsi is not None,
    }


# ─── Confidence report (from the selection engine) ─────────────────────────


def _confidence_report(selection: Any) -> dict[str, Any]:
    return {
        "tier":           selection.confidence_tier,
        "composite":      round(selection.composite_confidence, 4),
        "statement":      selection.confidence_statement,
        "completeness":   selection.completeness,
        "gaps":           selection.gaps,
        "strongest_data": selection.strongest_data,
        "weakest_data":   selection.weakest_data,
        "per_criterion": {
            c.criterion_id: {
                "confidence":      c.confidence,
                "tier":            c.confidence_tier,
                "quality_note":    c.quality_note,
                "selected_source": (c.selected_sources[0]["source_id"]
                                    if c.selected_sources else None),
            }
            for c in selection.criteria
        },
    }


# ─── Orchestrator ──────────────────────────────────────────────────────────


async def score_hazard(
    pool: asyncpg.Pool, latitude: float, longitude: float,
) -> dict[str, Any]:
    """Combined wildfire + flood hazard assessment (Workflow Integration Spec).

    Returns per-peril scores (NOT combined into one number), the selection
    engine's confidence report covering all 10 hazard criteria, and the
    methodology documentation with academic citations."""
    selection = await select_data(pool, "hazard_assessment", latitude, longitude)
    methodology = await get_methodology_doc(pool, "hazard_assessment")

    wildfire = await _wildfire_block(pool, latitude, longitude)
    flood = await _flood_block(pool, latitude, longitude)

    confidence = _confidence_report(selection)
    # Per-peril confidence subsets so each block carries its own quality view.
    wildfire["criteria_confidence"] = {
        k: v for k, v in confidence["per_criterion"].items() if k in WILDFIRE_CRITERIA
    }
    flood["criteria_confidence"] = {
        k: v for k, v in confidence["per_criterion"].items() if k in FLOOD_CRITERIA
    }

    return {
        "module":         MODULE_NAME,
        "module_version": MODULE_VERSION,
        "query":          {"latitude": latitude, "longitude": longitude},
        "wildfire":       wildfire,
        "flood":          flood,
        "confidence":     confidence,
        "methodology":    methodology,
    }
