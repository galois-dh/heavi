"""Load CAL FIRE FRAP fire perimeters (statewide California).

Source: CAL FIRE FRAP FirePerimeters_FS FeatureServer. Paginated via
resultOffset because the service caps at 1000 features per request and the
full dataset is ~22 800 polygons.
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

TABLE_NAME = "wildfire_frap_perimeters"
SERVICE_URL = (
    "https://egis.fire.ca.gov/arcgis/rest/services/FRAP/FirePerimeters_FS/"
    "FeatureServer/0/query"
)
PAGE_SIZE = 1000  # service maximum
OUT_FIELDS = (
    "OBJECTID,YEAR_,STATE,AGENCY,UNIT_ID,FIRE_NAME,IRWINID,INC_NUM,"
    "ALARM_DATE,CONT_DATE,CAUSE,GIS_ACRES,COMPLEX_NAME,COMPLEX_ID"
)


def fetch_page(offset: int) -> dict:
    params = {
        "where": "1=1",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": PAGE_SIZE,
        "resultOffset": offset,
        "orderByFields": "OBJECTID",
    }
    r = requests.get(SERVICE_URL, params=params, timeout=180)
    r.raise_for_status()
    return r.json()


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    all_features: list[dict] = []
    offset = 0
    while True:
        print(f"Fetching offset={offset} ...")
        data = fetch_page(offset)
        feats = data.get("features", [])
        all_features.extend(feats)
        print(f"  +{len(feats)} (total {len(all_features)})")
        if len(feats) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.2)

    if not all_features:
        print("ERROR: no perimeters returned", file=sys.stderr)
        sys.exit(1)

    print(f"Total perimeters: {len(all_features)}")
    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": all_features},
        crs="EPSG:4326",
    )
    gdf.columns = [c.lower() for c in gdf.columns]
    # Drop rows with no/empty geometry — invalid perimeters in the source.
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    engine = create_engine(database_url)
    print(f"Writing {len(gdf)} perimeters to '{TABLE_NAME}' ...")
    chunk = 2_000
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
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_year "
                f"ON {TABLE_NAME} (year_);"
            )
        )
        conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_firename "
                f"ON {TABLE_NAME} (fire_name);"
            )
        )
        conn.commit()
    print("Indexes created (GIST geom, year_, fire_name).")

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
            "CAL FIRE FRAP historical fire perimeters — California statewide, "
            "polygon footprint per recorded wildfire.",
            SERVICE_URL,
            "MultiPolygon",
            json.dumps(bbox),
            len(gdf),
        ),
    )
    cur.close()
    catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers. Done.")


if __name__ == "__main__":
    main()
