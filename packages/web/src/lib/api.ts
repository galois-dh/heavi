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

// ─── Heavi Energy — solar siting v2 (Phase 4 / 5) ────────────────────────

export interface SolarScoreV2 {
  module: string;
  module_version: string;
  query: { latitude: number; longitude: number };
  score: number | null;
  rating: "High" | "Moderate" | "Low" | "Excluded" | "CANNOT ASSESS";
  cannot_assess?: boolean;
  message?: string;
  missing_sources?: Array<{ criterion: string; sources: string[]; message: string }>;
  exclusions?: string[];
  weight_profile?: {
    region: string | null;
    method: string;
    n_installations_in_calibration?: number;
    note?: string;
  };
  criteria_scores: Record<string, {
    score: number | null;
    weight: number | null;
    weighted_contribution?: number;
    basis: Record<string, unknown>;
    confidence: number;
    selected_source: string | null;
  }>;
  exclusion_results: Record<string, {
    excluded: boolean | null;
    basis: Record<string, unknown>;
    confidence: number;
    selected_source: string | null;
  }>;
  confidence: {
    tier: "HIGH" | "MODERATE" | "LOW" | "INSUFFICIENT";
    composite: number;
    statement: string;
    completeness: string;
    gaps: string[];
    strongest_data: string[];
    weakest_data: string[];
    per_criterion: Record<string, {
      confidence: number;
      tier: "HIGH" | "MODERATE" | "LOW" | "NONE";
      quality_note: string;
      selected_source: string | null;
    }>;
  };
  methodology: {
    workflow_type: string;
    framework_citations: Array<{ name: string; role: string; venue: string }>;
    criteria_count: number;
    scored_count: number;
    exclusion_count: number;
    criteria: Array<{
      criterion_id: string;
      criterion_name: string;
      criterion_type: "scored" | "exclusion";
      weight_default: number | null;
      weight_range: [number, number] | null;
      weight_rationale: string | null;
      exclusion_threshold: string | null;
      exclusion_rationale: string | null;
      data_sources: Array<{
        source_id: string;
        relationship: string;
        quality: string;
        provides: string;
      }>;
    }>;
    academic_sources: Array<{
      author: string; year: number; title: string;
      journal?: string; volume?: string; pages?: string; finding?: string;
    }>;
  };
}

export async function postSolarScoreV2(body: {
  latitude: number;
  longitude: number;
  weights_override?: Record<string, number>;
}): Promise<SolarScoreV2> {
  const res = await fetch(`${API_BASE}/solar/score-v2`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Solar scoring failed (${res.status}): ${text}`);
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

// ─── Solar site suitability ────────────────────────────────────────────────
// Shapes mirror packages/api/app/solar_scoring.py.

export type SolarRating = "High" | "Moderate" | "Low";

export interface SolarCriteria {
  solar_irradiance_ghi_kwh_m2_day: number | null;
  solar_irradiance_score: number;
  grid_distance_km: number | null;
  grid_proximity_score: number;
  slope_degrees: number | null;
  slope_percent: number | null;
  slope_score: number;
  aspect_deviation_from_south_degrees: number | null;
  aspect_score: number;
  soil_capability_class: number | null;
  soil_score: number;
  road_distance_km: number | null;
  road_access_score: number;
  land_use_category: string | null;
  land_use_score: number;
}

export interface SolarConstraints {
  min_acreage: boolean;
  max_slope: boolean;
  flood_zone_clear: boolean;
  wetlands_clear: boolean;
  protected_lands_clear: boolean;
}

export interface SolarResult {
  parcel_id: string;
  suitability_score: number;
  suitability_rating: SolarRating;
  acreage: number | null;
  estimated_capacity_mw: number;
  location: { longitude: number | null; latitude: number | null };
  criteria_scores: SolarCriteria;
  constraints_passed: SolarConstraints;
  constraints_all_passed: boolean;
  natural_language_summary: string;
  methodology: {
    summary: string;
    weights_source: string;
    capacity_method: string;
    environmental_constraints: string;
    data_sources: string[];
  };
  data_notes?: string[];
}

export interface SolarPortfolioSummary {
  total_parcels_evaluated: number;
  parcels_passing_constraints: number;
  total_estimated_capacity_mw: number;
  score_distribution: { High: number; Moderate: number; Low: number };
  returned: number;
}

export interface SolarConfig {
  min_acreage: number;
  max_slope_pct: number;
  grid_max_distance_km: number;
  road_max_distance_km: number;
  high_threshold: number;
  moderate_threshold: number;
  acres_per_mw: number;
  weights: Record<string, number>;
}

export interface SolarDiscoverResponse {
  mode: "discover";
  geography: string | { bbox: number[] };
  portfolio_summary: SolarPortfolioSummary;
  results: SolarResult[];
  config: SolarConfig;
  methodology_endpoint: string;
  notes: string[];
  // present only when the geography isn't pre-loaded
  error?: string;
  available_geographies?: string[];
}

export interface SolarScoreResponse {
  mode: "score";
  parcel_count: number;
  scored_count: number;
  results: SolarResult[];
  config: SolarConfig;
  methodology_endpoint: string;
}

export async function postSolarDiscover(body: {
  geography: string | number[];
  top_n?: number;
  min_acreage?: number;
  max_slope?: number;
}): Promise<SolarDiscoverResponse> {
  const res = await fetch(`${API_BASE}/solar/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Solar discover failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function postSolarScore(file: File): Promise<SolarScoreResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/solar/score`, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Solar score failed (${res.status}): ${text}`);
  }
  return res.json();
}

