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
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import httpx

from .wildfire_loss import (
    METHODOLOGY_SUMMARY,
    MODEL,
    NOMINATIM_UA,
    score_property,
)

MAX_ROWS = 500
NOMINATIM_QPS = 1.0  # absolute upper bound; we sleep 1.05 s between calls
JOB_TTL = timedelta(hours=1)


# ─── Job cache (process-local, TTL-pruned) ────────────────────────────────


@dataclass
class PortfolioJob:
    job_id: str
    created_at: datetime
    per_property: list[dict[str, Any]]
    portfolio_summary: dict[str, Any]
    top_10_highest_risk: list[dict[str, Any]]


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


async def _geocode_one(
    client: httpx.AsyncClient, address: str
) -> tuple[float, float, str] | None:
    try:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]


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


# ─── Portfolio runner ─────────────────────────────────────────────────────


async def run_portfolio(pool: asyncpg.Pool, rows: list[InputRow]) -> PortfolioJob:
    """Geocode + score every row, then aggregate. Sleeps 1.05 s between
    Nominatim calls; rows with lat/lng don't burn quota. DB lookups are
    sub-100ms each (GIST index)."""

    per_property: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=15.0, headers={"User-Agent": NOMINATIM_UA}
    ) as client:
        last_geocode_t = 0.0
        for row in rows:
            need_geocode = row.address is not None and (
                row.latitude is None or row.longitude is None
            )
            if need_geocode:
                # Throttle to ≤1 req/s globally across the loop.
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
                per_property.append(record)
                continue

            assert lat is not None and lng is not None
            try:
                core = await score_property(pool, lat, lng, search_radius_m=500)
            except Exception as e:  # noqa: BLE001
                record["status"] = "error"
                record["error"] = f"scoring failed: {e}"
                record["annual_risk_usd"] = None
                per_property.append(record)
                continue

            record.update(core)
            if core.get("match") is None:
                record["status"] = "no_coverage"
                record["annual_risk_usd"] = None
            else:
                eal = (
                    core["loss_estimate"].get("expected_annual_loss_usd_persisted")
                    or core["loss_estimate"]["expected_annual_loss_usd_recomputed"]
                )
                record["status"] = "scored"
                record["annual_risk_usd"] = eal
            per_property.append(record)

    summary = _summarize(per_property)
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


def _summarize(per_property: list[dict[str, Any]]) -> dict[str, Any]:
    eals = [
        r["annual_risk_usd"] for r in per_property if r.get("annual_risk_usd") is not None
    ]
    n = len(per_property)
    n_scored = len(eals)
    if not eals:
        return {
            "property_count": n,
            "scored_count": 0,
            "total_annual_risk": 0.0,
            "mean_risk": 0.0,
            "median_risk": 0.0,
            "risk_distribution": [{"bucket": b[0], "n": 0} for b in _BUCKETS],
            "high_risk_count": 0,
            "moderate_risk_count": 0,
            "low_risk_count": 0,
            "error_count": sum(1 for r in per_property if r.get("status") == "error"),
            "no_coverage_count": sum(
                1 for r in per_property if r.get("status") == "no_coverage"
            ),
        }

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

    return {
        "property_count": n,
        "scored_count": n_scored,
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


def job_to_response(job: PortfolioJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "generated_at": job.created_at.isoformat(),
        "methodology_summary": METHODOLOGY_SUMMARY,
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
    methodology_summary (already attached at top level), keep everything
    useful for the table view."""
    out = {k: v for k, v in r.items() if k != "methodology_summary"}
    return out
