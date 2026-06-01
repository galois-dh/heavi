"""USDA Soil Data Access (SDA) — national SSURGO via Tabular SQL.

POST JSON with a T-SQL query that uses SDA_Get_Mukey_from_intersection_with_WktWgs84
to resolve a point's mapunit, then joins the component table for drainage class,
hydric rating, and depth-to-water. Works nationally — no AOI clipping required.

Verified 2026-06-05 at Kern coord → returned mukey=463785 / 'Urban land' /
drainage=None / hydric=No (urban-classed cell, soil characteristics suppressed).
"""

from __future__ import annotations

from typing import Any

import httpx

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"

# Top-component SQL (highest comppct_r) for the mapunit at the point.
_SQL_TEMPLATE = (
    "SELECT TOP 1 mu.mukey, mu.muname, c.compname, c.compkind, c.comppct_r, "
    "c.drainagecl, c.hydricrating, c.taxclname, "
    "(SELECT MIN(ch.hzdept_r) FROM chorizon ch WHERE ch.cokey = c.cokey)"
    " AS top_horizon_depth_cm, "
    "(SELECT MAX(ch.hzdepb_r) FROM chorizon ch WHERE ch.cokey = c.cokey)"
    " AS bottom_horizon_depth_cm "
    "FROM mapunit mu "
    "INNER JOIN component c ON c.mukey = mu.mukey "
    "WHERE mu.mukey IN (SELECT mukey FROM "
    "SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lng} {lat})')) "
    "ORDER BY c.comppct_r DESC"
)


async def sda_point(
    client: httpx.AsyncClient, *, latitude: float, longitude: float
) -> dict[str, Any] | None:
    """Return the dominant soil component at the point, or None if the SDA
    didn't return a mapunit (e.g. ocean / outside CONUS / data gap)."""
    payload = {
        "format": "json+columnname",
        "query": _SQL_TEMPLATE.format(lng=longitude, lat=latitude),
    }
    r = await client.post(SDA_URL, json=payload)
    r.raise_for_status()
    data = r.json()
    table = data.get("Table") or []
    if len(table) < 2:
        return None  # only the column-header row → no data
    cols = table[0]
    row = table[1]
    rec = dict(zip(cols, row, strict=False))
    return {
        "mukey":           rec.get("mukey"),
        "mapunit_name":    rec.get("muname"),
        "component_name":  rec.get("compname"),
        "component_kind":  rec.get("compkind"),
        "component_pct":   _to_int(rec.get("comppct_r")),
        "drainage_class":  rec.get("drainagecl"),
        "hydric_rating":   rec.get("hydricrating"),
        "taxonomy":        rec.get("taxclname"),
        "top_horizon_depth_cm":    _to_int(rec.get("top_horizon_depth_cm")),
        "bottom_horizon_depth_cm": _to_int(rec.get("bottom_horizon_depth_cm")),
    }


def _to_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
