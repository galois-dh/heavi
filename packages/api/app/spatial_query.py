"""NL-to-SQL spatial query pipeline.

Mirrors the MCP server's spatial-query.ts logic:
1. Discover schema from PostGIS
2. Build system prompt with full table schemas
3. Call Claude to generate SQL
4. Execute with result-size guardrails
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass

import anthropic
import asyncpg
import httpx

GEOJSON_THRESHOLD = 1000

# Hardcoded Sonoma County city bounding boxes (min_lng, min_lat, max_lng,
# max_lat) in EPSG:4326. Checked before geocoding so the common cities resolve
# deterministically (no network round-trip, exact coordinates) — geocoding
# below handles anything not in this list.
SONOMA_CITY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "santa rosa": (-122.78, 38.40, -122.62, 38.50),
    "petaluma": (-122.68, 38.21, -122.58, 38.28),
    "sonoma": (-122.48, 38.28, -122.43, 38.32),
    "windsor": (-122.84, 38.52, -122.78, 38.56),
    "healdsburg": (-122.88, 38.60, -122.84, 38.64),
    "cloverdale": (-123.02, 38.78, -122.98, 38.82),
    "rohnert park": (-122.72, 38.33, -122.68, 38.36),
    "cotati": (-122.74, 38.32, -122.72, 38.34),
    "sebastopol": (-122.84, 38.39, -122.82, 38.41),
}

# Candidate place name after a locator preposition, e.g. "in Santa Rosa",
# "near Geyserville". Captures up to four Title-Case-ish tokens.
_PLACE_RE = re.compile(
    r"\b(?:in|near|around|within|at|inside)\s+"
    r"([A-Z][A-Za-z.\-']*(?:\s+[A-Z][A-Za-z.\-']*){0,3})"
)


@dataclass
class PlaceContext:
    name: str
    bbox: tuple[float, float, float, float]  # min_lng, min_lat, max_lng, max_lat


@dataclass
class ColumnInfo:
    column_name: str
    udt_name: str


@dataclass
class TableSchema:
    table_name: str
    geom_column: str
    geom_type: str
    srid: int
    row_count: int
    columns: list[ColumnInfo]


async def discover_schema(pool: asyncpg.Pool) -> list[TableSchema]:
    async with pool.acquire() as conn:
        geom_rows = await conn.fetch(
            # Expose both the catalog_* layers (Alameda reference data) and the
            # wildfire_* layers (Sonoma DINS / FRAP / NSI / footprints) so chat
            # queries can target either region. catalog_layers is the metadata
            # table and is excluded by name.
            """SELECT f_table_name AS table_name, f_geometry_column AS geom_column,
                      type AS geom_type, srid
               FROM geometry_columns
               WHERE (f_table_name LIKE 'catalog_%' OR f_table_name LIKE 'wildfire_%')
                 AND f_table_name != 'catalog_layers'
               ORDER BY f_table_name"""
        )

        tables: list[TableSchema] = []
        for g in geom_rows:
            cols = await conn.fetch(
                """SELECT column_name, udt_name
                   FROM information_schema.columns
                   WHERE table_name = $1
                   ORDER BY ordinal_position""",
                g["table_name"],
            )
            cnt = await conn.fetchval(
                "SELECT reltuples::bigint FROM pg_class WHERE relname = $1",
                g["table_name"],
            )
            tables.append(
                TableSchema(
                    table_name=g["table_name"],
                    geom_column=g["geom_column"],
                    geom_type=g["geom_type"],
                    srid=g["srid"],
                    row_count=int(cnt or 0),
                    columns=[ColumnInfo(c["column_name"], c["udt_name"]) for c in cols],
                )
            )
    return tables


# ─── Place-name resolution (hardcoded cities → geocoding fallback) ────────


def _hardcoded_place(question: str) -> PlaceContext | None:
    """Match a known Sonoma city name in the question. Longest names first so
    'rohnert park' wins over a bare token, and skip '<city> county' (the
    region, not the city)."""
    q = question.lower()
    for name in sorted(SONOMA_CITY_BBOX, key=len, reverse=True):
        idx = q.find(name)
        if idx == -1:
            continue
        after = q[idx + len(name):].lstrip()
        if after.startswith("county"):
            continue
        return PlaceContext(name=name.title(), bbox=SONOMA_CITY_BBOX[name])
    return None


async def _mapbox_bbox(
    client: httpx.AsyncClient, place: str, token: str
) -> tuple[float, float, float, float] | None:
    url = (
        "https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{urllib.parse.quote(place)}.json"
    )
    try:
        r = await client.get(
            url,
            params={
                "access_token": token,
                "limit": 1,
                "country": "us",
                "types": "place,locality,region,district,neighborhood",
            },
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        feats = r.json().get("features") or []
    except ValueError:
        return None
    if not feats:
        return None
    f = feats[0]
    bbox = f.get("bbox")
    if bbox and len(bbox) == 4:
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    center = f.get("center")
    if center and len(center) == 2:
        lng, lat = float(center[0]), float(center[1])
        d = 0.05  # ~5.5 km half-box when no bbox is supplied
        return (lng - d, lat - d, lng + d, lat + d)
    return None


async def _nominatim_bbox(
    client: httpx.AsyncClient, place: str
) -> tuple[float, float, float, float] | None:
    try:
        r = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": place, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": "Heavi/0.1 (spatial-query)"},
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    if not data:
        return None
    # Nominatim boundingbox = [min_lat, max_lat, min_lng, max_lng] (strings).
    bb = data[0].get("boundingbox")
    if bb and len(bb) == 4:
        min_lat, max_lat, min_lng, max_lng = (float(x) for x in bb)
        return (min_lng, min_lat, max_lng, max_lat)
    return None


async def resolve_place_context(question: str) -> PlaceContext | None:
    """Resolve a place name from the question to a bounding box.

    Order: hardcoded Sonoma cities first (deterministic, no network), then
    geocode an extracted place name via Mapbox (if MAPBOX_TOKEN set) or
    Nominatim. Returns None when no place is detected or geocoding fails —
    the caller still injects the no-POI-join rule, just without a bbox."""
    hardcoded = _hardcoded_place(question)
    if hardcoded:
        return hardcoded

    m = _PLACE_RE.search(question)
    if not m:
        return None
    candidate = m.group(1).strip()
    # Drop a trailing "County" so "Sonoma County" geocodes as the county.
    token = os.getenv("MAPBOX_TOKEN")
    async with httpx.AsyncClient(timeout=10.0) as client:
        bbox = (
            await _mapbox_bbox(client, candidate, token)
            if token
            else await _nominatim_bbox(client, candidate)
        )
    if bbox is None:
        return None
    return PlaceContext(name=candidate, bbox=bbox)


def build_system_prompt(
    tables: list[TableSchema], place_context: PlaceContext | None = None
) -> str:
    schema_block = "\n\n".join(
        "TABLE {t}  (~{n:,} rows)\n{cols}".format(
            t=t.table_name,
            n=t.row_count,
            cols="\n".join(
                f"  {c.column_name} geometry({t.geom_type}, {t.srid})  -- spatial column"
                if c.column_name == t.geom_column
                else f"  {c.column_name} {c.udt_name}"
                for c in t.columns
            ),
        )
        for t in tables
    )

    place_block = ""
    if place_context is not None:
        mn_lng, mn_lat, mx_lng, mx_lat = place_context.bbox
        place_block = f"""

