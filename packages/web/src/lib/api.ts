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
  // large_result_summary — backend returns a 5-row sample. When the query is
  // a feature query, each entry is a full GeoJSON Feature ({type, geometry,
  // properties}); the map renders these and the data table extracts
  // `.properties`. Otherwise entries are plain row dicts.
  total_count?: number;
  message?: string;
  sample_rows?: Array<Record<string, unknown>>;
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

// ─── Wildfire risk assessment ────────────────────────────────────────────
// Shape mirrors packages/api/app/wildfire_loss.py exactly.

export interface WildfireFeatures {
  wildfire_likelihood: number;
  distance_to_fuel_m: number;
  canopy_cover_30m: number;
  canopy_cover_100m: number;
  canopy_cover_300m: number;
  slope_degrees: number;
  is_res1: number;
}

export interface WildfireMatch {
  fd_id: number;
  match_distance_m: number;
  nsi_location: { latitude: number; longitude: number };
  occupancy_type: string | null;
  replacement_value_usd: number;
  tract_fips: string | null;
}

export interface WildfirePropertyVulnerability {
  damage_probability: number;
  log_odds: number;
  exceeds_risk_threshold: boolean;
  optimal_threshold: number;
  validation_auc_roc: number;
  model_run_id: string;
  methodology_hash: string;
}

export interface WildfireRiskEstimate {
  annual_damage_frequency: number;
  annual_risk_estimate_usd: number;
  annual_risk_estimate_usd_persisted: number | null;
  return_period_years: number | null;
}

export interface WildfireRiskAssessment {
  query: {
    latitude: number;
    longitude: number;
    address: string | null;
    resolved_address: string | null;
    search_radius_m: number;
  };
  match: WildfireMatch | null;
  features?: WildfireFeatures;
  property_vulnerability?: WildfirePropertyVulnerability;
  risk_estimate?: WildfireRiskEstimate;
  methodology_note?: string;
  natural_language_summary?: string;
  message?: string;
}

export async function postWildfireLoss(
  body: { address?: string; latitude?: number; longitude?: number; search_radius_m?: number },
): Promise<WildfireRiskAssessment> {
  const res = await fetch(`${API_BASE}/wildfire-loss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Wildfire risk failed (${res.status}): ${text}`);
  }
  return res.json();
}

// ─── Portfolio risk ──────────────────────────────────────────────────────

export interface PortfolioRow {
  property_id: string | null;
  row_index: number;
  input_address: string | null;
  resolved_address: string | null;
  latitude: number | null;
  longitude: number | null;
  status: "scored" | "no_coverage" | "error";
  error?: string;
  annual_risk_usd: number | null;
  match?: WildfireMatch | null;
  features?: WildfireFeatures;
  property_vulnerability?: WildfirePropertyVulnerability;
  risk_estimate?: WildfireRiskEstimate;
  message?: string;
}

export interface RiskDistributionEntry {
  bucket: string;
  n: number;
}

export interface PortfolioSummary {
  property_count: number;
  scored_count: number;
  total_annual_risk: number;
  mean_risk: number;
  median_risk: number;
  min_risk?: number;
  max_risk?: number;
  p95_risk?: number;
  risk_distribution: RiskDistributionEntry[];
  high_risk_count: number;
  moderate_risk_count: number;
  low_risk_count: number;
  error_count: number;
  no_coverage_count: number;
}

export interface PortfolioResponse {
  job_id: string;
  generated_at: string;
  methodology_note: string;
  model: { run_id: string; auc_roc: number; methodology_hash: string };
  portfolio_summary: PortfolioSummary;
  top_10_highest_risk: PortfolioRow[];
  per_property: PortfolioRow[];
}

export async function postPortfolioRisk(file: File): Promise<PortfolioResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/portfolio-risk`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Portfolio risk failed (${res.status}): ${text}`);
  }
  return res.json();
}

export function portfolioReportUrl(jobId: string): string {
  return `${API_BASE}/portfolio-risk/${jobId}/report`;
}

export function portfolioSampleCsvUrl(): string {
  return `${API_BASE}/portfolio-risk/sample.csv`;
}
