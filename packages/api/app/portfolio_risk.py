"""Portfolio-level wildfire risk: CSV ingest → per-property scoring → PDF.

Endpoints in main.py compose this module:
  POST /portfolio-risk            → run_portfolio()  → returns {job_id, …}
  GET  /portfolio-risk/{id}/report → render_pdf()    → application/pdf

Job storage is a process-local TTL dict (see JOBS). Acceptable v1 trade-off:
results survive the FastAPI worker's lifetime, not a restart, and don't shard
across Railway replicas. Documented as a known limitation.

Nominatim is respected at ≤1 req/s with the User-Agent the rest of the
codebase uses. CSVs are capped at 500 rows; over that we 413.
"""

from __future__ import annotations

import asyncio
import csv
import io
import math
import os
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx

from .wildfire_loss import (
    METHODOLOGY_NOTE,
    MODEL,
    NOMINATIM_UA,
    score_property,
)

MAX_ROWS = 500
# Nominatim ToS: ≤1 req/s with a stable User-Agent. Only enforced when we
# fall back to Nominatim (MAPBOX_TOKEN unset). Mapbox geocoding has no
# per-second cap at the public-token tier (~600 req/min ceiling), so we
# loop unthrottled when it's the active provider.
NOMINATIM_QPS = 1.0
JOB_TTL = timedelta(hours=1)

# 5 mi in metres for the FRAP-proximity query. The number is exact to PostGIS
# precision; the user-facing prose still says "within 5 miles".
FIRE_PROXIMITY_M = 8047


# ─── Job cache (process-local, TTL-pruned) ────────────────────────────────


@dataclass
class PortfolioJob:
    job_id: str
    created_at: datetime
    per_property: list[dict[str, Any]]
    portfolio_summary: dict[str, Any]
    top_10_highest_risk: list[dict[str, Any]]
    # Cache of Mapbox static-API tile bytes keyed by "lat,lng" rounded to
    # six decimals. Populated lazily on first PDF render so repeated
    # report downloads don't hammer Mapbox.
    satellite_image_cache: dict[str, bytes | None] = field(default_factory=dict)


JOBS: dict[str, PortfolioJob] = {}


def _prune_jobs() -> None:
    now = datetime.now(timezone.utc)
    stale = [k for k, j in JOBS.items() if now - j.created_at > JOB_TTL]
    for k in stale:
        JOBS.pop(k, None)


def get_job(job_id: str) -> PortfolioJob | None:
    _prune_jobs()
    return JOBS.get(job_id)


# ─── CSV parsing ──────────────────────────────────────────────────────────


@dataclass
class InputRow:
    row_index: int  # 1-based for human-friendly errors
    property_id: str | None
    address: str | None
    latitude: float | None
    longitude: float | None


