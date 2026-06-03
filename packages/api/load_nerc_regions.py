"""Load NERC region polygons into PostGIS (Weight Adaptation Spec, Step 1).

Applies migrations/2026-06-07_weight_adaptation.sql, then builds nerc_regions by
dissolving the vendored US state polygons (nerc_us_states.geojson) by the
canonical STATE_TO_NERC membership. Each region becomes one MultiPolygon
(ST_Union of its member states, forced to MULTI).

Idempotent: truncates and reloads nerc_regions on each run.

Usage:
    cd packages/api && source .venv/bin/activate && python load_nerc_regions.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.nerc_regions import NERC_REGION_NAMES, STATE_TO_NERC  # noqa: E402

GEOJSON = Path(__file__).resolve().parent / "nerc_us_states.geojson"
MIGRATION = Path(__file__).resolve().parent / "migrations" / "2026-06-07_weight_adaptation.sql"


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            # 1) schema
            await conn.execute(MIGRATION.read_text())
            print("applied migration: nerc_regions, regional_weight_profiles")

            # 2) parse state polygons → per-region list of state GeoJSON geometries
            fc = json.loads(GEOJSON.read_text())
            by_region: dict[str, list[str]] = {}
            skipped: list[str] = []
            for feat in fc["features"]:
                postal = feat.get("id")
                region = STATE_TO_NERC.get(postal)
                if region is None:
                    skipped.append(postal)
                    continue
                by_region.setdefault(region, []).append(json.dumps(feat["geometry"]))
            print(f"states mapped: {sum(len(v) for v in by_region.values())}, "
                  f"unmapped (no NERC region): {sorted(skipped)}")

            # 3) dissolve each region's states into one MultiPolygon and upsert
            await conn.execute("TRUNCATE nerc_regions")
            for region, geoms in sorted(by_region.items()):
                # ST_Union the member-state geometries, force MULTI, set SRID 4326.
                await conn.execute(
                    """
                    INSERT INTO nerc_regions (region, name, geometry)
                    SELECT $1, $2,
                           ST_Multi(ST_SetSRID(
                               ST_Union(ST_GeomFromGeoJSON(g)), 4326))
                    FROM unnest($3::text[]) AS g
                    """,
                    region, NERC_REGION_NAMES[region], geoms,
                )
                n_states = len(geoms)
                print(f"  {region}: dissolved {n_states} states")

            # 4) verify: every region present + a few known points resolve
            rows = await conn.fetch(
                "SELECT region, ST_GeometryType(geometry) gt, ST_NPoints(geometry) np "
                "FROM nerc_regions ORDER BY region"
            )
            print("\nloaded regions:")
            for r in rows:
                print(f"  {r['region']:6s} {r['gt']:18s} npoints={r['np']}")

            checks = [
                (32.0, -119.5, "WECC"),   # off CA coast? -> actually inland check below
                (31.0, -99.0,  "ERCOT"),  # central TX
                (35.5, -119.0, "WECC"),   # Kern County CA
                (35.7, -78.6,  "SERC"),   # Raleigh NC
                (33.4, -112.0, "WECC"),   # Phoenix AZ
                (27.9, -81.7,  "SERC"),   # central FL
                (40.0, -75.5,  "PJM"),    # PA/NJ
                (44.9, -93.2,  "MISO"),   # Minneapolis MN
                (42.9, -75.5,  "NPCC"),   # central NY
                (37.7, -97.3,  "SPP"),    # Wichita KS
            ]
            print("\npoint-in-region checks:")
            for lat, lng, expect in checks:
                got = await conn.fetchval(
                    "SELECT region FROM nerc_regions "
                    "WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint($1,$2),4326)) LIMIT 1",
                    lng, lat,
                )
                flag = "ok" if got == expect else f"EXPECTED {expect}"
                print(f"  ({lat:.1f},{lng:.1f}) -> {got}  [{flag}]")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
