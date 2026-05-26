"""NL-to-SQL spatial query pipeline.

Mirrors the MCP server's spatial-query.ts logic:
1. Discover schema from PostGIS
2. Build system prompt with full table schemas
3. Call Claude to generate SQL
4. Execute with result-size guardrails
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import anthropic
import asyncpg

GEOJSON_THRESHOLD = 1000


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


def build_system_prompt(tables: list[TableSchema]) -> str:
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

    return f"""You are a PostGIS SQL expert. You translate natural language questions into a SINGLE executable PostgreSQL/PostGIS query.

DATABASE SCHEMA:
{schema_block}

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
12. The catalog_fema_flood table contains flood hazard zones. fld_zone values include 'A', 'AE', 'AH', 'AO', 'VE' (Special Flood Hazard Areas where sfha_tf='T') and 'X' (minimal risk). Filter on sfha_tf = 'T' or fld_zone != 'X' when the user asks about "flood zones" generically."""


async def generate_sql(question: str, tables: list[TableSchema], api_key: str) -> str:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=build_system_prompt(tables),
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
            clean = _LIMIT_RE.sub("", sql).rstrip("; \n")
            limited_sql = f"{clean} LIMIT {effective_limit}"
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

    try:
        sql = await generate_sql(question, tables, api_key)
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
