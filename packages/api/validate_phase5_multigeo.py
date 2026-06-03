"""Phase 5 multi-geography validation harness.

Implements Test 1 (Solar multi-state EIA validation) and Test 5 (Data
selection engine 50-location verification) from docs/specs/
Heavi_Multi_Geography_Validation_Spec.md.

Calls the scoring + selection functions directly (no HTTP) to avoid needing
a running uvicorn process and to keep the dependency graph honest.

Output: one JSON file per test under docs/validation/raw/ that the summary
generator reads back. Stdout is a streaming progress log.

Usage:
    cd packages/api && source .venv/bin/activate
    python validate_phase5_multigeo.py --test 1     # solar only
    python validate_phase5_multigeo.py --test 5     # selection only
    python validate_phase5_multigeo.py --test all   # default
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.data_selection import select_data
from app.solar_scoring_v2 import score_solar_siting

OUTPUT_DIR = REPO_ROOT / "docs" / "validation" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Approximate state bounding boxes for random sampling. Some random points
# will land in water or urban areas — the scoring methodology should reflect
# that (Excluded or Low). That's a feature, not a bug.
STATE_BBOX = {
    "TX": {"lat": (25.84, 36.50), "lng": (-106.65, -93.51)},
    "AZ": {"lat": (31.33, 37.00), "lng": (-114.82, -109.05)},
    "NC": {"lat": (33.84, 36.59), "lng": (-84.32, -75.46)},
    "NV": {"lat": (35.00, 42.00), "lng": (-120.01, -114.04)},
    "FL": {"lat": (24.50, 31.00), "lng": (-87.63, -80.03)},
}

SAMPLE_PER_STATE = 5
CONCURRENCY = 1           # serial — concurrency=4 hit a contention wall (80/120 timeouts)
PER_LOCATION_TIMEOUT_S = 150.0   # single-call wall is ~70s; 150s leaves margin for slow API days
PROGRESS_FLUSH = True     # line-flush stdout so tail -f sees each location
ABORT_TIMEOUT_RATE = 0.60        # fail-safe: stop early if >60% timeout after 20 locations
ABORT_MIN_SAMPLES = 20


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1 — Solar multi-state EIA validation
# ─────────────────────────────────────────────────────────────────────────────


async def score_one(
    pool: asyncpg.Pool,
    lat: float,
    lng: float,
    sem: asyncio.Semaphore,
    label: str,
    progress: dict[str, Any],
) -> dict[str, Any]:
    """Score one location with a hard per-location timeout. Logs a progress
    line on completion (or timeout) so a stuck run is obvious in tail -f."""
    async with sem:
        t0 = time.time()
        try:
            r = await asyncio.wait_for(
                score_solar_siting(pool, lat, lng),
                timeout=PER_LOCATION_TIMEOUT_S,
            )
            elapsed = time.time() - t0
            result = {
                "lat": lat, "lng": lng,
                "score": r.get("score"),
                "rating": r.get("rating"),
                "exclusions": r.get("exclusions") or [],
                "confidence_tier": r.get("confidence", {}).get("tier"),
                "composite_confidence": r.get("confidence", {}).get("composite"),
                "elapsed_s": round(elapsed, 2),
                "error": None,
            }
            progress["done"] += 1
            print(
                f"  [{progress['done']:>3}/{progress['total']}] {label} "
                f"({lat:.4f},{lng:.4f}) {elapsed:5.1f}s  "
                f"score={result['score']}  rating={result['rating']}  "
                f"tier={result['confidence_tier']}",
                flush=PROGRESS_FLUSH,
            )
            return result
        except asyncio.TimeoutError:
            elapsed = time.time() - t0
            progress["done"] += 1
            progress["timeouts"] += 1
            print(
                f"  [{progress['done']:>3}/{progress['total']}] {label} "
                f"({lat:.4f},{lng:.4f}) {elapsed:5.1f}s  TIMEOUT (>{PER_LOCATION_TIMEOUT_S}s)",
                flush=PROGRESS_FLUSH,
            )
            return {
                "lat": lat, "lng": lng,
                "score": None, "rating": None, "exclusions": [],
                "confidence_tier": None, "composite_confidence": None,
                "elapsed_s": round(elapsed, 2),
                "error": "TIMEOUT",
            }
        except Exception as e:  # noqa: BLE001
            elapsed = time.time() - t0
            progress["done"] += 1
            progress["errors"] += 1
            print(
                f"  [{progress['done']:>3}/{progress['total']}] {label} "
                f"({lat:.4f},{lng:.4f}) {elapsed:5.1f}s  ERROR {type(e).__name__}",
                flush=PROGRESS_FLUSH,
            )
            return {
                "lat": lat, "lng": lng,
                "score": None, "rating": None, "exclusions": [],
                "confidence_tier": None, "composite_confidence": None,
                "elapsed_s": round(elapsed, 2),
                "error": f"{type(e).__name__}: {e}",
            }


async def test_1_solar(pool: asyncpg.Pool) -> dict[str, Any]:
    print(
        "\n[TEST 1] Solar multi-state EIA validation",
        flush=PROGRESS_FLUSH,
    )
    print(
        f"  states={list(STATE_BBOX.keys())}  per-state={SAMPLE_PER_STATE} EIA + {SAMPLE_PER_STATE} random  "
        f"concurrency={CONCURRENCY}  per-loc-timeout={PER_LOCATION_TIMEOUT_S}s",
        flush=PROGRESS_FLUSH,
    )

    rng = random.Random(42)
    results_by_state: dict[str, dict[str, Any]] = {}
    sem = asyncio.Semaphore(CONCURRENCY)
    total_locations = len(STATE_BBOX) * SAMPLE_PER_STATE * 2
    progress = {"done": 0, "total": total_locations, "timeouts": 0, "errors": 0, "aborted": False}

    for state in STATE_BBOX:
        if progress["aborted"]:
            print(f"  [{state}] skipped — earlier fail-safe trip", flush=PROGRESS_FLUSH)
            continue
        state_t0 = time.time()

        # 1. EIA sample — operating PV plants in this state, seed 42
        async with pool.acquire() as conn:
            eia_rows = await conn.fetch(
                """
                SELECT plant_code, plant_name, county, capacity_mw, latitude, longitude
                FROM solar_eia_installations
                WHERE state = $1 AND operating_status = 'OP'
                ORDER BY plant_code
                """,
                state,
            )
        eia_pool = [dict(r) for r in eia_rows]
        rng_state = random.Random(42)  # per-state determinism
        rng_state.shuffle(eia_pool)
        eia_sample = eia_pool[:SAMPLE_PER_STATE]
        print(f"  {state}: {len(eia_pool)} operating EIA installations available → sampling {len(eia_sample)}")

        # 2. Random sample in state bbox (seed 42 + state-mixin for determinism)
        bbox = STATE_BBOX[state]
        rng_rand = random.Random(f"42-{state}")
        random_sample = [
            {
                "lat": round(rng_rand.uniform(*bbox["lat"]), 4),
                "lng": round(rng_rand.uniform(*bbox["lng"]), 4),
            }
            for _ in range(SAMPLE_PER_STATE)
        ]

        # 3. Score both in parallel (sem-limited)
        eia_tasks = [
            score_one(pool, e["latitude"], e["longitude"], sem,
                      f"{state} EIA {i+1}/{len(eia_sample)}", progress)
            for i, e in enumerate(eia_sample)
        ]
        rand_tasks = [
            score_one(pool, r["lat"], r["lng"], sem,
                      f"{state} rand {i+1}/{len(random_sample)}", progress)
            for i, r in enumerate(random_sample)
        ]
        eia_scored, rand_scored = await asyncio.gather(
            asyncio.gather(*eia_tasks),
            asyncio.gather(*rand_tasks),
        )

        # Attach EIA metadata
        for src, dst in zip(eia_sample, eia_scored, strict=True):
            dst["plant_code"] = src["plant_code"]
            dst["plant_name"] = src["plant_name"]
            dst["county"] = src["county"]
            dst["capacity_mw"] = src["capacity_mw"]

        results_by_state[state] = {
            "eia_count_available": len(eia_pool),
            "eia_sample_size": len(eia_sample),
            "random_sample_size": len(random_sample),
            "eia_results": eia_scored,
            "random_results": rand_scored,
            "elapsed_s": round(time.time() - state_t0, 1),
        }
        # Mid-state log
        eia_high = sum(1 for r in eia_scored if r["rating"] == "High")
        rand_high = sum(1 for r in rand_scored if r["rating"] == "High")
        print(
            f"  [{state}] state done in {results_by_state[state]['elapsed_s']}s — "
            f"EIA High {eia_high}/{len(eia_scored)}, "
            f"random High {rand_high}/{len(rand_scored)}, "
            f"timeouts {progress['timeouts']} cumulative",
            flush=PROGRESS_FLUSH,
        )

        # Fail-safe — abort early if timeout rate is catastrophic so we don't burn
        # another hour producing unusable results.
        if (
            progress["done"] >= ABORT_MIN_SAMPLES
            and progress["timeouts"] / progress["done"] > ABORT_TIMEOUT_RATE
        ):
            print(
                f"  ABORT — timeout rate {progress['timeouts']}/{progress['done']} "
                f"({100*progress['timeouts']/progress['done']:.0f}%) exceeds {100*ABORT_TIMEOUT_RATE:.0f}% "
                f"after {progress['done']} locations; stopping early.",
                flush=PROGRESS_FLUSH,
            )
            progress["aborted"] = True

    return results_by_state


def summarize_test_1(state_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build the aggregate stats the REPORTING section calls for."""
    state_summaries: dict[str, dict[str, Any]] = {}
    overall_eia: list[dict[str, Any]] = []
    overall_rand: list[dict[str, Any]] = []

    for state, payload in state_results.items():
        eia = payload["eia_results"]
        rand = payload["random_results"]
        overall_eia.extend(eia)
        overall_rand.extend(rand)

        def pct_high(rows: list[dict[str, Any]]) -> float:
            if not rows:
                return 0.0
            return 100.0 * sum(1 for r in rows if r["rating"] == "High") / len(rows)

        def mean_score(rows: list[dict[str, Any]]) -> float | None:
            xs = [r["score"] for r in rows if r["score"] is not None]
            return round(statistics.mean(xs), 4) if xs else None

        eia_rating_dist = Counter(r["rating"] for r in eia)
        eia_tier_dist = Counter(r["confidence_tier"] for r in eia)
        rand_rating_dist = Counter(r["rating"] for r in rand)

        state_summaries[state] = {
            "eia_sample_size":            len(eia),
            "eia_pct_high":               round(pct_high(eia), 1),
            "eia_mean_score":             mean_score(eia),
            "eia_rating_distribution":    dict(eia_rating_dist),
            "eia_confidence_tier_distribution": dict(eia_tier_dist),
            "eia_errors":                 sum(1 for r in eia if r["error"]),
            "random_sample_size":         len(rand),
            "random_pct_high":            round(pct_high(rand), 1),
            "random_mean_score":          mean_score(rand),
            "random_rating_distribution": dict(rand_rating_dist),
            "score_separation":           (
                round((mean_score(eia) or 0.0) - (mean_score(rand) or 0.0), 4)
                if mean_score(eia) is not None and mean_score(rand) is not None
                else None
            ),
            "low_scoring_eia_installations": [
                {
                    "plant_code": r.get("plant_code"),
                    "plant_name": r.get("plant_name"),
                    "score":      r["score"],
                    "rating":     r["rating"],
                    "exclusions": r["exclusions"],
                }
                for r in eia
                if r["rating"] in ("Low", "Excluded")
            ],
        }

    # National aggregate
    def pct_high_all(rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        return 100.0 * sum(1 for r in rows if r["rating"] == "High") / len(rows)

    eia_scores = [r["score"] for r in overall_eia if r["score"] is not None]
    rand_scores = [r["score"] for r in overall_rand if r["score"] is not None]

    aggregate = {
        "total_eia_scored":     len(overall_eia),
        "total_random_scored":  len(overall_rand),
        "national_pct_high":    round(pct_high_all(overall_eia), 1),
        "national_mean_eia":    round(statistics.mean(eia_scores), 4) if eia_scores else None,
        "national_mean_random": round(statistics.mean(rand_scores), 4) if rand_scores else None,
        "states_passing_70pct": sum(1 for s in state_summaries.values() if s["eia_pct_high"] >= 70.0),
        "states_passing_60pct": sum(1 for s in state_summaries.values() if s["eia_pct_high"] >= 60.0),
    }

    # Pass criteria from spec §TEST 1
    pass_criteria = {
        "AC1_60pct_national": aggregate["national_pct_high"] >= 60.0,
        "AC2_mean_separation_every_state": all(
            (s["score_separation"] or 0.0) > 0 for s in state_summaries.values()
        ),
        "AC3_70pct_in_3_of_5": aggregate["states_passing_70pct"] >= 3,
    }

    return {
        "per_state":      state_summaries,
        "aggregate":      aggregate,
        "pass_criteria":  pass_criteria,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST 5 — Data selection engine 50-location verification
# ─────────────────────────────────────────────────────────────────────────────


async def test_5_selection(pool: asyncpg.Pool) -> dict[str, Any]:
    print("\n[TEST 5] Data selection engine — 50 random CONUS locations")
    rng = random.Random(42)
    locations = []
    for i in range(50):
        lat = round(rng.uniform(26.0, 47.5), 4)
        lng = round(rng.uniform(-123.0, -70.0), 4)
        locations.append({"id": f"VAL-{i:03d}", "lat": lat, "lng": lng})

    sem = asyncio.Semaphore(CONCURRENCY)

    async def run_one(loc: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            t0 = time.time()
            try:
                result = await select_data(pool, "solar_siting", loc["lat"], loc["lng"])
                payload = result.to_dict()
                # Per-criterion source + confidence
                selections_summary = []
                for c in payload["criteria"]:
                    sel_src = (c.get("selected_sources") or [{}])[0].get("source_id")
                    selections_summary.append({
                        "criterion_id": c["criterion_id"],
                        "criterion_type": c["criterion_type"],
                        "selected_source": sel_src,
                        "confidence": c["confidence"],
                        "confidence_tier": c["confidence_tier"],
                        "n_sources_tried": len(c.get("sources_tried") or []),
                    })
                return {
                    **loc,
                    "composite_confidence": payload["composite_confidence"],
                    "confidence_tier":      payload["confidence_tier"],
                    "completeness":         payload["completeness"],
                    "gaps":                 payload["gaps"],
                    "criteria":             selections_summary,
                    "elapsed_s":            round(time.time() - t0, 2),
                    "error":                None,
                }
            except Exception as e:  # noqa: BLE001
                return {
                    **loc,
                    "composite_confidence": None,
                    "confidence_tier":      None,
                    "completeness":         None,
                    "gaps":                 None,
                    "criteria":             [],
                    "elapsed_s":            round(time.time() - t0, 2),
                    "error":                f"{type(e).__name__}: {e}",
                }

    results = await asyncio.gather(*[run_one(loc) for loc in locations])

    # Reverse geocode state using PostGIS census tracts if loaded; cheap and offline
    async with pool.acquire() as conn:
        has_tracts = await conn.fetchval(
            "SELECT to_regclass('public.census_tracts') IS NOT NULL"
        )
        for r in results:
            if has_tracts and r["error"] is None:
                row = await conn.fetchrow(
                    """
                    SELECT statefp FROM census_tracts
                    WHERE ST_Intersects(geometry, ST_SetSRID(ST_MakePoint($1,$2),4326))
                    LIMIT 1
                    """,
                    r["lng"], r["lat"],
                )
                r["statefp"] = row["statefp"] if row else None
            else:
                r["statefp"] = None
    return {"locations": results}


def summarize_test_5(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["locations"]
    n_total = len(rows)
    n_valid = sum(1 for r in rows if r["error"] is None and r["composite_confidence"] is not None)
    n_errors = sum(1 for r in rows if r["error"] is not None)

    composites = [r["composite_confidence"] for r in rows if r["composite_confidence"] is not None]
    distinct_composites = len({round(c, 3) for c in composites})

    tier_dist = Counter(r["confidence_tier"] for r in rows if r["confidence_tier"])

    # Known PostGIS-loaded source IDs (data_repository_seed: substations, NWI,
    # OSM POIs, HIFLD transmission lines). Any selected source ending in
    # "_overpass" is an Overpass fallback. These two sets are mutually exclusive
    # per the source naming convention.
    POSTGIS_SOURCES = {
        "hifld_transmission", "osm_substations", "osm_pois", "nwi_wetlands",
        "calfire_fhsz",
    }

    cache_hit_locs = 0
    overpass_locs = 0
    api_failure_locs = 0
    silent_failures: list[dict[str, Any]] = []

    for r in rows:
        if r["error"]:
            api_failure_locs += 1
            continue
        sources_used = [(c["selected_source"] or "").lower() for c in r["criteria"]]
        if any(s in POSTGIS_SOURCES for s in sources_used):
            cache_hit_locs += 1
        if any(s.endswith("_overpass") for s in sources_used):
            overpass_locs += 1
        # Silent failure check: if confidence is non-zero but some criterion has 0
        # confidence and the gaps array doesn't surface it, that would be a silent
        # failure. We just record the gap count — every 0-confidence criterion
        # should appear in gaps[].
        zero_conf = [c["criterion_id"] for c in r["criteria"] if c["confidence"] == 0.0]
        if zero_conf and len(r["gaps"] or []) < len(zero_conf):
            silent_failures.append({"id": r["id"], "missing_in_gaps": zero_conf})

    mean_composite = round(statistics.mean(composites), 4) if composites else None

    pass_criteria = {
        # Spec literal: "≥45 of 50 locations return a valid selection result"
        "AC1_45_of_50_valid":           n_valid >= 45,
        # Spec literal: "Confidence varies across locations (not all the same value)"
        "AC2_confidence_varies":        distinct_composites >= 2,
        # Spec literal: "PostGIS cache hits occur for locations in loaded states"
        "AC3_postgis_cache_hits":       cache_hit_locs > 0,
        # Spec literal: "Overpass fallback fires for locations outside loaded states"
        "AC4_overpass_fallback_fires":  overpass_locs > 0,
        # Spec literal: "No silent failures — every unavailable source is explicitly logged"
        "AC5_no_silent_failures":       len(silent_failures) == 0,
        # Spec literal: "API timeout rate < 10% across all 50 locations"
        "AC6_api_timeout_under_10pct":  (api_failure_locs / max(n_total, 1)) < 0.10,
    }

    return {
        "n_total":               n_total,
        "n_valid":               n_valid,
        "n_errors":              n_errors,
        "distinct_composites":   distinct_composites,
        "mean_composite":        mean_composite,
        "tier_distribution":     dict(tier_dist),
        "postgis_cache_hit_locations": cache_hit_locs,
        "postgis_cache_hit_rate_pct":  round(100 * cache_hit_locs / max(n_total, 1), 1),
        "overpass_fallback_locations": overpass_locs,
        "overpass_fallback_rate_pct":  round(100 * overpass_locs / max(n_total, 1), 1),
        "api_failure_rate_pct":  round(100 * api_failure_locs / max(n_total, 1), 1),
        "silent_failures":       silent_failures,
        "pass_criteria":         pass_criteria,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────


async def main(test: str) -> None:
    dsn = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn, min_size=4, max_size=12)
    try:
        if test in ("1", "all"):
            t0 = time.time()
            state_results = await test_1_solar(pool)
            test_1_payload = {
                "spec_section":  "TEST 1",
                "seed":          42,
                "concurrency":   CONCURRENCY,
                "states_tested": list(STATE_BBOX.keys()),
                "elapsed_s":     round(time.time() - t0, 1),
                "raw_results":   state_results,
                "summary":       summarize_test_1(state_results),
            }
            (OUTPUT_DIR / "test1_solar_multistate.json").write_text(
                json.dumps(test_1_payload, indent=2, default=str)
            )
            print(f"\n[TEST 1] wrote docs/validation/raw/test1_solar_multistate.json "
                  f"({test_1_payload['elapsed_s']}s)")
        if test in ("5", "all"):
            t0 = time.time()
            payload = await test_5_selection(pool)
            test_5_payload = {
                "spec_section": "TEST 5",
                "seed":         42,
                "n_locations":  50,
                "concurrency":  CONCURRENCY,
                "elapsed_s":    round(time.time() - t0, 1),
                "raw_results":  payload,
                "summary":      summarize_test_5(payload),
            }
            (OUTPUT_DIR / "test5_selection_engine.json").write_text(
                json.dumps(test_5_payload, indent=2, default=str)
            )
            print(f"\n[TEST 5] wrote docs/validation/raw/test5_selection_engine.json "
                  f"({test_5_payload['elapsed_s']}s)")
    finally:
        await pool.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--test", choices=["1", "5", "all"], default="all")
    args = p.parse_args()
    asyncio.run(main(args.test))
