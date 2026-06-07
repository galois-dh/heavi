"""Regenerate the docs/sales sample output package from the live scoring engine.

Scores 10 Kern County, CA parcels through the current production solar engine
(`score_solar_siting`) and renders the two sample PDFs with `app/solar_pdf.py`:

  * Heavi_Sample_Batch_Portfolio.pdf      — ranked summary + per-site detail
  * Heavi_Sample_Single_Site_Assessment.pdf — the lead corridor parcel

The 10 parcels (5 greenfield in the Solar Star / Edwards-Sanborn corridor + 5
random San Joaquin Valley agricultural parcels) match the package described in
docs/validation/Heavi_Month2_Sprint_Validation.md. The original run did not
persist its inputs; this script and Heavi_Sample_Parcels.csv now do, so the
package is reproducible. PDFs pick up the natural-language display names
(criterion/source) from app/display_names.py.

Usage (from packages/api, with the repo-root .env providing DATABASE_URL +
NREL_API_KEY):

    .venv/bin/python -m scripts.generate_sample_package
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]
SALES = REPO_ROOT / "docs" / "sales"

# 10 Kern County, CA parcels. Lead 5 are greenfield in the Solar Star /
# Edwards-Sanborn utility-solar corridor; the next 5 are random agricultural
# parcels in the San Joaquin Valley farm belt (Wasco / Shafter / Bakersfield).
PARCELS: list[dict] = [
    {"name": "Solar Star Corridor 1", "lat": 34.8200, "lng": -118.3600},
    {"name": "Solar Star Corridor 2", "lat": 34.8350, "lng": -118.3850},
    {"name": "Solar Star Corridor 3", "lat": 34.8100, "lng": -118.3400},
    {"name": "Edwards-Sanborn Corridor 4", "lat": 34.8500, "lng": -118.4050},
    {"name": "Edwards-Sanborn Corridor 5", "lat": 34.7950, "lng": -118.3250},
    {"name": "San Joaquin Valley Ag 1 (W of Wasco)", "lat": 35.5800, "lng": -119.4200},
    {"name": "San Joaquin Valley Ag 2 (Buttonwillow)", "lat": 35.3900, "lng": -119.5500},
    {"name": "San Joaquin Valley Ag 3 (Semitropic)", "lat": 35.5600, "lng": -119.6500},
    {"name": "San Joaquin Valley Ag 4 (near Shafter)", "lat": 35.5080, "lng": -119.2730},
    {"name": "San Joaquin Valley Ag 5 (near Lost Hills)", "lat": 35.6150, "lng": -119.6900},
]


async def _init(conn: asyncpg.Connection) -> None:
    for t in ("json", "jsonb"):
        await conn.set_type_codec(
            t, encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )


async def main() -> int:
    load_dotenv(REPO_ROOT / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set (expected in repo-root .env)")

    # Imports that need the package on sys.path; run as `python -m scripts....`.
    from app.solar_pdf import solar_batch_pdf, solar_single_pdf
    from app.solar_scoring_v2 import score_solar_siting

    pool = await asyncpg.create_pool(
        url, min_size=2, max_size=6, ssl="require", init=_init
    )

    results: list[dict] = []
    for p in PARCELS:
        try:
            r = await score_solar_siting(pool, p["lat"], p["lng"])
            r = {**r, "name": p["name"]}
        except Exception as e:  # noqa: BLE001 — one bad parcel must not fail the batch
            r = {
                "query": {"latitude": p["lat"], "longitude": p["lng"]},
                "name": p["name"], "score": None, "rating": "CANNOT ASSESS",
                "error": f"{type(e).__name__}: {e}",
            }
        results.append(r)
        print(f"  {p['name']:<42} score={r.get('score')} rating={r.get('rating')}")
    await pool.close()

    SALES.mkdir(parents=True, exist_ok=True)

    # Persist the inputs so the package is reproducible next time.
    with (SALES / "Heavi_Sample_Parcels.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "latitude", "longitude", "category"])
        for i, p in enumerate(PARCELS):
            cat = "corridor_greenfield" if i < 5 else "valley_agricultural"
            w.writerow([p["name"], p["lat"], p["lng"], cat])

    batch_pdf = solar_batch_pdf(results)
    (SALES / "Heavi_Sample_Batch_Portfolio.pdf").write_bytes(batch_pdf)

    lead = results[0]
    single_pdf = solar_single_pdf(
        lead, address="Kern County, CA — Solar Star / Edwards-Sanborn corridor"
    )
    (SALES / "Heavi_Sample_Single_Site_Assessment.pdf").write_bytes(single_pdf)

    print(f"\nwrote batch PDF  ({len(batch_pdf)} bytes)")
    print(f"wrote single PDF ({len(single_pdf)} bytes)")
    print(f"wrote inputs     ({SALES / 'Heavi_Sample_Parcels.csv'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
