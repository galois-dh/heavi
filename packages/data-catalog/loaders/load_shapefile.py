"""Shapefile → PostGIS loader.

Usage:
    python -m loaders.load_shapefile \
        --path /data/parcels.shp \
        --table parcels
"""

from __future__ import annotations

import argparse
import os
import sys

import geopandas as gpd
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()


def load(path: str, table_name: str, srid: int = 4326) -> int:
    """Load a Shapefile into PostGIS. Returns row count."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {path} ...")
    gdf = gpd.read_file(path)

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
    parser = argparse.ArgumentParser(description="Load Shapefile into PostGIS")
    parser.add_argument("--path", required=True, help="Path to .shp file")
    parser.add_argument("--table", required=True, help="Target PostGIS table name")
    parser.add_argument("--srid", type=int, default=4326, help="Target SRID (default 4326)")
    args = parser.parse_args()
    load(args.path, args.table, args.srid)


if __name__ == "__main__":
    main()
