"""Persist a finalized decision trail to the decision_trails Supabase table.

Schema (created by migrations/2026-06-04_decision_trails.sql)::

    CREATE TABLE decision_trails (
        execution_id     uuid        PRIMARY KEY,
        module           text        NOT NULL,
        module_version   text,
        started_at       timestamptz NOT NULL,
        duration_ms      float8,
        inputs           jsonb       NOT NULL,
        trail            jsonb       NOT NULL,
        scored_output    jsonb
    );
    CREATE INDEX decision_trails_module_started_at
      ON decision_trails (module, started_at DESC);
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import asyncpg

log = logging.getLogger(__name__)


async def persist_trail(
    pool: asyncpg.Pool,
    *,
    finalized: dict[str, Any],
    inputs: dict[str, Any],
) -> None:
    """Best-effort insert. Logs and swallows failure rather than 5xx-ing a
    successful scoring call when the audit table is unavailable."""
    # asyncpg's pool is configured (in main.py _init_connection) with a json
    # type-codec that auto-encodes Python dicts via json.dumps; we pass the
    # dicts directly. Pre-encoding here would produce double-escaped strings.
    trail_payload = {
        "events":       finalized["events"],
        "queries":      finalized["queries"],
        "http_calls":   finalized["http_calls"],
        "data_layers":  finalized["data_layers"],
        "data_sources": finalized["data_sources"],
    }
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO decision_trails
                  (execution_id, module, module_version, started_at,
                   duration_ms, inputs, trail, scored_output)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (execution_id) DO NOTHING
                """,
                finalized["execution_id"],
                finalized["module"],
                finalized.get("module_version"),
                datetime.fromisoformat(finalized["started_at"]),
                finalized.get("duration_ms"),
                _coerce(inputs),
                _coerce(trail_payload),
                _coerce(finalized.get("scored_output") or {}),
            )
    except Exception as e:  # noqa: BLE001 — audit must never break scoring
        log.warning("persist_trail failed: %s", e)


def _coerce(o: Any) -> Any:
    """Recursively coerce dataclass / set / Decimal / datetime → JSON-safe primitives.
    Needed because the asyncpg json codec relies on json.dumps but doesn't know
    about anything beyond stdlib types."""
    import dataclasses
    import datetime as _dt
    import decimal

    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return _coerce(dataclasses.asdict(o))
    if isinstance(o, dict):
        return {k: _coerce(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_coerce(v) for v in o]
    if isinstance(o, (_dt.datetime, _dt.date)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return float(o)
    return o