def parse_csv(raw: bytes) -> list[InputRow]:
    """Parse the upload. Required: address OR (latitude AND longitude).
    Optional: property_id. Header names are case-insensitive and tolerate a
    few synonyms (lat/lng, lon)."""
    try:
        text = raw.decode("utf-8-sig")  # strip Excel BOM if present
    except UnicodeDecodeError as e:
        raise ValueError(f"CSV is not UTF-8: {e}") from None

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row.")

    # Normalize fieldname lookup.
    aliases = {
        "address": {"address", "addr", "street"},
        "latitude": {"latitude", "lat", "y"},
        "longitude": {"longitude", "lng", "lon", "long", "x"},
        "property_id": {"property_id", "id", "propertyid", "prop_id"},
    }
    header_map: dict[str, str | None] = {k: None for k in aliases}
    lower_headers = {h.lower().strip(): h for h in reader.fieldnames}
    for canonical, alias_set in aliases.items():
        for a in alias_set:
            if a in lower_headers:
                header_map[canonical] = lower_headers[a]
                break

    if not header_map["address"] and not (header_map["latitude"] and header_map["longitude"]):
        raise ValueError(
            "CSV must contain an 'address' column OR both 'latitude' and 'longitude'."
        )

    rows: list[InputRow] = []
    for i, raw_row in enumerate(reader, start=1):
        addr_col = header_map["address"]
        lat_col = header_map["latitude"]
        lng_col = header_map["longitude"]
        pid_col = header_map["property_id"]

        address = (raw_row.get(addr_col) or "").strip() if addr_col else ""
        lat_str = (raw_row.get(lat_col) or "").strip() if lat_col else ""
        lng_str = (raw_row.get(lng_col) or "").strip() if lng_col else ""
        property_id = (raw_row.get(pid_col) or "").strip() if pid_col else ""

        latitude = float(lat_str) if lat_str else None
        longitude = float(lng_str) if lng_str else None

        if not address and (latitude is None or longitude is None):
            # Skip blank lines; raise only if user supplied an obviously
            # incomplete row (a property_id with no location).
            if property_id:
                raise ValueError(
                    f"Row {i}: property_id '{property_id}' has no address or lat/lng."
                )
            continue

        rows.append(
            InputRow(
                row_index=i,
                property_id=property_id or None,
                address=address or None,
                latitude=latitude,
                longitude=longitude,
            )
        )

    if len(rows) > MAX_ROWS:
        raise ValueError(
            f"CSV has {len(rows)} rows; per-request cap is {MAX_ROWS}. "
            "Split into smaller batches."
        )
    if not rows:
        raise ValueError("CSV contained no usable rows.")
    return rows


# ─── Geocoding loop ───────────────────────────────────────────────────────


def _active_geocoder() -> str:
    """Single source of truth for which geocoder this run will use.
    Decided once per run_portfolio invocation; if the operator changes
    MAPBOX_TOKEN mid-flight we still use whatever was set at loop start."""
    return "mapbox" if os.getenv("MAPBOX_TOKEN") else "nominatim"


async def _geocode_mapbox(
    client: httpx.AsyncClient, address: str, token: str
) -> tuple[float, float, str] | None:
    """Mapbox Geocoding API v5. Better US address coverage than Nominatim
    and no per-second rate limit at the public-token tier."""
    url = (
        "https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{urllib.parse.quote(address)}.json"
    )
    try:
        r = await client.get(
            url,
            params={"access_token": token, "limit": 1, "country": "us"},
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    features = data.get("features") or []
    if not features:
        return None
    f = features[0]
    coords = f.get("center") or (f.get("geometry") or {}).get("coordinates")
    if not coords or len(coords) < 2:
        return None
    return float(coords[1]), float(coords[0]), f.get("place_name") or address


async def _geocode_nominatim(
    client: httpx.AsyncClient, address: str
) -> tuple[float, float, str] | None:
    """OSM Nominatim — used as the fallback when MAPBOX_TOKEN is unset."""
    try:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
            headers={"User-Agent": NOMINATIM_UA},
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]


async def _geocode_one(
    client: httpx.AsyncClient, address: str
) -> tuple[float, float, str] | None:
    """Dispatcher — picks Mapbox if MAPBOX_TOKEN is set, otherwise Nominatim.
    Same return shape regardless of provider so callers don't care."""
    token = os.getenv("MAPBOX_TOKEN")
    if token:
        return await _geocode_mapbox(client, address, token)
    return await _geocode_nominatim(client, address)


async def _resolve_row(
    client: httpx.AsyncClient, row: InputRow
) -> tuple[float | None, float | None, str | None, str | None]:
    """Return (lat, lng, resolved_address, error). Honors lat/lng-first rows
    (no geocode needed) and falls through to Nominatim only when needed."""
    if row.latitude is not None and row.longitude is not None:
        return row.latitude, row.longitude, row.address, None
    if not row.address:
        return None, None, None, "no address or coordinates"
    g = await _geocode_one(client, row.address)
    if g is None:
        return None, None, None, f"geocoding failed: {row.address!r}"
    lat, lng, display = g
    return lat, lng, display, None


