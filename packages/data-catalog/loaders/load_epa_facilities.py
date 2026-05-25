"""Load EPA facility locations (TRI + brownfields) for Alameda County, CA.

Queries the EPA Envirofacts REST API for TRI (Toxics Release Inventory)
facilities and the EPA ECHO API for brownfield sites.
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

TABLE_NAME = "catalog_epa_facilities"

# EPA Envirofacts TRI Facility endpoint
TRI_URL = (
    "https://data.epa.gov/efservice/tri_facility"
    "/state_abbr/=/CA/county_name/=/ALAMEDA"
    "/rows/0:9999/JSON"
)

# EPA ECHO (Enforcement and Compliance History) for brownfields/superfund
# Query facilities in Alameda County with environmental interest
ECHO_URL = (
    "https://echodata.epa.gov/echo/echo_rest_services.get_facilities"
    "?output=JSON"
    "&p_st=CA"
    "&p_cnty=ALAMEDA"
    "&p_act=Y"
    "&responseset=5000"
)


def fetch_tri_facilities() -> pd.DataFrame:
    """Fetch TRI facilities from EPA Envirofacts."""
    print("Fetching EPA TRI facilities for Alameda County ...")

    resp = requests.get(TRI_URL, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    if not data:
        print("  No TRI facilities returned")
        return pd.DataFrame()

    df = pd.DataFrame(data)
    print(f"  {len(df)} TRI facility records")

    # TRI may have multiple rows per facility (one per chemical).
    # Deduplicate by facility ID.
    df.columns = [c.strip().upper() for c in df.columns]

    # Deduplicate by facility
    df = df.drop_duplicates(subset=["TRI_FACILITY_ID"])

    # TRI stores lat/lon in DMS-as-integer format: DDMMSS (e.g. 373823 = 37°38'23")
    # pref_latitude/pref_longitude are preferred decimal coords but often null.
    def dms_int_to_decimal(val):
        """Convert DMS integer like 373823 to decimal degrees 37.6397..."""
        if pd.isna(val) or val == 0:
            return float("nan")
        val = int(val)
        sign = -1 if val < 0 else 1
        val = abs(val)
        seconds = val % 100
        minutes = (val // 100) % 100
        degrees = val // 10000
        return sign * (degrees + minutes / 60 + seconds / 3600)

    df["lat"] = df["PREF_LATITUDE"].apply(
        lambda x: float(x) if pd.notna(x) and x != "None" else float("nan")
    )
    df["lon"] = df["PREF_LONGITUDE"].apply(
        lambda x: float(x) if pd.notna(x) and x != "None" else float("nan")
    )

    # Fill missing preferred coords from DMS fac_latitude/fac_longitude
    mask = df["lat"].isna()
    df.loc[mask, "lat"] = pd.to_numeric(df.loc[mask, "FAC_LATITUDE"], errors="coerce").apply(dms_int_to_decimal)
    df.loc[mask, "lon"] = pd.to_numeric(df.loc[mask, "FAC_LONGITUDE"], errors="coerce").apply(dms_int_to_decimal).apply(lambda x: -abs(x) if pd.notna(x) else x)

    df = df.dropna(subset=["lat", "lon"])
    df = df[(df["lat"] != 0) & (df["lon"] != 0)]
    # Sanity: filter to rough Alameda County bounds
    df = df[(df["lat"] > 37) & (df["lat"] < 38.5) & (df["lon"] < -121) & (df["lon"] > -123)]

    out = pd.DataFrame()
    out["facility_id"] = df["TRI_FACILITY_ID"].values
    out["name"] = df["FACILITY_NAME"].values
    out["facility_type"] = "TRI"
    out["address"] = df["STREET_ADDRESS"].values
    out["city"] = df["CITY_NAME"].values
    out["lat"] = df["lat"].values
    out["lon"] = df["lon"].values

    print(f"  {len(out)} unique TRI facilities with coordinates")
    return out


def fetch_echo_facilities() -> pd.DataFrame:
    """Fetch facilities from EPA ECHO (brownfields, superfund, etc.)."""
    print("Fetching EPA ECHO facilities for Alameda County ...")

    try:
        resp = requests.get(ECHO_URL, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  WARNING: ECHO API request failed: {e}")
        return pd.DataFrame()

    # ECHO response structure: {"Results": {"Facilities": [...]}}
    facilities = data.get("Results", {}).get("Facilities", [])
    if not facilities:
        print("  No ECHO facilities returned")
        return pd.DataFrame()

    df = pd.DataFrame(facilities)
    print(f"  {len(df)} ECHO facility records")

    # ECHO uses specific column names
    lat_col = next((c for c in df.columns if c in ("Lat", "FacLat", "RegistryLatitude")), None)
    lon_col = next((c for c in df.columns if c in ("Lon", "FacLong", "RegistryLongitude")), None)

    if not lat_col or not lon_col:
        print(f"  Available columns: {list(df.columns)[:20]}")
        print("  WARNING: No lat/lon in ECHO data")
        return pd.DataFrame()

    df["lat"] = pd.to_numeric(df[lat_col], errors="coerce")
    df["lon"] = pd.to_numeric(df[lon_col], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df = df[(df["lat"] != 0) & (df["lon"] != 0)]

    out = pd.DataFrame()
    id_col = next((c for c in df.columns if "RegistryId" in c or "FacId" in c or "SourceID" in c), None)
    name_col = next((c for c in df.columns if "Name" in c), None)

    out["facility_id"] = df[id_col].values if id_col else df.index.astype(str)
    out["name"] = df[name_col].values if name_col else "Unknown"
    out["facility_type"] = "ECHO"
    out["address"] = df["FacStreet"].values if "FacStreet" in df.columns else None
    out["city"] = df["FacCity"].values if "FacCity" in df.columns else None
    out["lat"] = df["lat"].values
    out["lon"] = df["lon"].values

    print(f"  {len(out)} ECHO facilities with coordinates")
    return out


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    tri_df = fetch_tri_facilities()
    echo_df = fetch_echo_facilities()

    dfs = [df for df in [tri_df, echo_df] if not df.empty]
    if not dfs:
        print("ERROR: No EPA facility data retrieved.")
        sys.exit(1)

    combined = pd.concat(dfs, ignore_index=True)

    # Deduplicate by proximity (facilities may appear in both TRI and ECHO)
    combined = combined.drop_duplicates(subset=["name", "lat", "lon"])

    geometry = [Point(lon, lat) for lon, lat in zip(combined["lon"], combined["lat"])]
    gdf = gpd.GeoDataFrame(
        combined.drop(columns=["lat", "lon"]),
        geometry=geometry,
        crs="EPSG:4326",
    )

    engine = create_engine(database_url)

    print(f"Writing {len(gdf)} EPA facilities to table '{TABLE_NAME}' ...")
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
            "EPA TRI (Toxics Release Inventory) and ECHO environmental facilities for Alameda County, CA",
            "https://enviro.epa.gov/enviro/efservice/tri_facility",
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
