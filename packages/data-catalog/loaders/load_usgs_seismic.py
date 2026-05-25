"""Load USGS earthquake hazard data for Alameda County, CA.

Downloads USGS Quaternary Faults and Folds database features and
probabilistic seismic hazard contours for the Alameda County area.
"""

from __future__ import annotations

import json
import os
import sys
import time

import geopandas as gpd
import pandas as pd
import psycopg2
import requests
from dotenv import load_dotenv
from shapely.geometry import Point
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_usgs_seismic"

# USGS Quaternary Faults — ArcGIS REST service
QFAULTS_URL = (
    "https://earthquake.usgs.gov/arcgis/rest/services/eq/map_faults/MapServer/0/query"
)

# USGS Earthquake Hazards — recent significant earthquakes near Bay Area
EARTHQUAKE_CATALOG_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
)

# Alameda County bbox
BBOX = {"minx": -122.37, "miny": 37.45, "maxx": -121.47, "maxy": 37.91}
BBOX_ENVELOPE = f"{BBOX['minx']},{BBOX['miny']},{BBOX['maxx']},{BBOX['maxy']}"


def fetch_quaternary_faults() -> gpd.GeoDataFrame:
    """Fetch USGS Quaternary Faults from ArcGIS REST service."""
    print("Fetching USGS Quaternary Faults ...")
    all_features = []
    offset = 0
    page_size = 1000

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
            resp = requests.get(QFAULTS_URL, params=params, timeout=120)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  WARNING: Quaternary faults query failed: {e}")
            break

        features = data.get("features", [])
        if not features:
            break

        all_features.extend(features)
        print(f"  Fetched {len(features)} fault features (total: {len(all_features)})")

        if len(features) < page_size:
            break
        offset += page_size
        time.sleep(0.3)

    if not all_features:
        print("  No quaternary faults found in area")
        return gpd.GeoDataFrame()

    geojson = {"type": "FeatureCollection", "features": all_features}
    gdf = gpd.GeoDataFrame.from_features(geojson, crs="EPSG:4326")
    gdf.columns = [c.lower() for c in gdf.columns]
    gdf["feature_type"] = "quaternary_fault"
    return gdf


def fetch_significant_earthquakes() -> gpd.GeoDataFrame:
    """Fetch historical significant earthquakes from USGS FDSN catalog."""
    print("Fetching USGS earthquake catalog for Bay Area ...")

    params = {
        "format": "geojson",
        "starttime": "1900-01-01",
        "endtime": "2026-04-20",
        "minlatitude": BBOX["miny"],
        "maxlatitude": BBOX["maxy"],
        "minlongitude": BBOX["minx"],
        "maxlongitude": BBOX["maxx"],
        "minmagnitude": 2.5,
        "orderby": "magnitude",
        "limit": 2000,
    }

    try:
        resp = requests.get(EARTHQUAKE_CATALOG_URL, params=params, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  WARNING: Earthquake catalog query failed: {e}")
        return gpd.GeoDataFrame()

    features = data.get("features", [])
    print(f"  {len(features)} earthquakes M2.5+ found")

    if not features:
        return gpd.GeoDataFrame()

    rows = []
    for f in features:
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [None, None])
        if coords[0] is None:
            continue
        rows.append({
            "name": props.get("title", ""),
            "magnitude": props.get("mag"),
            "depth_km": coords[2] if len(coords) > 2 else None,
            "event_time": props.get("time"),
            "event_type": props.get("type", "earthquake"),
            "place": props.get("place", ""),
            "feature_type": "earthquake",
            "lon": coords[0],
            "lat": coords[1],
        })

    df = pd.DataFrame(rows)
    geometry = [Point(lon, lat) for lon, lat in zip(df["lon"], df["lat"])]
    gdf = gpd.GeoDataFrame(df.drop(columns=["lon", "lat"]), geometry=geometry, crs="EPSG:4326")
    return gdf


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    faults_gdf = fetch_quaternary_faults()
    quakes_gdf = fetch_significant_earthquakes()

    parts = [df for df in [faults_gdf, quakes_gdf] if not df.empty]
    if not parts:
        print("ERROR: No seismic data retrieved.")
        sys.exit(1)

    # Combine — faults are lines, earthquakes are points.
    # We'll keep them in one table with a feature_type column to distinguish.
    # Use unary_union-compatible approach: just concat and let mixed geometry work.
    combined = pd.concat(parts, ignore_index=True)
    gdf = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} seismic features to table '{TABLE_NAME}' ...")
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
    bbox_val = {
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
            "USGS earthquake hazard data: quaternary faults and historical earthquakes (M2.5+) for Alameda County, CA",
            "https://earthquake.usgs.gov",
            "Mixed (LineString + Point)",
            json.dumps(bbox_val),
            len(gdf),
        ),
    )
    cur.close()
    catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers.")
    print("Done.")


if __name__ == "__main__":
    main()
