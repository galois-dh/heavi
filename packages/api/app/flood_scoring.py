"""National flood-risk scoring — federal hazard/exposure data queried on-demand.

Nothing is pre-loaded except the HAZUS depth-damage functions (flood_hazus_ddfs).
For any US point we query, at request time:
  - FEMA NFHL  (flood zone + Base Flood Elevation)            ArcGIS REST
  - USACE NSI  (nearest structure: occupancy, foundation, FFH, values)
  - USGS 3DEP  (ground elevation)
then look up the HAZUS depth-damage function and compute structural + contents
loss and an annual risk estimate (loss × annual exceedance probability).

Risk tiers match the wildfire module: HIGH > $500/yr, MODERATE $50-500, LOW < $50.
"""

from __future__ import annotations

import math
from typing import Any

import asyncpg
import httpx

# ─── Federal services ──────────────────────────────────────────────────────
# The public NFHL service lives under /arcgis/ (the /gis/ host sits behind an
# auth gateway). Layer 28 = "Flood Hazard Zones" (S_FLD_HAZ_AR).
NFHL_QUERY_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)
NSI_URL = "https://nsi.sec.usace.army.mil/nsiapi/structures"
DEM_GETSAMPLES_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/getSamples"
)
UA = "Mozilla/5.0 Heavi/0.1 (flood-risk)"
M_TO_FT = 3.28084

# Nominal 100-yr inundation depth above grade used when a property is in an SFHA
# but the NFHL has no static BFE (very common — many AE/A zones publish BFE only
# on the FIRM panel, not in STATIC_BFE). Configurable; documented as a limitation.
DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT = 3.0
DEFAULT_FIRST_FLOOR_HEIGHT_FT = 1.0

# Annual exceedance probability (1 / return period) by flood zone.
RETURN_PERIODS = {
    "high_risk": 0.01,    # A / AE / AH / AO / AR / A99 / V / VE — 100-yr
    "shaded_x": 0.002,    # 0.2% annual (500-yr) shaded X
    "minimal": 0.001,     # unshaded X / residual risk
}

METHODOLOGY_NOTE = (
    "Flood risk estimated from FEMA National Flood Hazard Layer (NFHL) zone and "
    "Base Flood Elevation data, USACE National Structure Inventory exposure, USGS "
    "3DEP ground elevation, and HAZUS Flood Model depth-damage functions. See the "
    "methodology endpoint for full data lineage, citations, and known limitations."
)


# ─── Federal API queries ────────────────────────────────────────────────────


