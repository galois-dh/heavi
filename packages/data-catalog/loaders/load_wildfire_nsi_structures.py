"""Load USACE National Structures Inventory for Sonoma County (FIPS 06097).

Note: the canonical NSI endpoint as of 2025+ is /nsiapi/structures (not
/nsiapi/20/structure as some older docs suggest). We default to the working
path; override via env if the upstream URL changes.
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

TABLE_NAME = "wildfire_nsi_structures"
SONOMA_FIPS = "06097"
NSI_URL = os.getenv(
    "NSI_URL",
    f"https://nsi.sec.usace.army.mil/nsiapi/structures?fips={SONOMA_FIPS}&fmt=fc",
)


def download(dest: Path) -> None:
    print(f"Downloading NSI (Sonoma, FIPS {SONOMA_FIPS}) → {dest} ...")
    with requests.get(NSI_URL, stream=True, timeout=600) as r:
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
        tmp_path = Path(tmp) / "nsi.geojson"
        cached = Path("/tmp/nsi_sonoma.json")
        if cached.exists() and cached.stat().st_size > 50_000_000:
            src = cached
            print(f"Using cached {cached}")
        else:
            download(tmp_path)
            src = tmp_path

        print("Reading GeoJSON with pyogrio ...")
        gdf = gpd.read_file(src, engine="pyogrio")

    print(f"  {len(gdf)} structures, CRS {gdf.crs}")
    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)

    gdf.columns = [c.lower() for c in gdf.columns]

    engine = create_engine(database_url)
    print(f"Writing {len(gdf)} structures to '{TABLE_NAME}' ...")
    chunk = 25_000
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
        if "occtype" in gdf.columns:
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_occtype "
                    f"ON {TABLE_NAME} (occtype);"
                )
            )
        conn.commit()
    print("Indexes created.")

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
            "USACE National Structures Inventory (NSI) v2 — Sonoma County, CA "
            "(FIPS 06097). Per-structure occupancy, replacement value, foundation, "
            "and story-count attributes.",
            NSI_URL,
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
