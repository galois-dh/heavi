"""Generic GeoJSON → PostGIS loader.

Usage:
    python -m loaders.load_geojson \
        --url https://example.com/data.geojson \
        --table my_layer \
        --srid 4326
"""

from __future__ import annotations

import argparse
import os
import sys

import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


def load(url_or_path: str, table_name: str, srid: int = 4326) -> int:
    """Load a GeoJSON file or URL into PostGIS. Returns row count."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {url_or_path} ...")
    gdf = gpd.read_file(url_or_path)

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=srid)
    elif gdf.crs.to_epsg() != srid:
        gdf = gdf.to_crs(epsg=srid)

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} features to table '{table_name}' ...")
    gdf.to_postgis(table_name, engine, if_exists="replace", index=False)

    print("Done.")
    return len(gdf)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load GeoJSON into PostGIS")
    parser.add_argument("--url", required=True, help="URL or local path to GeoJSON")
    parser.add_argument("--table", required=True, help="Target PostGIS table name")
    parser.add_argument("--srid", type=int, default=4326, help="Target SRID (default 4326)")
    args = parser.parse_args()
    load(args.url, args.table, args.srid)


if __name__ == "__main__":
    main()
