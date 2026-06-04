"""NIFC Interagency Fire Perimeter History — historical burn frequency.

A national ArcGIS REST source used as a *proxy* for wildfire burn probability
when FSim is unavailable (Data Tree Completeness Spec). A spatial query within a
local fire-shed buffer returns historical perimeters; fire_frequency =
distinct_fire_count / years_of_record is a crude but real signal — locations
whose vicinity has burned repeatedly have demonstrably higher future risk.

Note: the exact query point is often unburned (between perimeters), so a buffer
(default 5 km) captures the local fire-shed. Field names are INCIDENT /
FIRE_YEAR / GIS_ACRES (verified 2026-06-08; the spec's attr_* names were stale).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

ENDPOINT = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0/query"
)
YEARS_OF_RECORD = 45  # 1980-2024
DEFAULT_BUFFER_M = 5000


async def query_nifc_perimeters(
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
    buffer_m: int = DEFAULT_BUFFER_M,
) -> dict[str, Any] | None:
    """Return historical fire frequency near a point, or None on failure.

    Result: {fire_count, fire_frequency, years_of_record, fires:[{name,year,acres}]}.
    """
    params = {
        "geometry": json.dumps({"x": longitude, "y": latitude,
                                "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "distance": str(buffer_m),
        "units": "esriSRUnit_Meter",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "INCIDENT,FIRE_YEAR,FIRE_YEAR_INT,GIS_ACRES",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        r = await client.get(ENDPOINT, params=params,
                             headers={"User-Agent": "Heavi/0.1 (wildfire)"})
        data = r.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None
    feats = data.get("features") or []
    seen: set[tuple[str, Any]] = set()
    fires: list[dict[str, Any]] = []
    for f in feats:
        a = f.get("attributes") or {}
        name = a.get("INCIDENT")
        year = a.get("FIRE_YEAR_INT") or a.get("FIRE_YEAR")
        key = ((name or "").strip().upper(), year)
        if key in seen:
            continue
        seen.add(key)
        fires.append({"name": name, "year": year, "acres": a.get("GIS_ACRES")})
    count = len(fires)
    return {
        "fire_count": count,
        "fire_frequency": round(count / YEARS_OF_RECORD, 4),
        "years_of_record": YEARS_OF_RECORD,
        "buffer_m": buffer_m,
        "fires": sorted(fires, key=lambda x: (x["year"] or 0), reverse=True)[:10],
    }
