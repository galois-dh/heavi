"""USGS PAD-US (Protected Areas Database) — national ArcGIS FeatureServer.

Verified 2026-06-05: PADUS_Protected_Areas_National hosts 306,082 polygons
nationally. Per-point ST_Intersects returns the protected area unit, its
manager, public access category, GAP status, and IUCN classification.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

URL = (
    "https://services.arcgis.com/v01gqwM5QqNysAAi/ArcGIS/rest/services/"
    "PADUS_Protected_Areas_National/FeatureServer/0/query"
)


async def padus_at_point(
    client: httpx.AsyncClient, *, latitude: float, longitude: float
) -> list[dict[str, Any]]:
    """Return all protected-area units intersecting the point. Empty list →
    not in a designated protected area."""
    geometry = json.dumps({
        "x": longitude, "y": latitude,
        "spatialReference": {"wkid": 4326},
    })
    params = {
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": (
            "Unit_Nm,Category,Pub_Access,GAP_Sts,IUCN_Cat,IUCN_Cat_Reclass,"
            "MngTp_Desc,MngNm_Desc,DesTp_Desc"
        ),
        "returnGeometry": "false",
        "f": "json",
    }
    r = await client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features") or []
    return [
        {
            "unit_name":          a.get("Unit_Nm"),
            "category":           a.get("Category"),
            "public_access":      a.get("Pub_Access"),
            "gap_status":         a.get("GAP_Sts"),
            "iucn_category":      a.get("IUCN_Cat"),
            "iucn_reclassified":  a.get("IUCN_Cat_Reclass"),
            "manager_type":       a.get("MngTp_Desc"),
            "manager_name":       a.get("MngNm_Desc"),
            "designation_type":   a.get("DesTp_Desc"),
        }
        for f in feats
        if (a := f.get("attributes") or {})
    ]
