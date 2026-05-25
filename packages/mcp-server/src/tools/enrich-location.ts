import { z } from "zod";
import { query } from "../db.js";

export const enrichLocationSchema = z.object({
  latitude: z.number().min(-90).max(90).describe("Latitude of the point"),
  longitude: z.number().min(-180).max(180).describe("Longitude of the point"),
  radius_meters: z
    .number()
    .optional()
    .default(500)
    .describe("Search radius in meters for nearby features"),
});

export type EnrichLocationInput = z.infer<typeof enrichLocationSchema>;

export async function enrichLocation(input: EnrichLocationInput) {
  const point = `ST_SetSRID(ST_MakePoint(${input.longitude}, ${input.latitude}), 4326)`;
  const bufferGeom = `ST_Transform(ST_Buffer(ST_Transform(${point}, 3857), ${input.radius_meters}), 4326)`;

  // Discover all spatial tables
  const tablesResult = await query<{ table_name: string; geom_column: string; geom_type: string }>(
    `SELECT f_table_name AS table_name, f_geometry_column AS geom_column, type AS geom_type
     FROM geometry_columns ORDER BY f_table_name`,
  );

  const profile: Record<string, unknown> = {
    location: { latitude: input.latitude, longitude: input.longitude },
    radius_meters: input.radius_meters,
  };

  for (const table of tablesResult.rows) {
    const isPolygon = table.geom_type.includes("POLYGON") || table.geom_type.includes("MULTI");

    if (isPolygon) {
      // For polygons, check containment — return properties of the containing feature
      const containsResult = await query<{ props: Record<string, unknown> }>(
        `SELECT to_jsonb(t) - '${table.geom_column}' AS props
         FROM "${table.table_name}" t
         WHERE ST_Contains(${table.geom_column}, ${point})
         LIMIT 1`,
      );
      if (containsResult.rows.length > 0) {
        profile[table.table_name] = {
          relationship: "contains",
          properties: containsResult.rows[0].props,
        };
      }
    } else {
      // For points/lines, count nearby and return closest
      const nearbyResult = await query<{
        cnt: string;
        nearest_props: Record<string, unknown> | null;
        nearest_distance: number | null;
      }>(
        `SELECT
           COUNT(*) OVER() AS cnt,
           to_jsonb(t) - '${table.geom_column}' AS nearest_props,
           ST_Distance(ST_Transform(${table.geom_column}, 3857), ST_Transform(${point}, 3857)) AS nearest_distance
         FROM "${table.table_name}" t
         WHERE ST_Intersects(${table.geom_column}, ${bufferGeom})
         ORDER BY ${table.geom_column} <-> ${point}
         LIMIT 1`,
      );
      if (nearbyResult.rows.length > 0) {
        profile[table.table_name] = {
          relationship: "nearby",
          count_within_radius: parseInt(nearbyResult.rows[0].cnt, 10),
          nearest: {
            properties: nearbyResult.rows[0].nearest_props,
            distance_meters: Math.round((nearbyResult.rows[0].nearest_distance ?? 0) * 100) / 100,
          },
        };
      }
    }
  }

  return profile;
}
