"""Source-specific availability probing (Heavi Platform Build Spec Phase 1).

This is the SourceResult-producing layer the spec calls ``check_source_avail-
ability``: unlike the metadata-only ``get_source_availability`` (kept in
data_repository.py for backwards compat), this one actually queries the
underlying data — PostGIS sources run a spatial probe, REST APIs return
verified-without-probe for national-verified entries and live-probe for
degraded entries.

The returned ``SourceResult`` carries the actual query result alongside the
boolean so the Phase 3 selection engine can reuse it across criteria (per the
"query each source ONCE" rule in the methodology doc).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import httpx


@dataclass
class SourceResult:
    source_id: str
    available: bool
    quality: str        # 'full' | 'degraded' | 'partial' | 'unavailable'
    data: Any | None    # actual probe result (rows, features, …) for reuse
    error: str | None = None
    query_time_ms: float = 0.0
    note: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id":      self.source_id,
            "available":      self.available,
            "quality":        self.quality,
            "data":           self.data,
            "error":          self.error,
            "query_time_ms":  round(self.query_time_ms, 1),
            "note":           self.note,
            "detail":         self.detail or None,
        }


# Radius (metres) for the spatial-existence probe per source. The values are
# the smallest radius at which "data exists nearby" is operationally useful
# for the consuming criterion.
_POSTGIS_PROBE_RADIUS_M: dict[str, int] = {
    "hifld_transmission":          50_000,
    "osm_substations":             50_000,
    "eia_form860":                 25_000,
    "epa_ejscreen":                 1_000,  # block-group lookup happens elsewhere
    "nwi_wetlands":                 1_000,
    "google_inundation_history":    5_000,
    "usgs_padus":                   1_000,
    "usfws_critical_habitat":       1_000,
    "census_lehd":                  1_000,
    "osm_pois":                     5_000,
    "hazus_ddfs":                       0,  # non-spatial — always available if pool ok
    "usfs_fsim":                    1_000,
    "landfire_fuels_canopy":        1_000,
}


# ─── PostGIS probe ─────────────────────────────────────────────────────────


# Cache of table → has a pre-computed `geog geography` column. Probing the same
# table across many locations (the selection engine queries each source once per
# location) would otherwise re-hit information_schema every time. Populated lazily
# on first probe of each table; persists for the process lifetime.
_GEOG_COLUMN_CACHE: dict[str, bool] = {}


async def _table_has_geog(pool: asyncpg.Pool, table: str) -> bool:
    """True if `table` has a `geog` column (a pre-computed geography we can probe
    against the GiST index, avoiding a per-row geometry::geography cast)."""
    if table in _GEOG_COLUMN_CACHE:
        return _GEOG_COLUMN_CACHE[table]
    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = $1 AND column_name = 'geog'
                )
                """,
                table,
            )
    except Exception:  # noqa: BLE001
        exists = False
    _GEOG_COLUMN_CACHE[table] = bool(exists)
    return bool(exists)


