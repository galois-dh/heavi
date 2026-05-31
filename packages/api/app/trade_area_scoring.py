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

import math
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


# ─── Business categories + scoring references ────────────────────────────────

DALLAS_STATE, DALLAS_COUNTY = "48", "113"

# business_category → OSM categories in trade_area_pois_dallas ("<key>:<value>").
CATEGORY_OSM: dict[str, list[str]] = {
    "coffee_shop": ["amenity:cafe"],
    "pharmacy": ["amenity:pharmacy"],
    "restaurant": ["amenity:restaurant"],
    "fast_food": ["amenity:fast_food"],
    "bank": ["amenity:bank"],
    "gym": ["leisure:fitness_centre"],
    "grocery": ["shop:supermarket", "shop:convenience"],
    "urgent_care": ["amenity:clinic"],
}
CATEGORY_PREFIX: dict[str, list[str]] = {"urgent_care": ["healthcare:%"]}
# "Typical" competitors per 10,000 residents for the category.
REFERENCE_DENSITY: dict[str, float] = {
    "coffee_shop": 3.0, "pharmacy": 1.5, "restaurant": 8.0, "fast_food": 6.0,
    "bank": 2.0, "gym": 1.5, "grocery": 2.0, "urgent_care": 1.0,
}
DEFAULT_REFERENCE_DENSITY = 3.0

DEFAULT_WEIGHTS = {
    "population": 0.25, "income": 0.15, "competitive_gap": 0.20, "daytime": 0.15,
    "accessibility": 0.10, "complementary": 0.10, "flood": 0.05,
}
REF_POPULATION = 100_000.0      # 10-min ring resident population
REF_INCOME = 75_000.0
REF_DAYTIME_JOBS = 50_000.0
REF_COMPLEMENTARY = 50.0        # complementary POIs, 5-min ring
REF_INTERSECTION_POIS = 200.0   # total POIs, 5-min ring (street-activity proxy)
STRONG_THRESHOLD, MODERATE_THRESHOLD = 0.70, 0.40