async def query_nfhl(client: httpx.AsyncClient, lng: float, lat: float) -> dict[str, Any]:
    """FEMA NFHL flood hazard area at a point: flood_zone, zone_subtype, BFE."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,STATIC_BFE",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        r = await client.get(NFHL_QUERY_URL, params=params, headers={"User-Agent": UA})
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return {"flood_zone": None, "zone_subtype": None, "static_bfe": None}
    feats = data.get("features") or []
    if not feats:
        return {"flood_zone": None, "zone_subtype": None, "static_bfe": None}
    a = feats[0].get("attributes", {})
    bfe = a.get("STATIC_BFE")
    if bfe is not None and bfe <= -9000:  # NFHL sentinel for "no static BFE"
        bfe = None
    return {
        "flood_zone": a.get("FLD_ZONE"),
        "zone_subtype": a.get("ZONE_SUBTY"),
        "static_bfe": bfe,
    }


async def query_nsi(client: httpx.AsyncClient, lng: float, lat: float) -> dict[str, Any] | None:
    """Nearest USACE NSI structure to the point. The bbox GET currently 500s
    server-side, so we POST a small polygon (the documented alternative) and pick
    the nearest returned structure."""
    d = 0.005
    poly = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [lng - d, lat - d],
                            [lng + d, lat - d],
                            [lng + d, lat + d],
                            [lng - d, lat + d],
                            [lng - d, lat - d],
                        ]
                    ],
                },
            }
        ],
    }
    try:
        r = await client.post(
            NSI_URL,
            params={"fmt": "fc"},
            json=poly,
            headers={"User-Agent": UA, "Content-Type": "application/json"},
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    feats = data.get("features") if isinstance(data, dict) else None
    if not feats:
        return None
    best = None
    best_d2 = float("inf")
    for f in feats:
        coords = (f.get("geometry") or {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        sx, sy = float(coords[0]), float(coords[1])
        d2 = (sx - lng) ** 2 + (sy - lat) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best = f
    if best is None:
        return None
    p = best.get("properties", {})
    coords = best["geometry"]["coordinates"]
    return {
        "occtype": p.get("occtype"),
        "found_type": p.get("found_type"),
        "num_story": p.get("num_story"),
        "found_ht": p.get("found_ht"),
        "val_struct": p.get("val_struct"),
        "val_cont": p.get("val_cont"),
        "bldgtype": p.get("bldgtype"),
        "ground_elv_ft": p.get("ground_elv"),
        "longitude": float(coords[0]),
        "latitude": float(coords[1]),
        "distance_m": math.sqrt(best_d2) * 111_320.0,
    }


async def query_3dep_ground_ft(client: httpx.AsyncClient, lng: float, lat: float) -> float | None:
    """USGS 3DEP ground elevation at the point, in feet (service returns metres)."""
    import json as _json

    geometry = {"points": [[lng, lat]], "spatialReference": {"wkid": 4326}}
    try:
        r = await client.get(
            DEM_GETSAMPLES_URL,
            params={
                "geometry": _json.dumps(geometry),
                "geometryType": "esriGeometryMultipoint",
                "returnFirstValueOnly": "true",
                "f": "json",
            },
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    samples = data.get("samples") or []
    if not samples:
        return None
    try:
        return float(samples[0]["value"]) * M_TO_FT
    except (KeyError, TypeError, ValueError):
        return None


# ─── HAZUS mapping + lookup ─────────────────────────────────────────────────


def map_occupancy_class(occtype: str | None, num_story: Any, found_type: str | None) -> str:
    """NSI (occtype, num_story, found_type) → HAZUS DDF occupancy_class."""
    occ = (occtype or "").upper()
    basement = (found_type or "").upper() == "B"
    if occ.startswith("RES1"):
        try:
            stories = 2 if int(float(num_story)) >= 2 else 1
        except (TypeError, ValueError):
            stories = 1
        return f"RES1-{stories}S{'W' if basement else 'N'}B"
    if occ.startswith("RES2"):
        return "RES2"
    return "COM1"  # commercial / other → retail-trade default


async def ddf_lookup(
    pool: asyncpg.Pool, occupancy_class: str, depth_ft: float
) -> dict[str, Any] | None:
    """Nearest-depth HAZUS damage row for the occupancy class."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT occupancy_class, foundation_type, depth_ft,
                      structural_damage_pct, contents_damage_pct
               FROM flood_hazus_ddfs
               WHERE occupancy_class = $1
               ORDER BY abs(depth_ft - $2) ASC
               LIMIT 1""",
            occupancy_class,
            depth_ft,
        )
    if row is None:
        return None
    return dict(row)


def classify_zone(flood_zone: str | None, zone_subtype: str | None) -> dict[str, Any]:
    """Return {is_sfha, annual_probability, return_period_years, tier_label}."""
    z = (flood_zone or "").upper()
    sub = (zone_subtype or "").upper()
    is_sfha = z.startswith("A") or z.startswith("V")
    if is_sfha:
        prob = RETURN_PERIODS["high_risk"]
    elif z == "X" and ("0.2" in sub or "0.2 PCT" in sub or "SHADED" in sub):
        prob = RETURN_PERIODS["shaded_x"]
    else:
        prob = RETURN_PERIODS["minimal"]
    return {
        "is_sfha": is_sfha,
        "annual_probability": prob,
        "return_period_years": round(1.0 / prob),
    }


# ─── Natural-language summary ────────────────────────────────────────────────


def _tier(annual_risk: float) -> str:
    return "HIGH" if annual_risk > 500 else "MODERATE" if annual_risk >= 50 else "LOW"


def natural_language_summary(
    annual_risk: float,
    flood_zone: str | None,
    depth_above_first_floor: float | None,
) -> str:
    tier = _tier(annual_risk)
    zone = flood_zone or "X (unmapped / minimal)"
    parts = [
        f"This property has {tier} flood risk with an annual risk estimate of "
        f"${round(annual_risk):,}.",
        f"Located in FEMA flood zone {zone}.",
    ]
    if depth_above_first_floor is not None:
        if depth_above_first_floor > 0:
            parts.append(
                f"The base flood elevation exceeds the first floor by "
                f"{depth_above_first_floor:.1f} feet."
            )
        else:
            parts.append(
                f"The first floor sits {abs(depth_above_first_floor):.1f} feet above "
                f"the base flood elevation."
            )
    parts.append(
        "Assessment uses FEMA NFHL hazard data and HAZUS depth-damage methodology."
    )
    return " ".join(parts)


# ─── Pipeline ────────────────────────────────────────────────────────────────


async def assess_flood_risk(
    pool: asyncpg.Pool,
    *,
    latitude: float,
    longitude: float,
    address: str | None = None,
    resolved_address: str | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        nfhl = await query_nfhl(client, longitude, latitude)
        nsi = await query_nsi(client, longitude, latitude)
        ground_ft = await query_3dep_ground_ft(client, longitude, latitude)

    zone = nfhl["flood_zone"]
    zinfo = classify_zone(zone, nfhl["zone_subtype"])
    bfe = nfhl["static_bfe"]

    # First-floor height above grade (NSI), with a national default fallback.
    ffh = (
        float(nsi["found_ht"])
        if nsi and nsi.get("found_ht") is not None
        else DEFAULT_FIRST_FLOOR_HEIGHT_FT
    )
    if ground_ft is None and nsi and nsi.get("ground_elv_ft") is not None:
        ground_ft = float(nsi["ground_elv_ft"])

    # Flood depth relative to the first floor (positive = water above first floor).
    depth_ft: float | None
    depth_basis: str
    if zinfo["is_sfha"] and bfe is not None and ground_ft is not None:
        depth_ft = bfe - ground_ft - ffh
        depth_basis = "NFHL static BFE minus ground elevation minus first-floor height"
    elif zinfo["is_sfha"]:
        depth_ft = DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT - ffh
        depth_basis = (
            f"nominal {DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT:.0f} ft 100-yr depth above "
            "grade (no static BFE published) minus first-floor height"
        )
    else:
        depth_ft = None  # not in an SFHA → no modeled 100/500-yr inundation
        depth_basis = "outside the Special Flood Hazard Area — no modeled inundation"

    occupancy_class = (
        map_occupancy_class(nsi.get("occtype"), nsi.get("num_story"), nsi.get("found_type"))
        if nsi
        else "RES1-1SNB"
    )

    val_struct = float(nsi["val_struct"]) if nsi and nsi.get("val_struct") is not None else 0.0
    val_cont = float(nsi["val_cont"]) if nsi and nsi.get("val_cont") is not None else 0.0

    struct_pct = cont_pct = 0.0
    ddf = None
    if depth_ft is not None:
        ddf = await ddf_lookup(pool, occupancy_class, depth_ft)
        if ddf:
            struct_pct = float(ddf["structural_damage_pct"])
            cont_pct = float(ddf["contents_damage_pct"])

    structural_loss = round(val_struct * struct_pct / 100.0, 2)
    contents_loss = round(val_cont * cont_pct / 100.0, 2)
    total_loss = round(structural_loss + contents_loss, 2)
    annual_risk = round(total_loss * zinfo["annual_probability"], 2)

    summary = natural_language_summary(annual_risk, zone, depth_ft)

    return {
        "natural_language_summary": summary,
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "resolved_address": resolved_address,
        },
        "flood_zone": {
            "zone": zone,
            "zone_subtype": nfhl["zone_subtype"],
            "static_bfe_ft": bfe,
            "in_special_flood_hazard_area": zinfo["is_sfha"],
            "annual_exceedance_probability": zinfo["annual_probability"],
            "return_period_years": zinfo["return_period_years"],
        },
        "structure": (
            {
                "match_distance_m": round(nsi["distance_m"], 1),
                "occupancy_type": nsi.get("occtype"),
                "hazus_occupancy_class": occupancy_class,
                "foundation_type": nsi.get("found_type"),
                "num_stories": nsi.get("num_story"),
                "first_floor_height_ft": ffh,
                "replacement_value_structure_usd": val_struct,
                "replacement_value_contents_usd": val_cont,
                "structure_location": {
                    "latitude": nsi["latitude"],
                    "longitude": nsi["longitude"],
                },
            }
            if nsi
            else None
        ),
        "elevation": {
            "ground_elevation_ft": round(ground_ft, 2) if ground_ft is not None else None,
            "first_floor_height_ft": ffh,
            "flood_depth_above_first_floor_ft": (
                round(depth_ft, 2) if depth_ft is not None else None
            ),
            "depth_basis": depth_basis,
        },
        "damage": {
            "hazus_occupancy_class": occupancy_class,
            "structural_damage_pct": struct_pct,
            "contents_damage_pct": cont_pct,
            "structural_loss_usd": structural_loss,
            "contents_loss_usd": contents_loss,
            "total_loss_usd": total_loss,
        },
        "risk_estimate": {
            "annual_risk_estimate_usd": annual_risk,
            "risk_tier": _tier(annual_risk),
            "annual_exceedance_probability": zinfo["annual_probability"],
            "return_period_years": zinfo["return_period_years"],
        },
        "methodology_note": METHODOLOGY_NOTE,
    }


# ─── Methodology documentation ───────────────────────────────────────────────


def methodology_doc() -> dict[str, Any]:
    return {
        "summary": (
            "On-demand national flood-risk assessment combining FEMA NFHL hazard "
            "zones, USACE NSI structure exposure, USGS 3DEP elevation, and HAZUS "
            "depth-damage functions to estimate annual flood risk per property."
        ),
        "pipeline": [
            "Geocode (if address) → point",
            "FEMA NFHL: flood zone + Base Flood Elevation at the point",
            "USACE NSI: nearest structure (occupancy, foundation, first-floor height, values)",
            "USGS 3DEP: ground elevation",
            "Flood depth = BFE − ground elevation − first-floor height",
            "HAZUS depth-damage lookup → structural & contents damage %",
            "Loss = value × damage %; annual risk = loss × annual exceedance probability",
        ],
        "data_sources": [
            {"name": "FEMA National Flood Hazard Layer (NFHL)", "use": "Flood zone + BFE",
             "endpoint": NFHL_QUERY_URL},
            {"name": "USACE National Structure Inventory (NSI)", "use": "Structure exposure",
             "endpoint": NSI_URL},
            {"name": "USGS 3DEP", "use": "Ground elevation", "endpoint": DEM_GETSAMPLES_URL},
            {"name": "HAZUS Flood Model depth-damage functions", "use": "Damage %",
             "table": "flood_hazus_ddfs"},
        ],
        "depth_damage_functions": {
            "source": "FEMA HAZUS Flood Model Technical Manual (USACE/FIA generic curves).",
            "occupancy_classes": [
                "RES1-1SNB", "RES1-1SWB", "RES1-2SNB", "RES1-2SWB", "RES2", "COM1",
            ],
            "depth_range_ft": "−4 to +24, 1-ft steps, relative to the first floor.",
            "citation": (
                "Federal Emergency Management Agency (2022). HAZUS Flood Model "
                "Technical Manual. Depth-damage relationships derived from USACE and "
                "Federal Insurance Administration credibility-weighted curves."
            ),
        },
        "annual_exceedance_probabilities": {
            "Zone A / AE / AH / AO / AR / A99": "0.01 (100-year)",
            "Zone V / VE": "0.01 (100-year)",
            "Zone X (shaded, 0.2%)": "0.002 (500-year)",
            "Zone X (unshaded) / unmapped": (
                "0.001 residual (≈ share of NFIP claims from outside the SFHA)"
            ),
        },
        "risk_tiers": {"HIGH": "> $500/yr", "MODERATE": "$50-500/yr", "LOW": "< $50/yr"},
        "configurable_defaults": [
            {
                "name": "default_sfha_depth_above_grade_ft",
                "value": DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT,
                "rationale": "Nominal 100-yr inundation depth above grade used when an SFHA "
                "parcel has no published static BFE in the NFHL.",
            },
            {
                "name": "default_first_floor_height_ft",
                "value": DEFAULT_FIRST_FLOOR_HEIGHT_FT,
                "rationale": "First-floor height used when NSI does not report found_ht.",
            },
        ],
        "known_limitations": [
            "STATIC_BFE is null in much of the NFHL; SFHA parcels without a published "
            "BFE fall back to a nominal 100-yr depth-above-grade assumption.",
            "Annual risk uses a single representative depth at the zone's design event, "
            "not a full depth-frequency integration across all return periods.",
            "NSI exposure is modeled (occupancy/value estimates), not a site survey.",
            "Zone X residual risk is a flat assumption; ~25% of NFIP claims historically "
            "originate outside the mapped SFHA.",
            "No pluvial (rainfall) or future-conditions flooding — NFHL fluvial/coastal only.",
        ],
        "validation": "Predicted losses to be validated against OpenFEMA NFIP redacted "
        "claims for Harris County, TX (flood_nfip_claims_harris).",
    }