async def _probe_postgis(
    pool: asyncpg.Pool,
    source_id: str,
    access_config: dict[str, Any],
    latitude: float, longitude: float,
) -> SourceResult:
    """Spatial-existence probe with a small nearest-features pull so the data
    is cached for the selection engine."""
    if source_id == "hazus_ddfs":
        # Non-spatial lookup table — confirm rows present. The catalog records
        # the logical table name (hazus_ddfs); the physical name in PostGIS is
        # flood_hazus_ddfs from the original loader. Try logical first, then
        # the known physical alias.
        candidates = [access_config["table"], "flood_hazus_ddfs"]
        n = 0
        used = None
        for tbl in candidates:
            try:
                async with pool.acquire() as conn:
                    n = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
                used = tbl
                if n and n > 0:
                    break
            except Exception:  # noqa: BLE001
                continue
        return SourceResult(
            source_id=source_id,
            available=bool(n and n > 0),
            quality="full" if n else "unavailable",
            data={"row_count": int(n) if n else 0, "physical_table": used},
            note=(None if used else "expected lookup table not found"),
        )

    table = access_config.get("table")
    geom_col = access_config.get("geometry_column", "geometry")
    if not table:
        return SourceResult(
            source_id=source_id, available=False, quality="unavailable",
            data=None, error="access_config.table missing",
        )

    radius = _POSTGIS_PROBE_RADIUS_M.get(source_id, 1_000)
    point_sql = (
        "ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography"
    )
    # Prefer a pre-computed `geog` column (probed directly against its GiST
    # index) over casting `geometry::geography` per row, which defeats the index
    # and forces a sequential scan. Falls back to the runtime cast when the table
    # has no geog column. The raw geometry column is left untouched for callers
    # that still use it.
    geo_expr = "t.geog" if await _table_has_geog(pool, table) else f"t.{geom_col}::geography"
    t0 = time.perf_counter()
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                WITH parcel AS (SELECT {point_sql} AS g)
                SELECT
                  COUNT(*)::int AS n,
                  MIN(ST_Distance({geo_expr}, p.g)) AS nearest_m
                FROM {table} t, parcel p
                WHERE ST_DWithin({geo_expr}, p.g, $3)
                """,
                longitude, latitude, float(radius),
            )
    except Exception as e:  # noqa: BLE001 — bad table / missing column / etc.
        # A missing physical table means the source isn't actually loaded;
        # return unavailable instead of bubbling up an exception (so the
        # selection engine can mark the criterion as a gap).
        return SourceResult(
            source_id=source_id, available=False, quality="unavailable",
            data=None, error=str(e),
            query_time_ms=(time.perf_counter() - t0) * 1000.0,
            note=f"PostGIS probe failed on table '{table}'",
        )
    n = int(row["n"] or 0)
    nearest_m = float(row["nearest_m"]) if row["nearest_m"] is not None else None
    return SourceResult(
        source_id=source_id,
        available=n > 0,
        quality="full" if n > 0 else "unavailable",
        data={"feature_count": n, "nearest_m": nearest_m, "probe_radius_m": radius},
        query_time_ms=(time.perf_counter() - t0) * 1000.0,
        note=(
            f"{n} feature(s) within {radius//1000} km" if n else
            f"no features within {radius//1000} km (probe table: {table})"
        ),
    )


# ─── REST API probe ────────────────────────────────────────────────────────


_DNS_CACHE: dict[str, bool] = {}


async def _host_resolves(host: str) -> bool:
    """Best-effort DNS check using stdlib; caches positive results."""
    if host in _DNS_CACHE:
        return _DNS_CACHE[host]
    try:
        loop = asyncio.get_event_loop()
        await loop.getaddrinfo(host, None)
        _DNS_CACHE[host] = True
        return True
    except Exception:  # noqa: BLE001
        _DNS_CACHE[host] = False
        return False


async def _probe_rest(
    source_id: str,
    access_config: dict[str, Any],
    reliability: str,
    latitude: float, longitude: float,
) -> SourceResult:
    """For verified-reliability national REST APIs, trust the catalog —
    return available without paying for an HTTP round-trip. For degraded
    sources, do a lightweight live probe so the result reflects current
    service health."""
    endpoint = access_config.get("endpoint") or ""
    host = endpoint.split("://", 1)[-1].split("/", 1)[0]

    if reliability == "verified":
        return SourceResult(
            source_id=source_id,
            available=True,
            quality="full",
            data={"endpoint": endpoint, "method": "rest_api"},
            note="catalog-declared verified national REST endpoint",
        )

    # Degraded sources: probe live.
    if not host:
        return SourceResult(
            source_id=source_id, available=False, quality="unavailable",
            data=None, error="no endpoint",
        )

    t0 = time.perf_counter()
    if not await _host_resolves(host):
        return SourceResult(
            source_id=source_id, available=False, quality="unavailable",
            data=None, error=f"DNS unresolved: {host}",
            query_time_ms=(time.perf_counter() - t0) * 1000.0,
        )

    # NWI-specific live probe — small envelope, GET, parse JSON for error.
    if source_id == "nwi_wetlands_rest":
        hx = 0.005
        geom = json.dumps({
            "xmin": longitude - hx, "ymin": latitude - hx,
            "xmax": longitude + hx, "ymax": latitude + hx,
            "spatialReference": {"wkid": 4326},
        })
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(endpoint, params={
                    "geometry": geom, "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "*", "returnGeometry": "false", "f": "json",
                })
                body = r.json()
        except Exception as e:  # noqa: BLE001
            return SourceResult(
                source_id=source_id, available=False, quality="unavailable",
                data=None, error=str(e),
                query_time_ms=(time.perf_counter() - t0) * 1000.0,
            )
        err = body.get("error") if isinstance(body, dict) else None
        if err:
            return SourceResult(
                source_id=source_id, available=False, quality="degraded",
                data=None, error=str(err),
                note="NWI REST returned an error response",
                query_time_ms=(time.perf_counter() - t0) * 1000.0,
            )
        feats = (body.get("features") or []) if isinstance(body, dict) else []
        return SourceResult(
            source_id=source_id, available=True, quality="full",
            data={"feature_count": len(feats)},
            note="NWI REST responded successfully",
            query_time_ms=(time.perf_counter() - t0) * 1000.0,
        )

    # Generic degraded REST: just check DNS + endpoint reachability.
    return SourceResult(
        source_id=source_id, available=True, quality="degraded",
        data={"endpoint": endpoint},
        note="degraded reliability — endpoint host resolves but content not verified",
        query_time_ms=(time.perf_counter() - t0) * 1000.0,
    )


# ─── WMS + file probes (lightweight) ───────────────────────────────────────


async def _probe_wms(
    source_id: str, access_config: dict[str, Any], reliability: str,
) -> SourceResult:
    if reliability == "verified":
        return SourceResult(
            source_id=source_id, available=True, quality="full",
            data={"endpoint": access_config.get("endpoint")},
            note="catalog-declared verified WMS",
        )
    return SourceResult(
        source_id=source_id, available=False, quality="degraded",
        data=None, note="WMS reliability is degraded; live probe not implemented",
    )


async def _probe_file(
    source_id: str, access_config: dict[str, Any], reliability: str,
) -> SourceResult:
    if reliability == "verified":
        return SourceResult(
            source_id=source_id, available=True, quality="full",
            data={"location": access_config.get("location"),
                  "format": access_config.get("format")},
            note="catalog-declared file source — deps required at consume time",
        )
    return SourceResult(
        source_id=source_id, available=False, quality="degraded",
        data=None, note="file source reliability is degraded",
    )


# ─── Public entry point ───────────────────────────────────────────────────


async def check_source_availability(
    pool: asyncpg.Pool,
    source_id: str,
    latitude: float,
    longitude: float,
) -> SourceResult:
    """Source-specific availability probe — Phase 1 of the build spec.

    PostGIS sources: spatial existence probe with ST_DWithin (radius per source).
    REST APIs:       verified → True without probing; degraded → live probe.
    WMS / file:      lightweight check; verified sources return True.

    Returns a ``SourceResult`` whose ``data`` field carries enough nearest-
    feature context that downstream stages (and the Phase 3 selection engine)
    can reuse it without re-querying.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT access_method, access_config, reliability, coverage_type,
                   coverage_states
            FROM data_sources WHERE source_id = $1
            """,
            source_id,
        )
    if row is None:
        return SourceResult(
            source_id=source_id, available=False, quality="unavailable",
            data=None, error=f"unknown source_id '{source_id}'",
        )
    method      = row["access_method"]
    config      = row["access_config"]
    reliability = row["reliability"]

    if isinstance(config, str):
        try:
            config = json.loads(config)
        except Exception:  # noqa: BLE001
            config = {}

    if method == "postgis_table":
        return await _probe_postgis(pool, source_id, config, latitude, longitude)
    if method == "rest_api":
        return await _probe_rest(source_id, config, reliability, latitude, longitude)
    if method == "wms":
        return await _probe_wms(source_id, config, reliability)
    if method == "file":
        return await _probe_file(source_id, config, reliability)
    return SourceResult(
        source_id=source_id, available=False, quality="unavailable",
        data=None, error=f"unhandled access_method '{method}'",
    )
