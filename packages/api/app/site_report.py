"""Site suitability report.

Builds a composite score + per-factor breakdown + nearby-feature list for an
arbitrary point. Factors:
  - flood_risk       inverse of FEMA SFHA containment
  - demographics     census tract presence (proxy for served area)
  - transit_access   transit stop count within the analysis radius
  - environmental    EPA facilities + CalFire fire-hazard containment
  - competition      Overture POI density within the radius
"""

from __future__ import annotations

from typing import Any

import asyncpg
import httpx

MILE_IN_METERS = 1609
NOMINATIM_UA = "Heavi/0.1 (site-report)"


async def geocode(address: str) -> tuple[float, float, str] | None:
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": NOMINATIM_UA}) as c:
        r = await c.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "addressdetails": 0,
                "countrycodes": "us",
            },
        )
        data = r.json()
    if not data:
        return None
    return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]


async def reverse_geocode(lat: float, lng: float) -> str | None:
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": NOMINATIM_UA}) as c:
        r = await c.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 18},
        )
    if r.status_code != 200:
        return None
    return r.json().get("display_name")


async def site_report(
    pool: asyncpg.Pool,
    lat: float,
    lng: float,
    radius_m: int = MILE_IN_METERS,
    address: str | None = None,
) -> dict[str, Any]:
    point = f"ST_SetSRID(ST_MakePoint({lng}, {lat}), 4326)"
    buf = f"ST_Transform(ST_Buffer(ST_Transform({point}, 3857), {radius_m}), 4326)"

    async with pool.acquire() as conn:
        in_sfha = await conn.fetchval(
            f"""SELECT EXISTS(
                  SELECT 1 FROM catalog_fema_flood
                  WHERE sfha_tf = 'T' AND ST_Contains(geometry, {point}))"""
        )
        flood_risk = 0 if in_sfha else 100

        transit_count = int(
            await conn.fetchval(
                f"SELECT COUNT(*) FROM catalog_transit_stops "
                f"WHERE ST_Intersects(geometry, {buf})"
            )
        )
        transit_access = min(100, round((transit_count / 5) * 100))

        tract = await conn.fetchrow(
            f"""SELECT to_jsonb(t) - 'geometry' AS props
                FROM catalog_census_demographics t
                WHERE ST_Contains(t.geometry, {point}) LIMIT 1"""
        )
        demographics = 75 if tract else 40

        epa_count = int(
            await conn.fetchval(
                f"SELECT COUNT(*) FROM catalog_epa_facilities "
                f"WHERE ST_Intersects(geometry, {buf})"
            )
        )
        in_fire_hazard = await conn.fetchval(
            f"""SELECT EXISTS(
                  SELECT 1 FROM catalog_calfire_fhsz
                  WHERE ST_Contains(geometry, {point}))"""
        )
        environmental = max(0, 100 - epa_count * 20 - (40 if in_fire_hazard else 0))

        poi_count = int(
            await conn.fetchval(
                f"SELECT COUNT(*) FROM catalog_overture_pois "
                f"WHERE ST_Intersects(geometry, {buf})"
            )
        )
        # Curve: none = dead zone (40), 30 = sweet spot (80), saturation penalty above.
        if poi_count == 0:
            competition = 40
        elif poi_count <= 30:
            competition = round(40 + (poi_count / 30) * 40)
        else:
            competition = max(20, 80 - round((poi_count - 30) / 3))

        factors = {
            "flood_risk": flood_risk,
            "demographics": demographics,
            "transit_access": transit_access,
            "environmental": environmental,
            "competition": competition,
        }
        composite = round(sum(factors.values()) / len(factors))

        async def nearest(table: str, n: int = 3) -> list[dict[str, Any]]:
            rows = await conn.fetch(
                f"""SELECT to_jsonb(t) - 'geometry' AS props,
                           ST_Distance(ST_Transform(t.geometry, 3857),
                                       ST_Transform({point}, 3857)) AS dist_m,
                           ST_X(t.geometry) AS lng, ST_Y(t.geometry) AS lat
                    FROM {table} t
                    WHERE ST_Intersects(t.geometry, {buf})
                    ORDER BY t.geometry <-> {point}
                    LIMIT {n}"""
            )
            return [
                {
                    "properties": r["props"],
                    "distance_m": round(r["dist_m"] or 0),
                    "longitude": r["lng"],
                    "latitude": r["lat"],
                }
                for r in rows
            ]

        nearby = {
            "schools": await nearest("catalog_nces_schools"),
            "transit_stops": await nearest("catalog_transit_stops"),
            "epa_facilities": await nearest("catalog_epa_facilities"),
        }

    return {
        "address": address,
        "location": {"latitude": lat, "longitude": lng},
        "radius_meters": radius_m,
        "composite_score": composite,
        "factors": factors,
        "counts": {
            "transit_stops": transit_count,
            "epa_facilities": epa_count,
            "pois": poi_count,
            "in_flood_zone": bool(in_sfha),
            "in_fire_hazard": bool(in_fire_hazard),
            "in_census_tract": tract is not None,
        },
        "nearby": nearby,
    }
