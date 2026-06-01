"""Load Google's Inundation History dataset into PostGIS.

Source: gs://flood-forecasting/inundation_history (public bucket, CC-BY-4.0)
Format: ~1,629 GeoJSON tiles, ~1 GB total, lat/lng-tiled
Layers per tile: High_risk (≥5% wet), Medium_risk (≥1%), Low_risk (≥0.5%)
Coverage: lat -39 to 43, lng -125 to 170
  ⚠ Excludes US territory above ~43°N (northern WA/MT/ND/MN/WI/MI/NY/VT/NH/ME).

Verified 2026-06-05 via storage.googleapis.com REST listing — bucket is anon-
readable; HTTPS access works without gsutil.

Target table: flood_inundation_history
Schema: id PK, risk_level text (high|medium|low), wet_freq_pct_min float,
        tile_min_lat/lng/max_lat/max_lng float8, geometry MULTIPOLYGON(4326)

NOTE: tiles are world-wide. We filter to US bbox (-125, 24, -66, 50) at load
time to skip the ~70% of files outside North America.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import geopandas as gpd
import psycopg2
import requests
from dotenv import load_dotenv
from shapely.geometry import MultiPolygon, shape
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

TABLE_NAME = "flood_inundation_history"
BUCKET = "flood-forecasting"
PREFIX = "inundation_history/data/"
LIST_URL = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"
DOWNLOAD_BASE = f"https://storage.googleapis.com/{BUCKET}/"

# US conterminous bbox (rough — keeps coastal islands, drops Alaska/Hawaii since
# this dataset's lat ceiling of 43° already excludes most of Alaska anyway).
US_BBOX = (-125.0, 24.0, -66.0, 49.0)

# Each tile filename encodes its corners: inundation_history_{min_lat:.3f}_{min_lng:.3f}_{max_lat:.3f}_{max_lng:.3f}.geojson
TILE_NAME_PARTS = 4  # 4 floats after the stem


def _parse_tile_bbox(name: str) -> tuple[float, float, float, float] | None:
    base = name.split("/")[-1].replace(".geojson", "")
    parts = base.split("_")[-TILE_NAME_PARTS:]
    try:
        nums = [float(p) for p in parts]
        return (nums[1], nums[0], nums[3], nums[2])  # min_lng, min_lat, max_lng, max_lat
    except (ValueError, IndexError):
        return None


def _bbox_intersects(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def list_us_tiles() -> list[tuple[str, tuple[float, float, float, float]]]:
    """Page through the GCS listing, returning only US-overlapping tiles."""
    tiles: list[tuple[str, tuple[float, float, float, float]]] = []
    token: str | None = None
    while True:
        params = {"prefix": PREFIX, "maxResults": 1000}
        if token:
            params["pageToken"] = token
        url = f"{LIST_URL}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
        for item in data.get("items", []):
            name = item.get("name", "")
            if not name.endswith(".geojson"):
                continue
            bb = _parse_tile_bbox(name)
            if bb and _bbox_intersects(bb, US_BBOX):
                tiles.append((name, bb))
        token = data.get("nextPageToken")
        if not token:
            break
    return tiles


def fetch_tile(name: str) -> dict:
    url = DOWNLOAD_BASE + name
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def tile_records(geojson: dict, tile_bbox: tuple[float, float, float, float]) -> list[dict]:
    """Each tile contains 3 named features (high/medium/low). Flatten."""
    out: list[dict] = []
    feats = geojson.get("features") or []
    for f in feats:
        props = f.get("properties") or {}
        name = (props.get("name") or "").lower()
        if "high" in name:
            risk_level, min_pct = "high", 5.0
        elif "medium" in name:
            risk_level, min_pct = "medium", 1.0
        elif "low" in name:
            risk_level, min_pct = "low", 0.5
        else:
            continue
        try:
            geom = shape(f["geometry"])
        except Exception:  # noqa: BLE001
            continue
        if geom.is_empty:
            continue
        # Coerce to MultiPolygon for column-type consistency (some tiles are plain Polygon).
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        elif geom.geom_type != "MultiPolygon":
            continue  # ignore points / lines
        out.append({
            "risk_level":        risk_level,
            "wet_freq_pct_min":  min_pct,
            "tile_min_lat":      tile_bbox[1],
            "tile_min_lng":      tile_bbox[0],
            "tile_max_lat":      tile_bbox[3],
            "tile_max_lng":      tile_bbox[2],
            "geometry":          geom,
        })
    return out


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr); sys.exit(1)

    print("Listing US-overlapping tiles in gs://flood-forecasting/inundation_history/data/ ...")
    tiles = list_us_tiles()
    print(f"  {len(tiles)} US tiles")
    if not tiles:
        print("ERROR: no tiles found", file=sys.stderr); sys.exit(1)

    engine = create_engine(database_url)
    # Drop + recreate to keep loads idempotent.
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME} CASCADE"))
    print(f"  Dropped {TABLE_NAME} (if it existed); will recreate.")

    total_rows = 0
    t0 = time.perf_counter()
    for i, (name, bbox) in enumerate(tiles, 1):
        try:
            data = fetch_tile(name)
            recs = tile_records(data, bbox)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(tiles)}] FAIL {name}: {e}", file=sys.stderr)
            continue
        if not recs:
            continue
        gdf = gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:4326")
        mode = "replace" if total_rows == 0 else "append"
        gdf.to_postgis(TABLE_NAME, engine, if_exists=mode, index=False)
        total_rows += len(gdf)
        if i % 25 == 0 or i == len(tiles):
            elapsed = time.perf_counter() - t0
            rate = i / max(elapsed, 0.1)
            eta = (len(tiles) - i) / rate
            print(f"  [{i}/{len(tiles)}]  rows so far: {total_rows:,}  ({rate:.1f} tile/s, ETA {eta:.0f}s)")

    print(f"\nTotal rows: {total_rows:,}  elapsed: {time.perf_counter()-t0:.1f}s")

    # Indexes
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geom "
            f"ON {TABLE_NAME} USING GIST (geometry)"))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_risk "
            f"ON {TABLE_NAME} (risk_level)"))
    print("Indexes created.")

    # Register in catalog_layers
    bounds_q = (
        f"SELECT ST_XMin(ST_Extent(geometry)), ST_YMin(ST_Extent(geometry)), "
        f"ST_XMax(ST_Extent(geometry)), ST_YMax(ST_Extent(geometry)) FROM {TABLE_NAME}"
    )
    with engine.connect() as conn:
        xmin, ymin, xmax, ymax = list(conn.execute(text(bounds_q)).first())  # type: ignore[misc]
    catalog_conn = psycopg2.connect(database_url)
    catalog_conn.autocommit = True
    cur = catalog_conn.cursor()
    cur.execute(
        """
        INSERT INTO catalog_layers (name, description, source_url, geometry_type, bbox, row_count, updated_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, now())
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description, source_url = EXCLUDED.source_url,
            geometry_type = EXCLUDED.geometry_type, bbox = EXCLUDED.bbox,
            row_count = EXCLUDED.row_count, updated_at = now();
        """,
        (
            TABLE_NAME,
            "Google Inundation History — satellite-derived flood frequency from GLAD "
            "(1999-2020). High_risk (≥5% wet), Medium_risk (≥1%), Low_risk (≥0.5%). "
            "Coverage lat -39 to 43, lng -125 to 170 — excludes US territory above ~43°N. "
            "License: CC-BY-4.0.",
            "gs://flood-forecasting/inundation_history",
            "MultiPolygon",
            json.dumps({"minx": xmin, "miny": ymin, "maxx": xmax, "maxy": ymax}),
            total_rows,
        ),
    )
    cur.close(); catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers. Done.")


if __name__ == "__main__":
    main()
