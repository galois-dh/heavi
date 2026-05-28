"""REST entry-point for the Sonoma wildfire vulnerability/loss model.

Loads the fitted-coefficient bundle once at import time so a missing model file
fails the boot rather than the first request. Re-scores P(destroyed) in-process
using the exact same coefficients the persisted `expected_annual_loss` column
was computed from, so the recomputed and persisted EAL agree to floating-point
precision.

Mirrors the MCP `wildfire_loss` tool (packages/mcp-server/src/tools/wildfire-loss.ts)
so REST and MCP consumers see the same shape.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import asyncpg
import httpx

NOMINATIM_UA = "Heavi/0.1 (wildfire-loss-api)"

# Resolution chain for the fitted vulnerability model bundle. We try, in order:
#   1. WILDFIRE_MODEL_PATH env var (explicit override for ops)
#   2. packages/api/app/wildfire_vulnerability_model.json — the local mirror
#      next to this file. This is what Railway uses, where the Root Directory
#      is packages/api and sibling packages are NOT in the container.
#   3. ../../validation/modules/wildfire_vulnerability/fitted_model.json
#      (monorepo dev/CI layout — only resolvable when the full repo is on disk).
# The local mirror is the canonical artifact for the API service. When the
# validation package retrains the model, refresh both copies in the same commit.
_HERE = Path(__file__).resolve().parent


def _candidate_paths() -> list[Path]:
    """Build the resolution chain lazily so a non-existent monorepo path can't
    raise IndexError at import time (it did on Railway, where the file lives
    at /app/app/wildfire_loss.py and parents[3] is out of bounds)."""
    paths: list[Path] = []
    env = os.getenv("WILDFIRE_MODEL_PATH")
    if env:
        paths.append(Path(env))
    paths.append(_HERE / "wildfire_vulnerability_model.json")
    # Monorepo path is OPTIONAL — only attempt it if we have enough ancestors.
    parents = Path(__file__).resolve().parents
    if len(parents) >= 4:
        paths.append(
            parents[3]
            / "packages"
            / "validation"
            / "modules"
            / "wildfire_vulnerability"
            / "fitted_model.json"
        )
    return paths


def _load_model() -> dict[str, Any]:
    candidates = _candidate_paths()
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text())
    tried = "\n  ".join(str(p) for p in candidates)
    raise RuntimeError(
        "wildfire_loss: fitted_model.json not found. Tried:\n  " + tried
    )


# Loaded at import so a missing/corrupt bundle fails the boot, not the first
# request. The bundle is ~600 bytes — no memory concern.
MODEL: dict[str, Any] = _load_model()


def _logistic(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _score_destruction(features: dict[str, float]) -> tuple[float, float]:
    c = MODEL["coefficients"]
    z = (
        c["const"]
        + c["burn_probability"] * features["burn_probability"]
        + c["distance_to_fuel_m"] * features["distance_to_fuel_m"]
        + c["canopy_cover_100m"] * features["canopy_cover_100m"]
        + c["slope_degrees"] * features["slope_degrees"]
        + c["is_res1"] * features["is_res1"]
    )
    return _logistic(z), z


async def _geocode(address: str) -> tuple[float, float, str] | None:
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": NOMINATIM_UA}) as c:
        r = await c.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "us"},
        )
        data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]


async def _reverse_geocode(lat: float, lng: float) -> str | None:
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": NOMINATIM_UA}) as c:
        r = await c.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 18},
        )
    if r.status_code != 200:
        return None
    return r.json().get("display_name")


_NEAREST_SQL = """
WITH p AS (SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS g)
SELECT
    n.fd_id,
    n.occtype,
    n.val_struct,
    n.burn_probability,
    n.distance_to_fuel_m,
    n.canopy_cover_30m,
    n.canopy_cover_100m,
    n.canopy_cover_300m,
    n.slope_degrees,
    n.expected_annual_loss,
    n.cbfips,
    ST_X(n.geometry) AS lng,
    ST_Y(n.geometry) AS lat,
    ST_Distance(n.geometry::geography, p.g::geography) AS match_dist_m
