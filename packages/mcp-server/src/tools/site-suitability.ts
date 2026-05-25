import { z } from "zod";
import { query } from "../db.js";

export const siteSuitabilitySchema = z.object({
  latitude: z.number().min(-90).max(90).describe("Latitude of the site"),
  longitude: z.number().min(-180).max(180).describe("Longitude of the site"),
  radius_meters: z
    .number()
    .optional()
    .default(1000)
    .describe("Analysis radius in meters"),
  criteria: z
    .record(z.string(), z.number().min(0).max(1))
    .optional()
    .default({})
    .describe(
      "Criteria weights as key-value pairs (e.g. { \"transit_access\": 0.8, \"green_space\": 0.6 }). Values 0-1.",
    ),
});

export type SiteSuitabilityInput = z.infer<typeof siteSuitabilitySchema>;

export async function siteSuitability(input: SiteSuitabilityInput) {
  const point = `ST_SetSRID(ST_MakePoint(${input.longitude}, ${input.latitude}), 4326)`;
  const bufferGeom = `ST_Transform(ST_Buffer(ST_Transform(${point}, 3857), ${input.radius_meters}), 4326)`;

  // Discover spatial tables
  const tablesResult = await query<{ table_name: string; geom_column: string }>(
    `SELECT f_table_name AS table_name, f_geometry_column AS geom_column
     FROM geometry_columns ORDER BY f_table_name`,
  );

  // Count features from each layer within the radius
  const layerScores: Record<string, { count: number; weight: number; score: number }> = {};

  for (const table of tablesResult.rows) {
    const countResult = await query<{ cnt: string }>(
      `SELECT COUNT(*) AS cnt FROM "${table.table_name}"
       WHERE ST_Intersects(${table.geom_column}, ${bufferGeom})`,
    );
    const count = parseInt(countResult.rows[0]?.cnt ?? "0", 10);
    const weight = input.criteria[table.table_name] ?? 0.5;
    // Normalize: log scale so diminishing returns on density
    const normalizedCount = count > 0 ? Math.min(Math.log10(count + 1) / 3, 1) : 0;

    layerScores[table.table_name] = {
      count,
      weight,
      score: normalizedCount * weight,
    };
  }

  const totalWeight = Object.values(layerScores).reduce((s, l) => s + l.weight, 0);
  const totalScore = totalWeight > 0
    ? Object.values(layerScores).reduce((s, l) => s + l.score, 0) / totalWeight
    : 0;

  return {
    location: { latitude: input.latitude, longitude: input.longitude },
    radius_meters: input.radius_meters,
    overall_score: Math.round(totalScore * 100) / 100,
    layer_scores: layerScores,
    criteria_applied: input.criteria,
  };
}
