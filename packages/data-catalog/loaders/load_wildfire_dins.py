"""Load CAL FIRE DINS (Damage Inspection) records for all of California.

Source: CNRA GeoJSON direct download. Source CRS is EPSG:6414 (California Albers,
NAD83(2011)); reprojected to EPSG:4326 before persistence so it matches the
rest of the catalog.

We keep all of California (filter to Sonoma at query time) — the DINS dataset
is small enough (~175 MB GeoJSON, ~130k point features) that it doesn't
warrant a county-level filter at load time, and we may want neighbour-county
records (Napa, Lake) for cross-fire calibration of the wildfire module.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import geopandas as gpd
import psycopg2
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "wildfire_dins"
SOURCE_URL = (
    "https://gis.data.cnra.ca.gov/api/download/v1/items/"
    "994d3dc4569640caadbbc3198d5a3da1/geojson?layers=0"
)


def download(dest: Path) -> None:
    print(f"Downloading DINS → {dest} ...")
    with requests.get(SOURCE_URL, stream=True, timeout=600) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            shutil.copyfileobj(r.raw, f)
    print(f"  {dest.stat().st_size / 1_000_000:.1f} MB")


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "dins.geojson"
        # Allow reuse of an already-downloaded copy at /tmp/dins.geojson for re-runs.
        cached = Path("/tmp/dins.geojson")
        if cached.exists() and cached.stat().st_size > 50_000_000:
            print(f"Using cached download at {cached}")
            src = cached
        else:
            download(tmp_path)
            src = tmp_path

        print("Reading GeoJSON with pyogrio ...")
        gdf = gpd.read_file(src, engine="pyogrio")

    print(f"  {len(gdf)} features, source CRS {gdf.crs}")
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        print("  Reprojecting to EPSG:4326 ...")
        gdf = gdf.to_crs(4326)

    gdf.columns = [c.lower() for c in gdf.columns]
    # Drop ESRI internal columns that won't reload cleanly.
    for drop_col in ("shape__length", "shape__area"):
        if drop_col in gdf.columns:
            gdf = gdf.drop(columns=[drop_col])

    engine = create_engine(database_url)
    print(f"Writing {len(gdf)} rows to '{TABLE_NAME}' ...")
    chunk = 20_000
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
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_incident "
                f"ON {TABLE_NAME} (incidentname);"
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_county "
                f"ON {TABLE_NAME} (county);"
            )
        )
        conn.commit()
    print("Indexes created (GIST geom, incidentname, county).")

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
            "CAL FIRE Damage Inspection (DINS) records — California statewide, "
            "per-structure damage assessments from post-fire field surveys.",
            SOURCE_URL,
            "Point",
            json.dumps(bbox),
            len(gdf),
        ),
    )
    cur.close()
    catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers. Done.")


if __name__ == "__main__":
    main()
