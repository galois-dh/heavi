"""Data Repository — query API for the data_sources catalog.

Two functions per spec (Heavi_Platform_Refactor_Spec.md, Phase 1):

  get_sources_for_workflow(workflow_type) -> list[dict]
    Every source where workflow_type is in applicable_workflows.

  get_source_availability(source_id, latitude, longitude) -> dict
    Availability + quality for a specific source at a specific location.
    Per-coverage-type logic per spec.

State resolution from (lat, lng) uses simple bounding boxes — the spec
explicitly allows "a simple bounding box check or reverse geocode" and bbox
is fast + dependency-free. Multi-state bbox overlaps return the first
match; the response field ``state_resolution_method`` makes the
approximation visible.
"""

from __future__ import annotations

from typing import Any

import asyncpg

# ─── US state bounding boxes (west, south, east, north) ───────────────────
# Conterminous US + AK + HI + DC. Used for the lat/lng → state heuristic.
# Bboxes overlap in places; iteration order is alphabetical by abbreviation
# (states are deterministic but not picked by area).
_US_STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "AL": (-88.4731, 30.1448, -84.8884, 35.0084),
    "AK": (-179.1486, 51.2095, -129.9795, 71.3525),
    "AZ": (-114.8163, 31.3322, -109.0452, 37.0043),
    "AR": (-94.6178, 33.0040, -89.6446, 36.4996),
    "CA": (-124.4096, 32.5343, -114.1312, 42.0095),
    "CO": (-109.0602, 36.9924, -102.0418, 41.0034),
    "CT": (-73.7274, 40.9509, -71.7869, 42.0502),
    "DE": (-75.7891, 38.4515, -75.0489, 39.8394),
    "DC": (-77.1198, 38.7916, -76.9094, 38.9955),
    "FL": (-87.6349, 24.5232, -80.0312, 31.0009),
    "GA": (-85.6051, 30.3556, -80.7514, 35.0006),
    "HI": (-160.5471, 18.9117, -154.8068, 22.2356),
    "ID": (-117.2435, 41.9881, -111.0436, 49.0011),
    "IL": (-91.5131, 36.9701, -87.4946, 42.5083),
    "IN": (-88.0978, 37.7715, -84.7846, 41.7613),
    "IA": (-96.6395, 40.3754, -90.1401, 43.5011),
    "KS": (-102.0517, 36.9930, -94.5882, 40.0031),
    "KY": (-89.5715, 36.4972, -81.9647, 39.1474),
    "LA": (-94.0431, 28.9290, -88.7589, 33.0193),
    "ME": (-71.0838, 43.0596, -66.9468, 47.4598),
    "MD": (-79.4866, 37.9117, -75.0489, 39.7232),
    "MA": (-73.5081, 41.2391, -69.9282, 42.8868),
    "MI": (-90.4180, 41.6961, -82.4225, 48.3061),
    "MN": (-97.2390, 43.4994, -89.4912, 49.3845),
    "MS": (-91.6550, 30.1738, -88.0978, 35.0084),
    "MO": (-95.7414, 35.9957, -89.1015, 40.6136),
    "MT": (-116.0489, 44.3582, -104.0407, 49.0011),
    "NE": (-104.0531, 39.9994, -95.3082, 43.0017),
    "NV": (-120.0064, 35.0019, -114.0396, 42.0022),
    "NH": (-72.5573, 42.6970, -70.7110, 45.3055),
    "NJ": (-75.5586, 38.9285, -73.8941, 41.3574),
    "NM": (-109.0502, 31.3322, -103.0019, 37.0003),
    "NY": (-79.7624, 40.4961, -71.8562, 45.0152),
    "NC": (-84.3219, 33.7528, -75.4001, 36.5881),
    "ND": (-104.0489, 45.9351, -96.5544, 49.0009),
    "OH": (-84.8203, 38.4031, -80.5188, 41.9777),
    "OK": (-103.0019, 33.6155, -94.4313, 37.0023),
    "OR": (-124.5663, 41.9918, -116.4634, 46.2920),
    "PA": (-80.5189, 39.7198, -74.6895, 42.5160),
    "RI": (-71.8624, 41.0959, -71.1170, 42.0188),
    "SC": (-83.3535, 32.0346, -78.5417, 35.2154),
    "SD": (-104.0577, 42.4795, -96.4364, 45.9450),
    "TN": (-90.3103, 34.9829, -81.6469, 36.6783),
    "TX": (-106.6456, 25.8371, -93.5083, 36.5007),
    "UT": (-114.0530, 36.9979, -109.0410, 42.0017),
    "VT": (-73.4378, 42.7269, -71.4651, 45.0167),
    "VA": (-83.6754, 36.5408, -75.2419, 39.4660),
    "WA": (-124.7330, 45.5435, -116.9165, 49.0024),
    "WV": (-82.6447, 37.2015, -77.7190, 40.6388),
    "WI": (-92.8881, 42.4915, -86.2495, 47.0796),
    "WY": (-111.0568, 40.9948, -104.0521, 45.0054),
}


def _state_at_point(latitude: float, longitude: float) -> str | None:
    """Return the first US state whose bbox contains the point, or None.

    Bbox overlaps (notably along straight-line borders) mean this can be
    ambiguous; callers should treat ``state_resolution_method='bbox'`` as a
    hint, not ground truth. Border parcels may resolve to a neighbouring
    state — the only correct fix is a polygon-level state layer, which is
    out of scope for Phase 1.
    """
    for st, (w, s, e, n) in _US_STATE_BBOXES.items():
        if w <= longitude <= e and s <= latitude <= n:
            return st
    return None


