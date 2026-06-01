"""USFWS Final Critical Habitat — national ArcGIS FeatureServer.

Verified 2026-06-05: services.arcgis.com FeatureServer hosts 802 designated
habitat polygons covering all listed species. Per-point ST_Intersects via
the ESRI geometry parameter returns matching units.

Returns the species (common + scientific name), unit name, listing entity,
and overlap area in m² if available.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

URL = (
    "https://services.arcgis.com/QVENGdaPbd4LUkLV/ArcGIS/rest/services/"
    "USFWS_Critical_Habitat/FeatureServer/0/query"
)


async def critical_habitat_in_envelope(
    client: httpx.AsyncClient,
    *,
    west: float, south: float, east: float, north: float,
    max_records: int = 50,
) -> list[dict[str, Any]]:
    """Return critical-habitat units intersecting an envelope, with geometry
    (GeoJSON) so callers can compute intersection area. Empty list → no
    designated habitat in the bbox."""
    geom = json.dumps({
        "xmin": west, "ymin": south, "xmax": east, "ymax": north,
        "spatialReference": {"wkid": 4326},
    })
    params = {
        "geometry":         geom,
        "geometryType":     "esriGeometryEnvelope",
        "inSR":             "4326",
        "spatialRel":       "esriSpatialRelIntersects",
        "outFields":        ("comname,sciname,spcode,unit,subunit,"
                             "unitname,listing_st,fedreg_no,pubdate"),
        "returnGeometry":   "true",
        "outSR":            "4326",
        "f":                "geojson",
        "resultRecordCount": max_records,
    }
    r = await client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    return data.get("features") or []


async def critical_habitat_at_point(
    client: httpx.AsyncClient, *, latitude: float, longitude: float
) -> list[dict[str, Any]]:
    """Return the list of designated critical-habitat units intersecting the
    point (one record per species/unit overlap). Empty list → no overlap.
    """
    geometry = json.dumps({
        "x": longitude, "y": latitude,
        "spatialReference": {"wkid": 4326},
    })
    params = {
        "geometry": geometry,
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "comname,sciname,spcode,unit,subunit,unitname,listing_st,fedreg_no,pubdate",
        "returnGeometry": "false",
        "f": "json",
    }
    r = await client.get(URL, params=params)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features") or []
    return [
        {
            "common_name":      a.get("comname"),
            "scientific_name":  a.get("sciname"),
            "species_code":     a.get("spcode"),
            "unit":             a.get("unit"),
            "subunit":          a.get("subunit"),
            "unit_name":        a.get("unitname"),
            "listing_status":   a.get("listing_st"),
            "federal_register": a.get("fedreg_no"),
            "publication_date": a.get("pubdate"),
        }
        for f in feats
        if (a := f.get("attributes") or {})
    ]
