import { z } from "zod";

// The solar suitability tool is served by the Heavi API (it reads pre-enriched
// PostGIS columns and runs the multi-criteria scoring); the MCP tool is a thin
// client. Base URL from env, defaulting to the hosted API.
const API_BASE =
  process.env.HEAVI_API_URL ||
  process.env.API_URL ||
  "https://heavi-production.up.railway.app";

const METHODOLOGY_CITATION =
  "Multi-criteria weighted-overlay framework (Doorga et al. 2019; Charabi & " +
  "Gastli 2011), capacity from the NREL land-use factor (Ong et al. 2016), and " +
  "environmental exclusions from Hernandez et al. (2015). Grid-dominant weights " +
  "tuned for the California Central Valley and validated against EIA Form 860 " +
  "solar installations in Kern County.";

// ─── Schema ───────────────────────────────────────────────────────────────
export const solarSiteSuitabilitySchema = z.object({
  mode: z
    .enum(["score", "discover"])
    .describe(
      "'score' to evaluate a specific parcel by coordinates/address (works anywhere " +
        "with data coverage); 'discover' to find top-ranked candidate parcels in a geography.",
    ),
  latitude: z.number().min(-90).max(90).optional().describe("Score mode: latitude (WGS84)."),
  longitude: z.number().min(-180).max(180).optional().describe("Score mode: longitude (WGS84)."),
  address: z
    .string()
    .optional()
    .describe("Score mode: street address (geocoded via Nominatim if lat/lng omitted)."),
  geography: z
    .string()
    .optional()
    .default("kern")
    .describe("Discover mode: geography to search. 'kern' for Kern County, CA (the pre-loaded demo geography)."),
  top_n: z.number().int().min(1).max(100).optional().default(10).describe("Discover mode: number of top parcels to return (default 10)."),
  min_acreage: z.number().min(0).optional().default(10).describe("Discover mode: minimum parcel acreage (default 10)."),
});
export type SolarSiteSuitabilityInput = z.infer<typeof solarSiteSuitabilitySchema>;

// ─── API response shapes (subset we read) ──────────────────────────────────
type Criteria = {
  solar_irradiance_ghi_kwh_m2_day: number | null;
  solar_irradiance_score: number;
  grid_distance_km: number | null;
  grid_proximity_score: number;
  slope_percent: number | null;
  slope_score: number;
  aspect_score: number;
  soil_capability_class: number | null;
  soil_score: number;
  road_distance_km: number | null;
  road_access_score: number;
  land_use_category: string | null;
  land_use_score: number;
};
type SolarResult = {
  parcel_id: string;
  suitability_score: number;
  suitability_rating: "High" | "Moderate" | "Low";
  acreage: number | null;
  estimated_capacity_mw: number;
  location: { longitude: number | null; latitude: number | null };
  criteria_scores: Criteria;
  constraints_passed: Record<string, boolean>;
  natural_language_summary: string;
};
type DiscoverResponse = {
  portfolio_summary: {
    total_parcels_evaluated: number;
    parcels_passing_constraints: number;
    total_estimated_capacity_mw: number;
    score_distribution: { High: number; Moderate: number; Low: number };
    returned: number;
  };
  results: SolarResult[];
  error?: string;
  available_geographies?: string[];
};
type ScoreResponse = { parcel_count: number; scored_count: number; results: SolarResult[] };

// ─── Geocoding fallback (matches the wildfire tool) ────────────────────────
async function geocodeNominatim(address: string): Promise<{ lat: number; lng: number; display: string } | null> {
  const url =
    "https://nominatim.openstreetmap.org/search?" +
    new URLSearchParams({ q: address, format: "json", limit: "1", countrycodes: "us" }).toString();
  const r = await fetch(url, { headers: { "User-Agent": "Heavi/0.1 (solar-suitability-mcp)" } });
  if (!r.ok) return null;
  const data = (await r.json()) as Array<{ lat: string; lon: string; display_name: string }>;
  if (!data.length) return null;
  return { lat: parseFloat(data[0].lat), lng: parseFloat(data[0].lon), display: data[0].display_name };
}

// Top scoring factors of a parcel, in plain language (for the discover summary).
function topFactors(c: Criteria): string[] {
  const ranked: [number, string][] = [
    [c.grid_proximity_score, "excellent grid access"],
    [c.slope_score, "flat terrain"],
    [c.solar_irradiance_score, "strong solar resource"],
    [c.road_access_score, "strong road access"],
    [c.soil_score, "suitable foundation soils"],
    [c.land_use_score, "favorable agricultural land use"],
    [c.aspect_score, "south-facing orientation"],
  ];
  return ranked
    .sort((a, b) => b[0] - a[0])
    .slice(0, 2)
    .map(([, phrase]) => phrase);
}

