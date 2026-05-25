import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { query } from "../db.js";

export const spatialQuerySchema = z.object({
  natural_language_query: z
    .string()
    .describe("Natural language description of the spatial query to execute"),
  limit: z
    .number()
    .optional()
    .default(1000)
    .describe("Maximum number of GeoJSON features to return (default 1000). Large results return counts/summaries instead."),
});

export type SpatialQueryInput = z.infer<typeof spatialQuerySchema>;

// ---------------------------------------------------------------------------
// Schema discovery — builds the LLM system prompt dynamically
// ---------------------------------------------------------------------------

interface ColumnInfo {
  column_name: string;
  udt_name: string;
}

interface TableSchema {
  table_name: string;
  geom_column: string;
  geom_type: string;
  srid: number;
  row_count: number;
  columns: ColumnInfo[];
}

async function discoverSchema(): Promise<TableSchema[]> {
  // Spatial tables
  const geomResult = await query<{
    table_name: string;
    geom_column: string;
    geom_type: string;
    srid: number;
  }>(
    `SELECT f_table_name AS table_name, f_geometry_column AS geom_column,
            type AS geom_type, srid
     FROM geometry_columns
     WHERE f_table_name LIKE 'catalog_%' AND f_table_name != 'catalog_layers'
     ORDER BY f_table_name`,
  );

  const tables: TableSchema[] = [];

  for (const g of geomResult.rows) {
    // Column details
    const colResult = await query<ColumnInfo>(
      `SELECT column_name, udt_name
       FROM information_schema.columns
       WHERE table_name = $1
       ORDER BY ordinal_position`,
      [g.table_name],
    );

    // Approximate row count (fast, avoids full table scan)
    const countResult = await query<{ n: string }>(
      `SELECT reltuples::bigint AS n
       FROM pg_class WHERE relname = $1`,
      [g.table_name],
    );

    tables.push({
      table_name: g.table_name,
      geom_column: g.geom_column,
      geom_type: g.geom_type,
      srid: g.srid,
      row_count: parseInt(countResult.rows[0]?.n ?? "0", 10),
      columns: colResult.rows,
    });
  }

  return tables;
}

function buildSystemPrompt(tables: TableSchema[]): string {
  const schemaBlock = tables
    .map((t) => {
      const cols = t.columns
        .map((c) =>
          c.column_name === t.geom_column
            ? `  ${c.column_name} geometry(${t.geom_type}, ${t.srid})  -- spatial column`
            : `  ${c.column_name} ${c.udt_name}`,
        )
        .join("\n");
      return `TABLE ${t.table_name}  (~${t.row_count.toLocaleString()} rows)\n${cols}`;
    })
    .join("\n\n");

  return `You are a PostGIS SQL expert. You translate natural language questions into a SINGLE executable PostgreSQL/PostGIS query.

DATABASE SCHEMA:
${schemaBlock}

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
   )
8. NEVER use SELECT * — always list specific columns or use the GeoJSON pattern above.
9. Default LIMIT to 1000 unless the user specifies otherwise or the query is an aggregate.
10. Prefer ST_Intersects for polygon-polygon and polygon-point joins.
11. If the question is ambiguous, prefer the interpretation that uses a spatial join.
12. The catalog_fema_flood table contains flood hazard zones. fld_zone values include 'A', 'AE', 'AH', 'AO', 'VE' (Special Flood Hazard Areas where sfha_tf='T') and 'X' (minimal risk). Filter on sfha_tf = 'T' or fld_zone != 'X' when the user asks about "flood zones" generically.`;
}

// ---------------------------------------------------------------------------
// SQL generation via Claude
// ---------------------------------------------------------------------------

let anthropic: Anthropic | null = null;

function getClient(): Anthropic {
  if (!anthropic) {
    anthropic = new Anthropic();  // reads ANTHROPIC_API_KEY from env
  }
  return anthropic;
}

async function generateSQL(naturalLanguage: string, tables: TableSchema[]): Promise<string> {
  const systemPrompt = buildSystemPrompt(tables);

  const response = await getClient().messages.create({
    model: "claude-sonnet-4-20250514",
    max_tokens: 1024,
    system: systemPrompt,
    messages: [{ role: "user", content: naturalLanguage }],
  });

  const text = response.content
    .filter((b): b is Anthropic.TextBlock => b.type === "text")
    .map((b) => b.text)
    .join("");

  // Strip markdown fences if the model included them despite instructions
  return text.replace(/^```(?:sql)?\n?/i, "").replace(/\n?```$/i, "").trim();
}

