import { query } from "../db.js";

export async function dataLayers() {
  const result = await query<{
    table_name: string;
    geom_column: string;
    geom_type: string;
    srid: number;
  }>(
    `SELECT
       f_table_name AS table_name,
       f_geometry_column AS geom_column,
       type AS geom_type,
       srid
     FROM geometry_columns
     ORDER BY f_table_name`,
  );

  // Get row counts for each table
  const layers = await Promise.all(
    result.rows.map(async (row) => {
      const countResult = await query<{ cnt: string }>(
        `SELECT COUNT(*) AS cnt FROM "${row.table_name}"`,
      );
      return {
        name: row.table_name,
        geometry_column: row.geom_column,
        geometry_type: row.geom_type,
        srid: row.srid,
        feature_count: parseInt(countResult.rows[0]?.cnt ?? "0", 10),
      };
    }),
  );

  return { layers, total: layers.length };
}
