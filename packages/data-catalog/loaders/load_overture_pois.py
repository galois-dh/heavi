"""Load Overture Maps POIs (places) for Alameda County, CA.

Uses DuckDB to query the Overture places theme from S3 GeoParquet.
"""

from __future__ import annotations

import json
import os
import sys

import duckdb
import geopandas as gpd
import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_overture_pois"

BBOX = {"minx": -122.37, "miny": 37.45, "maxx": -121.47, "maxy": 37.91}

OVERTURE_S3_PATH = (
    "s3://overturemaps-us-west-2/release/2026-04-15.0/theme=places/type=place/*"
)


def fetch_pois() -> gpd.GeoDataFrame:
    print("Querying Overture Maps places via DuckDB ...")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL spatial; LOAD spatial;")
    con.execute("SET s3_region='us-west-2';")
    con.execute("SET s3_access_key_id=''; SET s3_secret_access_key='';")

    query = f"""
    SELECT
        id,
        names.primary AS name,
        categories.primary AS category,
        addresses[1].freeform AS address,
        addresses[1].locality AS city,
        sources[1].dataset AS source_dataset,
        confidence,
        ST_AsText(geometry) AS geometry_wkt
    FROM read_parquet('{OVERTURE_S3_PATH}', filename=true, hive_partitioning=true)
    WHERE bbox.xmin >= {BBOX['minx']}
      AND bbox.xmax <= {BBOX['maxx']}
      AND bbox.ymin >= {BBOX['miny']}
      AND bbox.ymax <= {BBOX['maxy']}
    """

    print("  Executing query (this may take a few minutes) ...")
    result = con.execute(query).fetchdf()
    con.close()

    print(f"  Fetched {len(result)} POIs")

    result["geometry"] = gpd.GeoSeries.from_wkt(result["geometry_wkt"])
    result = result.drop(columns=["geometry_wkt"])
    gdf = gpd.GeoDataFrame(result, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.dropna(subset=["geometry"])
    return gdf


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    gdf = fetch_pois()
    if gdf.empty:
        print("ERROR: No POIs fetched.")
        sys.exit(1)

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} POIs to table '{TABLE_NAME}' ...")
    chunk_size = 50_000
    for i in range(0, len(gdf), chunk_size):
        chunk = gdf.iloc[i : i + chunk_size]
        mode = "replace" if i == 0 else "append"
        chunk.to_postgis(TABLE_NAME, engine, if_exists=mode, index=False)
        print(f"  Wrote chunk {i // chunk_size + 1} ({min(i + chunk_size, len(gdf))}/{len(gdf)})")

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
            "Overture Maps points of interest (restaurants, retail, offices, etc.) for Alameda County, CA",
            "https://overturemaps.org",
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
