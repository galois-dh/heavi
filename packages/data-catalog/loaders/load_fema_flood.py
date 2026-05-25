"""Load FEMA National Flood Hazard Layer (NFHL) for Alameda County, CA.

Queries the FEMA NFHL ArcGIS REST service for the S_FLD_HAZ_AR
(Special Flood Hazard Area) layer, filtered to Alameda County (DFIRM_ID=06001C).
"""

from __future__ import annotations

import json
import os
import sys
import time

import geopandas as gpd
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from shapely.geometry import shape
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_fema_flood"

# FEMA NFHL MapServer - Layer 28 = S_FLD_HAZ_AR (flood hazard areas)
BASE_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)

# Alameda County FIPS: 06001, DFIRM_ID format: 06001C
QUERY_PARAMS = {
    "where": "DFIRM_ID='06001C'",
    "outFields": "FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH,VELOCITY,LEN_UNIT,V_DATUM,STUDY_TYP,SOURCE_CIT",
    "returnGeometry": "true",
    "f": "geojson",
    "resultRecordCount": 2000,
    "resultOffset": 0,
}


def fetch_all_features() -> list[dict]:
    """Paginate through the FEMA REST API to get all flood hazard polygons."""
    import requests

    all_features = []
    offset = 0
    page_size = 2000

    while True:
        params = {**QUERY_PARAMS, "resultOffset": offset, "resultRecordCount": page_size}
        print(f"  Fetching offset={offset} ...")

        resp = requests.get(BASE_URL, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        print(f"  Got {len(features)} features (total: {len(all_features)})")

        if len(features) < page_size:
            break

        offset += page_size
        time.sleep(0.5)  # be polite to FEMA servers

    return all_features


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print("Fetching FEMA NFHL flood hazard areas for Alameda County ...")
    features = fetch_all_features()

    if not features:
        print("WARNING: No features returned from FEMA API.")
        print("Trying alternative: querying by county geometry envelope ...")
        # Fallback: use Alameda County bounding box as a spatial filter
        import requests

        envelope = "-122.37,37.45,-121.47,37.91"
        params = {
            "where": "1=1",
            "geometry": envelope,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH,VELOCITY,SOURCE_CIT",
            "returnGeometry": "true",
            "f": "geojson",
            "resultRecordCount": 2000,
            "resultOffset": 0,
        }
        all_features = []
        offset = 0
        while True:
            params["resultOffset"] = offset
            resp = requests.get(BASE_URL, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("features", [])
            if not batch:
                break
            all_features.extend(batch)
            print(f"  Got {len(batch)} features (total: {len(all_features)})")
            if len(batch) < 2000:
                break
            offset += 2000
            time.sleep(0.5)
        features = all_features

    if not features:
        print("ERROR: Could not retrieve FEMA flood data. The FEMA API may be unavailable.")
        sys.exit(1)

    print(f"Total features fetched: {len(features)}")

    # Build GeoDataFrame
    geojson = {"type": "FeatureCollection", "features": features}
    gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")

    # Clean column names to lowercase
    gdf.columns = [c.lower() for c in gdf.columns]

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} features to table '{TABLE_NAME}' ...")
    gdf.to_postgis(TABLE_NAME, engine, if_exists="replace", index=False)

    # Create spatial index
    with engine.connect() as conn:
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geom ON {TABLE_NAME} USING GIST (geometry);'))
        conn.commit()
    print("Spatial index created.")

    # Register in catalog_layers
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    bbox = {"minx": float(bounds[0]), "miny": float(bounds[1]), "maxx": float(bounds[2]), "maxy": float(bounds[3])}

    catalog_conn = psycopg2.connect(database_url)
    catalog_conn.autocommit = True
    cur = catalog_conn.cursor()
    cur.execute(
        """
        INSERT INTO catalog_layers (name, description, source_url, geometry_type, bbox, row_count, updated_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, now())
        ON CONFLICT (name) DO UPDATE SET
            description = EXCLUDED.description,
            source_url = EXCLUDED.source_url,
            geometry_type = EXCLUDED.geometry_type,
            bbox = EXCLUDED.bbox,
            row_count = EXCLUDED.row_count,
            updated_at = now();
        """,
        (
            TABLE_NAME,
            "FEMA National Flood Hazard Layer - Special Flood Hazard Areas for Alameda County, CA",
            "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28",
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