// ─── Flood risk ─────────────────────────────────────────────────────────────
// Shape mirrors packages/api/app/flood_scoring.py assess_flood_risk().

export interface FloodRiskAssessment {
  natural_language_summary: string;
  query: {
    latitude: number;
    longitude: number;
    address: string | null;
    resolved_address: string | null;
  };
  flood_zone: {
    zone: string | null;
    zone_subtype: string | null;
    static_bfe_ft: number | null;
    in_special_flood_hazard_area: boolean;
    annual_exceedance_probability: number;
    return_period_years: number;
  };
  structure: {
    match_distance_m: number;
    occupancy_type: string | null;
    hazus_occupancy_class: string;
    foundation_type: string | null;
    num_stories: number | null;
    first_floor_height_ft: number;
    replacement_value_structure_usd: number;
    replacement_value_contents_usd: number;
    structure_location: { latitude: number; longitude: number };
  } | null;
  elevation: {
    ground_elevation_ft: number | null;
    first_floor_height_ft: number;
    flood_depth_above_first_floor_ft: number | null;
    depth_basis: string;
  };
  damage: {
    hazus_occupancy_class: string;
    structural_damage_pct: number;
    contents_damage_pct: number;
    structural_loss_usd: number;
    contents_loss_usd: number;
    total_loss_usd: number;
  };
  risk_estimate: {
    annual_risk_estimate_usd: number;
    risk_tier: "HIGH" | "MODERATE" | "LOW";
    annual_exceedance_probability: number;
    return_period_years: number;
  };
  methodology_note: string;
}

export async function postFloodRisk(body: {
  address?: string;
  latitude?: number;
  longitude?: number;
}): Promise<FloodRiskAssessment> {
  const res = await fetch(`${API_BASE}/flood/risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Flood risk failed (${res.status}): ${text}`);
  }
  return res.json();
}

// ─── Earthquake risk ────────────────────────────────────────────────────────
// Shape mirrors packages/api/app/earthquake_scoring.py assess_earthquake_risk().