# ─── Fire-history query (FRAP perimeters within 5 mi) ─────────────────────


# Single point ↔ all-near-perimeters query. Returns up to 10 nearest fires
# with a flag for whether the property point falls inside that perimeter.
# distance_miles is positive even for contained points (PostGIS returns 0,
# which is correct geographically).
_FIRE_HISTORY_SQL = """
SELECT
    fire_name,
    year_,
    gis_acres,
    ST_Distance(
        geometry::geography,
        ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
    ) / 1609.34 AS distance_miles,
    ST_Contains(
        geometry,
        ST_SetSRID(ST_MakePoint($1, $2), 4326)
    ) AS contains_point
FROM wildfire_frap_perimeters
WHERE ST_DWithin(
    geometry::geography,
    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography,
    $3
)
ORDER BY distance_miles
LIMIT 10
"""

_COUNTY_BENCHMARK_SQL = """
SELECT AVG(expected_annual_loss)::float AS mean_eal,
       COUNT(*)::int                     AS n_structures
FROM wildfire_nsi_structures
WHERE expected_annual_loss IS NOT NULL
"""


async def _fire_history(
    conn: asyncpg.Connection, lat: float, lng: float
) -> list[dict[str, Any]]:
    """Pre-format the FRAP rows so the PDF layer can consume them directly.
    Distance is rounded to 2 decimal places; fire_name normalised to Title
    Case for display."""
    rows = await conn.fetch(_FIRE_HISTORY_SQL, lng, lat, FIRE_PROXIMITY_M)
    out = []
    for r in rows:
        fname = (r["fire_name"] or "").strip().title() if r["fire_name"] else "Unknown"
        out.append(
            {
                "fire_name": fname,
                "year": int(r["year_"]) if r["year_"] is not None else None,
                "gis_acres": float(r["gis_acres"] or 0.0),
                "distance_miles": round(float(r["distance_miles"] or 0.0), 2),
                "contains_point": bool(r["contains_point"]),
            }
        )
    return out


async def _county_benchmark(pool: asyncpg.Pool) -> dict[str, Any]:
    """One-shot county-wide mean EAL benchmark from the persisted
    wildfire_nsi_structures.expected_annual_loss column. Cached on the
    JOBS module via a sentinel so repeated portfolio runs in the same
    process don't re-query."""
    global _COUNTY_BENCHMARK_CACHE
    if _COUNTY_BENCHMARK_CACHE is not None:
        return _COUNTY_BENCHMARK_CACHE
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_COUNTY_BENCHMARK_SQL)
    _COUNTY_BENCHMARK_CACHE = {
        "mean_eal": float(row["mean_eal"] or 0.0),
        "n_structures": int(row["n_structures"] or 0),
    }
    return _COUNTY_BENCHMARK_CACHE


_COUNTY_BENCHMARK_CACHE: dict[str, Any] | None = None


# ─── Portfolio runner ─────────────────────────────────────────────────────