# ─── Query 1: workflow → sources ───────────────────────────────────────────


async def get_sources_for_workflow(
    pool: asyncpg.Pool, workflow_type: str
) -> list[dict[str, Any]]:
    """Return every data source where ``workflow_type`` is in applicable_workflows.

    Result ordering: data_category, then source_id, for deterministic output."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                source_id, name, provider, description, access_method,
                access_config, coverage_type, coverage_states, coverage_notes,
                resolution, vintage, update_frequency, reliability,
                last_verified, known_gaps, license, source_url, citation,
                data_category, applicable_workflows,
                created_at, updated_at
            FROM data_sources
            WHERE $1 = ANY(applicable_workflows)
            ORDER BY data_category, source_id
            """,
            workflow_type,
        )
    return [dict(r) for r in rows]


# ─── Query 2: source × location → availability ────────────────────────────


async def get_source_availability(
    pool: asyncpg.Pool,
    source_id: str,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Return availability + quality for a source at a specific location.

    Per Phase 1 spec:
      coverage_type='national' + reliability='verified'  → available, quality=full
      coverage_type='national' + reliability='degraded'  → available, quality=degraded
      coverage_type∈{'state','regional'} → check state in coverage_states; if not,
                                            check access_config.fallback; else unavailable
      coverage_type='county'             → unavailable + coverage note
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT source_id, name, coverage_type, coverage_states, coverage_notes,
                   reliability, known_gaps, access_config, access_method
            FROM data_sources WHERE source_id = $1
            """,
            source_id,
        )
    if row is None:
        return {
            "source_id":     source_id,
            "available":     False,
            "quality":       "unknown",
            "note":          f"unknown source_id '{source_id}'",
            "error":         "source not found in data_sources",
        }
    coverage_type   = row["coverage_type"]
    coverage_states = row["coverage_states"]
    reliability     = row["reliability"]
    known_gaps      = row["known_gaps"]
    access_config   = row["access_config"]

    base = {
        "source_id":              source_id,
        "name":                   row["name"],
        "coverage_type":          coverage_type,
        "reliability":            reliability,
        "state_resolution_method": "bbox",
        "state_resolved":          _state_at_point(latitude, longitude),
    }

    # 1) National coverage.
    if coverage_type == "national":
        if reliability == "verified":
            return {**base, "available": True, "quality": "full"}
        if reliability == "degraded":
            return {
                **base, "available": True, "quality": "degraded",
                "note": known_gaps or "service is degraded — fall back may be required",
            }
        # reliability == "unavailable"
        return {**base, "available": False, "quality": "unavailable",
                "note": known_gaps or "marked unavailable"}

    # 2) Regional or state coverage — check whether the resolved state is in
    #    the coverage list; otherwise look for a fallback access path.
    if coverage_type in ("state", "regional"):
        state_resolved = base["state_resolved"]
        in_coverage = bool(
            state_resolved
            and coverage_states
            and state_resolved in coverage_states
        )
        if in_coverage:
            return {
                **base, "available": True,
                "quality": "full" if reliability == "verified" else reliability,
                "note": None if reliability == "verified" else known_gaps,
            }
        # Not in pre-loaded coverage — does the access_config declare a fallback?
        fallback = _coverage_fallback(access_config)
        if fallback:
            return {
                **base, "available": True, "quality": "fallback",
                "note": "on-demand query, may add latency",
                "fallback": fallback,
            }
        return {
            **base, "available": False, "quality": "out_of_coverage",
            "note": known_gaps or
                    f"location is in {state_resolved or 'unknown state'}; "
                    f"loaded coverage is {coverage_states or '(none)'}",
        }

    # 3) County coverage — per spec literal: always unavailable unless fallback,
    #    regardless of whether the resolved state matches coverage_states.
    #    Rationale: 'county' means "loaded for a specific county only" — the
    #    state-level bbox check is too coarse to confirm the parcel is in the
    #    actual loaded county. The spec author chose conservative; we follow.
    if coverage_type == "county":
        fallback = _coverage_fallback(access_config)
        if fallback:
            return {
                **base, "available": True, "quality": "fallback",
                "note": "on-demand query, may add latency",
                "fallback": fallback,
            }
        return {
            **base, "available": False, "quality": "out_of_coverage",
            "note": (
                f"only loaded for {row['coverage_notes'] or coverage_states or '(unspecified)'}"
            ),
        }

    # Unknown coverage_type — surface explicitly.
    return {
        **base, "available": False, "quality": "unknown",
        "note": f"unhandled coverage_type='{coverage_type}'",
    }


def _coverage_fallback(access_config: Any) -> dict[str, Any] | None:
    """Extract a usable fallback descriptor from access_config, if any.

    Recognises both ``access_config.fallback`` (the canonical spot used by
    osm_substations and nwi_wetlands) and any future top-level ``fallback`` key.
    Returns None if no fallback exists OR the fallback itself is marked
    UNVERIFIED — we don't want to suggest a fallback path the spec already
    flagged as broken (e.g. the NWI national REST endpoint).
    """
    if not isinstance(access_config, dict):
        return None
    fb = access_config.get("fallback")
    if not isinstance(fb, dict):
        return None
    status = (fb.get("status") or "").upper()
    if status.startswith("UNVERIFIED") or "DEGRADED" in status:
        return None
    return fb