export interface EarthquakeRiskAssessment {
  natural_language_summary: string;
  query: {
    latitude: number;
    longitude: number;
    address: string | null;
    resolved_address: string | null;
  };
  hazard: {
    bedrock_pga_g: number;
    adjusted_pga_g: number;
    hazard_level: string;
    return_period_years: number;
    annual_exceedance_probability: number;
  };
  site: {
    vs30_m_per_s: number;
    site_class: string;
    site_description: string;
    amplification_factor: number;
    slope_m_per_m: number | null;
    slope_basis: string;
  };
  structure: {
    match_distance_m: number;
    occupancy_type: string | null;
    nsi_building_type: string | null;
    hazus_building_type: string;
    code_level: string;
    num_stories: number | null;
    median_year_built: number | null;
    replacement_value_structure_usd: number;
    replacement_value_contents_usd: number;
    structure_location: { latitude: number; longitude: number };
  } | null;
  damage_state_probabilities: {
    exceedance: { slight: number; moderate: number; extensive: number; complete: number };
    exclusive: { slight: number; moderate: number; extensive: number; complete: number };
    expected_damage_ratio: number;
  };
  risk_estimate: {
    annual_risk_estimate_usd: number;
    risk_tier: "HIGH" | "MODERATE" | "LOW";
    structural_loss_at_hazard_usd: number;
    contents_loss_at_hazard_usd: number;
    total_loss_at_hazard_usd: number;
    annual_exceedance_probability: number;
    return_period_years: number;
  };
  methodology_note: string;
}

export async function postEarthquakeRisk(body: {
  address?: string;
  latitude?: number;
  longitude?: number;
}): Promise<EarthquakeRiskAssessment> {
  const res = await fetch(`${API_BASE}/earthquake/risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Earthquake risk failed (${res.status}): ${text}`);
  }
  return res.json();
}

// ─── Trade area analysis ─────────────────────────────────────────────────────
// Shapes mirror packages/api/app/trade_area_scoring.py.

export type TradeAreaRating = "Strong" | "Moderate" | "Weak";

export interface TradeAreaRing {
  drive_time_minutes: number;
  isochrone: GeoJSON.Polygon;
  population: number;
  households: number;
  median_household_income: number | null;
  daytime_jobs: number;
  poi_count: number;
  competitor_count: number;
  complementary_count: number;
  competitive_density_per_10k: number;
  competitive_gap: number;
}

export interface TradeAreaScoreResponse {
  query: {
    latitude: number;
    longitude: number;
    address: string | null;
    resolved_address: string | null;
    business_category: string;
  };
  geography: string;
  suitability_score: number;
  suitability_rating: TradeAreaRating;
  criteria_scores: Record<string, number>;
  competitive_analysis: {
    business_category: string;
    reference_density_per_10k: number;
    nearest_competitor_m: number | null;
    road_proximity_m: number | null;
    in_flood_zone: boolean;
    per_ring: Array<{
      drive_time_minutes: number;
      competitor_count: number;
      complementary_count: number;
      competitive_density_per_10k: number;
      competitive_gap: number;
    }>;
  };
  cannibalization: {
    cannibalization_risk: string;
    nearest_existing_km: number | null;
    max_cannibalization_estimate: number;
    per_existing_location: Array<Record<string, unknown>>;
  } | null;
  trade_area_rings: TradeAreaRing[];
  natural_language_summary: string;
  methodology_note: string;
}

export interface TradeAreaCandidate {
  latitude: number;
  longitude: number;
  approx_population_1mi: number;
  competitor_count_1mi: number;
  competitive_density_per_10k: number;
  lightweight_score: number;
}

export interface TradeAreaDiscoverResponse {
  geography: string | { bbox: number[] };
  business_category: string;
  grid_points_evaluated: number;
  candidates_passing_filters: number;
  results: TradeAreaCandidate[];
  note: string;
}

export async function postTradeAreaScore(body: {
  address?: string;
  latitude?: number;
  longitude?: number;
  business_category: string;
  existing_locations?: Array<{ latitude: number; longitude: number; name?: string }>;
}): Promise<TradeAreaScoreResponse> {
  const res = await fetch(`${API_BASE}/trade-area/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Trade area score failed (${res.status}): ${text}`);
  }
  return res.json();
}

export async function postTradeAreaDiscover(body: {
  geography?: string | number[];
  business_category: string;
  top_n?: number;
}): Promise<TradeAreaDiscoverResponse> {
  const res = await fetch(`${API_BASE}/trade-area/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Trade area discover failed (${res.status}): ${text}`);
  }
  return res.json();
}

