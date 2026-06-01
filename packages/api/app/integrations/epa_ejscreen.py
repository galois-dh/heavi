"""EPA EJScreen — block-group EJ indicators looked up from PostGIS.

EPA discontinued the EJScreen REST broker in Feb 2025; ejscreen.epa.gov is
NXDOMAIN. We load the last published EJScreen dataset (2024 v2.32) from the
Internet Archive into the ``ejscreen_blockgroups`` table (see
packages/data-catalog/loaders/solar/load_ejscreen.py).

This integration is a two-step lookup:
  1. Census Geocoder API → 12-digit block group GEOID for (lat, lng).
  2. SELECT … FROM ejscreen_blockgroups WHERE id = $1.

Verified 2026-06-05 — loader populated 243,022 rows across 56 states/territories.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import httpx

CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
)
BENCHMARK = "Public_AR_Current"
VINTAGE = "Current_Current"


async def geocode_block_group(
    client: httpx.AsyncClient, *, latitude: float, longitude: float
) -> str | None:
    """Return the 12-digit Census block group GEOID containing the point,
    or None if outside US Census coverage."""
    r = await client.get(
        CENSUS_GEOCODER_URL,
        params={
            "x": longitude,
            "y": latitude,
            "benchmark": BENCHMARK,
            "vintage":   VINTAGE,
            "format":    "json",
            "layers":    "Census Block Groups",
        },
    )
    r.raise_for_status()
    data = r.json()
    bgs = (
        data.get("result", {})
            .get("geographies", {})
            .get("Census Block Groups") or []
    )
    if not bgs:
        return None
    geoid = bgs[0].get("GEOID")
    return geoid if geoid and len(geoid) == 12 else None


# Columns we surface — state-percentiles for the EJ indicators that matter to
# solar siting (community-impact context).
_OUT_COLS = [
    "id", "state_name", "st_abbrev", "cnty_name", "acstotpop",
    "p_demogidx_2", "p_demogidx_5",
    "p_peopcolorpct", "p_lowincpct", "p_unemppct", "p_disabilitypct",
    "p_pm25", "p_ozone", "p_dslpm", "p_ptraf",
    "p_ldpnt", "p_pnpl", "p_prmp", "p_ptsdf", "p_dwater",
]


async def ejscreen_at_point(
    pool: asyncpg.Pool,
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
) -> dict[str, Any] | None:
    """Returns the loaded EJScreen indicators for the block group containing
    the point, or None if the geocoder can't resolve it or the block group
    isn't in the loaded dataset (e.g. tribal/military census areas)."""
    geoid = await geocode_block_group(client, latitude=latitude, longitude=longitude)
    if not geoid:
        return None
    cols = ", ".join(_OUT_COLS)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {cols} FROM ejscreen_blockgroups WHERE id = $1", geoid,
        )
    if row is None:
        return {"block_group_geoid": geoid, "found_in_dataset": False}
    out = {"block_group_geoid": geoid, "found_in_dataset": True, **dict(row)}
    return out
