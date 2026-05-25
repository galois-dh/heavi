"""Load Microsoft Building Footprints for Sonoma County, CA.

Downloads the legacy USBuildingFootprints v2 California zip, extracts the
GeoJSON, and uses pyogrio's bbox spatial filter so we only materialize features
inside the Sonoma County bounding box. EPSG:4326 in source and target.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import psycopg2
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "wildfire_ms_footprints"
SOURCE_URL = (
    "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/"
    "California.geojson.zip"
)
# Sonoma County bounding box (lon_min, lat_min, lon_max, lat_max), padded.
SONOMA_BBOX = (-123.55, 38.05, -122.35, 38.86)


def download_zip(dest: Path) -> None:
    print(f"Downloading MS California footprints → {dest} (~466 MB) ...")
    with requests.get(SOURCE_URL, stream=True, timeout=1800) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=8 << 20):
                f.write(chunk)
    print(f"  {dest.stat().st_size / 1_000_000:.1f} MB downloaded")


def extract(zip_path: Path, out_dir: Path) -> Path:
    print(f"Extracting {zip_path.name} ...")
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        geojson_members = [m for m in members if m.lower().endswith(".geojson")]
        if not geojson_members:
            raise RuntimeError(f"No GeoJSON found in zip; members: {members}")
        member = geojson_members[0]
        zf.extract(member, out_dir)
    out = out_dir / member
    print(f"  extracted {out} ({out.stat().st_size / 1_000_000:.1f} MB)")
    return out


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    cache_zip = Path("/tmp/ms_california.geojson.zip")
    cache_geo = Path("/tmp/ms_california.geojson")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        if cache_geo.exists() and cache_geo.stat().st_size > 1_000_000_000:
            print(f"Using cached {cache_geo}")
            geo_path = cache_geo
        else:
            if cache_zip.exists() and cache_zip.stat().st_size > 100_000_000:
                print(f"Using cached zip {cache_zip}")
                zip_path = cache_zip
            else:
                zip_path = tmp_dir / "california.zip"
                download_zip(zip_path)
                shutil.copy(zip_path, cache_zip)
            extracted = extract(zip_path, tmp_dir)
            # Keep extracted GeoJSON cached for re-runs.
            shutil.copy(extracted, cache_geo)
            geo_path = cache_geo

        print(f"Reading bbox {SONOMA_BBOX} via pyogrio ...")
        gdf = gpd.read_file(geo_path, engine="pyogrio", bbox=SONOMA_BBOX)
        print(f"  {len(gdf)} footprints in bbox")

    if gdf.empty:
        print("ERROR: no footprints in Sonoma bbox", file=sys.stderr)
        sys.exit(1)

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)

    gdf.columns = [c.lower() for c in gdf.columns]
    # Drop empty/null geometries.
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    engine = create_engine(database_url)
    print(f"Writing {len(gdf)} polygons to '{TABLE_NAME}' ...")
    chunk = 50_000
    for i in range(0, len(gdf), chunk):
        mode = "replace" if i == 0 else "append"
        gdf.iloc[i : i + chunk].to_postgis(TABLE_NAME, engine, if_exists=mode, index=False)
        print(f"  wrote {min(i + chunk, len(gdf))}/{len(gdf)}")

    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geom "
                f"ON {TABLE_NAME} USING GIST (geometry);"
            )
        )
        conn.commit()
    print("Spatial index created.")

    bounds = gdf.total_bounds
    bbox = {
        "minx": float(bounds[0]),
        "miny": float(bounds[1]),
        "maxx": float(bounds[2]),
        "maxy": float(bounds[3]),
    }
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
            "Microsoft USBuildingFootprints v2 — Sonoma County subset "
            "(ML-derived polygon footprints).",
            SOURCE_URL,
            "Polygon",
            json.dumps(bbox),
            len(gdf),
        ),
    )
    cur.close()
    catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers. Done.")


if __name__ == "__main__":
    main()
