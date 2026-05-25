const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface QueryResult {
  type: string;
  // FeatureCollection
  features?: GeoJSON.Feature[];
  metadata?: { sql: string; total_count: number; returned: number };
  // aggregate_result / row_result
  rows?: Record<string, unknown>[];
  row_count?: number;
  sql?: string;
  // large_result_summary
  total_count?: number;
  message?: string;
  sample_rows?: Record<string, unknown>[];
  // error
  generated_sql?: string;
}

export async function postQuery(question: string): Promise<QueryResult> {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export type FactorKey =
  | "flood_risk"
  | "demographics"
  | "transit_access"
  | "environmental"
  | "competition";

export interface NearbyFeature {
  properties: Record<string, unknown>;
  distance_m: number;
  longitude: number;
  latitude: number;
}

export interface SiteReport {
  address: string;
  location: { latitude: number; longitude: number };
  radius_meters: number;
  composite_score: number;
  factors: Record<FactorKey, number>;
  counts: {
    transit_stops: number;
    epa_facilities: number;
    pois: number;
    in_flood_zone: boolean;
    in_fire_hazard: boolean;
    in_census_tract: boolean;
  };
  nearby: {
    schools: NearbyFeature[];
    transit_stops: NearbyFeature[];
    epa_facilities: NearbyFeature[];
  };
}

export async function postSiteReport(
  body: { address?: string; latitude?: number; longitude?: number; radius_meters?: number },
): Promise<SiteReport> {
  const res = await fetch(`${API_BASE}/site-report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Site report failed (${res.status}): ${text}`);
  }
  return res.json();
}