// ─── Workflow Integration v2 (hazard + trade area) ─────────────────────────

export interface ConfidenceReport {
  tier: string;
  composite: number;
  statement: string;
  completeness?: string;
  gaps: string[];
  strongest_data?: string[];
  weakest_data?: string[];
  per_criterion: Record<
    string,
    { confidence: number; tier: string; quality_note: string; selected_source: string | null }
  >;
}

export interface HazardScoreV2 {
  module: string;
  query: { latitude: number; longitude: number };
  wildfire: {
    available: boolean;
    cannot_assess?: boolean;
    annual_risk_usd: number | null;
    risk_tier: string | null;
    damage_probability: number | null;
    message?: string;
    missing_sources?: string[];
    note?: string;
    [k: string]: unknown;
  };
  flood: {
    available: boolean;
    cannot_assess?: boolean;
    annual_risk_usd: number | null;
    risk_tier: string | null;
    flood_zone: string | null;
    depth_ft: number | null;
    message?: string;
    missing_sources?: string[];
    [k: string]: unknown;
  };
  confidence: ConfidenceReport;
  methodology: Record<string, unknown>;
}

export async function postHazardScoreV2(body: {
  address?: string;
  latitude?: number;
  longitude?: number;
}): Promise<HazardScoreV2> {
  const res = await fetch(`${API_BASE}/hazard/score-v2`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Hazard score-v2 failed (${res.status}): ${text}`);
  }
  return res.json();
}

export interface TradeAreaScoreV2 {
  module: string;
  query: Record<string, unknown>;
  coverage: string;
  suitability_score: number | null;
  suitability_rating: string;
  cannot_assess?: boolean;
  message?: string;
  missing_sources?: Array<{ criterion: string; sources: string[]; message: string }>;
  criteria_scores: Record<string, number>;
  competitive_analysis?: Record<string, unknown> | null;
  data_sources_used: Record<string, string | null>;
  coverage_gaps?: string[];
  coverage_note?: string;
  trade_area_rings?: Array<Record<string, unknown>>;
  competitor_pois?: Array<{ latitude: number; longitude: number }>;
  natural_language_summary?: string;
  confidence: ConfidenceReport;
  methodology: Record<string, unknown>;
}

export async function postTradeAreaScoreV2(body: {
  address?: string;
  latitude?: number;
  longitude?: number;
  business_category?: string;
  existing_locations?: { latitude: number; longitude: number; name?: string }[];
}): Promise<TradeAreaScoreV2> {
  const res = await fetch(`${API_BASE}/trade-area/score-v2`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Trade area score-v2 failed (${res.status}): ${text}`);
  }
  return res.json();
}

// ─── Geocoding (Month-1 Sprint, Feature 1) ─────────────────────────────────

export interface GeocodeResult {
  latitude: number;
  longitude: number;
  formatted_address: string;
  source: "census" | "nominatim" | "coordinates";
}

// "35.35, -119.05" or "35.35 -119.05" — raw coordinate pair.
const COORD_RE = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;

/** Resolve an address / place name / city-state / raw coords to coordinates.
 *  Raw coordinates are detected client-side and returned WITHOUT any /geocode
 *  call (AC3); everything else hits GET /geocode (Census → Nominatim). */
export async function resolveLocation(input: string): Promise<GeocodeResult> {
  const q = input.trim();
  const m = q.match(COORD_RE);
  if (m) {
    const lat = parseFloat(m[1]);
    const lng = parseFloat(m[2]);
    if (Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
      return {
        latitude: lat, longitude: lng,
        formatted_address: `${lat.toFixed(5)}, ${lng.toFixed(5)}`,
        source: "coordinates",
      };
    }
  }
  const res = await fetch(`${API_BASE}/geocode?q=${encodeURIComponent(q)}`);
  if (!res.ok) {
    throw new Error(
      "Could not find that location. Try a different address or enter coordinates directly.",
    );
  }
  return res.json();
}
