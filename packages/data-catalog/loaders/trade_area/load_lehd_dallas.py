"""Load LEHD LODES8 Workplace Area Characteristics (WAC) for Dallas County →
trade_area_lehd_dallas.

WAC gives JOBS by workplace census block — i.e. DAYTIME population, which matters
more than residential population for commercial trade-area scoring. We keep the
block-level rows and tag each with its tract GEOID (first 11 digits of the
15-digit block geocode) so the trade-area pipeline can aggregate jobs to the
tract geometries it already has.

Source: https://lehd.ces.census.gov/data/lodes/LODES8/tx/wac/tx_wac_S000_JT00_2021.csv.gz
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from psycopg2.extras import execute_values

load_dotenv(Path(__file__).resolve().parents[4] / ".env")

TABLE = "trade_area_lehd_dallas"
SOURCE_URL = (
    "https://lehd.ces.census.gov/data/lodes/LODES8/tx/wac/tx_wac_S000_JT00_2021.csv.gz"
)
COUNTY_PREFIX = "48113"  # Dallas County block geocodes start with this


def main() -> None:
    print("Downloading TX WAC (LODES8) ...")
    r = requests.get(SOURCE_URL, timeout=300)
    r.raise_for_status()
    text = gzip.decompress(r.content).decode("utf-8")
    lines = text.splitlines()
    header = lines[0].split(",")
    idx = {name: i for i, name in enumerate(header)}
    cols = ["w_geocode", "C000", "CE01", "CE02", "CE03"]
    ci = [idx[c] for c in cols]

    rows: list[tuple] = []
    for line in lines[1:]:
        parts = line.split(",")
        geocode = parts[ci[0]]
        if not geocode.startswith(COUNTY_PREFIX):
            continue
        rows.append((
            geocode,
            geocode[:11],  # tract GEOID
            int(float(parts[ci[1]])),
            int(float(parts[ci[2]])),
            int(float(parts[ci[3]])),
            int(float(parts[ci[4]])),
        ))
    print(f"  {len(rows)} Dallas County workplace blocks")

    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=20)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(
        f"""CREATE TABLE {TABLE} (
            w_geocode text NOT NULL,
            tract_geoid text NOT NULL,
            c000 integer,   -- total jobs
            ce01 integer,   -- jobs, earnings <= $1250/mo
            ce02 integer,   -- jobs, earnings $1251-3333/mo
            ce03 integer    -- jobs, earnings > $3333/mo
        )"""
    )
    execute_values(
        cur,
        f"INSERT INTO {TABLE} (w_geocode, tract_geoid, c000, ce01, ce02, ce03) VALUES %s",
        rows,
        page_size=5000,
    )
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_tract ON {TABLE} (tract_geoid)")
    cur.execute(f"SELECT COUNT(*), SUM(c000), COUNT(DISTINCT tract_geoid) FROM {TABLE}")
    n, jobs, ntr = cur.fetchone()
    print(f"Loaded {n} blocks into {TABLE}: {jobs:,} total jobs across {ntr} tracts.")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
