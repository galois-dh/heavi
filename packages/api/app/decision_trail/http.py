"""HTTP tracer — httpx event-hook wrapper.

Records every outbound HTTP call the scoring pipeline makes (FEMA NFHL, USACE
NSI, USGS 3DEP / ASCE Design Maps, etc.) so the decision trail can show the
caller exactly which federal endpoint produced which input value.

Usage::

    async with ctx.http_client(timeout=30.0) as client:
        r = await client.get(NFHL_QUERY_URL, params=...)

The returned client is an ``httpx.AsyncClient`` with our event hooks already
installed — drop-in for the bare ``httpx.AsyncClient`` the modules use today.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx


@dataclass
class HttpEvent:
    method: str
    host: str
    path: str
    status: int
    duration_ms: float
    response_size: int
    # Filled when the hostname doesn't match a known source.
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Map known federal hostnames to a human-readable data-source label so the
# trail / advisories can group HTTP calls by provider without re-parsing URLs.
_SOURCE_LABELS = {
    "hazards.fema.gov":          "FEMA National Flood Hazard Layer",
    "nsi.sec.usace.army.mil":    "USACE National Structure Inventory",
    "elevation.nationalmap.gov": "USGS 3DEP Elevation",
    "earthquake.usgs.gov":       "USGS Earthquake Hazards / ASCE Design Maps",
    "api.mapbox.com":            "Mapbox Geocoding",
    "nominatim.openstreetmap.org": "Nominatim (OSM) Geocoding",
}


def _source_label(host: str) -> str | None:
    return _SOURCE_LABELS.get(host)


class HttpTracer:
    def __init__(self) -> None:
        self.events: list[HttpEvent] = []
        self._sources: set[str] = set()

    def record(
        self,
        *,
        method: str,
        url: httpx.URL,
        status: int,
        duration_ms: float,
        response_size: int,
    ) -> None:
        host = url.host
        src = _source_label(host)
        if src:
            self._sources.add(src)
        self.events.append(
            HttpEvent(
                method=method,
                host=host,
                path=url.path or "/",
                status=status,
                duration_ms=round(duration_ms, 3),
                response_size=response_size,
                source=src,
            )
        )

    @property
    def data_sources(self) -> list[str]:
        return sorted(self._sources)

    @property
    def total_duration_ms(self) -> float:
        return round(sum(e.duration_ms for e in self.events), 3)


def make_traced_client(tracer: HttpTracer, **kwargs: Any) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` whose request lifecycle is fed to the tracer.

    Any keyword args are passed through to ``httpx.AsyncClient`` so callers can
    still set timeout/headers/verify like they do with a plain client.
    """

    async def on_request(request: httpx.Request) -> None:
        request.extensions["_trail_t0"] = time.perf_counter()

    async def on_response(response: httpx.Response) -> None:
        t0 = response.request.extensions.get("_trail_t0", time.perf_counter())
        duration_ms = (time.perf_counter() - t0) * 1000.0
        # httpx populates Content-Length on the response headers for non-streaming
        # responses; falling back to 0 keeps the trace honest when we don't know.
        try:
            size = int(response.headers.get("content-length", 0) or 0)
        except ValueError:
            size = 0
        tracer.record(
            method=response.request.method,
            url=response.request.url,
            status=response.status_code,
            duration_ms=duration_ms,
            response_size=size,
        )

    hooks = kwargs.pop("event_hooks", {}) or {}
    # Merge with any caller-provided hooks rather than overwriting.
    hooks.setdefault("request", []).insert(0, on_request)
    hooks.setdefault("response", []).insert(0, on_response)
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
