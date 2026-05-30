"""Validate the flood scoring pipeline against Harris County NFIP claims.

Claims are tract-level. For the top-N tracts by claim volume we compute the
actual average annual loss, then score a sample of real NSI structures inside
each tract (exact tract polygons from Census TIGERweb) with the production
flood-scoring logic, and compare predicted vs. actual at tract level.

Writes app/flood_validation.json (consumed by GET /flood/methodology).
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

import asyncpg
import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.flood_scoring import (  # noqa: E402
    DEFAULT_FIRST_FLOOR_HEIGHT_FT,
    DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT,
    UA,
    classify_zone,
    ddf_lookup,
    map_occupancy_class,
    query_3dep_ground_ft,
    query_nfhl,
)

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

TIGERWEB = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Tracts_Blocks/MapServer/0/query"
)
NSI_URL = "https://nsi.sec.usace.army.mil/nsiapi/structures"
TOP_TRACTS = 50
STRUCTS_PER_TRACT = 15
CONCURRENCY = 8
OUT = Path(__file__).resolve().parent / "app" / "flood_validation.json"


# ─── helpers ────────────────────────────────────────────────────────────────


async def tract_polygon(client: httpx.AsyncClient, geoid: str) -> list[list[float]] | None:
    try:
        r = await client.get(
            TIGERWEB,
            params={
                "where": f"GEOID='{geoid}'",
                "outFields": "GEOID",
                "returnGeometry": "true",
                "outSR": "4326",
                "f": "json",
            },
        )
        feats = r.json().get("features", [])
    except (httpx.HTTPError, ValueError):
        return None
    if not feats:
        return None
    rings = feats[0].get("geometry", {}).get("rings")
    return rings[0] if rings else None


async def nsi_in_polygon(client: httpx.AsyncClient, ring: list[list[float]]) -> list[dict]:
    poly = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {},
             "geometry": {"type": "Polygon", "coordinates": [ring]}}
        ],
    }
    try:
        r = await client.post(
            NSI_URL, params={"fmt": "fc"}, json=poly,
            headers={"User-Agent": UA, "Content-Type": "application/json"},
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return []
    return data.get("features", []) if isinstance(data, dict) else []


async def score_structure(
    client: httpx.AsyncClient, pool: asyncpg.Pool, feat: dict
) -> float | None:
    """Predicted annual flood risk ($) for one NSI structure, using the same
    NFHL + 3DEP + HAZUS logic as the production pipeline (NSI attrs already in hand)."""
    g = feat.get("geometry", {})
    coords = g.get("coordinates")
    if not coords or len(coords) < 2:
        return None
    lng, lat = float(coords[0]), float(coords[1])
    p = feat.get("properties", {})
    nfhl = await query_nfhl(client, lng, lat)
    zinfo = classify_zone(nfhl["flood_zone"], nfhl["zone_subtype"])
    bfe = nfhl["static_bfe"]

    ffh = float(p["found_ht"]) if p.get("found_ht") is not None else DEFAULT_FIRST_FLOOR_HEIGHT_FT
    ground_ft = await query_3dep_ground_ft(client, lng, lat)
    if ground_ft is None and p.get("ground_elv") is not None:
        ground_ft = float(p["ground_elv"])

    if zinfo["is_sfha"] and bfe is not None and ground_ft is not None:
        depth_ft = bfe - ground_ft - ffh
    elif zinfo["is_sfha"]:
        depth_ft = DEFAULT_SFHA_DEPTH_ABOVE_GRADE_FT - ffh
    else:
        return 0.0  # outside SFHA → no modeled inundation

    occ = map_occupancy_class(p.get("occtype"), p.get("num_story"), p.get("found_type"))
    ddf = await ddf_lookup(pool, occ, depth_ft)
    if not ddf:
        return 0.0
    vs = float(p["val_struct"]) if p.get("val_struct") is not None else 0.0
    vc = float(p["val_cont"]) if p.get("val_cont") is not None else 0.0
    loss = vs * ddf["structural_damage_pct"] / 100.0 + vc * ddf["contents_damage_pct"] / 100.0
    return loss * zinfo["annual_probability"]


def spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((rx[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ry[i] - my) ** 2 for i in range(n)))
    return num / (dx * dy) if dx > 0 and dy > 0 else 0.0


# ─── main ───────────────────────────────────────────────────────────────────


async def main() -> None:
    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=2, max_size=10, ssl="require"
    )

    rows = await pool.fetch(
        """SELECT census_tract,
                  COUNT(*) AS n,
                  SUM(COALESCE(amount_paid_on_building_claim,0)
                      + COALESCE(amount_paid_on_contents_claim,0)) AS paid,
                  MIN(date_of_loss) AS mn, MAX(date_of_loss) AS mx
           FROM flood_nfip_claims_harris
           WHERE census_tract IS NOT NULL AND length(census_tract) = 11
           GROUP BY census_tract
           ORDER BY n DESC
           LIMIT 200"""
    )
    print(f"Candidate tracts: {len(rows)}; scoring up to {TOP_TRACTS} ...", flush=True)

    # Zone accuracy from the full claims set.
    zrow = await pool.fetchrow(
        """SELECT
             COUNT(*) FILTER (WHERE flood_zone ~ '^(A|V)') AS sfha,
             COUNT(*) FILTER (WHERE NOT (flood_zone ~ '^(A|V)') OR flood_zone IS NULL) AS nonsfha,
             COUNT(*) AS total
           FROM flood_nfip_claims_harris"""
    )
    pct_claims_sfha = round(100.0 * zrow["sfha"] / zrow["total"], 1)
    pct_claims_outside = round(100.0 * zrow["nonsfha"] / zrow["total"], 1)

    results: list[dict] = []
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=30.0) as client:
        for row in rows:
            if len(results) >= TOP_TRACTS:
                break
            geoid = row["census_tract"]
            ring = await tract_polygon(client, geoid)
            if not ring:
                continue
            feats = await nsi_in_polygon(client, ring)
            if not feats:
                continue
            sample = feats[: STRUCTS_PER_TRACT]

            async def _score(f: dict) -> float | None:
                async with sem:
                    return await score_structure(client, pool, f)

            preds = await asyncio.gather(*(_score(f) for f in sample))
            preds = [p for p in preds if p is not None]
            if not preds:
                continue

            mn, mx = row["mn"], row["mx"]
            years = max(1.0, (mx - mn).days / 365.25) if mn and mx else 1.0
            nclaims = int(row["n"])
            actual_aal = float(row["paid"]) / years          # tract aggregate / yr
            actual_severity = float(row["paid"]) / nclaims    # avg paid per claim
            n_sfha = sum(1 for p in preds if p > 0)
            results.append({
                "tract": geoid,
                "n_claims": nclaims,
                "actual_avg_annual_loss": round(actual_aal, 2),
                "actual_loss_per_claim": round(actual_severity, 2),
                "predicted_mean_structure_risk": round(sum(preds) / len(preds), 2),
                "n_structures_scored": len(preds),
                "pct_structures_in_sfha": round(100.0 * n_sfha / len(preds), 1),
            })
            if len(results) % 10 == 0:
                print(f"  scored {len(results)} tracts "
                      f"({sum(r['n_structures_scored'] for r in results)} structures)", flush=True)

    n = len(results)
    pred = [r["predicted_mean_structure_risk"] for r in results]
    # Like-for-like actual: average paid PER CLAIM (loss severity/intensity),
    # comparable to predicted per-structure intensity. (Tract aggregate-per-year
    # scales with tract size and is not comparable to a per-structure mean.)
    sev = [r["actual_loss_per_claim"] for r in results]

    def decile_ratio(rank_by: list[float], value: list[float]) -> float | None:
        order = sorted(range(n), key=lambda i: rank_by[i])
        d = max(1, n // 10)
        bot = [value[i] for i in order[:d]]
        top = [value[i] for i in order[-d:]]
        mb = sum(bot) / len(bot)
        return round((sum(top) / len(top)) / mb, 2) if mb > 0 else None

    # Discrimination: predicted intensity in the top vs bottom decile of tracts
    # ranked by ACTUAL severity (does the model rate actually-severe tracts higher?).
    discrimination = decile_ratio(sev, pred)
    # Model's own dynamic range (top vs bottom decile of predicted).
    model_dynamic_range = decile_ratio(pred, pred)
    rho = round(spearman(pred, sev), 3)

    metrics = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "method": (
            "Tract-level backtest against OpenFEMA NFIP redacted claims (Harris "
            "County, TX). For each top tract by claim volume, real NSI structures "
            "inside the Census TIGERweb tract polygon were scored with the "
            "production NFHL+3DEP+HAZUS pipeline. Predicted mean per-structure "
            "annual risk is compared to the tract's actual loss per claim "
            "(like-for-like loss intensity)."
        ),
        "tracts_evaluated": n,
        "structures_scored": sum(r["n_structures_scored"] for r in results),
        "discrimination_ratio_top_vs_bottom_decile": discrimination,
        "model_dynamic_range_predicted": model_dynamic_range,
        "spearman_rank_correlation": rho,
        "zone_accuracy": {
            "pct_claims_in_sfha": pct_claims_sfha,
            "pct_claims_outside_sfha": pct_claims_outside,
            "note": (
                "Roughly half of Harris County NFIP claims originate outside the "
                "mapped SFHA — consistent with the model's residual-risk treatment "
                "of X zones and the documented ~25%+ national share of out-of-SFHA claims."
            ),
        },
        "targets": {"discrimination_ratio": ">4.0", "spearman_rank_correlation": ">0.4"},
        "targets_met": {
            "discrimination_ratio": discrimination is not None and discrimination > 4.0,
            "spearman_rank_correlation": rho > 0.4,
        },
        "interpretation": (
            "Predicted risk does not track Harris County NFIP loss severity "
            f"(discrimination {discrimination}, Spearman {rho}) and is well below the "
            ">4.0 / >0.4 targets. The backtest is dominated by Hurricane Harvey (2017), "
            "a >1000-year PLUVIAL (rainfall) event: 55.8% of Harris claims fall outside "
            "the FEMA SFHA. This model scores FLUVIAL/coastal 100-year NFHL hazard only "
            "(a documented limitation) and therefore cannot reproduce a pluvial-driven "
            "loss distribution. It is appropriate for screening NFHL-mapped fluvial/"
            "coastal flood risk; reproducing Harvey-type losses would require pluvial "
            "(rainfall) hazard layers — flagged as future work."
        ),
        "tracts": results,
    }
    OUT.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    print(f"\nWrote {OUT}")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
