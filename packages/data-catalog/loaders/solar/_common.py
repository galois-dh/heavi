"""Shared helpers for the solar site-suitability loaders.

Keeps each loader thin: DB engine, ArcGIS FeatureServer pagination (with
reprojection to EPSG:4326), bulk write-to-PostGIS with a GIST index, and
catalog_layers registration with source URL + download date.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import psycopg2
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[4] / ".env")


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return url


def nrel_api_key() -> str:
    key = os.getenv("NREL_API_KEY")
    if not key:
        raise RuntimeError("NREL_API_KEY not set")
    return key


def fetch_arcgis_layer(
    layer_url: str,
    *,
    where: str = "1=1",
    out_fields: str = "*",
    page_size: int = 2000,
    out_sr: int = 4326,
    geometry: str | None = None,
    geometry_type: str | None = None,
    in_sr: int | None = None,
    max_pages: int | None = None,
) -> gpd.GeoDataFrame:
    """Page through an ArcGIS FeatureServer/MapServer layer's /query endpoint
    and return a GeoDataFrame in EPSG:out_sr.

    The service is asked for GeoJSON directly with outSR=out_sr so PostGIS
    gets 4326 regardless of the service's native SR (HIFLD layers are
    Web Mercator 3857). Pagination via resultOffset until a short page.
    """
    base = layer_url.rstrip("/") + "/query"
    all_features: list[dict] = []
    offset = 0
    page = 0
    while True:
        params: dict[str, Any] = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": out_sr,
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "orderByFields": "OBJECTID",
        }
        if geometry:
            params["geometry"] = geometry
            params["geometryType"] = geometry_type or "esriGeometryEnvelope"
            params["inSR"] = in_sr or 4326
            params["spatialRel"] = "esriSpatialRelIntersects"
        r = requests.get(base, params=params, timeout=180)
        r.raise_for_status()
        data = r.json()
        feats = data.get("features", [])
        if not feats:
            break
        all_features.extend(feats)
        print(f"    page {page} (+{len(feats)}, total {len(all_features)})")
        page += 1
        if len(feats) < page_size:
            break
        if max_pages is not None and page >= max_pages:
            break
        offset += page_size

    if not all_features:
        return gpd.GeoDataFrame(geometry=[], crs=f"EPSG:{out_sr}")
    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": all_features}, crs=f"EPSG:{out_sr}"
    )
    return gdf


def write_postgis(
    gdf: gpd.GeoDataFrame,
    table_name: str,
    *,
    chunk_size: int = 20_000,
    geom_index: bool = True,
    extra_indexes: list[str] | None = None,
) -> int:
    """Write a GeoDataFrame to PostGIS (replace), lowercase columns, add a
    GIST index on geometry. Returns the row count written."""
    if gdf.empty:
        print(f"  WARNING: {table_name} GeoDataFrame is empty; nothing written.")
        return 0
    gdf = gdf.copy()
    gdf.columns = [c.lower() for c in gdf.columns]
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    # Drop ESRI bookkeeping columns that don't reload cleanly.
    for junk in ("shape__length", "shape__area", "shape_length", "shape_area"):
        if junk in gdf.columns:
            gdf = gdf.drop(columns=[junk])

    engine = create_engine(database_url())
    n = len(gdf)
    for i in range(0, n, chunk_size):
        mode = "replace" if i == 0 else "append"
        gdf.iloc[i : i + chunk_size].to_postgis(table_name, engine, if_exists=mode, index=False)
        print(f"    wrote {min(i + chunk_size, n)}/{n}")
    with engine.connect() as conn:
        if geom_index:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS idx_{table_name}_geom "
                    f"ON {table_name} USING GIST (geometry)"
                )
            )
        for stmt in extra_indexes or []:
            conn.execute(text(stmt))
        conn.commit()
    return n


def register_layer(
    table_name: str,
    description: str,
    source_url: str,
    geometry_type: str,
    gdf: gpd.GeoDataFrame | None = None,
    row_count: int | None = None,
) -> None:
    """Upsert a row in catalog_layers, logging source + download date."""
    bbox = None
    if gdf is not None and not gdf.empty:
        b = gdf.total_bounds
        bbox = {"minx": float(b[0]), "miny": float(b[1]), "maxx": float(b[2]), "maxy": float(b[3])}
    n = row_count if row_count is not None else (len(gdf) if gdf is not None else 0)
    desc = f"{description} [source_downloaded={date.today().isoformat()}]"
    conn = psycopg2.connect(database_url())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO catalog_layers (name, description, source_url, geometry_type, bbox, row_count, updated_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, now())
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description, source_url = EXCLUDED.source_url,
            geometry_type = EXCLUDED.geometry_type, bbox = EXCLUDED.bbox,
            row_count = EXCLUDED.row_count, updated_at = now();
        """,
        (table_name, desc, source_url, geometry_type, json.dumps(bbox) if bbox else None, n),
    )
    cur.close()
    conn.close()
    print(f"  registered '{table_name}' in catalog_layers ({n} rows)")


# California + Kern County extents (EPSG:4326) reused across loaders.
CALIFORNIA_BBOX = (-124.48, 32.53, -114.13, 42.01)  # minlng, minlat, maxlng, maxlat
KERN_BBOX = (-120.20, 34.79, -117.61, 35.80)
