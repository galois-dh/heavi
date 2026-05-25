import { z } from "zod";
import { query } from "../db.js";

export const bufferAnalysisSchema = z.object({
  geometry: z
    .object({
      type: z.enum(["Point", "LineString", "Polygon"]),
      coordinates: z.unknown(),
    })
    .describe("GeoJSON geometry to buffer around"),
  distance_meters: z.number().positive().describe("Buffer distance in meters"),
  layer: z
    .string()
    .optional()
    .describe("Specific layer to query. If omitted, queries all spatial tables."),
  limit: z.number().optional().default(500).describe("Max features to return"),
});

export type BufferAnalysisInput = z.infer<typeof bufferAnalysisSchema>;

export async function bufferAnalysis(input: BufferAnalysisInput) {
  const geojson = JSON.stringify(input.geometry);
  const bufferSql = `ST_Transform(ST_Buffer(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON($1), 4326), 3857), $2), 4326)`;

  // Determine which tables to search
  let tables: { table_name: string; geom_column: string }[];
  if (input.layer) {
    tables = [{ table_name: input.layer, geom_column: "geom" }];
    // Verify the column name from geometry_columns
    const check = await query<{ geom_column: string }>(
      `SELECT f_geometry_column AS geom_column FROM geometry_columns WHERE f_table_name = $1`,
      [input.layer],
    );
    if (check.rows.length > 0) {
      tables[0].geom_column = check.rows[0].geom_column;
    }
  } else {
    const tablesResult = await query<{ table_name: string; geom_column: string }>(
      `SELECT f_table_name AS table_name, f_geometry_column AS geom_column FROM geometry_columns`,
    );
    tables = tablesResult.rows;
  }

  const allFeatures: { layer: string; feature: object }[] = [];
  const perLayer = Math.max(1, Math.floor(input.limit / Math.max(tables.length, 1)));

  for (const table of tables) {
    const sql = `
      SELECT '${table.table_name}' AS layer,
        jsonb_build_object(
          'type', 'Feature',
          'geometry', ST_AsGeoJSON(${table.geom_column})::jsonb,
          'properties', to_jsonb(t) - '${table.geom_column}'
        ) AS feature
      FROM "${table.table_name}" t
      WHERE ST_Intersects(${table.geom_column}, ${bufferSql})
      LIMIT $3
    `;
    const result = await query<{ layer: string; feature: object }>(sql, [
      geojson,
      input.distance_meters,
      perLayer,
    ]);
    allFeatures.push(...result.rows);
  }

  return {
    type: "FeatureCollection" as const,
    features: allFeatures.map((f) => f.feature),
    metadata: {
      buffer_distance_meters: input.distance_meters,
      input_geometry: input.geometry,
      layers_searched: tables.map((t) => t.table_name),
      total_features: allFeatures.length,
    },
  };
}
