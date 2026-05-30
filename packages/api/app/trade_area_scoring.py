"""Trade area analysis — Week 1: data access + isochrone↔demographics pipeline.

National demographics are fetched on-demand from the Census ACS5 API; drive-time
isochrones from OpenRouteService; Dallas POIs and LEHD workplace jobs are
pre-loaded in PostGIS. Given a location we compute concentric drive-time
isochrones and, for each, the area-weighted resident population / households /
median income, the daytime jobs (LEHD), and the POI count.

Composite scoring and competitive analysis are Week 2; Week 1 returns the raw
trade-area profile per ring.
"""

from __future__ import annotations

import os
from typing import Any

import asyncpg
import httpx

# ─── Census ACS5 ─────────────────────────────────────────────────────────────
ACS_URL = "https://api.census.gov/data/2022/acs/acs5"
# Census Reporter is a keyless open mirror of the SAME ACS5 data — used as a
# fallback so the module functions when CENSUS_API_KEY is missing/not-yet-active.
CENSUS_REPORTER_URL = "https://api.censusreporter.org/1.0/data/show/latest"

ACS_VARS = {
    "population": "B01001_001E",
    "households": "B11001_001E",
    "median_income": "B19013_001E",
    "commuters": "B08301_001E",
}
# Young-adult (18-34) age cells per the build spec: male B01001_007E–010E,
# female B01001_031E–034E.
AGE_VARS = [f"B01001_{n:03d}E" for n in list(range(7, 11)) + list(range(31, 35))]

_DEMO_CACHE: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # ACS uses large negative sentinels (e.g. -666666666) for null/suppressed.
    return None if f <= -666666666 else f


async def _fetch_acs_official(
    client: httpx.AsyncClient, state: str, county: str, key: str
) -> dict[str, dict[str, Any]] | None:
    get_vars = list(ACS_VARS.values()) + AGE_VARS
    params = [("get", ",".join(get_vars)), ("for", "tract:*"),
              ("in", f"state:{state}"), ("in", f"county:{county}"), ("key", key)]
    try:
        r = await client.get(ACS_URL, params=params)
        if r.status_code != 200 or not r.text.lstrip().startswith("["):
            return None
        rows = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    out: dict[str, dict[str, Any]] = {}
    for row in rows[1:]:
        geoid = row[idx["state"]] + row[idx["county"]] + row[idx["tract"]]
        age = sum(_num(row[idx[v]]) or 0 for v in AGE_VARS)
        out[geoid] = {
            "population": _num(row[idx[ACS_VARS["population"]]]),
            "households": _num(row[idx[ACS_VARS["households"]]]),
            "median_income": _num(row[idx[ACS_VARS["median_income"]]]),
            "commuters": _num(row[idx[ACS_VARS["commuters"]]]),
            "age_18_34": age,
        }
    return out or None


async def _fetch_census_reporter(
    client: httpx.AsyncClient, state: str, county: str
) -> dict[str, dict[str, Any]] | None:
    tables = "B01001,B11001,B19013,B08301"
    params = {"table_ids": tables, "geo_ids": f"140|05000US{state}{county}"}
    try:
        r = await client.get(CENSUS_REPORTER_URL, params=params)
        if r.status_code != 200 or not r.text.lstrip().startswith("{"):
            return None
        data = r.json().get("data", {})
    except (httpx.HTTPError, ValueError):
        return None
    out: dict[str, dict[str, Any]] = {}
    for cr_geo, rec in data.items():
        geoid = cr_geo.split("US")[-1]  # 14000US48113000100 -> 48113000100
        b01 = rec.get("B01001", {}).get("estimate", {})
        age = sum(
            _num(b01.get(f"B01001{n:03d}")) or 0
            for n in list(range(7, 11)) + list(range(31, 35))
        )
        out[geoid] = {
            "population": _num(rec.get("B01001", {}).get("estimate", {}).get("B01001001")),
            "households": _num(rec.get("B11001", {}).get("estimate", {}).get("B11001001")),
            "median_income": _num(rec.get("B19013", {}).get("estimate", {}).get("B19013001")),
            "commuters": _num(rec.get("B08301", {}).get("estimate", {}).get("B08301001")),
            "age_18_34": age,
        }
    return out or None