FROM wildfire_nsi_structures n, p
WHERE n.geometry && ST_Expand(p.g, $3::float8)
ORDER BY n.geometry <-> p.g
LIMIT 1
"""

METHODOLOGY_NOTE = (
    "Annual risk estimate computed from USFS wildfire likelihood data, a "
    "vulnerability model validated against CAL FIRE damage inspections "
    "(AUC 0.76), and USACE structure replacement values. See methodology "
    "documentation for full data lineage and known limitations."
)

# Nearest FRAP fire perimeter within 5 mi, preferring one that CONTAINS the
# point — feeds the "Located within the <year> <fire> perimeter" clause of the
# natural-language summary. wildfire_frap_perimeters is the DB layer; the
# columns (fire_name, year_) are read here for display only.
_NEAREST_FIRE_SQL = """
SELECT
    fire_name,
    year_,
    ST_Contains(geometry, ST_SetSRID(ST_MakePoint($1, $2), 4326)) AS contains_point
FROM wildfire_frap_perimeters
WHERE ST_DWithin(
    geometry::geography, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 8047
)
ORDER BY ST_Contains(geometry, ST_SetSRID(ST_MakePoint($1, $2), 4326)) DESC,
         geometry <-> ST_SetSRID(ST_MakePoint($1, $2), 4326)