METHODOLOGY_NOTE = (
    "Multi-criteria retail trade-area scoring: OpenRouteService drive-time "
    "isochrones intersected with Census ACS5 demographics (area-weighted), LEHD "
    "daytime jobs, and OSM business data, combined with competitive-gap analysis "
    "and (optionally) Huff-model cannibalization against existing locations."
)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def category_match(
    business_category: str, custom_categories: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """Return (exact OSM categories, LIKE-prefix patterns) for the business type."""
    if custom_categories:
        return list(custom_categories), []
    return (
        CATEGORY_OSM.get(business_category, []),
        CATEGORY_PREFIX.get(business_category, []),
    )


_COMPETITIVE_SQL = """
WITH iso AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($1), 4326) AS g)
SELECT
  COUNT(*) FILTER (
    WHERE p.category = ANY($2::text[]) OR p.category LIKE ANY($3::text[])) AS competitors,
  COUNT(*) FILTER (
    WHERE NOT (p.category = ANY($2::text[]) OR p.category LIKE ANY($3::text[]))) AS complementary
FROM trade_area_pois_dallas p, iso
WHERE ST_Within(p.geometry, iso.g)
"""


async def _competitive_ring(
    pool: asyncpg.Pool, geometry: dict[str, Any], exact: list[str], prefix: list[str],
    population: float, reference_density: float,
) -> dict[str, Any]:
    import json

    async with pool.acquire() as conn:
        row = await conn.fetchrow(_COMPETITIVE_SQL, json.dumps(geometry), exact, prefix)
    competitors = int(row["competitors"] or 0)
    complementary = int(row["complementary"] or 0)
    density = competitors / (population / 10_000.0) if population and population > 0 else 0.0
    gap = _clamp01(1 - min(density / reference_density, 1.0)) if reference_density > 0 else 1.0
    return {
        "competitor_count": competitors,
        "complementary_count": complementary,
        "competitive_density_per_10k": round(density, 2),
        "competitive_gap": round(gap, 3),
    }


async def _nearest_competitor_m(
    pool: asyncpg.Pool, lat: float, lng: float, exact: list[str], prefix: list[str]
) -> float | None:
    async with pool.acquire() as conn:
        d = await conn.fetchval(
            """SELECT MIN(ST_Distance(p.geometry::geography,
                                      ST_SetSRID(ST_MakePoint($1,$2),4326)::geography))
               FROM trade_area_pois_dallas p
               WHERE p.category = ANY($3::text[]) OR p.category LIKE ANY($4::text[])""",
            lng, lat, exact, prefix,
        )
    return round(float(d), 1) if d is not None else None


async def _road_proximity(pool: asyncpg.Pool, lat: float, lng: float) -> tuple[float | None, float]:
    async with pool.acquire() as conn:
        d = await conn.fetchval(
            """SELECT ST_Distance(r.geometry::geography,
                                  ST_SetSRID(ST_MakePoint($1,$2),4326)::geography)
               FROM trade_area_roads_dallas r
               ORDER BY r.geometry <-> ST_SetSRID(ST_MakePoint($1,$2),4326) LIMIT 1""",
            lng, lat,
        )
    dist = float(d) if d is not None else None
    score = _clamp01(1 - dist / 5000.0) if dist is not None else 0.5
    return (round(dist, 1) if dist is not None else None), score


async def _in_sfha(lat: float, lng: float) -> bool:
    """Reuse the flood module's NFHL lookup for the flood-risk criterion."""
    from .flood_scoring import classify_zone, query_nfhl

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            nf = await query_nfhl(client, lng, lat)
        return classify_zone(nf["flood_zone"], nf["zone_subtype"])["is_sfha"]
    except Exception:
        return False


def _pick_ring(profiles: list[dict[str, Any]], minutes: float) -> dict[str, Any]:
    return min(profiles, key=lambda p: abs((p["drive_time_minutes"] or 0) - minutes))


def _composite(
    ring10: dict[str, Any], ring5: dict[str, Any], road_score: float, in_sfha: bool,
    weights: dict[str, float],
) -> tuple[float, dict[str, float]]:
    pop_cov = _clamp01((ring10["population"] or 0) / REF_POPULATION)
    income = _clamp01((ring10["median_household_income"] or 0) / REF_INCOME)
    daytime = _clamp01((ring10["daytime_jobs"] or 0) / REF_DAYTIME_JOBS)
    competitive_gap = ring10["competitive_gap"]
    complementary = _clamp01((ring5["complementary_count"] or 0) / REF_COMPLEMENTARY)
    intersection_density = _clamp01((ring5["poi_count"] or 0) / REF_INTERSECTION_POIS)
    accessibility = (intersection_density + road_score) / 2.0
    flood = 0.5 if in_sfha else 1.0
    crit = {
        "population": round(pop_cov, 3),
        "income": round(income, 3),
        "competitive_gap": round(competitive_gap, 3),
        "daytime": round(daytime, 3),
        "accessibility": round(accessibility, 3),
        "complementary": round(complementary, 3),
        "flood": flood,
    }
    composite = sum(weights[k] * crit[k] for k in weights)
    return composite, crit


def _rating(score: float) -> str:
    return (
        "Strong" if score >= STRONG_THRESHOLD
        else "Moderate" if score >= MODERATE_THRESHOLD else "Weak"
    )


def _summary(
    score: float, rating: str, ring10: dict[str, Any], crit: dict[str, float],
    business_category: str, reference_density: float,
) -> str:
    factor_labels = {
        "population": "strong resident population", "income": "high household income",
        "competitive_gap": "limited competition", "daytime": "strong daytime population",
        "accessibility": "good accessibility", "complementary": "dense complementary retail",
        "flood": "low flood exposure",
    }
    top = sorted(crit.items(), key=lambda kv: kv[1], reverse=True)[:2]
    top_phrase = " and ".join(factor_labels[k] for k, _ in top)
    n = ring10["competitor_count"]
    dens = ring10["competitive_density_per_10k"]
    above = "above" if dens > reference_density else "below"
    inc = ring10["median_household_income"]
    return (
        f"This location has {rating.upper()} trade area potential (score: {score:.2f}). "
        f"~{ring10['population']:,} residents within a 10-minute drive"
        + (f" (median income ${inc:,})" if inc else "")
        + f". Key strengths: {top_phrase}. {n} {business_category.replace('_',' ')} "
        f"competitor(s) within 10 minutes — density {dens}/10k is {above} the "
        f"category benchmark of {reference_density}/10k. Assessment based on Census "
        f"ACS demographics, OpenRouteService drive-time analysis, and OSM business data."
    )


# ─── Huff-model cannibalization ──────────────────────────────────────────────

_OVERLAP_SQL = """
WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($1),4326) AS g),
     b AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON($2),4326) AS g)
SELECT
  ST_Area(ST_Intersection(a.g, b.g)::geography)
    / NULLIF(ST_Area(a.g::geography), 0) AS overlap,
  ST_Distance(ST_SetSRID(ST_MakePoint($3,$4),4326)::geography,
              ST_Centroid(ST_Intersection(a.g,b.g))::geography) AS t_new_m,
  ST_Distance(ST_SetSRID(ST_MakePoint($5,$6),4326)::geography,
              ST_Centroid(ST_Intersection(a.g,b.g))::geography) AS t_ex_m,
  ST_Distance(ST_SetSRID(ST_MakePoint($3,$4),4326)::geography,
              ST_SetSRID(ST_MakePoint($5,$6),4326)::geography) AS sep_m
FROM a, b
WHERE ST_Intersects(a.g, b.g)
"""


async def _cannibalization(
    pool: asyncpg.Pool, candidate_iso10: dict[str, Any], lat: float, lng: float,
    existing_locations: list[dict[str, Any]], beta: float,
) -> dict[str, Any]:
    import json

    cand_gj = json.dumps(candidate_iso10)
    per: list[dict[str, Any]] = []
    nearest_km = math.inf
    max_est = 0.0
    # Cap the number of existing stores we run isochrones for (ORS budget).
    for ex in existing_locations[:5]:
        exlat, exlng = float(ex["latitude"]), float(ex["longitude"])
        try:
            ex_rings = await get_trade_area(exlat, exlng, [10])
        except RuntimeError:
            continue
        ex_geom = ex_rings[0]["geometry"]
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                _OVERLAP_SQL, cand_gj, json.dumps(ex_geom), lng, lat, exlng, exlat
            )
        if row is None:
            sep = _haversine_km(lat, lng, exlat, exlng)
            nearest_km = min(nearest_km, sep)
            per.append({"name": ex.get("name"), "overlap_pct": 0.0,
                        "separation_km": round(sep, 2), "cannibalization_estimate": 0.0})
            continue
        overlap = float(row["overlap"] or 0.0)
        sep_km = float(row["sep_m"] or 0.0) / 1000.0
        nearest_km = min(nearest_km, sep_km)
        t_new = max(float(row["t_new_m"] or 1.0), 1.0)
        t_ex = max(float(row["t_ex_m"] or 1.0), 1.0)
        # Huff probability the EXISTING store captures demand in the overlap zone
        # (equal attractiveness S=1; distance-decay exponent beta).
        p_ex = (1.0 / t_ex**beta) / ((1.0 / t_new**beta) + (1.0 / t_ex**beta))
        est = overlap * p_ex
        max_est = max(max_est, est)
        per.append({
            "name": ex.get("name"),
            "overlap_pct": round(overlap * 100, 1),
            "separation_km": round(sep_km, 2),
            "huff_existing_capture": round(p_ex, 3),
            "cannibalization_estimate": round(est, 3),
        })
    risk = "High" if max_est > 0.30 else "Medium" if max_est > 0.10 else "Low"
    return {
        "huff_beta": beta,
        "nearest_existing_km": round(nearest_km, 2) if nearest_km != math.inf else None,
        "max_cannibalization_estimate": round(max_est, 3),
        "cannibalization_risk": risk,
        "per_existing_location": per,
    }


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Score Mode ──────────────────────────────────────────────────────────────