PLACE CONTEXT:
The question references "{place_context.name}". Its bounding box (EPSG:4326) is
min_lng={mn_lng}, min_lat={mn_lat}, max_lng={mx_lng}, max_lat={mx_lat}.
To restrict results to this place, filter with:
  ST_Within(geometry, ST_MakeEnvelope({mn_lng}, {mn_lat}, {mx_lng}, {mx_lat}, 4326))
Use these exact coordinates. Do NOT join to any POI/catalog table to filter by this place."""

    return f"""You are a PostGIS SQL expert. You translate natural language questions into a SINGLE executable PostgreSQL/PostGIS query.

DATABASE SCHEMA:
{schema_block}
{place_block}

RULES:
1. Return ONLY the raw SQL — no markdown fences, no explanation, no comments.
2. All geometry columns are in EPSG:4326. Use ST_Transform to 3857 for metric distances/areas.
3. For cross-table spatial joins use ST_Intersects(a.geometry, b.geometry).
4. Always alias tables for clarity (e.g. b for buildings, f for flood).
5. When the question asks "how many", use COUNT(*). When it asks for items, SELECT individual rows.
6. For aggregate / counting queries do NOT include geometry in the output.
7. When returning individual features, format each row as a GeoJSON Feature:
   jsonb_build_object(
     'type', 'Feature',
     'geometry', ST_AsGeoJSON(t.geometry)::jsonb,
     'properties', to_jsonb(t) - 'geometry'
   ) AS feature
