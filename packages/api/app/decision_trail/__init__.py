"""Runtime decision-trail infrastructure for scoring pipelines.

The package gives every scoring entrypoint a uniform way to record:

  - SQL calls   (via ``SqlTracer`` + ``TracedPool``, drop-in for asyncpg.Pool)
  - HTTP calls  (via ``HttpTracer`` + ``make_traced_client``, drop-in for httpx)
  - decision steps, factors, advisories, data-source declarations
    (via ``DecisionTrail``)

A scoring function receives a single :class:`RequestContext` that bundles all
three, runs as it always did, and returns a structured trail JSON the API can
ship back to the caller and persist for audit.
"""

from .http import HttpEvent, HttpTracer, make_traced_client
from .persistence import persist_trail
from .tracing import SqlEvent, SqlTracer, TracedConnection, TracedPool
from .trail import DecisionTrail, RequestContext, TrailEvent

__all__ = [
    "DecisionTrail",
    "HttpEvent",
    "HttpTracer",
    "RequestContext",
    "SqlEvent",
    "SqlTracer",
    "TracedConnection",
    "TracedPool",
    "TrailEvent",
    "make_traced_client",
    "persist_trail",
]