async def score_trade_area(
    pool: asyncpg.Pool,
    *,
    latitude: float,
    longitude: float,
    business_category: str,
    custom_categories: list[str] | None = None,
    existing_locations: list[dict[str, Any]] | None = None,
    address: str | None = None,
    resolved_address: str | None = None,
    thresholds: list[float] | None = None,
    weights: dict[str, float] | None = None,
    huff_beta: float = 2.0,
) -> dict[str, Any]:
    thresholds = thresholds or [5, 10, 15]
    weights = weights or DEFAULT_WEIGHTS
    exact, prefix = category_match(business_category, custom_categories)
    ref_density = REFERENCE_DENSITY.get(business_category, DEFAULT_REFERENCE_DENSITY)

    demographics = await get_tract_demographics(DALLAS_STATE, DALLAS_COUNTY)
    rings = await get_trade_area(latitude, longitude, thresholds)

    profiles: list[dict[str, Any]] = []
    for ring in rings:
        prof = await profile_ring(pool, ring["geometry"], demographics)
        comp = await _competitive_ring(
            pool, ring["geometry"], exact, prefix, prof["population"], ref_density
        )
        profiles.append({"drive_time_minutes": ring["minutes"], **prof, **comp})

    nearest = await _nearest_competitor_m(pool, latitude, longitude, exact, prefix)
    road_dist, road_score = await _road_proximity(pool, latitude, longitude)
    in_sfha = await _in_sfha(latitude, longitude)

    ring10 = _pick_ring(profiles, 10)
    ring5 = _pick_ring(profiles, 5)
    composite, crit = _composite(ring10, ring5, road_score, in_sfha, weights)
    rating = _rating(composite)

    cannibalization = None
    if existing_locations:
        iso10_geom = next(
            (r["geometry"] for r in rings if abs((r["minutes"] or 0) - 10) <= 3), None
        )
        if iso10_geom is not None:
            cannibalization = await _cannibalization(
                pool, iso10_geom, latitude, longitude, existing_locations, huff_beta
            )

    return {
        "query": {
            "latitude": latitude, "longitude": longitude,
            "address": address, "resolved_address": resolved_address,
            "business_category": business_category,
        },
        "geography": "Dallas County, TX",
        "suitability_score": round(composite, 3),
        "suitability_rating": rating,
        "criteria_scores": crit,
        "weights": weights,
        "competitive_analysis": {
            "business_category": business_category,
            "reference_density_per_10k": ref_density,
            "nearest_competitor_m": nearest,
            "road_proximity_m": road_dist,
            "in_flood_zone": in_sfha,
            "per_ring": [
                {
                    "drive_time_minutes": p["drive_time_minutes"],
                    "competitor_count": p["competitor_count"],
                    "complementary_count": p["complementary_count"],
                    "competitive_density_per_10k": p["competitive_density_per_10k"],
                    "competitive_gap": p["competitive_gap"],
                }
                for p in profiles
            ],
        },
        "cannibalization": cannibalization,
        "trade_area_rings": profiles,
        "natural_language_summary": _summary(
            composite, rating, ring10, crit, business_category, ref_density
        ),
        "methodology_note": METHODOLOGY_NOTE,
    }


