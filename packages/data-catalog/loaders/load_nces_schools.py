"""Load NCES school locations for Alameda County, CA.

Downloads the NCES EDGE geocoded public school data and filters to
Alameda County (FIPS county code 001, state 06).
"""

from __future__ import annotations

import json
import os
import sys

import geopandas as gpd
import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv
from shapely.geometry import Point
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_nces_schools"

# NCES EDGE geocoded public school locations (2024-25) — shapefile zip
NCES_URL = (
    "https://nces.ed.gov/programs/edge/data/EDGE_GEOCODE_PUBLICSCH_2425.zip"
)


def load_public_schools() -> gpd.GeoDataFrame:
    """Load public school locations from NCES EDGE shapefile."""
    print("Downloading NCES public school geocode data ...")

    import io
    import zipfile

    resp = requests.get(NCES_URL, timeout=180)
    resp.raise_for_status()

    # The zip contains a pipe-delimited TXT file with no header row.
    COLUMNS = [
        "NCESSCH", "LEAID", "NAME", "OPSTFIPS", "STREET", "CITY", "STATE",
        "ZIP", "STFIP", "CNTY", "NMCNTY", "LOCALE", "LAT", "LON", "CBSA",
        "NMCBSA", "CBSATYPE", "CSA", "NMCSA", "CD", "SLDL", "SLDU", "SCHOOLYEAR",
    ]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        txt_name = next(n for n in zf.namelist() if n.endswith(".TXT") or n.endswith(".txt"))
        with zf.open(txt_name) as f:
            df = pd.read_csv(f, sep="|", header=None, names=COLUMNS, dtype=str, low_memory=False)
    df["_lat"] = pd.to_numeric(df["LAT"], errors="coerce")
    df["_lon"] = pd.to_numeric(df["LON"], errors="coerce")
    df = df.dropna(subset=["_lat", "_lon"])
    df = df[(df["_lat"] != 0) & (df["_lon"] != 0)]

    print(f"  Total schools nationwide: {len(df)}")

    # Filter: California state FIPS 06, Alameda county FIPS 001
    df = df[df["STFIP"].str.strip() == "06"]
    df = df[df["CNTY"].str.strip().str[-3:] == "001"]

    print(f"  {len(df)} public schools in Alameda County")

    geometry = [Point(lon, lat) for lon, lat in zip(df["_lon"], df["_lat"])]
    out = gpd.GeoDataFrame(
        {
            "nces_id": df["NCESSCH"].values,
            "name": df["NAME"].values,
            "school_type": "public",
            "address": df["STREET"].values,
            "city": df["CITY"].values,
            "zip_code": df["ZIP"].values,
            "locale": df["LOCALE"].values,
        },
        geometry=geometry,
        crs="EPSG:4326",
    )
    return out


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    gdf = load_public_schools()

    if gdf.empty:
        print("ERROR: No schools found.")
        sys.exit(1)

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} schools to table '{TABLE_NAME}' ...")
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
            "NCES public school locations for Alameda County, CA (2022-23)",
            NCES_URL,
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