async def get_tract_demographics(state_fips: str, county_fips: str) -> dict[str, dict[str, Any]]:
    """Tract-level ACS5 demographics keyed by 11-digit GEOID, cached per county.
    Uses the official Census API when CENSUS_API_KEY is valid, else the keyless
    Census Reporter mirror."""
    state = str(state_fips).zfill(2)
    county = str(county_fips).zfill(3)
    ck = (state, county)
    if ck in _DEMO_CACHE:
        return _DEMO_CACHE[ck]
    key = os.getenv("CENSUS_API_KEY")
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        data = None
        if key:
            data = await _fetch_acs_official(client, state, county, key)
        if data is None:
            data = await _fetch_census_reporter(client, state, county)
    if data is None:
        raise RuntimeError(
            f"Could not fetch ACS demographics for state {state} county {county} "
            "(Census API key invalid/missing and Census Reporter fallback failed)."
        )
    _DEMO_CACHE[ck] = data
    return data


# ─── Isochrones (OpenRouteService) ───────────────────────────────────────────


async def compute_isochrone(
    lat: float, lng: float, minutes: float, profile: str = "driving-car"
) -> dict[str, Any] | None:
    """Single drive-time isochrone (GeoJSON Polygon geometry) for a location."""
    rings = await get_trade_area(lat, lng, thresholds=[minutes], profile=profile)
    return rings[0]["geometry"] if rings else None


async def get_trade_area(
    lat: float, lng: float, thresholds: list[float] | None = None, profile: str = "driving-car"
) -> list[dict[str, Any]]:
    """Concentric drive-time isochrones. Returns one entry per threshold:
    {minutes, geometry (GeoJSON Polygon)}."""
    thresholds = thresholds or [5, 10, 15]
    key = os.getenv("ORS_API_KEY")
    if not key:
        raise RuntimeError("ORS_API_KEY not set")
    url = f"https://api.openrouteservice.org/v2/isochrones/{profile}"
    body = {
        "locations": [[lng, lat]],
        "range": [int(m * 60) for m in thresholds],
        "range_type": "time",
    }
    async with httpx.AsyncClient(timeout=40.0) as client:
        r = await client.post(
            url, headers={"Authorization": key, "Content-Type": "application/json"}, json=body
        )
    if r.status_code != 200:
        raise RuntimeError(f"ORS isochrone failed ({r.status_code}): {r.text[:200]}")
    feats = r.json().get("features", [])
    out = []
    for f in feats:
        secs = f.get("properties", {}).get("value")
        out.append({"minutes": round(secs / 60) if secs else None, "geometry": f["geometry"]})
    out.sort(key=lambda x: x["minutes"] or 0)
    return out


# ─── Isochrone ↔ demographics / POI / jobs intersection ──────────────────────

_INTERSECT_SQL = """
WITH iso AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($1), 4326) AS g),
     jobs AS (SELECT tract_geoid, SUM(c000) AS c000 FROM trade_area_lehd_dallas
              GROUP BY tract_geoid)
SELECT t.geoid,
       ST_Area(ST_Intersection(t.geometry, iso.g)::geography)
         / NULLIF(ST_Area(t.geometry::geography), 0) AS frac,
       COALESCE(j.c000, 0) AS tract_jobs
FROM trade_area_census_tracts_dallas t
CROSS JOIN iso
LEFT JOIN jobs j ON j.tract_geoid = t.geoid
WHERE ST_Intersects(t.geometry, iso.g)
"""

_POI_SQL = """
WITH iso AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($1), 4326) AS g)
SELECT split_part(p.category, ':', 1) AS grp, COUNT(*) AS n
FROM trade_area_pois_dallas p, iso
WHERE ST_Within(p.geometry, iso.g)
GROUP BY grp
"""


async def profile_ring(
    pool: asyncpg.Pool, geometry: dict[str, Any], demographics: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    import json

    gj = json.dumps(geometry)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_INTERSECT_SQL, gj)
        poi_rows = await conn.fetch(_POI_SQL, gj)

    pop = hh = jobs = 0.0
    inc_num = inc_den = 0.0  # population-weighted median income
    age = 0.0
    for r in rows:
        frac = min(1.0, float(r["frac"] or 0.0))
        d = demographics.get(r["geoid"])
        jobs += float(r["tract_jobs"] or 0) * frac
        if not d:
            continue
        p = (d["population"] or 0) * frac
        pop += p
        hh += (d["households"] or 0) * frac
        age += (d["age_18_34"] or 0) * frac
        if d["median_income"] is not None and p > 0:
            inc_num += d["median_income"] * p
            inc_den += p
    poi_by_group = {r["grp"]: int(r["n"]) for r in poi_rows}
    return {
        "population": round(pop),
        "households": round(hh),
        "median_household_income": round(inc_num / inc_den) if inc_den > 0 else None,
        "age_18_34": round(age),
        "daytime_jobs": round(jobs),
        "poi_count": sum(poi_by_group.values()),
        "poi_by_category": poi_by_group,
        "tracts_intersected": len(rows),
    }


