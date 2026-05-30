"""Load OpenFEMA NFIP claims for Hurricane Ian (Lee County, FL; Sep-Oct 2022)
into flood_nfip_claims_lee_ian — a coastal/fluvial validation set to contrast
with the pluvial-dominated Harris County (Harvey) backtest.

Source: https://www.fema.gov/api/open/v2/FimaNfipClaims
Filter: countyCode 12071 (Lee County, FL), dateOfLoss 2022-09-01 .. 2022-11-01.
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

TABLE = "flood_nfip_claims_lee_ian"
BASE = "https://www.fema.gov/api/open/v2/FimaNfipClaims"
FILTER = (
    "countyCode eq '12071' and dateOfLoss ge '2022-09-01' "
    "and dateOfLoss le '2022-11-01'"
)
PAGE = 1000

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
        "$filter": FILTER,
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
            print(f"  skip={skip} attempt {attempt + 1} failed: {e}", flush=True)
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
            flood_zone text, census_tract text, date_of_loss date,
            occupancy_type integer, number_of_floors_in_insured_building integer,
            base_flood_elevation double precision, elevation_of_structure double precision,
            latitude double precision, longitude double precision
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
        execute_values(cur, f"INSERT INTO {TABLE} ({', '.join(COLS)}) VALUES %s", rows)
        total += len(recs)
        print(f"  loaded {total} ({time.time() - t0:.0f}s)", flush=True)
        if len(recs) < PAGE:
            break
        skip += PAGE

    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tract ON {TABLE} (census_tract)")
    cur.execute(
        f"""SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE flood_zone ~ '^(A|V)'),
                   ROUND(AVG(COALESCE(amount_paid_on_building_claim,0)
                             + COALESCE(amount_paid_on_contents_claim,0))::numeric,0)
            FROM {TABLE}"""
    )
    n, sfha, avg = cur.fetchone()
    print(f"Loaded {n} Lee County (Ian) claims into {TABLE}. "
          f"SFHA-rated: {sfha} ({100.0*sfha/n:.1f}%) | avg paid ${avg}.")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
