"""Constraint-layer GeoJSON for the map interface (Map Interface Spec, Step 5).

GET /constraints/{layer_id}?bbox=w,s,e,n&limit=N returns a GeoJSON
FeatureCollection of the requested constraint layer within the bounding box.

PostGIS-backed layers (transmission, substations, eia_solar, nwi) are queried
directly with a bbox && index filter. REST-backed layers (padus, nfhl) are
proxied to their ArcGIS FeatureServer/MapServer with f=geojson so the browser
avoids CORS. Small viewport volumes → client-side rendering, no tile server.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import httpx

# PostGIS-backed layers: layer_id → (table, geometry_column).
_POSTGIS_LAYERS: dict[str, tuple[str, str]] = {
    "transmission": ("solar_transmission_lines", "geometry"),
    "substations":  ("substations_osm_us", "geometry"),
    "eia_solar":    ("solar_eia_installations", "geometry"),
    "nwi":          ("solar_wetlands_ca", "geometry"),
    "interconnection_queue": ("interconnection_queue", "geometry"),
}

# REST-backed layers proxied to ArcGIS (envelope query, geojson out).
_REST_LAYERS: dict[str, dict[str, str]] = {
    "padus": {
        "url": (
            "https://services.arcgis.com/v01gqwM5QqNysAAi/ArcGIS/rest/services/"
            "PADUS_Protected_Areas_National/FeatureServer/0/query"
        ),
        "out_fields": "Unit_Nm,Category,Pub_Access,GAP_Sts,MngNm_Desc,DesTp_Desc",
    },
    "nfhl": {
        "url": (
            "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/"
            "MapServer/28/query"
        ),
        "out_fields": "FLD_ZONE,ZONE_SUBTY,STATIC_BFE",
    },
}

SUPPORTED_LAYERS = sorted([*_POSTGIS_LAYERS, *_REST_LAYERS])


def parse_bbox(bbox: str) -> tuple[float, float, float, float]:
    """Parse 'west,south,east,north' → (w, s, e, n). Raises ValueError."""
    parts = [p.strip() for p in (bbox or "").split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be 'west,south,east,north'")
    w, s, e, n = (float(p) for p in parts)
    if w >= e or s >= n:
        raise ValueError("bbox must have west<east and south<north")
    return w, s, e, n


async def _postgis_features(
    pool: asyncpg.Pool, table: str, geom_col: str,
    bbox: tuple[float, float, float, float], limit: int,
) -> list[dict[str, Any]]:
    w, s, e, n = bbox
    # to_jsonb(t) minus the geometry/geog columns → clean feature properties.
    sql = f"""
        SELECT jsonb_build_object(
            'type', 'Feature',
            'geometry', ST_AsGeoJSON(t.{geom_col})::jsonb,
            'properties', (to_jsonb(t) - '{geom_col}' - 'geog')
        ) AS feature
        FROM {table} t
        WHERE t.{geom_col} && ST_MakeEnvelope($1, $2, $3, $4, 4326)
        LIMIT $5
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, w, s, e, n, limit)
    return [r["feature"] for r in rows]


async def _rest_features(
    layer_id: str, bbox: tuple[float, float, float, float], limit: int,
) -> list[dict[str, Any]]:
    cfg = _REST_LAYERS[layer_id]
    w, s, e, n = bbox
    params = {
        "geometry":          f"{w},{s},{e},{n}",
        "geometryType":      "esriGeometryEnvelope",
        "inSR":              "4326",
        "spatialRel":        "esriSpatialRelIntersects",
        "outFields":         cfg["out_fields"],
        "returnGeometry":    "true",
        "outSR":             "4326",
        "f":                 "geojson",
        "resultRecordCount": str(limit),
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(cfg["url"], params=params,
                                  headers={"User-Agent": "Heavi/0.1 (map-constraints)"})
            data = r.json()
    except Exception:  # noqa: BLE001
        return []
    feats = data.get("features") if isinstance(data, dict) else None
    return feats or []


async def get_constraint_geojson(
    pool: asyncpg.Pool, layer_id: str, bbox: str, limit: int = 5000,
) -> dict[str, Any]:
    """Return a GeoJSON FeatureCollection for `layer_id` within `bbox`."""
    box = parse_bbox(bbox)
    limit = max(1, min(int(limit), 10000))
    if layer_id in _POSTGIS_LAYERS:
        table, geom_col = _POSTGIS_LAYERS[layer_id]
        features = await _postgis_features(pool, table, geom_col, box, limit)
    elif layer_id in _REST_LAYERS:
        features = await _rest_features(layer_id, box, limit)
    else:
        raise KeyError(layer_id)
    return {
        "type": "FeatureCollection",
        "layer_id": layer_id,
        "bbox": list(box),
        "feature_count": len(features),
        "features": features,
    }