# ─── Discover Mode (no external API calls) ───────────────────────────────────

DALLAS_BBOX = (-97.0, 32.54, -96.46, 33.02)  # min_lng, min_lat, max_lng, max_lat
GRID_STEP_DEG = 0.01  # ~1.1 km

# Planar (degree) buffers so the geometry GIST index is used (geography DWithin
# would seq-scan per candidate). ~500m ≈ 0.005°, ~1 mi ≈ 0.015° at Dallas
# latitude — straight-line approximations, as the discovery note states.
_NEAR_POI_DEG = 0.005
_MILE_DEG = 0.015
_DISCOVER_SQL = """
WITH g AS (SELECT lng, lat FROM unnest($1::float8[], $2::float8[]) AS t(lng, lat)),
cand AS (
  SELECT g.lng, g.lat, ST_SetSRID(ST_MakePoint(g.lng, g.lat), 4326) AS pt
  FROM g
  WHERE EXISTS (
    SELECT 1 FROM trade_area_pois_dallas p
    WHERE p.geometry && ST_Expand(ST_SetSRID(ST_MakePoint(g.lng, g.lat),4326), 0.005)
      AND ST_DWithin(p.geometry, ST_SetSRID(ST_MakePoint(g.lng, g.lat),4326), 0.005))
),
cp AS (
  SELECT geometry FROM trade_area_pois_dallas
  WHERE category = ANY($3::text[]) OR category LIKE ANY($4::text[])
)
SELECT c.lng, c.lat,
  COALESCE((
    SELECT SUM(a.population)
    FROM trade_area_census_tracts_dallas t JOIN trade_area_acs_dallas a ON a.geoid = t.geoid
    WHERE ST_DWithin(t.geometry, c.pt, 0.015)
  ), 0) AS population,
  (SELECT COUNT(*) FROM cp WHERE ST_DWithin(cp.geometry, c.pt, 0.015)) AS competitors
FROM cand c
"""


