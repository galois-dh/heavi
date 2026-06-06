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
from .critical_sources import CANNOT_ASSESS, selection_critical_gaps
from .data_selection import select_data
from .display_names import enrich_result
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
from .integrations import (
    query_landfire_canopy,
    query_landfire_fuel,
    query_nifc_perimeters,
)
from .methodology_repository import get_methodology_doc

MODULE_NAME = "hazard_assessment_scoring_v2"
MODULE_VERSION = "0.2.0"  # data-tree completeness: NIFC + LANDFIRE WCS fallback

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


NSI_SOURCE = "USACE National Structure Inventory"

# NSI occupancy-type prefix → plain-English structure category.
_NSI_OCC_CATEGORY = {
    "RES": "residential", "COM": "commercial", "IND": "industrial",
    "AGR": "agricultural", "REL": "religious", "GOV": "government",
    "EDU": "educational", "PUB": "public",
}
# NSI building-material code → plain-English construction type.
_NSI_BLDG_MATERIAL = {
    "W": "wood frame", "M": "masonry", "C": "concrete", "S": "steel",
    "H": "manufactured", "MH": "manufactured",
}


def _nsi_building_type(occtype: str | None, bldgtype: str | None) -> str | None:
    """Human-readable building type from NSI codes, e.g. ('RES1','W') →
    'residential wood frame'. Returns None when neither code is present."""
    occ = (occtype or "").upper()
    category = next((v for k, v in _NSI_OCC_CATEGORY.items() if occ.startswith(k)), None)
    material = _NSI_BLDG_MATERIAL.get((bldgtype or "").upper())
    parts = [p for p in (category, material) if p]
    return " ".join(parts) if parts else None


def _nsi_attribution(nsi: dict[str, Any] | None) -> dict[str, Any]:
    """Replacement-value provenance fields shared by both perils. A structure is
    'matched' only when NSI returns a positive replacement value; otherwise the
    dollar estimate is N/A (no structure to value), never a default/zero."""
    val = (float(nsi["val_struct"])
           if nsi and nsi.get("val_struct") not in (None, 0, 0.0) else None)
    return {
        "nsi_replacement_value": val,
        "nsi_building_type": (_nsi_building_type(nsi.get("occtype"), nsi.get("bldgtype"))
                              if nsi else None),
        "nsi_source": NSI_SOURCE if nsi else None,
        "nsi_available": val is not None,
    }


# ─── Wildfire peril ────────────────────────────────────────────────────────


def _picks(selection: Any) -> dict[str, tuple[str | None, float]]:
    """criterion_id → (selected_source_id, confidence) from the selection."""
    return {
        c.criterion_id: (
            (c.selected_sources[0]["source_id"] if c.selected_sources else None),
            c.confidence,
        )
        for c in selection.criteria
    }


def _wildfire_cannot_assess(sources: list[str], message: str) -> dict[str, Any]:
    """CANNOT ASSESS peril shape — null risk, not $0/LOW (Insufficient Data Spec)."""
    return {
        "available": False,
        "cannot_assess": True,
        "annual_risk_usd": None,
        "risk_tier": CANNOT_ASSESS,
        "damage_probability": None,
        "missing_sources": sources,
        "message": message,
    }


def _flood_cannot_assess(sources: list[str], message: str) -> dict[str, Any]:
    return {
        "available": False,
        "cannot_assess": True,
        "annual_risk_usd": None,
        "risk_tier": CANNOT_ASSESS,
        "flood_zone": None,
        "depth_ft": None,
        "missing_sources": sources,
        "message": message,
    }


def _fsim_result(res: dict[str, Any]) -> dict[str, Any]:
    """Shape the pre-loaded FSim/LANDFIRE structure-model result."""
    pv = res["property_vulnerability"]
    risk = res["risk_estimate"]
    annual = (
        risk.get("annual_risk_estimate_usd_persisted")
        if risk.get("annual_risk_estimate_usd_persisted") is not None
        else risk.get("annual_risk_estimate_usd")
    )
    return {
        "available": True,
        "method": "fsim_preloaded",
        "annual_risk_usd": annual,
        "risk_tier": _tier(annual),
        "damage_probability": pv.get("damage_probability"),
        "features": res.get("features"),
        "match": res.get("match"),
        "validation_auc_roc": pv.get("validation_auc_roc"),
        "confidence": 1.0,
        "note": _WILDFIRE_CALIBRATION_NOTE,
    }


