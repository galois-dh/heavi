import { z } from "zod";
import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { query } from "../db.js";

// ─── Fitted vulnerability model ───────────────────────────────────────────
// Loaded once at module import. Resolves both in dev (tsx, src/) and prod
// (compiled, dist/) by walking up to packages/.
type FittedModel = {
  run_id: string;
  methodology_hash: string;
  coefficients: Record<string, number>;
  predictors: string[];
  optimal_threshold: number;
  auc_roc: number;
};

function loadFittedModel(): FittedModel {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  // src or dist → packages/mcp-server → packages/ → packages/validation/...
  const candidates = [
    resolve(__dirname, "..", "..", "..", "validation", "modules", "wildfire_vulnerability", "fitted_model.json"),
    resolve(__dirname, "..", "..", "validation", "modules", "wildfire_vulnerability", "fitted_model.json"),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return JSON.parse(readFileSync(p, "utf-8")) as FittedModel;
  }
  throw new Error(
    `wildfire_loss: could not locate fitted_model.json. Tried:\n  ${candidates.join("\n  ")}`,
  );
}

let _model: FittedModel | null = null;
function model(): FittedModel {
  if (!_model) _model = loadFittedModel();
  return _model;
}

function logistic(z: number): number {
  return 1.0 / (1.0 + Math.exp(-z));
}

function scoreDestruction(features: {
  burn_probability: number;
  distance_to_fuel_m: number;
  canopy_cover_100m: number;
  slope_degrees: number;
  is_res1: number;
}): { p_destroyed: number; log_odds: number } {
  const c = model().coefficients;
  const z =
    c.const +
    c.burn_probability * features.burn_probability +
    c.distance_to_fuel_m * features.distance_to_fuel_m +
    c.canopy_cover_100m * features.canopy_cover_100m +
    c.slope_degrees * features.slope_degrees +
    c.is_res1 * features.is_res1;
  return { p_destroyed: logistic(z), log_odds: z };
}

// ─── Geocoding fallback ───────────────────────────────────────────────────
async function geocodeNominatim(address: string): Promise<{ lat: number; lng: number; display: string } | null> {
  const url =
    "https://nominatim.openstreetmap.org/search?" +
    new URLSearchParams({
      q: address,
      format: "json",
      limit: "1",
      countrycodes: "us",
    }).toString();
  const r = await fetch(url, { headers: { "User-Agent": "Heavi/0.1 (wildfire-loss-mcp)" } });
  if (!r.ok) return null;
  const data = (await r.json()) as Array<{ lat: string; lon: string; display_name: string }>;
  if (!data.length) return null;
  return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon), display: data[0].display_name };
}

// ─── Schema ───────────────────────────────────────────────────────────────
export const wildfireLossSchema = z.object({
  latitude: z.number().min(-90).max(90).optional().describe("Latitude (WGS84). Either lat+lng or address is required."),
  longitude: z.number().min(-180).max(180).optional().describe("Longitude (WGS84)."),
  address: z.string().optional().describe("Street address. Geocoded via Nominatim if lat/lng not provided."),
  search_radius_m: z
    .number()
    .min(10)
    .max(5000)
    .optional()
    .default(500)
    .describe("Search radius in metres for nearest NSI structure (default 500 m)."),
});
export type WildfireLossInput = z.infer<typeof wildfireLossSchema>;

type NsiHit = {
  fd_id: number;
  occtype: string | null;
  val_struct: number | null;
  burn_probability: number | null;
  distance_to_fuel_m: number | null;
  canopy_cover_30m: number | null;
  canopy_cover_100m: number | null;
  canopy_cover_300m: number | null;
  slope_degrees: number | null;
  expected_annual_loss: number | null;
  cbfips: string | null;
  lng: number;
  lat: number;
  match_dist_m: number;
};

