import { z } from "zod";

// Trade-area analysis is served by the Heavi API (Census ACS + OpenRouteService
// isochrones + LEHD + OSM POIs + Huff model). This MCP tool is a thin client.
const API_BASE =
  process.env.HEAVI_API_URL ||
  process.env.API_URL ||
  "http://localhost:8000";

const METHODOLOGY_CITATION =
  "Multi-criteria retail trade-area model: OpenRouteService drive-time isochrones " +
  "intersected with Census ACS5 demographics and LEHD daytime jobs, OSM " +
  "competitive analysis, and Huff (1963, 1964) gravity-model cannibalization. " +
  "Validated against Dallas Starbucks locations (96.7% score Strong).";

export const tradeAreaAnalysisSchema = z.object({
  mode: z
    .enum(["score", "discover"])
    .describe(
      "'score' to evaluate a specific location (coordinates or address); " +
        "'discover' to find top candidate locations in a geography.",
    ),
  latitude: z.number().min(-90).max(90).optional().describe("Score mode: latitude (WGS84)."),
  longitude: z.number().min(-180).max(180).optional().describe("Score mode: longitude (WGS84)."),
  address: z.string().optional().describe("Score mode: street address (geocoded if lat/lng omitted)."),
  business_category: z
    .string()
    .optional()
    .default("coffee_shop")
    .describe(
      "Business type for competitive analysis: coffee_shop, pharmacy, restaurant, " +
        "fast_food, bank, gym, grocery, urgent_care (or a custom OSM category).",
    ),
  existing_locations: z
    .array(z.object({ latitude: z.number(), longitude: z.number(), name: z.string().optional() }))
    .optional()
    .describe("Score mode: customer's current stores, for Huff cannibalization analysis."),
  geography: z
    .string()
    .optional()
    .default("dallas")
    .describe("Discover mode: geography to scan ('dallas' is the pre-loaded demo)."),
  top_n: z.number().int().min(1).max(100).optional().default(25).describe("Discover mode: candidates to return."),
});
export type TradeAreaAnalysisInput = z.infer<typeof tradeAreaAnalysisSchema>;

async function postJson(path: string, body: unknown): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`trade_area_analysis: ${path} failed (${res.status}): ${await res.text()}`);
  }
  return (await res.json()) as Record<string, unknown>;
}

export async function tradeAreaAnalysis(input: TradeAreaAnalysisInput) {
  if (input.mode === "discover") {
    const d = await postJson("/trade-area/discover", {
      geography: input.geography,
      business_category: input.business_category,
      top_n: input.top_n,
    });
    return { mode: "discover", ...d, methodology_citation: METHODOLOGY_CITATION };
  }

  // Score mode.
  if (input.latitude === undefined && input.longitude === undefined && !input.address) {
    throw new Error("trade_area_analysis: score mode needs latitude+longitude or address");
  }
  const body: Record<string, unknown> = { business_category: input.business_category };
  if (input.latitude !== undefined && input.longitude !== undefined) {
    body.latitude = input.latitude;
    body.longitude = input.longitude;
  }
  if (input.address) body.address = input.address;
  if (input.existing_locations) body.existing_locations = input.existing_locations;

  // v2: wired through the selection engine — carries per-criterion confidence
  // and the POI/daytime source actually used.
  const d = (await postJson("/trade-area/score-v2", body)) as Record<string, unknown>;
  const confidence = (d.confidence ?? {}) as Record<string, unknown>;
  return {
    mode: "score",
    query: d.query,
    coverage: d.coverage,
    suitability_score: d.suitability_score,
    suitability_rating: d.suitability_rating,
    criteria_scores: d.criteria_scores,
    competitive_analysis: d.competitive_analysis,
    cannibalization: d.cannibalization,
    data_sources_used: d.data_sources_used,
    // Confidence tier + data gaps so the agent can present data quality.
    confidence_tier: confidence.tier,
    data_gaps: confidence.gaps ?? [],
    confidence,
    methodology_citation: METHODOLOGY_CITATION,
  };
}