LIMIT 1
"""


def _factor_phrases(features: dict[str, Any]) -> list[str]:
    """Plain-language risk factors, in descending severity, capped at 2.
    `features` uses the internal model keys (burn_probability etc.)."""
    dist = float(features.get("distance_to_fuel_m") or 0.0)
    slope = float(features.get("slope_degrees") or 0.0)
    canopy = float(features.get("canopy_cover_100m") or 0.0)
    likelihood = float(features.get("burn_probability") or 0.0)

    ranked: list[tuple[int, str]] = []
    if dist == 0:
        ranked.append((1, "direct adjacency to wildland fuel (0m from fuel)"))
    elif dist < 30:
        ranked.append((2, "close proximity to wildland fuel"))
    if likelihood > 0.002:
        ranked.append((3, "elevated wildfire likelihood"))
    if slope > 15:
        ranked.append((4, "steep terrain"))
    elif slope > 5:
        ranked.append((6, "moderate terrain slope"))
    if canopy > 20:
        ranked.append((5, "dense surrounding canopy"))

    ranked.sort(key=lambda x: x[0])
    return [phrase for _, phrase in ranked][:2]


def _natural_language_summary(
    annual_risk: float, features: dict[str, Any], fire: dict[str, Any] | None
) -> str:
    tier = "HIGH" if annual_risk > 500 else "MODERATE" if annual_risk >= 50 else "LOW"
    parts = [
        f"This property has {tier} wildfire risk with an annual risk estimate "
        f"of ${annual_risk:,.0f}."
    ]
    phrases = _factor_phrases(features)
    if len(phrases) >= 2:
        parts.append(f"Key risk factors include {phrases[0]} and {phrases[1]}.")
    elif len(phrases) == 1:
        parts.append(f"Key risk factor: {phrases[0]}.")
    if fire and fire.get("contains_point"):
        yr = fire.get("year")
        nm = fire.get("fire_name")
        if nm and yr:
            parts.append(f"Located within the {yr} {nm} perimeter.")
        elif nm:
            parts.append(f"Located within the {nm} perimeter.")
    parts.append("Assessment validated against CAL FIRE damage inspections (AUC 0.76).")
    return " ".join(parts)


async def score_property(
    pool: asyncpg.Pool,
    latitude: float,
    longitude: float,
    *,
    search_radius_m: int = 500,
) -> dict[str, Any]:
    """Pure scoring path: given a known lat/lng, look up the nearest NSI
    structure, compute the vulnerability + loss fields, return everything
    EXCEPT the geocoding query block.

    Returns a dict with `match`, `features`, `property_vulnerability`,
    `risk_estimate`, `methodology_note`, and `natural_language_summary` on
    success; on no-match, `match` is None and a `message` is set. No Nominatim
    calls are made — callers that need a display address must geocode themselves.

    Used by both the click-driven /wildfire-loss endpoint (which wraps this
    with Nominatim reverse-geocode) and the portfolio loop (which has
    already geocoded the address forward, so calling _reverse_geocode again
    would be wasted Nominatim quota)."""

    # 100 m ≈ 0.001° at Sonoma latitude; pad by 50 %.
    deg_expand = (search_radius_m / 100_000) * 1.5

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_NEAREST_SQL, longitude, latitude, deg_expand)

        if row is None or row["match_dist_m"] > search_radius_m:
            return {
                "match": None,
                "message": f"No NSI structure within {search_radius_m} m of the query point.",
            }

        # Nearest containing/within-5mi fire for the NL summary clause.
        fire_row = await conn.fetchrow(_NEAREST_FIRE_SQL, longitude, latitude)

    fire = None
    if fire_row is not None:
        fire = {
            "fire_name": (fire_row["fire_name"] or "").strip().title() or None,
            "year": int(fire_row["year_"]) if fire_row["year_"] is not None else None,
            "contains_point": bool(fire_row["contains_point"]),
        }

    occtype = row["occtype"] or ""
    is_res1 = 1 if occtype.startswith("RES1") else 0
    # Internal feature dict — keys MUST match the model coefficient names
    # (burn_probability etc.); only the RESPONSE renames to the new vocabulary.
    features = {
        "burn_probability": float(row["burn_probability"] or 0.0),
        "distance_to_fuel_m": float(row["distance_to_fuel_m"] or 0.0),
        "canopy_cover_100m": float(row["canopy_cover_100m"] or 0.0),
        "slope_degrees": float(row["slope_degrees"] or 0.0),
        "is_res1": is_res1,
    }
    damage_probability, log_odds = _score_destruction(features)
    # Guard against a negative NSI val_struct flowing into both the
    # replacement_value_usd field and the risk estimate; NSI values should
    # always be ≥ 0.
    val_struct = max(0.0, float(row["val_struct"] or 0.0))
    annual_damage_frequency = features["burn_probability"] * damage_probability
    annual_risk_estimate = annual_damage_frequency * val_struct

    persisted = (
        float(row["expected_annual_loss"])  # DB column name (not renamed)
        if row["expected_annual_loss"] is not None
        else None
    )
    # The headline annual risk for the NL summary: persisted column when
    # present, else the recomputed value.
    headline_risk = persisted if persisted is not None else annual_risk_estimate

    return {
        "match": {
            "fd_id": int(row["fd_id"]),
            "match_distance_m": round(float(row["match_dist_m"]), 1),
            "nsi_location": {"latitude": float(row["lat"]), "longitude": float(row["lng"])},
            "occupancy_type": occtype or None,
            "replacement_value_usd": val_struct,
            "tract_fips": (row["cbfips"] or "")[:11] or None,
        },
        "features": {
            "wildfire_likelihood": features["burn_probability"],
            "distance_to_fuel_m": features["distance_to_fuel_m"],
            "canopy_cover_30m": float(row["canopy_cover_30m"] or 0.0),
            "canopy_cover_100m": features["canopy_cover_100m"],
            "canopy_cover_300m": float(row["canopy_cover_300m"] or 0.0),
            "slope_degrees": features["slope_degrees"],
            "is_res1": is_res1,
        },
        "property_vulnerability": {
            "damage_probability": round(damage_probability, 4),
            "log_odds": round(log_odds, 3),
            "exceeds_risk_threshold": damage_probability >= MODEL["optimal_threshold"],
            "optimal_threshold": MODEL["optimal_threshold"],
            "validation_auc_roc": MODEL["auc_roc"],
            "model_run_id": MODEL["run_id"],
            "methodology_hash": MODEL["methodology_hash"],
        },
        "risk_estimate": {
            "annual_damage_frequency": round(annual_damage_frequency, 6),
            "annual_risk_estimate_usd": round(annual_risk_estimate, 2),
            "annual_risk_estimate_usd_persisted": persisted,
            "return_period_years": (
                round(1.0 / annual_damage_frequency) if annual_damage_frequency > 0 else None
            ),
        },
        "methodology_note": METHODOLOGY_NOTE,
        "natural_language_summary": _natural_language_summary(
            headline_risk or 0.0, features, fire
        ),
    }


async def wildfire_loss(
    pool: asyncpg.Pool,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    address: str | None = None,
    search_radius_m: int = 500,
) -> dict[str, Any]:
    if latitude is None or longitude is None:
        if not address:
            raise ValueError("Provide either latitude+longitude or address")
        g = await _geocode(address)
        if not g:
            raise ValueError(f"Could not geocode: {address}")
        latitude, longitude, resolved_address = g
    else:
        # Click-driven path — best-effort reverse geocode so the UI can show
        # an address. Failures are silent; the response just has None here.
        resolved_address = await _reverse_geocode(latitude, longitude)

    core = await score_property(pool, latitude, longitude, search_radius_m=search_radius_m)
    query_block = {
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "resolved_address": resolved_address,
            "search_radius_m": search_radius_m,
        },
    }
    return {**query_block, **core}
