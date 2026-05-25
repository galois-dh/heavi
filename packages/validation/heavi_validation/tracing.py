"""Lightweight asyncpg tracing.

Modules accept an ``asyncpg.Pool`` and call ``pool.acquire()`` to get a
connection. To capture the SQL a module executes without modifying the module
itself, we wrap the pool in :class:`TracedPool` which yields a
:class:`TracedConnection`. The traced connection proxies the standard fetch
methods, recording each call into a :class:`QueryTracer`.

This is duck-typed against asyncpg — the wrapper only implements the methods
the existing modules actually call (``fetch``, ``fetchval``, ``fetchrow``,
``execute``). Anything else falls through via ``__getattr__``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuditQuery:
    """A single recorded database call."""

    sql: str
    duration_ms: float
    row_count: int
    table_hits: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "duration_ms": round(self.duration_ms, 3),
            "row_count": self.row_count,
            "table_hits": self.table_hits,
        }


_TABLE_PAT = re.compile(r"\bFROM\s+([a-zA-Z_][\w]*)", re.IGNORECASE)


def _extract_tables(sql: str) -> list[str]:
    return sorted(set(_TABLE_PAT.findall(sql)))


class QueryTracer:
    """Accumulates SQL calls during a single module execution."""

    def __init__(self) -> None:
        self.queries: list[AuditQuery] = []
        self._tables: set[str] = set()

    def record(self, sql: str, duration_ms: float, row_count: int) -> None:
        tables = _extract_tables(sql)
        self._tables.update(tables)
        self.queries.append(
            AuditQuery(sql=sql, duration_ms=duration_ms, row_count=row_count, table_hits=tables)
        )

    @property
    def data_layers(self) -> list[str]:
        return sorted(self._tables)

    @property
    def total_duration_ms(self) -> float:
        return sum(q.duration_ms for q in self.queries)


class TracedConnection:
    """Proxies an asyncpg connection, recording each fetch into the tracer."""

    def __init__(self, conn: Any, tracer: QueryTracer) -> None:
        self._conn = conn
        self._tracer = tracer

    async def fetchval(self, query: str, *args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            result = await self._conn.fetchval(query, *args, **kwargs)
        finally:
            self._tracer.record(query, (time.perf_counter() - t0) * 1000.0, 1)
        return result

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
            result = await self._conn.execute(query, *args, **kwargs)
        finally:
            self._tracer.record(query, (time.perf_counter() - t0) * 1000.0, 0)
        return result

    def __getattr__(self, item: str) -> Any:
        return getattr(self._conn, item)


class _AcquireCM:
    """Replicates the ``async with pool.acquire() as conn`` protocol."""

    def __init__(self, pool: Any, tracer: QueryTracer) -> None:
        self._cm = pool.acquire()
        self._tracer = tracer
        self._conn: Any = None

    async def __aenter__(self) -> TracedConnection:
        self._conn = await self._cm.__aenter__()
        return TracedConnection(self._conn, self._tracer)

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        return await self._cm.__aexit__(exc_type, exc, tb)


class TracedPool:
    """A duck-typed asyncpg.Pool that wires every acquired connection to a tracer."""

    def __init__(self, pool: Any, tracer: QueryTracer) -> None:
        self._pool = pool
        self._tracer = tracer

    def acquire(self) -> _AcquireCM:
        return _AcquireCM(self._pool, self._tracer)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._pool, item)
