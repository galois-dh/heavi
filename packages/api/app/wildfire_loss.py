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
#   2. packages/api/app/wildfire_vulnerability_model.json (local mirror — works
#      on Railway with Root Directory = packages/api, where sibling packages
#      may not be in the container)
#   3. ../../validation/modules/wildfire_vulnerability/fitted_model.json
#      (monorepo dev/CI layout)
# When the validation package retrains the model, both copies should be
# refreshed in the same commit so they stay byte-identical. The local mirror is
# the canonical artifact for the API service.
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[3]

_MODEL_PATH_CANDIDATES = [
    Path(p) for p in (os.getenv("WILDFIRE_MODEL_PATH"),) if p
] + [
    _HERE / "wildfire_vulnerability_model.json",
    _REPO_ROOT / "packages" / "validation" / "modules" / "wildfire_vulnerability" / "fitted_model.json",
]


def _load_model() -> dict[str, Any]:
    for path in _MODEL_PATH_CANDIDATES:
        if path.exists():
            return json.loads(path.read_text())
    tried = "\n  ".join(str(p) for p in _MODEL_PATH_CANDIDATES)
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

METHODOLOGY_SUMMARY = (
    "EAL = burn_probability × P(destroyed | features) × replacement_value "
    "(Klugman, Panjer & Willmot, Loss Models §6). "
    "burn_probability: USFS WRC FSim 270 m, LANDFIRE 2014 fuels. "
    "P(destroyed): logistic regression on 5 predictors "
    "(burn_probability, distance_to_fuel_m, canopy_cover_100m, slope_degrees, "
    "is_res1) calibrated against DINS from 5 Sonoma fires "
    f"(AUC {MODEL['auc_roc']:.3f}). "
    "Replacement value: USACE NSI v2 val_struct (full total-loss assumption). "
    "Caveat: burn_probability appears in both terms with opposite signs "
    "(conditioning effect), compressing the EAL spread. "
    "See packages/validation/reports/wildfire_loss/methodology.md."
)


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
        resolved_address = None

    # 100 m ≈ 0.001° at Sonoma latitude; pad by 50 %.
    deg_expand = (search_radius_m / 100_000) * 1.5

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_NEAREST_SQL, longitude, latitude, deg_expand)

    if row is None or row["match_dist_m"] > search_radius_m:
        return {
            "query": {
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
                "resolved_address": resolved_address,
                "search_radius_m": search_radius_m,
            },
            "match": None,
            "message": f"No NSI structure within {search_radius_m} m of the query point.",
        }

    occtype = row["occtype"] or ""
    is_res1 = 1 if occtype.startswith("RES1") else 0
    features = {
        "burn_probability": float(row["burn_probability"] or 0.0),
        "distance_to_fuel_m": float(row["distance_to_fuel_m"] or 0.0),
        "canopy_cover_100m": float(row["canopy_cover_100m"] or 0.0),
        "slope_degrees": float(row["slope_degrees"] or 0.0),
        "is_res1": is_res1,
    }
    p_destroyed, log_odds = _score_destruction(features)
    val_struct = float(row["val_struct"] or 0.0)
    lambda_destroy = features["burn_probability"] * p_destroyed
    eal_recomputed = lambda_destroy * val_struct

    return {
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "resolved_address": resolved_address,
            "search_radius_m": search_radius_m,
        },
        "match": {
            "fd_id": int(row["fd_id"]),
            "match_distance_m": round(float(row["match_dist_m"]), 1),
            "nsi_location": {"latitude": float(row["lat"]), "longitude": float(row["lng"])},
            "occupancy_type": occtype or None,
            "replacement_value_usd": val_struct,
            "tract_fips": (row["cbfips"] or "")[:11] or None,
        },
        "features": {
            "burn_probability": features["burn_probability"],
            "distance_to_fuel_m": features["distance_to_fuel_m"],
            "canopy_cover_30m": float(row["canopy_cover_30m"] or 0.0),
            "canopy_cover_100m": features["canopy_cover_100m"],
            "canopy_cover_300m": float(row["canopy_cover_300m"] or 0.0),
            "slope_degrees": features["slope_degrees"],
            "is_res1": is_res1,
        },
        "vulnerability_score": {
            "p_destroyed": round(p_destroyed, 4),
            "log_odds": round(log_odds, 3),
            "exceeds_optimal_threshold": p_destroyed >= MODEL["optimal_threshold"],
            "optimal_threshold": MODEL["optimal_threshold"],
            "model_auc_roc": MODEL["auc_roc"],
            "model_run_id": MODEL["run_id"],
            "methodology_hash": MODEL["methodology_hash"],
        },
        "loss_estimate": {
            "lambda_destroy_per_year": round(lambda_destroy, 6),
            "expected_annual_loss_usd_recomputed": round(eal_recomputed, 2),
            "expected_annual_loss_usd_persisted": (
                float(row["expected_annual_loss"])
                if row["expected_annual_loss"] is not None
                else None
            ),
            "return_period_for_total_loss_years": (
                round(1.0 / lambda_destroy) if lambda_destroy > 0 else None
            ),
        },
        "methodology_summary": METHODOLOGY_SUMMARY,
    }