async def _wildfire_block(
    pool: asyncpg.Pool, latitude: float, longitude: float, selection: Any,
) -> dict[str, Any]:
    """Score wildfire from the sources the selection engine actually picked
    (Data Tree Completeness Spec).

    - wf_likelihood = FSim (pre-loaded) → use the validated structure model.
    - wf_likelihood = NIFC fire perimeters (proxy) → historical fire frequency
      × damage factor (from LANDFIRE WCS fuel/canopy) × NSI replacement value.
    - wf_likelihood unavailable (all nodes exhausted) → CANNOT ASSESS.
    """
    picks = _picks(selection)
    like_src, like_conf = picks.get("wf_likelihood", (None, 0.0))
    fuel_src, fuel_conf = picks.get("wf_fuel_proximity", (None, 0.0))
    canopy_src, canopy_conf = picks.get("wf_canopy", (None, 0.0))

    # CANNOT ASSESS only when the likelihood tree is fully exhausted (Insufficient
    # Data Handling Spec). With the completed trees this is rare — FSim missing but
    # NIFC available is ASSESSABLE.
    if like_src is None:
        return _wildfire_cannot_assess(
            ["usfs_fsim", "nifc_fire_perimeters"],
            "Wildfire burn-probability data (USFS FSim / NIFC fire history) "
            "unavailable at this location. Wildfire risk cannot be estimated.",
        )

    # FSim pre-loaded path (authoritative) when the catalog FSim source resolves.
    if like_src == "usfs_fsim":
        res = await wildfire_loss.score_property(pool, latitude, longitude)
        if res.get("match") is not None:
            return _fsim_result(res)

    # Proxy/fallback path: NIFC frequency + LANDFIRE WCS fuel/canopy + NSI value.
    async with httpx.AsyncClient(timeout=30.0) as client:
        nifc = (
            await query_nifc_perimeters(client, latitude=latitude, longitude=longitude)
            if like_src == "nifc_fire_perimeters" else None
        )
        # NIFC API failure (None) is distinct from "0 historical fires" (a valid
        # low-risk answer, e.g. Houston). Only the former is unassessable.
        if like_src == "nifc_fire_perimeters" and nifc is None:
            return _wildfire_cannot_assess(
                ["nifc_fire_perimeters"],
                "Wildfire fire-history service (NIFC) did not respond. Wildfire "
                "risk cannot be estimated at this location right now.",
            )
        fuel = (
            await query_landfire_fuel(client, latitude=latitude, longitude=longitude)
            if fuel_src == "landfire_wcs_fuel" else None
        )
        canopy_pct = (
            await query_landfire_canopy(client, latitude=latitude, longitude=longitude)
            if canopy_src == "landfire_wcs_canopy" else None
        )
        nsi = await query_nsi(client, longitude, latitude)

    fire_frequency = float((nifc or {}).get("fire_frequency") or 0.0)
    nsi_attr = _nsi_attribution(nsi)
    val_struct = nsi_attr["nsi_replacement_value"]  # None when no structure matched

    # Damage given a fire reaches the vicinity: fuel burnability + canopy density.
    burnable = fuel.get("burnable") if fuel else None
    burnable_factor = 1.0 if burnable else (0.25 if burnable is False else 0.5)
    canopy_factor = (canopy_pct / 100.0) if canopy_pct is not None else 0.0
    damage_probability = max(0.0, min(1.0, 0.30 + 0.40 * burnable_factor + 0.30 * canopy_factor))

    # No NSI structure → the dollar estimate is N/A, not a default-valued guess.
    annual_risk = (round(fire_frequency * damage_probability * val_struct, 2)
                   if val_struct is not None else None)
    wf_conf = min(like_conf, fuel_conf or 1.0, canopy_conf or 1.0)

    return {
        "available": True,
        "method": "proxy_fallback",
        "annual_risk_usd": annual_risk,
        "risk_tier": _tier(annual_risk),
        "damage_probability": round(damage_probability, 3),
        "fire_frequency_per_year": round(fire_frequency, 4),
        "historical_fires": (nifc or {}).get("fires"),
        "fuel_model_fbfm40": (fuel or {}).get("fbfm40"),
        "canopy_cover_pct": canopy_pct,
        "replacement_value_usd": val_struct,
        **nsi_attr,
        "confidence": round(wf_conf, 2),
        "sources_used": {
            "wf_likelihood": like_src, "wf_fuel_proximity": fuel_src, "wf_canopy": canopy_src,
        },
        "note": (
            "Proxy/fallback wildfire estimate: NIFC historical fire frequency "
            "(burn-probability proxy) × LANDFIRE on-demand fuel/canopy damage "
            "factor × NSI replacement value. Lower confidence than FSim. "
            + _WILDFIRE_CALIBRATION_NOTE
        ),
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
    nsi_attr = _nsi_attribution(nsi)
    val_struct = nsi_attr["nsi_replacement_value"]  # None when no structure matched
    val_cont = float(nsi["val_cont"]) if nsi and nsi.get("val_cont") is not None else None

    struct_pct = cont_pct = 0.0
    if depth_ft is not None and val_struct is not None:
        ddf = await ddf_lookup(pool, occupancy_class, depth_ft)
        if ddf:
            struct_pct = float(ddf["structural_damage_pct"])
            cont_pct = float(ddf["contents_damage_pct"])

    if val_struct is None:
        # No NSI structure → dollar loss is N/A; a structure that isn't there
        # cannot be valued at zero or a default.
        structural_loss = contents_loss = total_loss = annual_risk = None
    else:
        structural_loss = round(val_struct * struct_pct / 100.0, 2)
        contents_loss = round((val_cont or 0.0) * cont_pct / 100.0, 2)
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
        **nsi_attr,
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

    # Critical-source gaps: a peril whose critical criterion's whole tree is
    # exhausted (confidence 0.0) is CANNOT ASSESS, not $0/LOW.
    crit_by_peril: dict[str, dict[str, Any]] = {}
    for g in selection_critical_gaps(selection, "hazard_assessment"):
        if g.get("peril"):
            crit_by_peril[g["peril"]] = g

    wildfire = await _wildfire_block(pool, latitude, longitude, selection)
    if "flood" in crit_by_peril:
        g = crit_by_peril["flood"]
        flood = _flood_cannot_assess(g["sources"], g["message"])
    else:
        flood = await _flood_block(pool, latitude, longitude)

    confidence = _confidence_report(selection)
    # Per-peril confidence subsets so each block carries its own quality view.
    wildfire["criteria_confidence"] = {
        k: v for k, v in confidence["per_criterion"].items() if k in WILDFIRE_CRITERIA
    }
    flood["criteria_confidence"] = {
        k: v for k, v in confidence["per_criterion"].items() if k in FLOOD_CRITERIA
    }

    return enrich_result({
        "module":         MODULE_NAME,
        "module_version": MODULE_VERSION,
        "query":          {"latitude": latitude, "longitude": longitude},
        "wildfire":       wildfire,
        "flood":          flood,
        "confidence":     confidence,
        "methodology":    methodology,
    })
