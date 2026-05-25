"""Validation adapter for the site_suitability module in packages/api.

Wraps :func:`app.site_report.site_report` in a :class:`Module`-compatible
shape: ``execute(inputs, tracer)`` returns ``{"score": composite, "factors": {...}, ...}``.
The asyncpg pool is wrapped in a :class:`TracedPool` so the harness/audit
trail capture every SQL call without requiring changes to site_report.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from heavi_validation.tracing import QueryTracer, TracedPool

# Make the API package importable without packaging it as a wheel.
_API_PATH = Path(__file__).resolve().parents[3] / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

from app.site_report import site_report  # noqa: E402


class SiteSuitabilityModule:
    """Module-protocol wrapper around app.site_report.site_report."""

    name = "site_suitability"
    version = "0.1.0"

    async def execute(
        self,
        inputs: dict[str, Any],
        tracer: QueryTracer | None = None,
        pool: Any = None,
    ) -> dict[str, Any]:
        if pool is None:
            raise RuntimeError("site_suitability module requires an asyncpg pool")

        effective_pool: Any = TracedPool(pool, tracer) if tracer is not None else pool
        raw = await site_report(
            effective_pool,
            lat=float(inputs["latitude"]),
            lng=float(inputs["longitude"]),
            radius_m=int(inputs.get("radius_meters", 1609)),
            address=inputs.get("address"),
        )
        return {
            "score": raw["composite_score"],
            "factors": raw["factors"],
            "counts": raw.get("counts", {}),
            "nearby": raw.get("nearby", {}),
            "address": raw.get("address"),
            "location": raw.get("location"),
        }
