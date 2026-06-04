"""Step 1 — diagnose every Excluded EIA installation (Exclusion Precision Spec).

For each EIA installation that scored "Excluded" in Test 1, re-query the
underlying data to find the *specific* trigger behind each exclusion criterion:
  excl_protected → PAD-US GAP status + designation + managing agency
  excl_urban     → NLCD class
  excl_flood     → FEMA NFHL zone
  excl_steep     → computed slope %
  excl_wetlands  → wetland source + classification
  excl_critical_habitat → species

Writes a diagnostic table (markdown + JSON) under docs/validation/.

Usage:
    cd packages/api && source .venv/bin/activate && python diagnose_exclusions.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.flood_scoring import query_nfhl  # noqa: E402
from app.integrations import (  # noqa: E402
    critical_habitat_at_point, nlcd_class_at_point, padus_at_point,
)
from app.solar_scoring_v2 import _Measurements  # noqa: E402

TEST1 = REPO_ROOT / "docs" / "validation" / "raw" / "test1_solar_multistate.json"
OUT_JSON = REPO_ROOT / "docs" / "validation" / "raw" / "exclusion_diagnosis.json"
OUT_MD = REPO_ROOT / "docs" / "validation" / "exclusion_diagnosis.md"

# GAP status → whether the spec treats it as a hard exclusion
GAP_HARD = {"1", "2"}


def _excluded_eia() -> list[dict[str, Any]]:
    d = json.loads(TEST1.read_text())
    rows = []
    for state, p in d["raw_results"].items():
        for r in p["eia_results"]:
            if r.get("rating") == "Excluded":
                rows.append({**r, "state": state})
    return rows


async def diagnose_one(
    pool: asyncpg.Pool, client: httpx.AsyncClient, row: dict[str, Any],
) -> dict[str, Any]:
    lat, lng = row["lat"], row["lng"]
    fired = row.get("exclusions") or []
    meas = _Measurements(pool, client, lat, lng)
    triggers: dict[str, Any] = {}

    if "excl_protected" in fired:
        pa = await padus_at_point(client, latitude=lat, longitude=lng)
        triggers["excl_protected"] = [
            {"gap_status": p.get("gap_status"),
             "designation": p.get("designation_type"),
             "manager": p.get("manager_name"),
             "unit": p.get("unit_name")}
            for p in pa
        ]
    if "excl_urban" in fired:
        lc = await nlcd_class_at_point(client, latitude=lat, longitude=lng)
        triggers["excl_urban"] = {"nlcd_code": (lc or {}).get("code"),
                                  "label": (lc or {}).get("label")}
    if "excl_flood" in fired:
        nfhl = await query_nfhl(client, lng, lat)
        triggers["excl_flood"] = {"flood_zone": (nfhl or {}).get("flood_zone")}
    if "excl_steep" in fired:
        t = await meas.terrain()
        triggers["excl_steep"] = {"slope_pct": (t or {}).get("slope_pct")}
    if "excl_wetlands" in fired:
        triggers["excl_wetlands"] = {"note": "see scoring basis (NWI/SSURGO)"}
    if "excl_critical_habitat" in fired:
        ch = await critical_habitat_at_point(client, latitude=lat, longitude=lng)
        triggers["excl_critical_habitat"] = {
            "species": sorted({c.get("common_name") for c in ch if c.get("common_name")})[:3]
        }
    return {**row, "triggers": triggers}


def _assess(criterion: str, trig: Any) -> str:
    """Spec-rule assessment of whether this is a true exclusion or false positive."""
    if criterion == "excl_protected":
        gaps = [str(t.get("gap_status")) for t in trig]
        if any(g in GAP_HARD for g in gaps):
            return "TRUE (GAP 1-2)"
        return "FALSE POSITIVE (GAP 3-4 — multi-use, solar often permitted)"
    if criterion == "excl_urban":
        code = trig.get("nlcd_code")
        if code in (23, 24):
            return "TRUE (NLCD 23-24, dense development)"
        if code in (21, 22):
            return "FALSE POSITIVE (NLCD 21-22 — open/low-intensity)"
        return f"REVIEW (NLCD {code})"
    if criterion == "excl_flood":
        z = (trig.get("flood_zone") or "").upper()
        if z.startswith("V"):
            return "TRUE (V zone, coastal high hazard)"
        if z.startswith("A"):
            return "FALSE POSITIVE (A/AE — solar permitted w/ elevated mounting)"
        return f"FALSE POSITIVE (zone {z or 'none'})"
    if criterion == "excl_steep":
        s = trig.get("slope_pct")
        if s is not None and s >= 20.0:
            return f"TRUE (slope {s:.1f}% ≥ 20%)"
        return f"FALSE POSITIVE (slope {s if s is None else round(s,1)}% < 20% new threshold)"
    return "REVIEW"


async def main() -> None:
    excluded = _excluded_eia()
    pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=4)
    try:
        # enrich with operator/technology from the installations table
        async with pool.acquire() as conn:
            for r in excluded:
                meta = await conn.fetchrow(
                    "SELECT plant_name, capacity_mw, technology, operating_year "
                    "FROM solar_eia_installations WHERE plant_code=$1",
                    r.get("plant_code"),
                )
                if meta:
                    r["technology"] = meta["technology"]
                    r["operating_year"] = meta["operating_year"]
        async with httpx.AsyncClient(timeout=30.0) as client:
            results = []
            for r in excluded:
                results.append(await diagnose_one(pool, client, r))
                print(f"  diagnosed {r.get('plant_name')} ({r['state']}) "
                      f"fired={r.get('exclusions')}", flush=True)
    finally:
        await pool.close()

    # build rows with per-criterion assessment
    table = []
    for r in results:
        for crit, trig in r["triggers"].items():
            table.append({
                "plant": r.get("plant_name"),
                "state": r["state"],
                "capacity_mw": r.get("capacity_mw"),
                "criterion": crit,
                "trigger": trig,
                "assessment": _assess(crit, trig),
            })

    OUT_JSON.write_text(json.dumps({"n_excluded": len(results), "rows": table,
                                    "detail": results}, indent=2, default=str))

    # markdown table
    lines = [
        "# Exclusion Diagnosis — Excluded EIA Installations (Step 1)",
        "",
        f"Source: `docs/validation/raw/test1_solar_multistate.json` — "
        f"{len(results)} EIA installations rated Excluded.",
        "",
        "| EIA Plant | State | MW | Criterion | Specific Trigger | Assessment |",
        "|---|---|---|---|---|---|",
    ]
    for t in table:
        trig = t["trigger"]
        if t["criterion"] == "excl_protected":
            ts = "; ".join(f"GAP {x.get('gap_status')} · {x.get('designation') or x.get('unit')}"
                           f" ({x.get('manager')})" for x in trig) or "none"
        elif t["criterion"] == "excl_urban":
            ts = f"NLCD {trig.get('nlcd_code')} ({trig.get('label')})"
        elif t["criterion"] == "excl_flood":
            ts = f"FEMA zone {trig.get('flood_zone')}"
        elif t["criterion"] == "excl_steep":
            s = trig.get("slope_pct")
            ts = f"slope {round(s,1) if s is not None else 'n/a'}%"
        else:
            ts = json.dumps(trig, default=str)
        lines.append(f"| {t['plant']} | {t['state']} | {t['capacity_mw']} | "
                     f"{t['criterion']} | {ts} | {t['assessment']} |")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {OUT_MD.relative_to(REPO_ROOT)} and {OUT_JSON.name}")


if __name__ == "__main__":
    asyncio.run(main())
