"""Trade area scoring v2 — Workflow Integration Spec.

Wires the trade_area workflow through the Phase 1-4 platform architecture,
following solar_scoring_v2.py as the reference pattern:

  1. select_data("trade_area", lat, lng) establishes which sources are available
     and the per-criterion + composite confidence. Crucially it selects, per
     criterion, the source actually used:
       - ta_daytime:        census_lehd (loaded → HIGH) vs census_acs_commuter proxy
       - ta_competitive_gap/complementary: osm_pois PostGIS cache vs osm_pois_overpass
  2. Where the loaded geography covers the point (currently Dallas County), the
     full validated Huff/demographics pipeline (trade_area_scoring.score_trade_area)
     runs unchanged.
  3. Elsewhere, the competitive criteria are computed on-demand from Overpass and
     flood from FEMA NFHL; demographic ring-aggregation (which needs loaded tract
     geometries) is reported as a coverage gap. Either way the confidence report
     makes the data provenance explicit.

The existing /trade-area/score endpoint is unchanged; this is the new primary.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import httpx

from . import trade_area_scoring as ta
from .data_selection import select_data
from .flood_scoring import classify_zone, query_nfhl
from .methodology_repository import get_methodology_doc

MODULE_NAME = "trade_area_scoring_v2"
MODULE_VERSION = "0.1.0"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_RADIUS_M = 5000
# Reference counts within the 5 km Overpass radius for the national fallback
# (no resident-population denominator available outside the loaded geography).
REF_COMPETITORS_5KM = 15.0
REF_COMPLEMENTARY_5KM = 300.0
REF_TOTAL_POIS_5KM = 600.0

STRONG_THRESHOLD, MODERATE_THRESHOLD = 0.70, 0.40


def _rating(score: float) -> str:
    return ("Strong" if score >= STRONG_THRESHOLD
            else "Moderate" if score >= MODERATE_THRESHOLD else "Weak")


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


def _selected(selection: Any, criterion_id: str) -> str | None:
    for c in selection.criteria:
        if c.criterion_id == criterion_id and c.selected_sources:
            return c.selected_sources[0]["source_id"]
    return None


def _sources_used(selection: Any) -> dict[str, Any]:
    """Human-facing summary of which source backs each provenance-sensitive
    criterion (the spec's headline distinctions)."""
    return {
        "poi_source":     _selected(selection, "ta_competitive_gap"),
        "daytime_source": _selected(selection, "ta_daytime"),
        "population_source": _selected(selection, "ta_population"),
        "flood_source":   _selected(selection, "ta_flood"),
    }


# ─── National fallback (outside the loaded geography) ──────────────────────


async def _overpass_counts(
    latitude: float, longitude: float, exact: list[str], prefix: list[str],
) -> dict[str, Any] | None:
    """On-demand competitor / complementary POI counts within OVERPASS_RADIUS_M."""
    q = (
        f"[out:json][timeout:60];("
        f'node["amenity"](around:{OVERPASS_RADIUS_M},{latitude},{longitude});'
        f'node["shop"](around:{OVERPASS_RADIUS_M},{latitude},{longitude});'
        f");out center;"
    )
    try:
        async with httpx.AsyncClient(
            timeout=70.0, headers={"User-Agent": "Heavi/0.1 (trade-area-v2)"},
        ) as c:
            r = await c.post(OVERPASS_URL, data={"data": q})
            if r.status_code != 200:
                return None
            elements = r.json().get("elements", [])
    except Exception:  # noqa: BLE001
        return None
    exact_set = set(exact)
    competitors = complementary = 0
    competitor_pois: list[dict[str, float]] = []
    for el in elements:
        tags = el.get("tags") or {}
        cats = {f"{k}:{v}" for k, v in tags.items() if k in ("amenity", "shop")}
        is_comp = bool(cats & exact_set) or any(
            any(c.startswith(p.rstrip("%")) for c in cats) for p in prefix
        )
        if is_comp:
            competitors += 1
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lng = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is not None and lng is not None and len(competitor_pois) < 300:
                competitor_pois.append({"latitude": float(lat), "longitude": float(lng)})
        else:
            complementary += 1
    return {
        "competitor_count": competitors,
        "complementary_count": complementary,
        "total_pois": competitors + complementary,
        "competitor_pois": competitor_pois,
    }


async def _dallas_competitor_pois(
    pool: asyncpg.Pool, iso_geom: dict[str, Any] | None,
    business_category: str, custom_categories: list[str] | None,
) -> list[dict[str, float]]:
    """Same-category competitor POI points within the 10-min isochrone (Dallas
    PostGIS cache) — for the map's competitor markers."""
    if not iso_geom:
        return []
    import json
    exact, prefix = ta.category_match(business_category, custom_categories)
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH iso AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($1), 4326) AS g)
                SELECT ST_Y(p.geometry) AS lat, ST_X(p.geometry) AS lng
                FROM trade_area_pois_dallas p, iso
                WHERE ST_Within(p.geometry, iso.g)
                  AND (p.category = ANY($2::text[]) OR p.category LIKE ANY($3::text[]))
                LIMIT 500
                """,
                json.dumps(iso_geom), exact, prefix,
            )
    except Exception:  # noqa: BLE001
        return []
    return [{"latitude": float(r["lat"]), "longitude": float(r["lng"])} for r in rows]


async def _national_fallback(
    pool: asyncpg.Pool, latitude: float, longitude: float, business_category: str,
    custom_categories: list[str] | None, selection: Any,
) -> dict[str, Any]:
    """Partial trade-area score for points outside the loaded geography. Real
    competitive (Overpass) + flood (NFHL) signals; demographic ring-aggregation
    is a coverage gap (needs loaded tract geometries)."""
    exact, prefix = ta.category_match(business_category, custom_categories)
    counts = await _overpass_counts(latitude, longitude, exact, prefix)

    # flood
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            nf = await query_nfhl(client, longitude, latitude)
        in_sfha = classify_zone(nf["flood_zone"], nf["zone_subtype"])["is_sfha"]
        flood_zone = nf["flood_zone"]
    except Exception:  # noqa: BLE001
        in_sfha, flood_zone = False, None

    crit: dict[str, float] = {"flood": 0.5 if in_sfha else 1.0}
    coverage_gaps = ["ta_population", "ta_income", "ta_daytime"]
    competitive = None
    if counts is not None:
        gap = ta._clamp01(1 - min(counts["competitor_count"] / REF_COMPETITORS_5KM, 1.0))
        crit["competitive_gap"] = round(gap, 3)
        crit["complementary"] = round(
            ta._clamp01(counts["complementary_count"] / REF_COMPLEMENTARY_5KM), 3)
        crit["accessibility"] = round(
            ta._clamp01(counts["total_pois"] / REF_TOTAL_POIS_5KM), 3)
        competitive = counts
    else:
        coverage_gaps += ["ta_competitive_gap", "ta_complementary", "ta_accessibility"]

    # Re-normalize the default weights over the criteria we could actually score.
    w = ta.DEFAULT_WEIGHTS
    scored = {k: v for k, v in crit.items() if v is not None}
    wsum = sum(w[k] for k in scored if k in w)
    composite = sum(w[k] * scored[k] for k in scored if k in w) / wsum if wsum else 0.0

    return {
        "coverage": "national_fallback",
        "suitability_score": round(composite, 3),
        "suitability_rating": _rating(composite),
        "criteria_scores": crit,
        "scored_over_weight_fraction": round(wsum, 3),
        "competitive_analysis": competitive,
        "competitor_pois": (counts or {}).get("competitor_pois", []),
        "in_flood_zone": in_sfha,
        "flood_zone": flood_zone,
        "coverage_gaps": coverage_gaps,
        "coverage_note": (
            "Outside the loaded trade-area geography (Dallas County). Competitive "
            "and flood signals computed on-demand (Overpass + FEMA NFHL); resident "
            "population / income / daytime ring-aggregation requires loaded Census "
            "tract geometries and is reported as a data gap."
        ),
    }


# ─── Orchestrator ──────────────────────────────────────────────────────────


async def score_trade_area_v2(
    pool: asyncpg.Pool,
    latitude: float,
    longitude: float,
    *,
    business_category: str = "coffee_shop",
    custom_categories: list[str] | None = None,
    existing_locations: list[dict[str, Any]] | None = None,
    address: str | None = None,
    resolved_address: str | None = None,
) -> dict[str, Any]:
    """Trade area score wired through the selection engine (Workflow Integration
    Spec). Full Huff/demographics pipeline where the geography is loaded;
    on-demand partial scoring elsewhere. Always returns the selection engine's
    confidence report and the methodology documentation."""
    selection = await select_data(pool, "trade_area", latitude, longitude)
    methodology = await get_methodology_doc(pool, "trade_area")
    confidence = _confidence_report(selection)
    sources_used = _sources_used(selection)

    # Full pipeline is available where the OSM POI cache covers the point (the
    # loaded geography). Elsewhere fall back to the on-demand partial.
    poi_source = sources_used["poi_source"]
    base: dict[str, Any]
    if poi_source == "osm_pois":
        full = await ta.score_trade_area(
            pool,
            latitude=latitude, longitude=longitude,
            business_category=business_category,
            custom_categories=custom_categories,
            existing_locations=existing_locations,
            address=address, resolved_address=resolved_address,
        )
        # Competitor POI points within the 10-min isochrone (for the map markers).
        rings = full.get("trade_area_rings") or []
        iso10 = next((r.get("isochrone") for r in rings
                      if abs((r.get("drive_time_minutes") or 0) - 10) <= 3), None)
        competitor_pois = await _dallas_competitor_pois(
            pool, iso10, business_category, custom_categories) if iso10 else []
        base = {
            "coverage": "full",
            "suitability_score": full["suitability_score"],
            "suitability_rating": full["suitability_rating"],
            "criteria_scores": full["criteria_scores"],
            "competitive_analysis": full["competitive_analysis"],
            "cannibalization": full.get("cannibalization"),
            "trade_area_rings": full["trade_area_rings"],
            "competitor_pois": competitor_pois,
            "geography": full.get("geography"),
            "natural_language_summary": full.get("natural_language_summary"),
        }
    else:
        base = await _national_fallback(
            pool, latitude, longitude, business_category, custom_categories, selection,
        )

    return {
        "module":            MODULE_NAME,
        "module_version":    MODULE_VERSION,
        "query": {
            "latitude": latitude, "longitude": longitude,
            "address": address, "resolved_address": resolved_address,
            "business_category": business_category,
        },
        **base,
        "data_sources_used": sources_used,
        "confidence":        confidence,
        "methodology":       methodology,
    }
