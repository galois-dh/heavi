"""Step 3: within-AE discrimination check.

Pick Harris tracts that are predominantly SFHA (by claim rating), score real NSI
structures with the production pipeline, and confirm the model produces sensible,
varied, non-degenerate risk inside the zones where NFHL data is most accurate.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.flood_scoring import classify_zone, query_nfhl  # noqa: E402
from validate_flood_harris import nsi_in_polygon, score_structure, tract_polygon  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def main() -> None:
    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=2, max_size=8, ssl="require"
    )
    rows = await pool.fetch(
        """SELECT census_tract,
                  COUNT(*) AS n,
                  ROUND(100.0 * COUNT(*) FILTER (WHERE flood_zone ~ '^(A|V)')
                        / COUNT(*), 1) AS sfha_pct
           FROM flood_nfip_claims_harris
           WHERE length(census_tract) = 11
           GROUP BY census_tract
           HAVING COUNT(*) >= 80
           ORDER BY sfha_pct DESC, n DESC
           LIMIT 10"""
    )
    print("STEP 3 — WITHIN-AE DISCRIMINATION (predominantly-SFHA Harris tracts)")
    print(f"{'tract':12} {'claim_sfha%':>10} {'n_struct':>8} {'%AE':>5} "
          f"{'min$':>8} {'med$':>9} {'max$':>10}")
    all_preds: list[float] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for r in rows:
            ring = await tract_polygon(client, r["census_tract"])
            if not ring:
                continue
            feats = await nsi_in_polygon(client, ring)
            if not feats:
                continue
            sample = feats[:5]
            preds = await asyncio.gather(*(score_structure(client, pool, f) for f in sample))
            preds = [p for p in preds if p is not None]
            if not preds:
                continue
            # how many of the sampled structures are scored as in an SFHA zone?
            zones = []
            for f in sample:
                c = f.get("geometry", {}).get("coordinates")
                if c and len(c) >= 2:
                    nf = await query_nfhl(client, float(c[0]), float(c[1]))
                    zones.append(classify_zone(nf["flood_zone"], nf["zone_subtype"])["is_sfha"])
            pct_ae = round(100.0 * sum(zones) / len(zones), 0) if zones else 0
            all_preds.extend(preds)
            print(f"{r['census_tract']:12} {r['sfha_pct']:>9}% {len(preds):>8} {pct_ae:>4.0f}% "
                  f"{min(preds):>8,.0f} {statistics.median(preds):>9,.0f} {max(preds):>10,.0f}")
    print()
    if all_preds:
        nonzero = [p for p in all_preds if p > 0]
        print(f"Across all scored structures: n={len(all_preds)}, "
              f"non-zero={len(nonzero)} ({100.0*len(nonzero)/len(all_preds):.0f}%), "
              f"range ${min(all_preds):,.0f}-${max(all_preds):,.0f}, "
              f"median ${statistics.median(all_preds):,.0f}")
        spread = max(all_preds) / (min(nonzero) if nonzero else 1)
        print(f"Within-SFHA predicted spread (max/min-nonzero): {spread:.1f}x")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