// ---------------------------------------------------------------------------
// Execute with result-size guardrails
// ---------------------------------------------------------------------------

const GEOJSON_THRESHOLD = 1000;

async function executeWithGuardrails(sql: string, limit: number) {
  // Detect if this is an aggregate query (COUNT, SUM, AVG, etc.)
  const isAggregate = /\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b/i.test(sql);

  if (isAggregate) {
    // Aggregates are safe to run directly — small result sets
    const result = await query(sql);
    return {
      type: "aggregate_result" as const,
      rows: result.rows,
      row_count: result.rows.length,
      sql,
    };
  }

  // For non-aggregates, first check how many rows the query would return
  const countSql = `SELECT COUNT(*) AS total FROM (${sql}) _countq`;
  let totalRows: number;
  let countFailed = false;
  try {
    const countResult = await query<{ total: string }>(countSql);
    totalRows = parseInt(countResult.rows[0]?.total ?? "0", 10);
  } catch {
    // If the count wrapper fails, assume large and apply a safe limit
    totalRows = 0;
    countFailed = true;
  }

  const effectiveLimit = Math.min(limit, GEOJSON_THRESHOLD);

  if (!countFailed && totalRows <= effectiveLimit) {
    // Small enough — return full results (always enforce limit as safety net)
    const limitedSql = sql.replace(/;?\s*$/, ` LIMIT ${effectiveLimit}`);
    const result = await query(limitedSql);

    // Check if results contain GeoJSON features
    const hasFeatures = result.rows.length > 0 && "feature" in result.rows[0];

    if (hasFeatures) {
      return {
        type: "FeatureCollection" as const,
        features: result.rows.map((r: Record<string, unknown>) => r.feature),
        metadata: { sql, total_count: totalRows || result.rows.length, returned: result.rows.length },
      };
    }

    return {
      type: "row_result" as const,
      rows: result.rows,
      row_count: result.rows.length,
      sql,
    };
  }

  // Large result set — return summary with lightweight sample
  const sampleSql = sql
    .replace(/;?\s*$/, "")
    .replace(/LIMIT\s+\d+/i, "") + " LIMIT 5";
  let sampleRows: unknown[] = [];
  try {
    const sampleResult = await query(sampleSql);
    sampleRows = sampleResult.rows.map((r: Record<string, unknown>) => {
      // If result is a GeoJSON feature, strip the heavy geometry
      if (r.feature && typeof r.feature === "object") {
        const feat = r.feature as Record<string, unknown>;
        return { properties: feat.properties };
      }
      // If result is a jsonb_build_object, same approach
      const out: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(r)) {
        if (typeof v === "object" && v !== null && "geometry" in (v as Record<string, unknown>)) {
          const copy = { ...(v as Record<string, unknown>) };
          delete copy.geometry;
          out[k] = copy;
        } else {
          out[k] = v;
        }
      }
      return out;
    });
  } catch {
    // If sample fails, just return the count
  }

  return {
    type: "large_result_summary" as const,
    total_count: totalRows,
    message: countFailed
      ? `Result set is too large to return directly (count query timed out). Returning a sample of 5 rows (geometry stripped). Refine with a spatial filter, WHERE clause, or ask for a COUNT/aggregate instead.`
      : `Query matched ${totalRows.toLocaleString()} features, which exceeds the ${effectiveLimit} feature limit. Returning count and a sample of 5 rows (geometry stripped). Refine with a spatial filter, WHERE clause, or ask for a COUNT/aggregate instead.`,
    sample_rows: sampleRows,
    sql,
    suggestions: [
      "Add a spatial filter (e.g. 'within 1km of [location]')",
      "Ask for a count or summary instead",
      "Filter by a specific attribute (e.g. 'where class = house')",
    ],
  };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

export async function spatialQuery(input: SpatialQueryInput) {
  // 1. Discover schema
  const tables = await discoverSchema();

  if (tables.length === 0) {
    return {
      type: "error" as const,
      message: "No spatial tables found in database. Load data via the data-catalog package.",
    };
  }

  // 2. Generate SQL via Claude
  let sql: string;
  try {
    sql = await generateSQL(input.natural_language_query, tables);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      type: "error" as const,
      message: `Failed to generate SQL: ${msg}`,
      hint: "Ensure ANTHROPIC_API_KEY is set in your environment.",
    };
  }

  // 3. Execute with guardrails
  try {
    return await executeWithGuardrails(sql, input.limit);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    return {
      type: "sql_error" as const,
      message: `SQL execution failed: ${msg}`,
      generated_sql: sql,
      hint: "The generated SQL had an error. Try rephrasing your question.",
    };
  }
}