// ─── Tool ─────────────────────────────────────────────────────────────────
export async function wildfireLoss(input: WildfireLossInput) {
  // 1. Resolve coordinates.
  let lat = input.latitude;
  let lng = input.longitude;
  let resolvedAddress: string | null = null;
  if (lat === undefined || lng === undefined) {
    if (!input.address) {
      throw new Error("wildfire_loss: must provide either latitude+longitude or address");
    }
    const g = await geocodeNominatim(input.address);
    if (!g) throw new Error(`wildfire_loss: could not geocode '${input.address}'`);
    lat = g.lat;
    lng = g.lng;
    resolvedAddress = g.display;
  }

  // 2. Nearest NSI within the search radius (uses GIST KNN — see Stage 3
  //    perf note: never cast geometry::geography in the WHERE clause).
  const degExpand = (input.search_radius_m / 100_000).toFixed(6); // 100 m ≈ 0.001°; pad ×1.5
  const result = await query<NsiHit>(
    `WITH p AS (SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS g)
     SELECT n.fd_id, n.occtype, n.val_struct,
            n.burn_probability, n.distance_to_fuel_m,
            n.canopy_cover_30m, n.canopy_cover_100m, n.canopy_cover_300m,
            n.slope_degrees, n.expected_annual_loss,
            n.cbfips,
            ST_X(n.geometry) AS lng, ST_Y(n.geometry) AS lat,
            ST_Distance(n.geometry::geography, p.g::geography) AS match_dist_m
       FROM wildfire_nsi_structures n, p
      WHERE n.geometry && ST_Expand(p.g, ${degExpand}::float8)
      ORDER BY n.geometry <-> p.g
      LIMIT 1`,
    [lng, lat],
  );
  if (!result.rows.length || result.rows[0].match_dist_m > input.search_radius_m) {
    return {
      query: { latitude: lat, longitude: lng, address: input.address, resolved_address: resolvedAddress },
      match: null,
      message: `No NSI structure within ${input.search_radius_m} m of the query point.`,
    };
  }

  const nsi = result.rows[0];
  const is_res1 = (nsi.occtype ?? "").startsWith("RES1") ? 1 : 0;
  const m = model();

  // 3. Re-score in-process so callers see the exact coefficients used.
  const features = {
    burn_probability: Number(nsi.burn_probability ?? 0),
    distance_to_fuel_m: Number(nsi.distance_to_fuel_m ?? 0),
    canopy_cover_100m: Number(nsi.canopy_cover_100m ?? 0),
    slope_degrees: Number(nsi.slope_degrees ?? 0),
    is_res1,
  };
  const { p_destroyed, log_odds } = scoreDestruction(features);
  const val_struct = Number(nsi.val_struct ?? 0);
  const lambda_destroy = features.burn_probability * p_destroyed;
  const eal_recomputed = lambda_destroy * val_struct;

  return {
    query: {
      latitude: lat,
      longitude: lng,
      address: input.address,
      resolved_address: resolvedAddress,
      search_radius_m: input.search_radius_m,
    },
    match: {
      fd_id: nsi.fd_id,
      match_distance_m: Math.round(nsi.match_dist_m * 10) / 10,
      nsi_location: { latitude: nsi.lat, longitude: nsi.lng },
      occupancy_type: nsi.occtype,
      replacement_value_usd: val_struct,
      tract_fips: nsi.cbfips ? nsi.cbfips.slice(0, 11) : null,
    },
    features: {
      burn_probability: features.burn_probability,
      distance_to_fuel_m: features.distance_to_fuel_m,
      canopy_cover_30m: Number(nsi.canopy_cover_30m ?? 0),
      canopy_cover_100m: features.canopy_cover_100m,
      canopy_cover_300m: Number(nsi.canopy_cover_300m ?? 0),
      slope_degrees: features.slope_degrees,
      is_res1,
    },
    vulnerability_score: {
      p_destroyed: Math.round(p_destroyed * 10000) / 10000,
      log_odds: Math.round(log_odds * 1000) / 1000,
      exceeds_optimal_threshold: p_destroyed >= m.optimal_threshold,
      optimal_threshold: m.optimal_threshold,
      model_auc_roc: m.auc_roc,
      model_run_id: m.run_id,
      methodology_hash: m.methodology_hash,
    },
    loss_estimate: {
      lambda_destroy_per_year: Math.round(lambda_destroy * 1e6) / 1e6,
      expected_annual_loss_usd_recomputed: Math.round(eal_recomputed * 100) / 100,
      expected_annual_loss_usd_persisted: nsi.expected_annual_loss,
      return_period_for_total_loss_years:
        lambda_destroy > 0 ? Math.round(1.0 / lambda_destroy) : null,
    },
    methodology_summary: [
      "Risk Estimate = wildfire_likelihood × P(destroyed | features) × replacement_value (Klugman, Panjer & Willmot, Loss Models §6).",
      "wildfire_likelihood: USFS WRC FSim 270 m, LANDFIRE 2014 fuels.",
      "P(destroyed): logistic regression on 5 predictors (distance-to-fuel, canopy_cover_100m, slope, wildfire_likelihood, is_res1), calibrated against DINS from 5 Sonoma fires (AUC " +
        m.auc_roc.toFixed(3) +
        ").",
      "Replacement value: USACE NSI v2 val_struct (full total-loss assumption — see limitations).",
      "Caveat: wildfire_likelihood appears in both terms with opposite signs (conditioning effect), compressing the risk-estimate spread. See `packages/validation/reports/wildfire_loss/methodology.md` for the full discussion.",
    ].join(" "),
  };
}
