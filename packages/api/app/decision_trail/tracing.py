"""SQL tracer — duck-typed asyncpg.Pool wrapper.

Adapted from packages/validation/heavi_validation/tracing.py with two changes
for runtime use: SQL is trimmed to a configurable max length (the validation
log keeps the full text; the runtime trail keeps it short for response size),
and the record is a plain dict on serialization so it round-trips through
asyncpg's jsonb codec without dataclass-encoding gymnastics.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

_MAX_SQL_CHARS = 2000


@dataclass
class SqlEvent:
    sql: str
    duration_ms: float
    row_count: int
    table_hits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_TABLE_PAT = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([a-zA-Z_][\w]*)", re.IGNORECASE)


def _extract_tables(sql: str) -> list[str]:
    return sorted(set(_TABLE_PAT.findall(sql)))


def _trim(sql: str) -> str:
    s = " ".join(sql.split())
    return s if len(s) <= _MAX_SQL_CHARS else s[:_MAX_SQL_CHARS] + " …"


class SqlTracer:
    def __init__(self) -> None:
        self.events: list[SqlEvent] = []
        self._tables: set[str] = set()

    def record(self, sql: str, duration_ms: float, row_count: int) -> None:
        tables = _extract_tables(sql)
        self._tables.update(tables)
        self.events.append(
            SqlEvent(
                sql=_trim(sql),
                duration_ms=round(duration_ms, 3),
                row_count=row_count,
                table_hits=tables,
            )
        )

    @property
    def data_layers(self) -> list[str]:
        return sorted(self._tables)

    @property
    def total_duration_ms(self) -> float:
        return round(sum(e.duration_ms for e in self.events), 3)


class TracedConnection:
    """Proxies an asyncpg connection, recording each fetch into the tracer."""

    def __init__(self, conn: Any, tracer: SqlTracer) -> None:
        self._conn = conn
        self._tracer = tracer

    async def fetchval(self, query: str, *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return await self._conn.fetchval(query, *args, **kwargs)
        finally:
            self._tracer.record(query, (time.perf_counter() - t0) * 1000.0, 1)

    async def fetchrow(self, query: str, *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            row = await self._conn.fetchrow(query, *args, **kwargs)
        finally:
            self._tracer.record(query, (time.perf_counter() - t0) * 1000.0, 0 if row is None else 1)
        return row

    async def fetch(self, query: str, *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            rows = await self._conn.fetch(query, *args, **kwargs)
        finally:
            self._tracer.record(query, (time.perf_counter() - t0) * 1000.0, len(rows or []))
        return rows

    async def execute(self, query: str, *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return await self._conn.execute(query, *args, **kwargs)
        finally:
            self._tracer.record(query, (time.perf_counter() - t0) * 1000.0, 0)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._conn, item)


class _AcquireCM:
    """Replicates the ``async with pool.acquire() as conn`` protocol."""

    def __init__(self, pool: Any, tracer: SqlTracer) -> None:
        self._cm = pool.acquire()
        self._tracer = tracer

    async def __aenter__(self) -> TracedConnection:
        return TracedConnection(await self._cm.__aenter__(), self._tracer)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        return await self._cm.__aexit__(exc_type, exc, tb)


class TracedPool:
    """A duck-typed asyncpg.Pool that wires every acquired connection to a tracer."""

    def __init__(self, pool: Any, tracer: SqlTracer) -> None:
        self._pool = pool
        self._tracer = tracer

    def acquire(self) -> _AcquireCM:
        return _AcquireCM(self._pool, self._tracer)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._pool, item)
