"""Validate trade-area scoring against professionally-sited Starbucks locations.

Score a sample of Dallas County Starbucks (business_category=coffee_shop) vs. a
sample of random Dallas County locations; report the share scoring Strong and the
mean scores. Target: >50% of Starbucks score Strong.

ORS isochrones are rate-limited (≤20/min, 500/day) — each score is ONE ORS
request, throttled with a delay between calls.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.trade_area_scoring import score_trade_area  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

N = 30
ORS_DELAY_S = 3.5  # ~17/min, under the ORS 20/min isochrone limit


async def score_points(pool, points: list[tuple[float, float]], label: str) -> list[float]:
    scores: list[float] = []
    for i, (lat, lng) in enumerate(points):
        try:
            # wait_for guards against a stalled pooled connection hanging the run.
            r = await asyncio.wait_for(
                score_trade_area(
                    pool, latitude=lat, longitude=lng, business_category="coffee_shop"
                ),
                timeout=75,
            )
            scores.append(r["suitability_score"])
        except Exception as e:  # noqa: BLE001  (includes asyncio.TimeoutError)
            print(f"  {label} {i} ({lat},{lng}) failed: {type(e).__name__}: {e}", flush=True)
        if (i + 1) % 10 == 0:
            print(f"  {label}: scored {i + 1}/{len(points)}", flush=True)
        await asyncio.sleep(ORS_DELAY_S)
    return scores


async def main() -> None:
    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=2, max_size=6, ssl="require",
        command_timeout=30, max_inactive_connection_lifetime=20,
    )
    sb = await pool.fetch(
        """SELECT ST_Y(geometry) AS lat, ST_X(geometry) AS lng
           FROM trade_area_pois_dallas
           WHERE name ILIKE '%starbucks%'
           ORDER BY random() LIMIT $1""",
        N,
    )
    rnd = await pool.fetch(
        """SELECT ST_Y(p) AS lat, ST_X(p) AS lng FROM (
              SELECT ST_SetSRID(ST_MakePoint(-97.0 + random()*0.54,
                                             32.54 + random()*0.48), 4326) AS p
              FROM generate_series(1, 3000)
           ) s JOIN trade_area_census_tracts_dallas t ON ST_Contains(t.geometry, s.p)
           LIMIT $1""",
        N,
    )
    starbucks = [(float(r["lat"]), float(r["lng"])) for r in sb]
    random_pts = [(float(r["lat"]), float(r["lng"])) for r in rnd]
    print(f"Scoring {len(starbucks)} Starbucks + {len(random_pts)} random Dallas locations "
          f"(~{ORS_DELAY_S * (len(starbucks)+len(random_pts)):.0f}s) ...", flush=True)

    sb_scores = await score_points(pool, starbucks, "starbucks")
    rnd_scores = await score_points(pool, random_pts, "random")

    pct_strong = 100.0 * sum(1 for s in sb_scores if s >= 0.70) / len(sb_scores)
    rnd_strong = 100.0 * sum(1 for s in rnd_scores if s >= 0.70) / len(rnd_scores)
    print("\n──── Starbucks trade-area validation ────")
    print(f"Starbucks scored: {len(sb_scores)} | random scored: {len(rnd_scores)}")
    print(f"% Starbucks scoring Strong (>=0.70): {pct_strong:.1f}%")
    print(f"% random scoring Strong:             {rnd_strong:.1f}%")
    print(f"Mean score — Starbucks: {statistics.mean(sb_scores):.3f}")
    print(f"Mean score — random:    {statistics.mean(rnd_scores):.3f}")
    print(f"Median — Starbucks: {statistics.median(sb_scores):.3f} | "
          f"random: {statistics.median(rnd_scores):.3f}")
    print(f"TARGET met (>50% Starbucks Strong): {pct_strong > 50}")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