// ─── Tool ─────────────────────────────────────────────────────────────────
export async function solarSiteSuitability(input: SolarSiteSuitabilityInput) {
  if (input.mode === "score") {
    // Resolve coordinates.
    let lat = input.latitude;
    let lng = input.longitude;
    let resolvedAddress: string | null = null;
    if (lat === undefined || lng === undefined) {
      if (!input.address) {
        throw new Error("solar_site_suitability: score mode needs latitude+longitude or address");
      }
      const g = await geocodeNominatim(input.address);
      if (!g) throw new Error(`solar_site_suitability: could not geocode '${input.address}'`);
      lat = g.lat;
      lng = g.lng;
      resolvedAddress = g.display;
    }

    // POST a single-point GeoJSON feature to /solar/score (multipart upload).
    const fc = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { id: input.address ?? `${lat.toFixed(5)},${lng.toFixed(5)}` },
          geometry: { type: "Point", coordinates: [lng, lat] },
        },
      ],
    };
    const form = new FormData();
    form.append("file", new Blob([JSON.stringify(fc)], { type: "application/geo+json" }), "parcel.geojson");
    const res = await fetch(`${API_BASE}/solar/score`, { method: "POST", body: form });
    if (!res.ok) {
      throw new Error(`solar_site_suitability: /solar/score failed (${res.status}): ${await res.text()}`);
    }
    const data = (await res.json()) as ScoreResponse;
    const r = data.results?.[0];
    if (!r) {
      return {
        natural_language_summary: "No suitability result was produced for this location (no data coverage).",
        mode: "score",
        query: { latitude: lat, longitude: lng, address: input.address, resolved_address: resolvedAddress },
      };
    }
    return {
      // Lead with the human-readable summary so the agent presents it first.
      natural_language_summary: r.natural_language_summary,
      mode: "score",
      query: { latitude: lat, longitude: lng, address: input.address, resolved_address: resolvedAddress },
      suitability_score: r.suitability_score,
      suitability_rating: r.suitability_rating,
      acreage: r.acreage,
      estimated_capacity_mw: r.estimated_capacity_mw,
      criteria_scores: r.criteria_scores,
      constraints_passed: r.constraints_passed,
      methodology_citation: METHODOLOGY_CITATION,
    };
  }

  // ── Discover mode ─────────────────────────────────────────────────────────
  const res = await fetch(`${API_BASE}/solar/discover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      geography: input.geography,
      top_n: input.top_n,
      min_acreage: input.min_acreage,
    }),
  });
  if (!res.ok) {
    throw new Error(`solar_site_suitability: /solar/discover failed (${res.status}): ${await res.text()}`);
  }
  const data = (await res.json()) as DiscoverResponse;
  if (data.error) {
    return {
      natural_language_summary: data.error,
      mode: "discover",
      geography: input.geography,
      available_geographies: data.available_geographies,
    };
  }

  const s = data.portfolio_summary;
  const top = data.results[0];
  let summary: string;
  if (top) {
    const factors = topFactors(top.criteria_scores);
    summary =
      `I found ${s.parcels_passing_constraints.toLocaleString("en-US")} parcels passing the ` +
      `development constraints in ${input.geography} ` +
      `(${s.score_distribution.High.toLocaleString("en-US")} scoring High). The best of the top ` +
      `${data.results.length} scores ${top.suitability_score.toFixed(2)} out of 1.0 — a ` +
      `${top.acreage ?? "?"}-acre parcel with an estimated capacity of ${top.estimated_capacity_mw} MW, ` +
      `driven by ${factors[0]}${factors[1] ? ` and ${factors[1]}` : ""}. ` +
      `Total estimated capacity across passing parcels: ` +
      `${Math.round(s.total_estimated_capacity_mw).toLocaleString("en-US")} MW.`;
  } else {
    summary = `No parcels matched the constraints in ${input.geography}.`;
  }

  return {
    // Lead with the conversational summary.
    natural_language_summary: summary,
    mode: "discover",
    geography: input.geography,
    portfolio_summary: s,
    top_parcels: data.results.map((r) => ({
      parcel_id: r.parcel_id,
      suitability_score: r.suitability_score,
      suitability_rating: r.suitability_rating,
      acreage: r.acreage,
      estimated_capacity_mw: r.estimated_capacity_mw,
      location: r.location,
      criteria_scores: r.criteria_scores,
      natural_language_summary: r.natural_language_summary,
    })),
    methodology_citation: METHODOLOGY_CITATION,
  };
}
