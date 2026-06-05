"""Load a representative ISO interconnection queue (Month-1 Sprint, Feature 4).

The live ISO queue portals (CAISO RIMS, ERCOT GIS report, PJM, MISO, SPP) require
authenticated/interactive downloads not available from this environment. This
loader populates a REPRESENTATIVE / illustrative dataset:

  - CAISO and ERCOT projects are anchored to REAL substation coordinates
    (substations_osm_us) near Kern County and Houston respectively, plus a
    statewide spread, so spatial queries return meaningful results.
  - PJM / MISO / SPP projects use curated cluster centers (no substations in the
    6-state OSM cache for those regions).

Project profiles (fuel, capacity, status, queue date, study phase, cost) are
deterministic (fixed seed) and realistic but illustrative. Every row is flagged
data_source='representative'. Production should replace the generator with live
ISO queue files.

Usage:
    cd packages/api && source .venv/bin/activate && python load_interconnection_queue.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from datetime import date
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

MIGRATION = Path(__file__).resolve().parent / "migrations" / "2026-06-08_interconnection_queue.sql"

RNG = random.Random("heavi-interconnection-queue-v1")

_FUELS = ["Solar"] * 11 + ["Battery"] * 6 + ["Wind"] * 3  # ~55/30/15
_STATUS = ["Active"] * 60 + ["Withdrawn"] * 25 + ["Completed"] * 12 + ["Suspended"] * 3
_PHASE = ["Feasibility"] * 4 + ["System Impact"] * 4 + ["Facilities"] * 2

# Curated cluster centers for ISOs without substations in the OSM cache.
_CURATED = {
    "PJM": [("PA", 40.27, -76.88), ("NJ", 40.06, -74.40), ("OH", 39.96, -82.99),
            ("VA", 37.54, -77.43), ("MD", 39.29, -76.61), ("PA", 41.24, -77.00)],
    "MISO": [("IL", 39.78, -89.65), ("IN", 39.77, -86.16), ("MN", 44.95, -93.09),
             ("MI", 42.73, -84.55), ("IA", 41.59, -93.62)],
    "SPP": [("KS", 38.50, -98.00), ("OK", 35.47, -97.52), ("NE", 40.81, -96.70),
            ("SD", 44.37, -100.35)],
}


def _cap(fuel: str) -> float:
    if fuel == "Battery":
        return round(RNG.uniform(10, 300))
    if fuel == "Wind":
        return round(RNG.uniform(50, 400))
    return round(RNG.uniform(20, 500))


def _project(iso: str, idx: int, state: str, lat: float, lng: float, poi: str | None) -> dict:
    fuel = RNG.choice(_FUELS)
    cap = _cap(fuel)
    status = RNG.choice(_STATUS)
    yr = RNG.randint(2017, 2024)
    qd = date(yr, RNG.randint(1, 12), RNG.randint(1, 28))
    jit = 0.02
    return {
        "queue_id": f"{iso}-{idx:04d}",
        "iso": iso,
        "project_name": f"{state} {fuel} {idx}",
        "fuel_type": fuel,
        "capacity_mw": cap,
        "substation_poi": poi or f"{state} substation",
        "county": None,
        "state": state,
        "status": status,
        "queue_date": qd,
        "study_phase": RNG.choice(_PHASE),
        "estimated_cost_millions": (round(cap * RNG.uniform(0.1, 0.6), 1)
                                    if RNG.random() < 0.6 else None),
        "latitude": lat + RNG.uniform(-jit, jit),
        "longitude": lng + RNG.uniform(-jit, jit),
    }


async def _substation_anchors(conn, state: str, anchor_lat: float, anchor_lng: float,
                              near: int, spread: int) -> list[tuple[str, float, float, str | None]]:
    """Real substations: `near` nearest to the anchor + `spread` random statewide."""
    near_rows = await conn.fetch(
        """SELECT name, ST_Y(geometry) lat, ST_X(geometry) lng
           FROM substations_osm_us WHERE state=$1
           ORDER BY geometry <-> ST_SetSRID(ST_MakePoint($2,$3),4326) LIMIT $4""",
        state, anchor_lng, anchor_lat, near)
    spread_rows = await conn.fetch(
        """SELECT name, ST_Y(geometry) lat, ST_X(geometry) lng
           FROM substations_osm_us WHERE state=$1 ORDER BY random() LIMIT $2""",
        state, spread)
    out = []
    for r in [*near_rows, *spread_rows]:
        out.append((state, float(r["lat"]), float(r["lng"]), r["name"]))
    return out


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            await conn.execute(MIGRATION.read_text())
            await conn.execute("TRUNCATE interconnection_queue")
            rows: list[dict] = []
            idx = {"CAISO": 0, "ERCOT": 0, "PJM": 0, "MISO": 0, "SPP": 0}

            # CAISO — anchored near Kern County, CA.
            for st, lat, lng, poi in await _substation_anchors(conn, "CA", 35.35, -119.05, 32, 24):
                idx["CAISO"] += 1
                rows.append(_project("CAISO", idx["CAISO"], st, lat, lng, poi))
            # ERCOT — anchored near Houston, TX.
            for st, lat, lng, poi in await _substation_anchors(conn, "TX", 29.76, -95.37, 30, 26):
                idx["ERCOT"] += 1
                rows.append(_project("ERCOT", idx["ERCOT"], st, lat, lng, poi))
            # PJM / MISO / SPP — curated cluster centers.
            for iso, centers in _CURATED.items():
                per = 6 if iso == "PJM" else 4
                for (st, clat, clng) in centers:
                    for _ in range(per):
                        idx[iso] += 1
                        lat = clat + RNG.uniform(-0.4, 0.4)
                        lng = clng + RNG.uniform(-0.5, 0.5)
                        rows.append(_project(iso, idx[iso], st, lat, lng, None))

            await conn.executemany(
                """INSERT INTO interconnection_queue
                   (queue_id, iso, project_name, fuel_type, capacity_mw, substation_poi,
                    county, state, status, queue_date, study_phase, estimated_cost_millions,
                    latitude, longitude, geometry, data_source)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                           ST_SetSRID(ST_MakePoint($14,$13),4326), 'representative')""",
                [(r["queue_id"], r["iso"], r["project_name"], r["fuel_type"], r["capacity_mw"],
                  r["substation_poi"], r["county"], r["state"], r["status"], r["queue_date"],
                  r["study_phase"], r["estimated_cost_millions"], r["latitude"], r["longitude"])
                 for r in rows],
            )

            print(f"loaded {len(rows)} queue rows")
            dist = await conn.fetch(
                "SELECT iso, count(*) n, round(sum(capacity_mw)::numeric) mw "
                "FROM interconnection_queue GROUP BY iso ORDER BY iso")
            for d in dist:
                print(f"  {d['iso']:6s} {d['n']:3d} projects  {d['mw']} MW")
            for nm, (lat, lng) in {"Kern": (35.35, -119.05), "Houston": (29.76, -95.37)}.items():
                row = await conn.fetchrow(
                    """SELECT count(*) n, round(coalesce(sum(capacity_mw),0)::numeric) mw, max(iso) iso
                       FROM interconnection_queue
                       WHERE status='Active'
                         AND ST_DWithin(geometry::geography, ST_SetSRID(ST_MakePoint($1,$2),4326)::geography, 50000)""",
                    lng, lat)
                print(f"  active queue within 50km of {nm}: {row['n']} projects, {row['mw']} MW ({row['iso']})")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