async def run_portfolio(pool: asyncpg.Pool, rows: list[InputRow]) -> PortfolioJob:
    """Geocode + score every row, then aggregate.

    Geocoding provider is decided once at the top of the loop:
      * MAPBOX_TOKEN set   → Mapbox Geocoding v5, no per-second throttle
      * MAPBOX_TOKEN unset → Nominatim, 1.05 s sleep between requests
    Rows that come in with explicit lat/lng skip geocoding entirely.

    DB lookups (score_property + fire_history) are sub-100 ms each via the
    GIST index, so the loop's wall time is dominated by geocoding latency
    when addresses are present."""

    per_property: list[dict[str, Any]] = []
    benchmark = await _county_benchmark(pool)
    geocoder = _active_geocoder()
    throttle = geocoder == "nominatim"

    async with httpx.AsyncClient(timeout=15.0) as client:
        last_geocode_t = 0.0
        for row in rows:
            need_geocode = row.address is not None and (
                row.latitude is None or row.longitude is None
            )
            if need_geocode and throttle:
                elapsed = time.perf_counter() - last_geocode_t
                if elapsed < 1.05:
                    await asyncio.sleep(1.05 - elapsed)
                last_geocode_t = time.perf_counter()

            lat, lng, resolved_address, error = await _resolve_row(client, row)

            record: dict[str, Any] = {
                "property_id": row.property_id,
                "row_index": row.row_index,
                "input_address": row.address,
                "resolved_address": resolved_address,
                "latitude": lat,
                "longitude": lng,
            }

            if error:
                record["status"] = "error"
                record["error"] = error
                record["annual_risk_usd"] = None
                record["fire_history"] = []
                record["in_historical_perimeter"] = False
                per_property.append(record)
                continue

            assert lat is not None and lng is not None
            try:
                core = await score_property(pool, lat, lng, search_radius_m=500)
            except Exception as e:  # noqa: BLE001
                record["status"] = "error"
                record["error"] = f"scoring failed: {e}"
                record["annual_risk_usd"] = None
                record["fire_history"] = []
                record["in_historical_perimeter"] = False
                per_property.append(record)
                continue

            record.update(core)

            # Fire history: one round-trip per property. Cheap (GIST + ANALYZE
            # already in place) and the result feeds both the per-property
            # PDF cards and the portfolio-level validation count.
            try:
                async with pool.acquire() as conn:
                    fires = await _fire_history(conn, lat, lng)
            except Exception:
                fires = []
            record["fire_history"] = fires
            record["in_historical_perimeter"] = any(f["contains_point"] for f in fires)

            if core.get("match") is None:
                record["status"] = "no_coverage"
                record["annual_risk_usd"] = None
            else:
                risk = (
                    core["risk_estimate"].get("annual_risk_estimate_usd_persisted")
                    or core["risk_estimate"]["annual_risk_estimate_usd"]
                )
                record["status"] = "scored"
                record["annual_risk_usd"] = risk
            per_property.append(record)

    summary = _summarize(per_property, benchmark=benchmark)
    top10 = sorted(
        (r for r in per_property if r.get("annual_risk_usd") is not None),
        key=lambda r: r["annual_risk_usd"] or 0,
        reverse=True,
    )[:10]

    job = PortfolioJob(
        job_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        per_property=per_property,
        portfolio_summary=summary,
        top_10_highest_risk=top10,
    )
    JOBS[job.job_id] = job
    _prune_jobs()
    return job


# ─── Aggregation ──────────────────────────────────────────────────────────


_BUCKETS: list[tuple[str, float, float]] = [
    ("$0", -math.inf, 0.0),
    ("$0-10", 0.0, 10.0),
    ("$10-100", 10.0, 100.0),
    ("$100-500", 100.0, 500.0),
    ("$500-1000", 500.0, 1000.0),
    ("$1000+", 1000.0, math.inf),
]


def _bucket_for(eal: float) -> str:
    for label, lo, hi in _BUCKETS:
        if label == "$0":
            if eal == 0:
                return label
            continue
        if lo < eal <= hi:
            return label
    return _BUCKETS[-1][0]


def _tier_for(eal: float | None) -> str:
    if eal is None:
        return "unscored"
    if eal > 500:
        return "high"
    if eal >= 50:
        return "moderate"
    return "low"