8. NEVER use SELECT * — always list specific columns or use the GeoJSON pattern above.
9. Default LIMIT to 1000 unless the user specifies otherwise or the query is an aggregate.
10. Prefer ST_Intersects for polygon-polygon and polygon-point joins.
11. If the question is ambiguous, prefer the interpretation that uses a spatial join.
12. The catalog_fema_flood table contains flood hazard zones. fld_zone values include 'A', 'AE', 'AH', 'AO', 'VE' (Special Flood Hazard Areas where sfha_tf='T') and 'X' (minimal risk). Filter on sfha_tf = 'T' or fld_zone != 'X' when the user asks about "flood zones" generically.
13. REGIONS DO NOT OVERLAP. The wildfire_* tables (wildfire_nsi_structures, wildfire_dins, wildfire_frap_perimeters, wildfire_ms_footprints) cover SONOMA COUNTY only. The catalog_overture_pois table (and the other catalog_* layers) cover ALAMEDA COUNTY only. NEVER join a wildfire_* table to catalog_overture_pois or any catalog_* table to filter by city or place name — the regions don't intersect, so the join always returns zero rows.
14. To filter a wildfire_* table by a city or place name, do NOT join to a POI table. Use a bounding box: ST_Within(geometry, ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)). If a PLACE CONTEXT bounding box is provided above, use those exact coordinates.
15. wildfire_nsi_structures has an expected_annual_loss column (USD/year). "highest wildfire risk", "riskiest", or "most at-risk" structures means ORDER BY expected_annual_loss DESC NULLS LAST."""


async def generate_sql(
    question: str,
    tables: list[TableSchema],
    api_key: str,
    place_context: PlaceContext | None = None,
) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=build_system_prompt(tables, place_context),
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    text = re.sub(r"^```(?:sql)?\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n?```$", "", text, flags=re.IGNORECASE)
    return text.strip()


_AGG_RE = re.compile(r"\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b", re.IGNORECASE)
_LIMIT_RE = re.compile(r"LIMIT\s+\d+", re.IGNORECASE)


async def execute_with_guardrails(
    pool: asyncpg.Pool, sql: str, limit: int = 1000
) -> dict:
    # Strip trailing ; so we can wrap in `SELECT COUNT(*) FROM (…) _cq` below.
    sql = sql.rstrip("; \n")
    is_aggregate = bool(_AGG_RE.search(sql))

    async with pool.acquire() as conn:
        if is_aggregate:
            rows = await conn.fetch(sql)
            return {
                "type": "aggregate_result",
                "rows": [dict(r) for r in rows],
                "row_count": len(rows),
                "sql": sql,
            }

        # Count check
        count_failed = False
        total_rows = 0
        try:
            total_rows = await conn.fetchval(
                f"SELECT COUNT(*) FROM ({sql}) _cq"
            )
        except Exception:
            count_failed = True

        effective_limit = min(limit, GEOJSON_THRESHOLD)

        if not count_failed and total_rows <= effective_limit:
            # Respect an explicit LIMIT in the generated SQL when it's within
            # the GeoJSON threshold (e.g. "the 100 highest …" → LIMIT 100).
            # Previously we stripped the LLM's LIMIT and always re-applied the
            # 1000-row threshold, so "100 highest" silently returned up to
            # 1000 rows. Only impose the threshold when the query has no LIMIT
            # or asks for more than we'll render.
            existing = _LIMIT_RE.search(sql)
            existing_n = int(existing.group(0).split()[-1]) if existing else None
            final_limit = (
                min(existing_n, effective_limit) if existing_n is not None else effective_limit
            )
            clean = _LIMIT_RE.sub("", sql).rstrip("; \n")
            limited_sql = f"{clean} LIMIT {final_limit}"
            rows = await conn.fetch(limited_sql)

            if rows and "feature" in rows[0]:
                features = [dict(r)["feature"] for r in rows]
                return {
                    "type": "FeatureCollection",
                    "features": features,
                    "metadata": {
                        "sql": sql,
                        "total_count": total_rows,
                        "returned": len(features),
                    },
                }
            return {
                "type": "row_result",
                "rows": [dict(r) for r in rows],
                "row_count": len(rows),
                "sql": sql,
            }

        # Large result — return a 5-row sample with geometry intact so the
        # web client can preview the features on the map. The data-table
        # extracts `.properties` if present, so renderable features and
        # plain-row dicts both coexist in `sample_rows`.
        sample_sql = _LIMIT_RE.sub("", sql).rstrip("; \n") + " LIMIT 5"
        sample_rows: list[dict] = []
        try:
            raw = await conn.fetch(sample_sql)
            for r in raw:
                d = dict(r)
                if "feature" in d and isinstance(d["feature"], dict):
                    # Promote the GeoJSON Feature out of the wrapper column
                    # ({geometry, properties, type}) so the row IS the feature.
                    d = d["feature"]
                sample_rows.append(d)
        except Exception:
            pass

        msg = (
            f"Query matched {total_rows:,} features — exceeds the {effective_limit} "
            f"feature limit. Showing count and 5 sample rows."
            if not count_failed
            else "Result set too large. Showing sample."
        )
        return {
            "type": "large_result_summary",
            "total_count": total_rows,
            "message": msg,
            "sample_rows": sample_rows,
            "sql": sql,
        }


async def spatial_query(
    pool: asyncpg.Pool, question: str, api_key: str, limit: int = 1000
) -> dict:
    tables = await discover_schema(pool)
    if not tables:
        return {"type": "error", "message": "No spatial tables found."}

    # Resolve any place name to a bounding box BEFORE SQL generation so the
    # LLM filters wildfire_* tables by ST_MakeEnvelope instead of a POI join.
    try:
        place_context = await resolve_place_context(question)
    except Exception:
        place_context = None  # never let geocoding failure block the query

    try:
        sql = await generate_sql(question, tables, api_key, place_context)
    except Exception as e:
        return {"type": "error", "message": f"SQL generation failed: {e}"}

    try:
        return await execute_with_guardrails(pool, sql, limit)
    except Exception as e:
        return {
            "type": "sql_error",
            "message": f"SQL execution failed: {e}",
            "generated_sql": sql,
        }
