"""Load Census ACS 5-year demographics for Alameda County, CA census tracts.

Fetches demographic variables from the Census Bureau API and joins them
with TIGER/Line tract geometries.
"""

from __future__ import annotations

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
from sqlalchemy import create_engine, text

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

TABLE_NAME = "catalog_census_demographics"

# Census ACS 5-year variables
# B01003_001E = Total population
# B19013_001E = Median household income
# B15003_022E = Bachelor's degree
# B15003_023E = Master's degree
# B15003_024E = Professional school degree
# B15003_025E = Doctorate degree
# B15003_001E = Total (education universe, population 25+)
CENSUS_VARIABLES = "NAME,B01003_001E,B19013_001E,B15003_001E,B15003_022E,B15003_023E,B15003_024E,B15003_025E"

# ACS 5-year, state=06 (CA), county=001 (Alameda)
CENSUS_API_URL = (
    "https://api.census.gov/data/2022/acs/acs5"
    f"?get={CENSUS_VARIABLES}"
    "&for=tract:*"
    "&in=state:06%20county:001"
)

# TIGER/Line tract boundaries for California
TIGER_TRACTS_URL = "https://www2.census.gov/geo/tiger/TIGER2022/TRACT/tl_2022_06_tract.zip"


def fetch_census_data() -> pd.DataFrame:
    """Fetch ACS demographic data from Census API."""
    print("Fetching Census ACS 5-year data ...")
    resp = requests.get(CENSUS_API_URL, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # First row is header
    header = data[0]
    rows = data[1:]
    df = pd.DataFrame(rows, columns=header)

    # Build GEOID = state + county + tract
    df["geoid"] = df["state"] + df["county"] + df["tract"]

    # Rename and convert to numeric
    df = df.rename(columns={
        "NAME": "tract_name",
        "B01003_001E": "total_population",
        "B19013_001E": "median_household_income",
        "B15003_001E": "education_universe",
        "B15003_022E": "bachelors_degree",
        "B15003_023E": "masters_degree",
        "B15003_024E": "professional_degree",
        "B15003_025E": "doctorate_degree",
    })

    numeric_cols = [
        "total_population", "median_household_income", "education_universe",
        "bachelors_degree", "masters_degree", "professional_degree", "doctorate_degree",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Compute % with bachelor's or higher
    edu_total = df["bachelors_degree"].fillna(0) + df["masters_degree"].fillna(0) + \
                df["professional_degree"].fillna(0) + df["doctorate_degree"].fillna(0)
    pct = edu_total / df["education_universe"].replace(0, float("nan")) * 100
    df["pct_bachelors_or_higher"] = pct.round(1)

    keep_cols = [
        "geoid", "tract_name", "total_population", "median_household_income",
        "pct_bachelors_or_higher", "state", "county", "tract",
    ]
    return df[keep_cols]


def fetch_tiger_tracts() -> gpd.GeoDataFrame:
    """Download TIGER/Line tract boundaries for California, filter to Alameda County."""
    print("Downloading TIGER/Line tract boundaries ...")
    resp = requests.get(TIGER_TRACTS_URL, timeout=120)
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        gdf = gpd.read_file(io.BytesIO(resp.content))

    # Filter to Alameda County (COUNTYFP = 001)
    gdf = gdf[gdf["COUNTYFP"] == "001"].copy()
    gdf = gdf.to_crs(epsg=4326)
    print(f"  {len(gdf)} tracts in Alameda County")
    return gdf


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    census_df = fetch_census_data()
    print(f"  {len(census_df)} tracts from Census API")

    tiger_gdf = fetch_tiger_tracts()

    # Join census data with TIGER geometries
    merged = tiger_gdf.merge(census_df, left_on="GEOID", right_on="geoid", how="inner")

    # Keep only relevant columns
    keep = [
        "geoid", "tract_name", "total_population", "median_household_income",
        "pct_bachelors_or_higher", "geometry",
    ]
    result = merged[keep].copy()
    result = gpd.GeoDataFrame(result, geometry="geometry", crs="EPSG:4326")

    engine = create_engine(database_url)

    print(f"Writing {len(result)} tracts to table '{TABLE_NAME}' ...")
    result.to_postgis(TABLE_NAME, engine, if_exists="replace", index=False)

    # Create spatial index
    with engine.connect() as conn:
        conn.execute(text(f'CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_geom ON {TABLE_NAME} USING GIST (geometry);'))
        conn.commit()
    print("Spatial index created.")

    # Register in catalog_layers
    bounds = result.total_bounds
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
            "Census ACS 5-year demographics (population, income, education) for Alameda County, CA census tracts",
            "https://api.census.gov/data/2022/acs/acs5",
            "MultiPolygon",
            json.dumps(bbox),
            len(result),
        ),
    )
    cur.close()
    catalog_conn.close()
    print(f"Registered '{TABLE_NAME}' in catalog_layers.")
    print("Done.")


if __name__ == "__main__":
    main()
