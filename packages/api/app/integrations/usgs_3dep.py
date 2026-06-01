"""USGS 3DEP Elevation — single + multipoint ground elevation queries.

Two helpers:

  ground_elev_m(client, lat, lng)
    Single-point ground elevation in metres. Drop-in for the various scoring
    modules that currently query elevation per parcel centroid.

  elev_multipoint_m(client, points)
    Multi-point ground elevation — sends N (lng, lat) pairs in ONE HTTP call
    via the ImageServer's getSamples geometryType=esriGeometryMultipoint, so a
    terrain-grid stage doesn't burn an HTTP round-trip per sample.

Both return metres (the service's native unit). Caller converts if needed.

Verified 2026-06-05 with a 3×3 grid around Kern: 9 elevations returned in
one call, stdev 1.08 m (correctly flat).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

GETSAMPLES_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/"
    "3DEPElevation/ImageServer/getSamples"
)


async def ground_elev_m(
    client: httpx.AsyncClient, *, latitude: float, longitude: float
) -> float | None:
    """Ground elevation in metres at a single point, or None if 3DEP returns
    no sample (e.g. ocean / outside CONUS)."""
    geom = json.dumps({
        "points":           [[longitude, latitude]],
        "spatialReference": {"wkid": 4326},
    })
    try:
        r = await client.get(
            GETSAMPLES_URL,
            params={
                "geometry":              geom,
                "geometryType":          "esriGeometryMultipoint",
                "returnFirstValueOnly":  "true",
                "f":                     "json",
            },
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    samples = data.get("samples") or []
    if not samples:
        return None
    try:
        return float(samples[0]["value"])
    except (KeyError, TypeError, ValueError):
        return None


async def elev_multipoint_m(
    client: httpx.AsyncClient, points: list[tuple[float, float]]
) -> list[float | None]:
    """Return ground elevations (metres) for N (longitude, latitude) points in
    order. One HTTP round-trip per call. A None at index i means 3DEP did not
    return a value for that point (data gap)."""
    if not points:
        return []
    geom = json.dumps({
        "points":           [[float(lng), float(lat)] for (lng, lat) in points],
        "spatialReference": {"wkid": 4326},
    })
    try:
        r = await client.get(
            GETSAMPLES_URL,
            params={
                "geometry":              geom,
                "geometryType":          "esriGeometryMultipoint",
                "returnFirstValueOnly":  "true",
                "f":                     "json",
            },
        )
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return [None] * len(points)
    samples = data.get("samples") or []
    out: list[float | None] = [None] * len(points)
    for s in samples:
        # The service returns a 0-based ordering matching input points via
        # the OBJECTID attribute (sometimes 'pointid'). Both seen in practice;
        # fall back to enumerate order.
        attrs = s.get("attributes") or {}
        idx = attrs.get("OID") or attrs.get("OBJECTID") or attrs.get("Id")
        try:
            i = (int(idx) - 1) if idx is not None else samples.index(s)
        except (TypeError, ValueError):
            i = samples.index(s)
        if 0 <= i < len(points):
            try:
                out[i] = float(s["value"])
            except (KeyError, TypeError, ValueError):
                out[i] = None
    return out


# Re-export utilities the Stage 2 terrain pipeline uses for slope/aspect math.

def slope_aspect_from_grid(
    elevations: list[list[float | None]],
    dx_m: float,
    dy_m: float,
) -> tuple[list[list[dict[str, Any] | None]], dict[str, Any]]:
    """Given an NxM 2-D elevation grid (north up: row 0 is southernmost, last
    row is northernmost), return (per-cell slope/aspect, grid-summary).

    Per-cell value is None for grid edges (we use central differences only).
    """
    import math

    n_rows = len(elevations)
    n_cols = len(elevations[0]) if n_rows else 0
    cells: list[list[dict[str, Any] | None]] = [
        [None] * n_cols for _ in range(n_rows)
    ]

    slopes: list[float] = []
    aspect_xs: list[float] = []   # ∑ slope · sin(aspect)
    aspect_ys: list[float] = []   # ∑ slope · cos(aspect)

    for r in range(1, n_rows - 1):
        for c in range(1, n_cols - 1):
            z   = elevations[r][c]
            z_e = elevations[r][c + 1]
            z_w = elevations[r][c - 1]
            z_n = elevations[r + 1][c]
            z_s = elevations[r - 1][c]
            if None in (z, z_e, z_w, z_n, z_s):
                continue
            dz_dx = (z_e - z_w) / (2 * dx_m)
            dz_dy = (z_n - z_s) / (2 * dy_m)
            slope_grade = math.hypot(dz_dx, dz_dy)
            slope_pct   = slope_grade * 100.0
            slope_deg   = math.degrees(math.atan(slope_grade))
            # Aspect = compass direction the surface faces (downslope direction).
            # gradient points uphill → aspect = direction of -gradient.
            aspect_rad  = math.atan2(-dz_dx, -dz_dy)
            aspect_deg  = (math.degrees(aspect_rad) + 360.0) % 360.0
            cells[r][c] = {
                "slope_pct":  round(slope_pct, 2),
                "slope_deg":  round(slope_deg, 2),
                "aspect_deg": round(aspect_deg, 1),
            }
            slopes.append(slope_grade)
            aspect_xs.append(slope_grade * math.sin(math.radians(aspect_deg)))
            aspect_ys.append(slope_grade * math.cos(math.radians(aspect_deg)))

    summary: dict[str, Any] = {
        "interior_cells_with_data": len(slopes),
        "mean_slope_pct":           None,
        "mean_slope_deg":           None,
        "dominant_aspect_deg":      None,
    }
    if slopes:
        mean_grade = sum(slopes) / len(slopes)
        summary["mean_slope_pct"] = round(mean_grade * 100.0, 2)
        summary["mean_slope_deg"] = round(math.degrees(math.atan(mean_grade)), 2)
        # Slope-weighted circular mean of aspect. If all slopes ~0, aspect is
        # not meaningful — return None so the consumer knows.
        x = sum(aspect_xs)
        y = sum(aspect_ys)
        if math.hypot(x, y) > 1e-9:
            summary["dominant_aspect_deg"] = round(
                (math.degrees(math.atan2(x, y)) + 360.0) % 360.0, 1
            )
    return cells, summary
