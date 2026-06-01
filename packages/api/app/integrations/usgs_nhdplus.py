"""USGS NHDPlus High Resolution — national ArcGIS MapServer (on-demand).

Verified 2026-06-05: hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer
exposes 13 layers. We use:

  layer 12  WBDHU12               — HUC-12 watershed polygons
  layer 3   NetworkNHDFlowline    — connected flowlines (stream order, name, GNIS)

For a given (lat, lng) we return the containing HUC-12 + nearest flowline
within a search radius. Avoids needing the 22 GB national NHDPlus HR GDB.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

ROOT = "https://hydro.nationalmap.gov/arcgis/rest/services/NHDPlus_HR/MapServer"
HUC12_LAYER = 12
FLOWLINE_LAYER = 3


def _point_geom(lat: float, lng: float) -> str:
    return json.dumps({"x": lng, "y": lat, "spatialReference": {"wkid": 4326}})


def _envelope_geom(lat: float, lng: float, half_deg: float) -> str:
    return json.dumps({
        "xmin": lng - half_deg, "ymin": lat - half_deg,
        "xmax": lng + half_deg, "ymax": lat + half_deg,
        "spatialReference": {"wkid": 4326},
    })


async def nhdplus_at_point(
    client: httpx.AsyncClient,
    *,
    latitude: float,
    longitude: float,
    flowline_search_deg: float = 0.02,  # ~2 km
) -> dict[str, Any]:
    """Return {huc12, watershed_name, flowlines: [...nearest first]}.
    The flowlines list is empty if no NetworkNHDFlowline is within the search
    window — try a larger ``flowline_search_deg`` for sparsely-gauged areas.
    """
    huc = await _query_huc12(client, latitude, longitude)
    flowlines = await _query_flowlines(client, latitude, longitude, flowline_search_deg)
    return {
        "huc12":          huc.get("huc12") if huc else None,
        "watershed_name": huc.get("watershed_name") if huc else None,
        "states":         huc.get("states") if huc else None,
        "flowlines":      flowlines,
    }


async def _query_huc12(
    client: httpx.AsyncClient, lat: float, lng: float
) -> dict[str, Any] | None:
    r = await client.get(
        f"{ROOT}/{HUC12_LAYER}/query",
        params={
            "geometry":      _point_geom(lat, lng),
            "geometryType":  "esriGeometryPoint",
            "inSR":          "4326",
            "spatialRel":    "esriSpatialRelIntersects",
            "outFields":     "huc12,name,states,areasqkm",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    r.raise_for_status()
    feats = (r.json().get("features") or [])
    if not feats:
        return None
    a = feats[0].get("attributes") or {}
    return {
        "huc12":          a.get("huc12"),
        "watershed_name": a.get("name"),
        "states":         a.get("states"),
        "area_sq_km":     a.get("areasqkm"),
    }


async def _query_flowlines(
    client: httpx.AsyncClient, lat: float, lng: float, half_deg: float
) -> list[dict[str, Any]]:
    r = await client.get(
        f"{ROOT}/{FLOWLINE_LAYER}/query",
        params={
            "geometry":      _envelope_geom(lat, lng, half_deg),
            "geometryType":  "esriGeometryEnvelope",
            "inSR":          "4326",
            "spatialRel":    "esriSpatialRelIntersects",
            "outFields":     "gnis_name,permanent_identifier,streamorde,lengthkm,ftype,fcode",
            "returnGeometry": "false",
            "f": "json",
            "resultRecordCount": 25,
        },
    )
    r.raise_for_status()
    feats = (r.json().get("features") or [])
    return [
        {
            "name":             a.get("gnis_name"),
            "permanent_id":     a.get("permanent_identifier"),
            "stream_order":     a.get("streamorde"),
            "length_km":        a.get("lengthkm"),
            "feature_type":     a.get("ftype"),
            "feature_code":     a.get("fcode"),
        }
        for f in feats
        if (a := f.get("attributes") or {})
    ]
