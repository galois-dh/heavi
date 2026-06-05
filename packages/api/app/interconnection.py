"""Interconnection proximity context (Heavi Month-1 Sprint, Feature 4).

For a candidate solar site, summarize the interconnection environment near the
nearest substation: existing connected capacity (EIA Form 860), interconnection-
queue activity (interconnection_queue), a queue-status breakdown, and the ISO.

This is informational context from public data — NOT a power-flow / interconnection
study (PVcase's domain). The queue dataset is representative (see
load_interconnection_queue.py); actual capacity requires an ISO application.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

import asyncpg

_NOTE = (
    "This is informational context from public data, not an interconnection "
    "study. Actual capacity availability requires filing an interconnection "
    "application with the relevant ISO/RTO. The queue dataset is representative "
    "for demonstration; production uses live ISO queue files."
)


def _voltage_kv(raw: str | None) -> float | None:
    """OSM voltage strings are inconsistent ('115000', '230 kV', '500000;230000')."""
    if not raw:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", raw)]
    if not nums:
        return None
    v = max(nums)
    return round(v / 1000.0) if v > 1000 else round(v)


async def get_interconnection_context(
    pool: asyncpg.Pool, latitude: float, longitude: float, radius_km: float = 50.0,
) -> dict[str, Any]:
    radius_m = radius_km * 1000.0
    pt = "ST_SetSRID(ST_MakePoint($1, $2), 4326)"
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            f"""SELECT name, voltage,
                   ST_Distance(geometry::geography, {pt}::geography) AS d
                FROM substations_osm_us
                WHERE ST_DWithin(geometry::geography, {pt}::geography, $3)
                ORDER BY geometry <-> {pt} LIMIT 1""",
            longitude, latitude, radius_m,
        )
        eia = await conn.fetchrow(
            f"""SELECT COUNT(*)::int AS n, COALESCE(SUM(capacity_mw), 0) AS mw
                FROM solar_eia_installations
                WHERE operating_status = 'OP'
                  AND ST_DWithin(geometry::geography, {pt}::geography, $3)""",
            longitude, latitude, radius_m,
        )
        try:
            queue = await conn.fetch(
                f"""SELECT iso, fuel_type, status, capacity_mw, project_name, queue_date
                    FROM interconnection_queue
                    WHERE ST_DWithin(geometry::geography, {pt}::geography, $3)
                    ORDER BY queue_date DESC""",
                longitude, latitude, radius_m,
            )
        except Exception:  # noqa: BLE001 — table absent → empty queue
            queue = []

    active = [q for q in queue if q["status"] == "Active"]
    active_solar = [q for q in active if (q["fuel_type"] or "").lower() == "solar"]
    iso = Counter(q["iso"] for q in queue).most_common(1)[0][0] if queue else None
    status_counts = Counter(q["status"] for q in queue)

    nearest = None
    if sub is not None:
        nearest = {
            "name": sub["name"] or "(unnamed substation)",
            "voltage_kv": _voltage_kv(sub["voltage"]),
            "distance_mi": round(float(sub["d"]) / 1609.34, 1),
        }

    return {
        "nearest_substation": nearest,
        "existing_capacity_mw": round(float(eia["mw"]), 1),
        "existing_plant_count": eia["n"],
        "queue_projects_nearby": len(active_solar),
        "queue_capacity_mw": round(sum(float(q["capacity_mw"] or 0) for q in active_solar), 1),
        "queue_total_active": len(active),
        "queue_total_active_mw": round(sum(float(q["capacity_mw"] or 0) for q in active), 1),
        "queue_summary": {
            "active": status_counts.get("Active", 0),
            "withdrawn": status_counts.get("Withdrawn", 0),
            "completed": status_counts.get("Completed", 0),
            "suspended": status_counts.get("Suspended", 0),
        },
        "iso": iso,
        "radius_km": radius_km,
        "data_source": "representative",
        "note": _NOTE,
    }
