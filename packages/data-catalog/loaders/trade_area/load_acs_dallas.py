"""Persist Dallas County ACS5 tract demographics → trade_area_acs_dallas.

Score Mode fetches ACS on-demand (national), but Discover Mode evaluates ~2000
grid candidates with set-based SQL, so it needs population/income joinable to the
tract geometries in PostGIS. This loads the same ACS5 values into a small table
(645 rows). Census API (key) primary, keyless Census Reporter fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

TABLE = "trade_area_acs_dallas"
STATE, COUNTY = "48", "113"
ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
CR_URL = "https://api.censusreporter.org/1.0/data/show/latest"


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f <= -666666666 else f


def fetch_official(key: str) -> dict[str, dict] | None:
    params = {"get": "B01001_001E,B11001_001E,B19013_001E",
              "for": "tract:*", "in": [f"state:{STATE}", f"county:{COUNTY}"], "key": key}
    # requests handles list-valued params as repeated keys.
    r = requests.get(ACS_URL, params=params, timeout=60)
    if r.status_code != 200 or not r.text.lstrip().startswith("["):
        return None
    rows = r.json()
    idx = {n: i for i, n in enumerate(rows[0])}
    out = {}
    for row in rows[1:]:
        geoid = row[idx["state"]] + row[idx["county"]] + row[idx["tract"]]
        out[geoid] = {
            "population": _num(row[idx["B01001_001E"]]),
            "households": _num(row[idx["B11001_001E"]]),
            "median_income": _num(row[idx["B19013_001E"]]),
        }
    return out or None


def fetch_reporter() -> dict[str, dict] | None:
    r = requests.get(CR_URL, params={"table_ids": "B01001,B11001,B19013",
                                     "geo_ids": f"140|05000US{STATE}{COUNTY}"}, timeout=90)
    if r.status_code != 200 or not r.text.lstrip().startswith("{"):
        return None
    out = {}
    for cr_geo, rec in r.json().get("data", {}).items():
        geoid = cr_geo.split("US")[-1]
        out[geoid] = {
            "population": _num(rec.get("B01001", {}).get("estimate", {}).get("B01001001")),
            "households": _num(rec.get("B11001", {}).get("estimate", {}).get("B11001001")),
            "median_income": _num(rec.get("B19013", {}).get("estimate", {}).get("B19013001")),
        }
    return out or None


def main() -> None:
    key = os.getenv("CENSUS_API_KEY")
    data = (fetch_official(key) if key else None) or fetch_reporter()
    if not data:
        raise RuntimeError("Could not fetch Dallas ACS (key invalid and fallback failed).")
    print(f"Fetched {len(data)} Dallas tracts.")
    rows = [(g, d["population"], d["households"], d["median_income"]) for g, d in data.items()]

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(
        f"""CREATE TABLE {TABLE} (
            geoid text PRIMARY KEY,
            population double precision,
            households double precision,
            median_income double precision
        )"""
    )
    execute_values(
        cur, f"INSERT INTO {TABLE} (geoid, population, households, median_income) VALUES %s", rows
    )
    cur.execute(f"SELECT COUNT(*), SUM(population)::bigint FROM {TABLE}")
    n, pop = cur.fetchone()
    print(f"Loaded {n} tracts into {TABLE} (total pop {pop:,}).")
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
