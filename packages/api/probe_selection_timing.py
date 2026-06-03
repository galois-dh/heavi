"""One-off bottleneck probe for the data selection engine.

Runs resolve_sources() for a single location with HEAVI_SELECTION_TIMING=1 so
every source availability check prints `source_id: time_ms`, then reports the
top-5 slowest. Diagnostic only — not part of the validation harness.

Usage:
    cd packages/api && source .venv/bin/activate
    HEAVI_SELECTION_TIMING=1 python probe_selection_timing.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.data_selection import resolve_sources  # noqa: E402

LAT, LNG = 35.35, -119.05
WORKFLOW = "solar_siting"


async def main() -> None:
    os.environ["HEAVI_SELECTION_TIMING"] = "1"  # force per-source timing print
    dsn = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=8)
    try:
        print(f"Probing {WORKFLOW} at ({LAT}, {LNG})\n", flush=True)
        t0 = time.perf_counter()
        cache = await resolve_sources(pool, WORKFLOW, LAT, LNG)
        wall = time.perf_counter() - t0
        print(f"\nresolve_sources wall: {wall:.2f} s across {len(cache)} sources", flush=True)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