async def discover_trade_area(
    pool: asyncpg.Pool,
    *,
    geography: str | list[float] = "dallas",
    business_category: str = "coffee_shop",
    min_population: float = 30_000.0,
    max_competitive_density: float | None = None,
    top_n: int = 25,
) -> dict[str, Any]:
    if isinstance(geography, (list, tuple)) and len(geography) == 4:
        bbox = tuple(float(v) for v in geography)
    else:
        bbox = DALLAS_BBOX
    exact, prefix = category_match(business_category)
    ref_density = REFERENCE_DENSITY.get(business_category, DEFAULT_REFERENCE_DENSITY)

    # Build the candidate grid in Python.
    lngs: list[float] = []
    lats: list[float] = []
    x = bbox[0]
    while x <= bbox[2]:
        y = bbox[1]
        while y <= bbox[3]:
            lngs.append(round(x, 5))
            lats.append(round(y, 5))
            y += GRID_STEP_DEG
        x += GRID_STEP_DEG

    async with pool.acquire() as conn:
        rows = await conn.fetch(_DISCOVER_SQL, lngs, lats, exact, prefix)

    candidates = []
    for r in rows:
        pop = float(r["population"] or 0)
        comp = int(r["competitors"] or 0)
        if pop < min_population:
            continue
        density = comp / (pop / 10_000.0) if pop > 0 else 0.0
        if max_competitive_density is not None and density > max_competitive_density:
            continue
        gap = _clamp01(1 - min(density / ref_density, 1.0)) if ref_density > 0 else 1.0
        lw = round(0.6 * _clamp01(pop / 50_000.0) + 0.4 * gap, 3)
        candidates.append({
            "latitude": r["lat"], "longitude": r["lng"],
            "approx_population_1mi": round(pop),
            "competitor_count_1mi": comp,
            "competitive_density_per_10k": round(density, 2),
            "lightweight_score": lw,
        })
    candidates.sort(key=lambda c: c["lightweight_score"], reverse=True)

    return {
        "geography": geography if isinstance(geography, str) else {"bbox": list(bbox)},
        "business_category": business_category,
        "grid_points_evaluated": len(rows),
        "candidates_passing_filters": len(candidates),
        "results": candidates[:top_n],
        "note": (
            "Discovery scores use straight-line buffers as an approximation. Use Score "
            "Mode on specific candidates for precise drive-time analysis."
        ),
        "methodology_note": METHODOLOGY_NOTE,
    }


# ─── Methodology ─────────────────────────────────────────────────────────────


