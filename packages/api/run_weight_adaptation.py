"""Run constrained weight optimization per NERC region and store profiles.

Weight Adaptation Spec, Steps 4-5. Reads the cached criterion matrices written
by precompute_weight_matrix.py, optimizes each region's weights within the
literature bounds, stores the profiles in regional_weight_profiles, and writes a
human-readable summary to docs/validation/raw/weight_profiles.json.

Prints the AC3 (weights within bounds) and AC4 (Σ weights = 1.0) checks.

Usage:
    cd packages/api && source .venv/bin/activate && python run_weight_adaptation.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.weight_adaptation import (  # noqa: E402
    CACHE_DIR, load_bounds, optimize_region, store_profile,
)

ALL_REGIONS = ["WECC", "ERCOT", "SPP", "MISO", "PJM", "SERC", "NPCC"]
OUT = REPO_ROOT / "docs" / "validation" / "raw" / "weight_profiles.json"


async def main() -> None:
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)
    try:
        bounds = await load_bounds(pool)
        calibrated_at = datetime.now(timezone.utc).date().isoformat()
        profiles = []
        for region in ALL_REGIONS:
            cache = CACHE_DIR / f"{region}.json"
            if not cache.exists():
                print(f"[{region}] no cache ({cache.name}) — skipping", flush=True)
                continue
            payload = json.loads(cache.read_text())
            profile = optimize_region(region, payload, bounds, calibrated_at)
            await store_profile(pool, profile)
            profiles.append(profile)
            v = profile["validation"]
            print(
                f"[{region}] {profile['method']}  n_eia={profile['n_eia_installations']} "
                f"(excl {profile.get('n_eia_excluded')})  "
                f"high {v['pct_eia_high_default_weights']:.2f}→{v['pct_eia_high_optimized_weights']:.2f}  "
                f"sep {v['mean_separation_default']:.3f}→{v['mean_separation_optimized']:.3f}",
                flush=True,
            )

        # ── AC3 / AC4 checks ─────────────────────────────────────────────
        print("\n=== AC3 (weights within bounds) / AC4 (Σ = 1.0) ===")
        ac3_all = ac4_all = True
        for p in profiles:
            w = p["optimized_weights"]
            s = sum(w.values())
            in_bounds = all(
                bounds[c]["min"] - 1e-6 <= v <= bounds[c]["max"] + 1e-6
                for c, v in w.items()
            )
            ac3_all &= in_bounds
            ac4_all &= abs(s - 1.0) < 1e-6
            print(f"  {p['region']:6s} Σ={s:.6f}  bounds_ok={in_bounds}")
        print(f"AC3 within bounds (all): {ac3_all}")
        print(f"AC4 sum=1.0 (all):       {ac4_all}")
        print(f"AC2 profiles generated:  {len(profiles)}/7 regions")

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "calibrated_at": calibrated_at,
            "n_regions": len(profiles),
            "ac2_profiles_generated": len(profiles),
            "ac3_within_bounds": ac3_all,
            "ac4_sum_equals_one": ac4_all,
            "profiles": profiles,
        }, indent=2))
        print(f"\nwrote {OUT.relative_to(REPO_ROOT)}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