def _summarize(
    per_property: list[dict[str, Any]],
    *,
    benchmark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    eals = [
        r["annual_risk_usd"] for r in per_property if r.get("annual_risk_usd") is not None
    ]
    n = len(per_property)
    n_scored = len(eals)
    base: dict[str, Any] = {
        "property_count": n,
        "scored_count": n_scored,
        "county_benchmark_mean_eal": (benchmark or {}).get("mean_eal", 0.0),
        "county_benchmark_n_structures": (benchmark or {}).get("n_structures", 0),
    }

    # Validation: count properties that fall inside ANY historical FRAP
    # perimeter, and the tier mix among them. The argument the PDF will make
    # is "the model assigned X% of these to High/Moderate" — concrete evidence
    # that the predictions correspond to where fires actually burned.
    in_perim = [
        r for r in per_property if r.get("in_historical_perimeter")
        and r.get("annual_risk_usd") is not None
    ]
    n_in_perim = len(in_perim)
    n_in_perim_high_or_mod = sum(
        1 for r in in_perim if _tier_for(r.get("annual_risk_usd")) in {"high", "moderate"}
    )
    base["in_perimeter_count"] = n_in_perim
    base["in_perimeter_high_or_moderate_count"] = n_in_perim_high_or_mod
    base["in_perimeter_high_or_moderate_share"] = (
        round(n_in_perim_high_or_mod / n_in_perim, 4) if n_in_perim else None
    )

    if not eals:
        base.update(
            {
                "total_annual_risk": 0.0,
                "mean_risk": 0.0,
                "median_risk": 0.0,
                "min_risk": 0.0,
                "max_risk": 0.0,
                "p95_risk": 0.0,
                "risk_distribution": [{"bucket": b[0], "n": 0} for b in _BUCKETS],
                "high_risk_count": 0,
                "moderate_risk_count": 0,
                "low_risk_count": 0,
                "error_count": sum(1 for r in per_property if r.get("status") == "error"),
                "no_coverage_count": sum(
                    1 for r in per_property if r.get("status") == "no_coverage"
                ),
            }
        )
        return base

    eals_sorted = sorted(eals)
    mid = n_scored // 2
    median = (
        eals_sorted[mid]
        if n_scored % 2
        else (eals_sorted[mid - 1] + eals_sorted[mid]) / 2.0
    )

    bucket_counts = {b[0]: 0 for b in _BUCKETS}
    for v in eals:
        bucket_counts[_bucket_for(v)] += 1

    base.update(
        {
            "total_annual_risk": round(sum(eals), 2),
            "mean_risk": round(sum(eals) / n_scored, 2),
            "median_risk": round(median, 2),
            "min_risk": round(min(eals), 2),
            "max_risk": round(max(eals), 2),
            "p95_risk": round(eals_sorted[int(n_scored * 0.95)], 2)
            if n_scored > 1
            else round(eals_sorted[0], 2),
            "risk_distribution": [
                {"bucket": b[0], "n": bucket_counts[b[0]]} for b in _BUCKETS
            ],
            "high_risk_count": sum(1 for v in eals if v > 500),
            "moderate_risk_count": sum(1 for v in eals if 50 <= v <= 500),
            "low_risk_count": sum(1 for v in eals if v < 50),
            "error_count": sum(1 for r in per_property if r.get("status") == "error"),
            "no_coverage_count": sum(
                1 for r in per_property if r.get("status") == "no_coverage"
            ),
        }
    )
    return base


def job_to_response(job: PortfolioJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "generated_at": job.created_at.isoformat(),
        "methodology_note": METHODOLOGY_NOTE,
        "model": {
            "run_id": MODEL["run_id"],
            "auc_roc": MODEL["auc_roc"],
            "methodology_hash": MODEL["methodology_hash"],
        },
        "portfolio_summary": job.portfolio_summary,
        "top_10_highest_risk": [_summarize_row_for_response(r) for r in job.top_10_highest_risk],
        "per_property": [_summarize_row_for_response(r) for r in job.per_property],
    }


def _summarize_row_for_response(r: dict[str, Any]) -> dict[str, Any]:
    """Trim per-property records for JSON transport — drop the embedded
    methodology_note and natural_language_summary (the note is attached once
    at top level; the per-row NL summary would bloat the payload), keep
    everything useful for the table view."""
    drop = {"methodology_note", "natural_language_summary"}
    out = {k: v for k, v in r.items() if k not in drop}
    return out
