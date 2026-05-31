"""Decision-trail step recorder + per-request context.

The :class:`DecisionTrail` is what the spec calls a "step-by-step trace". It
sits one level *above* the raw SQL/HTTP tracers — scoring functions push named
business-meaningful events (a threshold check, a score component, a contextual
advisory) onto it. The raw query records are kept on the side and stitched
back in at finalization, so the response carries both views: what the pipeline
*did* (queries) and what the pipeline *decided* (steps).

:class:`RequestContext` is the single object scoring entrypoints accept. It
bundles the pool wrapper, the http client factory, and the trail so callers
have one parameter to thread through instead of four.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .http import HttpTracer
from .tracing import SqlTracer, TracedPool


@dataclass
class TrailEvent:
    """A single business-meaningful entry in the trail.

    ``kind`` is one of:
      - ``step``        — a threshold check or enrichment lookup (has source,
                          value, units, threshold, result pass/fail)
      - ``factor``      — a score component or intermediate value
      - ``advisory``    — a contextual note (info / warning / error severity)
      - ``data_source`` — declaration that a layer was consulted, separate from
                          any specific query (e.g. a static lookup table)
    """

    kind: str
    name: str
    source: str | None = None
    value: Any = None
    units: str | None = None
    threshold: dict[str, Any] | None = None
    result: str | None = None
    weight_pct: float | None = None
    severity: str | None = None
    message: str | None = None
    detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        # Drop None fields so the JSON stays compact and event shape is
        # implicit per kind.
        return {k: v for k, v in asdict(self).items() if v is not None}


class DecisionTrail:
    """Append-only list of trail events plus minimal metadata."""

    def __init__(self, module: str, module_version: str) -> None:
        self.execution_id = str(uuid.uuid4())
        self.module = module
        self.module_version = module_version
        self.started_at = datetime.now(UTC).isoformat()
        self.events: list[TrailEvent] = []

    # ── builders ────────────────────────────────────────────────────────────

    def step(
        self,
        name: str,
        *,
        source: str | None = None,
        value: Any = None,
        units: str | None = None,
        threshold: dict[str, Any] | None = None,
        result: str | None = None,
        weight_pct: float | None = None,
        **detail: Any,
    ) -> None:
        self.events.append(
            TrailEvent(
                kind="step",
                name=name,
                source=source,
                value=value,
                units=units,
                threshold=threshold,
                result=result,
                weight_pct=weight_pct,
                detail=detail or None,
            )
        )

    def factor(
        self, name: str, *, value: Any, source: str | None = None, **detail: Any
    ) -> None:
        self.events.append(
            TrailEvent(
                kind="factor",
                name=name,
                value=value,
                source=source,
                detail=detail or None,
            )
        )

    def advisory(
        self, message: str, *, severity: str = "info", name: str = "advisory", **detail: Any
    ) -> None:
        self.events.append(
            TrailEvent(
                kind="advisory",
                name=name,
                severity=severity,
                message=message,
                detail=detail or None,
            )
        )

    def data_source(
        self,
        name: str,
        *,
        vintage: str | None = None,
        source: str | None = None,
        **detail: Any,
    ) -> None:
        self.events.append(
            TrailEvent(
                kind="data_source",
                name=name,
                source=source,
                detail={"vintage": vintage, **detail} if (vintage or detail) else None,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "module": self.module,
            "module_version": self.module_version,
            "started_at": self.started_at,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class RequestContext:
    """One-stop bundle of pool + tracers + trail.

    Scoring functions accept this and use ``ctx.pool`` exactly like a regular
    asyncpg.Pool, and ``ctx.http_client(...)`` like ``httpx.AsyncClient(...)``.
    Everything else is bookkeeping the pipeline doesn't need to know about.
    """

    pool: TracedPool
    sql_tracer: SqlTracer
    http_tracer: HttpTracer
    trail: DecisionTrail
    _t0: float = field(default_factory=time.perf_counter)

    @classmethod
    def begin(cls, pool: Any, *, module: str, module_version: str) -> RequestContext:
        sql_t = SqlTracer()
        http_t = HttpTracer()
        return cls(
            pool=TracedPool(pool, sql_t),
            sql_tracer=sql_t,
            http_tracer=http_t,
            trail=DecisionTrail(module=module, module_version=module_version),
        )

    def http_client(self, **kwargs: Any) -> Any:
        """Return an httpx.AsyncClient with the per-request tracer attached."""
        from .http import make_traced_client

        return make_traced_client(self.http_tracer, **kwargs)

    # ── finalization ────────────────────────────────────────────────────────

    def finalize(self, *, scored_output: dict[str, Any]) -> dict[str, Any]:
        """Stitch trail events with raw query/HTTP records into one dict
        suitable for both the API response and the audit table row."""
        duration_ms = round((time.perf_counter() - self._t0) * 1000.0, 1)
        return {
            **self.trail.to_dict(),
            "queries":         [e.to_dict() for e in self.sql_tracer.events],
            "http_calls":      [e.to_dict() for e in self.http_tracer.events],
            "data_layers":     self.sql_tracer.data_layers,
            "data_sources":    self.http_tracer.data_sources,
            "duration_ms":     duration_ms,
            "scored_output":   scored_output,
        }