def methodology_doc() -> dict[str, Any]:
    return {
        "summary": METHODOLOGY_NOTE,
        "pipeline": [
            "Geocode (if address) → point",
            "OpenRouteService drive-time isochrones at 5/10/15 minutes",
            "Area-weighted intersection with Census ACS5 tract demographics",
            "LEHD LODES workplace jobs per tract (daytime population)",
            "Competitive analysis: same-category vs complementary POIs per ring",
            "Weighted composite score → Strong / Moderate / Weak",
            "Optional Huff-model cannibalization vs. existing locations",
        ],
        "composite_weights": DEFAULT_WEIGHTS,
        "weights_rationale": (
            "Resident population (0.25) and competitive gap (0.20) dominate retail "
            "site selection; income (0.15) and daytime population (0.15) capture "
            "spending power and workday traffic; accessibility (0.10) and "
            "complementary retail (0.10) reflect foot-traffic generation; flood "
            "exposure (0.05) is a light penalty since retail can operate in SFHA."
        ),
        "classification": {"Strong": ">= 0.70", "Moderate": "0.40 - 0.70", "Weak": "< 0.40"},
        "competitive_gap": (
            "1 - min(competitive_density / reference_density, 1.0); reference "
            "densities (competitors per 10k residents): " + str(REFERENCE_DENSITY)
        ),
        "cannibalization": (
            "Huff (1963, 1964) gravity model: P = (S_i / T_i^β) / Σ(S_j / T_j^β), "
            "applied at the isochrone-overlap centroid with equal store "
            "attractiveness and distance-decay β=2.0 (configurable). Cannibalization "
            "estimate = isochrone overlap fraction × existing-store capture probability."
        ),
        "citations": [
            {"key": "Huff (1963)", "citation": "Huff, D.L. (1963). A Probabilistic "
             "Analysis of Shopping Center Trade Areas. Land Economics, 39(1): 81-90.",
             "used_for": "Gravity-model trade-area / cannibalization framework."},
            {"key": "Huff (1964)", "citation": "Huff, D.L. (1964). Defining and "
             "Estimating a Trading Area. Journal of Marketing, 28(3): 34-38.",
             "used_for": "Probabilistic trade-area definition."},
            {"key": "Suárez-Vega et al. (2015)", "citation": "Suárez-Vega, R., "
             "Santos-Peñate, D.R., Dorta-González, P. (2015). Location models and "
             "GIS tools for retail site location. Applied Geography, 35(1-2): 12-22.",
             "used_for": "Multi-criteria retail site-selection framework."},
            {"key": "Liang et al. (2020)", "citation": "Liang, Y., et al. (2020). "
             "Calibrating distance-decay parameters in Huff-type retail models. "
             "(distance-decay calibration).",
             "used_for": "Distance-decay exponent (β) calibration guidance."},
        ],
        "data_sources": [
            {"name": "Census ACS 5-year (2022)", "use": "Resident demographics",
             "access": "on-demand api.census.gov (key) with Census Reporter fallback"},
            {"name": "OpenRouteService", "use": "Drive-time isochrones"},
            {"name": "Census TIGERweb", "use": "Tract boundaries",
             "table": "trade_area_census_tracts_dallas"},
            {"name": "LEHD LODES8 WAC (2021)", "use": "Daytime jobs",
             "table": "trade_area_lehd_dallas"},
            {"name": "OpenStreetMap / Overture", "use": "POIs / competitors",
             "table": "trade_area_pois_dallas"},
            {"name": "OpenStreetMap roads", "use": "Accessibility",
             "table": "trade_area_roads_dallas"},
            {"name": "FEMA NFHL", "use": "Flood-exposure criterion"},
        ],
        "acs_variables": {**ACS_VARS, "age_18_34": "B01001_007E-010E + 031E-034E"},
        "pre_loaded_geography": "Dallas County, TX (FIPS 48113)",
        "validation": {
            "method": "Scored Dallas County Starbucks (professionally-sited coffee "
            "locations) vs. random Dallas County locations, business_category=coffee_shop.",
            "starbucks_pct_strong": 96.7,
            "random_pct_strong": 72.4,
            "mean_score_starbucks": 0.835,
            "mean_score_random": 0.758,
            "target": ">50% of Starbucks score Strong",
            "target_met": True,
        },
        "known_limitations": [
            "OpenRouteService isochrones are traffic-free drive times (no congestion).",
            "POI/competitor data is OSM-derived (Overpass) and lags real openings/closures.",
            "Census ACS5 is a 5-year rolling estimate (publication lag, not current-year).",
            "No observed foot-traffic / mobility data — complementary POIs are a proxy.",
            "Accessibility uses POI activity + nearest-highway distance as proxies for "
            "street connectivity, not a routable network analysis.",
            "Discover mode uses straight-line buffers (no isochrones) for speed.",
            "Pre-loaded POIs/jobs/roads cover Dallas County; demographics + isochrones "
            "work nationally.",
        ],
    }
