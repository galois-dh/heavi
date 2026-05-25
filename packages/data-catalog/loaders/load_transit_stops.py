"""Load transit stops from BART and AC Transit GTFS feeds.

Downloads GTFS zip files, parses stops.txt, and loads into PostGIS.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import zipfile

import geopandas as gpd
import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv
from shapely.geometry import Point
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_transit_stops"

GTFS_FEEDS = {
    "BART": "https://www.bart.gov/dev/schedules/google_transit.zip",
    "AC Transit": "https://www.actransit.org/sites/default/files/google_transit.zip",
}


def parse_gtfs_stops(zip_bytes: bytes, agency: str) -> pd.DataFrame:
    """Extract stops.txt from a GTFS zip and parse it."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        # stops.txt might be at root or in a subdirectory
        stops_file = next((n for n in names if n.endswith("stops.txt")), None)
        if not stops_file:
            print(f"  WARNING: No stops.txt found in {agency} GTFS feed")
            return pd.DataFrame()

        with zf.open(stops_file) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
            rows = list(reader)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Standardize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # Filter to actual stops (location_type 0 or empty = stop, 1 = station)
    if "location_type" in df.columns:
        df["location_type"] = pd.to_numeric(df["location_type"], errors="coerce").fillna(0)
        df = df[df["location_type"].isin([0, 1])]

    df["agency"] = agency
    df["stop_lat"] = pd.to_numeric(df["stop_lat"], errors="coerce")
    df["stop_lon"] = pd.to_numeric(df["stop_lon"], errors="coerce")
    df = df.dropna(subset=["stop_lat", "stop_lon"])

    keep = ["stop_id", "stop_name", "stop_lat", "stop_lon", "agency"]
    if "location_type" in df.columns:
        keep.append("location_type")
    return df[[c for c in keep if c in df.columns]]


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    all_stops = []

    for agency, url in GTFS_FEEDS.items():
        print(f"Downloading {agency} GTFS feed ...")
        try:
            resp = requests.get(url, timeout=120, allow_redirects=True)
            resp.raise_for_status()
            zip_bytes = resp.content
        except Exception as e:
            print(f"  ERROR downloading {agency}: {e}")
            continue

        stops_df = parse_gtfs_stops(zip_bytes, agency)
        print(f"  Parsed {len(stops_df)} stops from {agency}")
        all_stops.append(stops_df)

    if not all_stops:
        print("ERROR: No stops parsed from any feed.")
        sys.exit(1)

    combined = pd.concat(all_stops, ignore_index=True)
    print(f"Total stops: {len(combined)}")

    # Create GeoDataFrame
    geometry = [Point(lon, lat) for lon, lat in zip(combined["stop_lon"], combined["stop_lat"])]
    gdf = gpd.GeoDataFrame(
        combined.drop(columns=["stop_lat", "stop_lon"]),
        geometry=geometry,
        crs="EPSG:4326",
    )

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} stops to table '{TABLE_NAME}' ...")
    gdf.to_postgis(TABLE_NAME, engine, if_exists="replace", index=False)

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
            "Transit stops from BART and AC Transit GTFS feeds for the SF Bay Area",
            "https://www.bart.gov/dev/schedules/developers/gtfs",
            "Point",
            json.dumps(bbox),
            len(gdf),
        ),
    )
    cur.close()
    catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers.")
    print("Done.")


if __name__ == "__main__":
    main()
