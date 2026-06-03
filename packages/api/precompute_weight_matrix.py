"""Pre-compute the per-criterion score matrix for weight optimization.

Weight Adaptation Spec, Steps 2-3 (the bottleneck). For each NERC region:

  Positives: up to 100 operating EIA Form 860 installations (by state→region
             map), sampled deterministically (seed 42).
  Negatives: a matched count of random points generated INSIDE the region
             polygon with PostGIS ST_GeneratePoints(geom, n, seed=42) — strictly
             in-region and deterministic.

Each location is scored once with score_solar_siting (default weights — the
per-criterion *scores* are weight-independent; only the composite uses weights).
We cache, per location, the 8 scored-criterion values and a validity mask
(1 where the criterion had data, 0 where it was missing). The optimizer later
reconstructs the composite as a masked weighted average, exactly mirroring the
scoring pipeline.

Output: weight_cache/<region>.json (one per region, written on completion so the
run is resumable — already-cached regions are skipped). Concurrency is fixed at
2 per the spec (conservative, avoids upstream-API contention).

Usage:
    cd packages/api && source .venv/bin/activate
    python precompute_weight_matrix.py            # all regions, skip cached
    python precompute_weight_matrix.py --region WECC --force
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.nerc_regions import STATE_TO_NERC, states_for_region  # noqa: E402
from app.solar_scoring_v2 import score_solar_siting  # noqa: E402

CACHE_DIR = Path(__file__).resolve().parent / "weight_cache"
CACHE_DIR.mkdir(exist_ok=True)

SAMPLE_PER_REGION = 100
CONCURRENCY = 2
PER_LOCATION_TIMEOUT_S = 150.0
SEED = 42

ALL_REGIONS = ["WECC", "ERCOT", "SPP", "MISO", "PJM", "SERC", "NPCC"]


async def scored_criteria_order(pool: asyncpg.Pool) -> list[str]:
    """The 8 scored solar criteria, in a stable order (alphabetical by id)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT criterion_id FROM methodology_criteria
            WHERE workflow_type='solar_siting' AND criterion_type='scored'
            ORDER BY criterion_id
            """
        )
    return [r["criterion_id"] for r in rows]


async def eia_locations(pool: asyncpg.Pool, region: str) -> list[dict[str, Any]]:
    states = states_for_region(region)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT plant_code, latitude, longitude
            FROM solar_eia_installations
            WHERE operating_status='OP' AND state = ANY($1::text[])
            ORDER BY plant_code
            """,
            states,
        )
    pool_rows = [dict(r) for r in rows]
    rng = random.Random(f"{SEED}-{region}-eia")
    rng.shuffle(pool_rows)
    sample = pool_rows[:SAMPLE_PER_REGION]
    return [
        {"kind": "eia", "id": f"{region}-EIA-{r['plant_code']}",
         "lat": float(r["latitude"]), "lng": float(r["longitude"])}
        for r in sample
    ]


async def random_locations(
    pool: asyncpg.Pool, region: str, n: int
) -> list[dict[str, Any]]:
    """n deterministic random points strictly inside the region polygon."""
    if n <= 0:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ST_Y(p) AS lat, ST_X(p) AS lng FROM (
                SELECT (ST_Dump(ST_GeneratePoints(geometry, $1, $2))).geom AS p
                FROM nerc_regions WHERE region = $3
            ) q
            """,
            n, SEED, region,
        )
    return [
        {"kind": "random", "id": f"{region}-RND-{i}",
         "lat": float(r["lat"]), "lng": float(r["lng"])}
        for i, r in enumerate(rows)
    ]


async def score_one(
    pool: asyncpg.Pool, loc: dict[str, Any], crit_order: list[str],
    sem: asyncio.Semaphore, progress: dict[str, int],
) -> dict[str, Any]:
    async with sem:
        t0 = time.time()
        try:
            r = await asyncio.wait_for(
                score_solar_siting(pool, loc["lat"], loc["lng"]),
                timeout=PER_LOCATION_TIMEOUT_S,
            )
            cs = r.get("criteria_scores", {})
            # weight-independent per-criterion scores + validity mask
            scores = [cs.get(c, {}).get("score") for c in crit_order]
            mask = [0.0 if s is None else 1.0 for s in scores]
            row = {
                **loc,
                "scores": [0.0 if s is None else float(s) for s in scores],
                "mask":   mask,
                "rating": r.get("rating"),
                "composite_default": r.get("score"),
                "exclusions": r.get("exclusions") or [],
                "elapsed_s": round(time.time() - t0, 1),
                "error": None,
            }
        except Exception as e:  # noqa: BLE001
            row = {
                **loc, "scores": None, "mask": None, "rating": None,
                "composite_default": None, "exclusions": [],
                "elapsed_s": round(time.time() - t0, 1),
                "error": f"{type(e).__name__}: {e}",
            }
        progress["done"] += 1
        if row["error"]:
            progress["errors"] += 1
        tag = "ERR" if row["error"] else f"{row['rating']:<9}"
        print(f"  [{progress['done']:>4}/{progress['total']}] {loc['id']:<18} "
              f"{row['elapsed_s']:5.1f}s {tag} "
              f"comp={row['composite_default']}", flush=True)
        return row


async def run_region(
    pool: asyncpg.Pool, region: str, crit_order: list[str], force: bool
) -> None:
    out = CACHE_DIR / f"{region}.json"
    if out.exists() and not force:
        print(f"[{region}] cached — skipping ({out.name})", flush=True)
        return

    eia = await eia_locations(pool, region)
    rnd = await random_locations(pool, region, len(eia))   # matched count
    locs = eia + rnd
    print(f"\n[{region}] {len(eia)} EIA + {len(rnd)} random = {len(locs)} locations",
          flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    progress = {"done": 0, "total": len(locs), "errors": 0}
    t0 = time.time()
    rows = await asyncio.gather(
        *[score_one(pool, loc, crit_order, sem, progress) for loc in locs]
    )
    eia_rows = [r for r in rows if r["kind"] == "eia"]
    rnd_rows = [r for r in rows if r["kind"] == "random"]
    n_excl = sum(1 for r in eia_rows if r["rating"] == "Excluded")
    payload = {
        "region": region,
        "criteria_order": crit_order,
        "seed": SEED,
        "n_eia": len(eia_rows),
        "n_random": len(rnd_rows),
        "n_errors": progress["errors"],
        "n_eia_excluded": n_excl,
        "eia": eia_rows,
        "random": rnd_rows,
        "elapsed_s": round(time.time() - t0, 1),
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f"[{region}] done in {payload['elapsed_s']}s — "
          f"{len(eia_rows)} EIA ({n_excl} excluded), {len(rnd_rows)} random, "
          f"{progress['errors']} errors → {out.name}", flush=True)


async def main(regions: list[str], force: bool) -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=4, max_size=8)
    try:
        crit_order = await scored_criteria_order(pool)
        print(f"scored criteria ({len(crit_order)}): {crit_order}", flush=True)
        grand_t0 = time.time()
        for region in regions:
            await run_region(pool, region, crit_order, force)
        print(f"\nALL DONE in {(time.time()-grand_t0)/60:.1f} min", flush=True)
    finally:
        await pool.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--region", choices=ALL_REGIONS, help="single region (default: all)")
    p.add_argument("--force", action="store_true", help="recompute even if cached")
    args = p.parse_args()
    regions = [args.region] if args.region else ALL_REGIONS
    asyncio.run(main(regions, args.force))
