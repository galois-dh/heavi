"""Load CAL FIRE Fire Hazard Severity Zones for Alameda County, CA.

Queries the Cal Fire FRAP ArcGIS REST service for FHSZs.
"""

from __future__ import annotations

import json
import os
import sys
import time

import geopandas as gpd
import psycopg2
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_calfire_fhsz"

# CAL FIRE FRAP — Fire Hazard Severity Zones (SRA + LRA combined)
# Layer 0 = SRA (State Responsibility Area)
# Layer 1 = LRA (Local Responsibility Area)
# Try the combined recommended layer first
FHSZ_URLS = [
    "https://egis.fire.ca.gov/arcgis/rest/services/FRAP/HHZ_ref_FHSZ/MapServer/0/query",
]

# Alameda County bounding box (EPSG:4326)
BBOX_ENVELOPE = "-122.37,37.45,-121.47,37.91"


def fetch_fhsz_from_url(url: str) -> list[dict]:
    """Fetch FHSZ features from a single ArcGIS REST layer."""
    all_features = []
    offset = 0
    page_size = 2000

    while True:
        params = {
            "where": "1=1",
            "geometry": BBOX_ENVELOPE,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": page_size,
            "resultOffset": offset,
        }

        try:
            resp = requests.get(url, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if offset == 0:
                return []  # This URL doesn't work, try next
            break

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        if len(features) < page_size:
            break

        offset += page_size
        time.sleep(0.3)

    return all_features


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    all_features = []
    for url in FHSZ_URLS:
        label = url.split("/MapServer/")[0].split("/")[-1] + " layer " + url.split("/")[-2]
        print(f"Trying {label} ...")
        features = fetch_fhsz_from_url(url)
        if features:
            print(f"  Got {len(features)} features")
            all_features.extend(features)

    if not all_features:
        print("ERROR: No FHSZ data retrieved from any Cal Fire endpoint.")
        sys.exit(1)

    print(f"Total FHSZ features: {len(all_features)}")

    geojson = {"type": "FeatureCollection", "features": all_features}
    gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")

    if gdf.empty:
        print("ERROR: GeoDataFrame is empty after parsing.")
        sys.exit(1)

    # Standardize column names
    gdf.columns = [c.lower() for c in gdf.columns]

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} FHSZ polygons to table '{TABLE_NAME}' ...")
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
            "CAL FIRE Fire Hazard Severity Zones (SRA + LRA) for Alameda County, CA",
            "https://egis.fire.ca.gov/arcgis/rest/services/FRAP/FHSZ/MapServer",
            "MultiPolygon",
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