# ─── Score Mode (Week 1: raw profile) ────────────────────────────────────────

# Dallas County — the pre-loaded geography for Week 1.
DALLAS_STATE, DALLAS_COUNTY = "48", "113"
METHODOLOGY_NOTE = (
    "Drive-time trade areas (OpenRouteService isochrones) intersected with Census "
    "ACS5 tract demographics (area-weighted), LEHD workplace jobs (daytime "
    "population), and OSM/Overture POIs. Week 1 returns the raw profile; composite "
    "scoring and competitive analysis follow in Week 2."
)


async def score_trade_area(
    pool: asyncpg.Pool,
    *,
    latitude: float,
    longitude: float,
    address: str | None = None,
    resolved_address: str | None = None,
    thresholds: list[float] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or [5, 10, 15]
    demographics = await get_tract_demographics(DALLAS_STATE, DALLAS_COUNTY)
    rings = await get_trade_area(latitude, longitude, thresholds)
    profiles = []
    for ring in rings:
        prof = await profile_ring(pool, ring["geometry"], demographics)
        profiles.append({"drive_time_minutes": ring["minutes"], **prof})
    return {
        "query": {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "resolved_address": resolved_address,
        },
        "geography": "Dallas County, TX",
        "trade_area_rings": profiles,
        "natural_language_summary": _summary(profiles, resolved_address or address),
        "methodology_note": METHODOLOGY_NOTE,
    }


def _summary(profiles: list[dict[str, Any]], label: str | None) -> str:
    if not profiles:
        return "No trade-area profile could be computed for this location."
    outer = profiles[-1]
    loc = f" around {label}" if label else ""
    inc = outer["median_household_income"]
    return (
        f"Within a {outer['drive_time_minutes']}-minute drive{loc}, the trade area "
        f"contains ~{outer['population']:,} residents in ~{outer['households']:,} "
        f"households"
        + (f" (median income ${inc:,})" if inc else "")
        + f", ~{outer['daytime_jobs']:,} daytime jobs, and {outer['poi_count']:,} "
        f"points of interest."
    )


# ─── Methodology ─────────────────────────────────────────────────────────────


def methodology_doc() -> dict[str, Any]:
    return {
        "summary": METHODOLOGY_NOTE,
        "pipeline": [
            "Geocode (if address) → point",
            "OpenRouteService drive-time isochrones at 5/10/15 minutes",
            "Area-weighted intersection with Census ACS5 tract demographics",
            "LEHD LODES workplace jobs aggregated per tract (daytime population)",
            "POI counts within each isochrone (ST_Within)",
        ],
        "data_sources": [
            {"name": "Census ACS 5-year (2022)", "use": "Resident demographics",
             "access": "on-demand api.census.gov (key) with Census Reporter fallback"},
            {"name": "OpenRouteService", "use": "Drive-time isochrones"},
            {"name": "Census TIGERweb", "use": "Tract boundaries",
             "table": "trade_area_census_tracts_dallas"},
            {"name": "LEHD LODES8 WAC (2021)", "use": "Daytime jobs",
             "table": "trade_area_lehd_dallas"},
            {"name": "OpenStreetMap / Overture", "use": "POIs",
             "table": "trade_area_pois_dallas"},
        ],
        "acs_variables": {**ACS_VARS, "age_18_34": "B01001_007E-010E + 031E-034E"},
        "pre_loaded_geography": "Dallas County, TX (FIPS 48113)",
        "known_limitations": [
            "Demographics are area-weighted by tract overlap, not dasymetrically "
            "redistributed within tracts.",
            "Daytime jobs are aggregated to tract level (LEHD block geocodes → tract), "
            "then area-weighted like residents.",
            "POIs are OSM-derived (Overpass), not the full Overture Places corpus.",
            "Isochrones use default OpenRouteService traffic-free drive times.",
            "Pre-loaded POIs/jobs cover Dallas County only; demographics + isochrones "
            "work nationally.",
        ],
        "note": "Week 1 returns the raw trade-area profile; composite scoring and "
        "competitive analysis arrive in Week 2.",
    }
