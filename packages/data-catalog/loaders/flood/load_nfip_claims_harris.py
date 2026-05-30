"""Load OpenFEMA NFIP Redacted Claims for Harris County, TX (FIPS 48201) into
flood_nfip_claims_harris.

This is VALIDATION data only — the flood module scores nationally on-demand and
never reads this table at request time. It is staged now so the Week 2/3
validation (predicted loss vs. actual paid claims) can run later.

Source: https://www.fema.gov/api/open/v2/FimaNfipClaims  (~170k Harris claims)
Paginated with $top/$skip; only the fields the validation needs are selected.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

TABLE = "flood_nfip_claims_harris"
BASE = "https://www.fema.gov/api/open/v2/FimaNfipClaims"
COUNTY = "48201"
PAGE = 1000

# OpenFEMA field → our column.
FIELDS = {
    "amountPaidOnBuildingClaim": "amount_paid_on_building_claim",
    "amountPaidOnContentsClaim": "amount_paid_on_contents_claim",
    "ratedFloodZone": "flood_zone",
    "censusTract": "census_tract",
    "dateOfLoss": "date_of_loss",
    "occupancyType": "occupancy_type",
    "numberOfFloorsInTheInsuredBuilding": "number_of_floors_in_insured_building",
    "baseFloodElevation": "base_flood_elevation",
    "lowestFloorElevation": "elevation_of_structure",
    "latitude": "latitude",
    "longitude": "longitude",
}
COLS = list(FIELDS.values())


def fetch_page(skip: int) -> list[dict]:
    params = {
        "$filter": f"countyCode eq '{COUNTY}'",
        "$select": ",".join(FIELDS.keys()) + ",id",
        "$orderby": "id",
        "$top": str(PAGE),
        "$skip": str(skip),
    }
    for attempt in range(4):
        try:
            r = requests.get(BASE, params=params, timeout=120)
            r.raise_for_status()
            return r.json().get("FimaNfipClaims", [])
        except requests.RequestException as e:
            print(f"  page skip={skip} attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(5)
    raise RuntimeError(f"OpenFEMA fetch failed at skip={skip}")


def main() -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(
        f"""CREATE TABLE {TABLE} (
            amount_paid_on_building_claim double precision,
            amount_paid_on_contents_claim double precision,
            flood_zone text,
            census_tract text,
            date_of_loss date,
            occupancy_type integer,
            number_of_floors_in_insured_building integer,
            base_flood_elevation double precision,
            elevation_of_structure double precision,
            latitude double precision,
            longitude double precision
        )"""
    )

    total = 0
    skip = 0
    t0 = time.time()
    while True:
        recs = fetch_page(skip)
        if not recs:
            break
        rows = [tuple(r.get(src) for src in FIELDS) for r in recs]
        execute_values(
            cur,
            f"INSERT INTO {TABLE} ({', '.join(COLS)}) VALUES %s",
            rows,
        )
        total += len(recs)
        if skip % 20000 == 0 or len(recs) < PAGE:
            print(f"  loaded {total} ({time.time() - t0:.0f}s)", flush=True)
        if len(recs) < PAGE:
            break
        skip += PAGE

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tract ON {TABLE} (census_tract)")
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_zone ON {TABLE} (flood_zone)")
    cur.execute(
        f"SELECT COUNT(*), ROUND(AVG(amount_paid_on_building_claim)::numeric, 0), "
        f"COUNT(DISTINCT flood_zone) FROM {TABLE}"
    )
    n, avg_paid, nzones = cur.fetchone()
    print(f"Loaded {n} Harris County NFIP claims into {TABLE} "
          f"(avg building paid ${avg_paid}, {nzones} distinct rated zones).")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
