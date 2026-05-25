"use client";

import type { QueryResult } from "../lib/api";

export function DataTable({ result }: { result: QueryResult | null }) {
  if (!result) return null;

  const rows = getRows(result);
  if (!rows.length) return null;

  const keys = Object.keys(rows[0]).filter(
    (k) => k !== "geometry" && k !== "feature",
  );

  return (
    <div className="border-t border-zinc-800 max-h-[220px] overflow-auto">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-zinc-900 text-left text-zinc-500">
          <tr>
            {keys.map((k) => (
              <th key={k} className="px-3 py-1.5 font-medium whitespace-nowrap">
                {k}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-zinc-300">
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-zinc-800/50 hover:bg-zinc-800/30">
              {keys.map((k) => (
                <td key={k} className="px-3 py-1 whitespace-nowrap max-w-[200px] truncate">
                  {formatCell(row[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function getRows(result: QueryResult): Record<string, unknown>[] {
  if (result.type === "aggregate_result" || result.type === "row_result") {
    return result.rows ?? [];
  }
  if (result.type === "FeatureCollection" && result.features?.length) {
    return result.features.map((f) => (f.properties ?? {}) as Record<string, unknown>);
  }
  if (result.type === "large_result_summary") {
    return (result.sample_rows ?? []).map((r) => {
      if ("properties" in r && typeof r.properties === "object" && r.properties !== null) {
        return r.properties as Record<string, unknown>;
      }
      return r;
    });
  }
  return [];
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
