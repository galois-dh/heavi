import { z } from "zod";

// Flood risk is served by the Heavi API (on-demand FEMA NFHL + USACE NSI + USGS
// 3DEP + HAZUS depth-damage). This MCP tool is a thin client.
const API_BASE =
  process.env.HEAVI_API_URL ||
  process.env.API_URL ||
  "http://localhost:8000";

const METHODOLOGY_CITATION =
  "FEMA National Flood Hazard Layer (flood zone + Base Flood Elevation), USACE " +
  "National Structure Inventory exposure, USGS 3DEP elevation, and FEMA HAZUS " +
  "Flood Model depth-damage functions. Validated against OpenFEMA NFIP redacted " +
  "claims for Harris County, TX.";

export const floodRiskAssessmentSchema = z.object({
  latitude: z.number().min(-90).max(90).optional().describe("Latitude (WGS84). Either lat+lng or address is required."),
  longitude: z.number().min(-180).max(180).optional().describe("Longitude (WGS84)."),
  address: z.string().optional().describe("Street address (geocoded if lat/lng not provided)."),
});
export type FloodRiskAssessmentInput = z.infer<typeof floodRiskAssessmentSchema>;

type HazardV2Response = {
  query: Record<string, unknown>;
  wildfire: Record<string, unknown>;
  flood: Record<string, unknown>;
  confidence: {
    tier: string;
    composite: number;
    statement: string;
    gaps: string[];
    per_criterion: Record<string, unknown>;
  };
  methodology: Record<string, unknown>;
};

export async function floodRiskAssessment(input: FloodRiskAssessmentInput) {
  if (input.latitude === undefined && input.longitude === undefined && !input.address) {
    throw new Error("flood_risk_assessment: provide latitude+longitude or address");
  }
  const body: Record<string, unknown> = {};
  if (input.latitude !== undefined && input.longitude !== undefined) {
    body.latitude = input.latitude;
    body.longitude = input.longitude;
  }
  if (input.address) body.address = input.address;

  // v2: the combined hazard endpoint carries the selection-engine confidence.
  const res = await fetch(`${API_BASE}/hazard/score-v2`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`flood_risk_assessment: /hazard/score-v2 failed (${res.status}): ${await res.text()}`);
  }
  const d = (await res.json()) as HazardV2Response;

  return {
    query: d.query,
    flood: d.flood,
    // Confidence tier + data gaps so the agent can present data quality.
    confidence_tier: d.confidence?.tier,
    confidence_statement: d.confidence?.statement,
    data_gaps: d.confidence?.gaps ?? [],
    confidence: d.confidence,
    methodology_citation: METHODOLOGY_CITATION,
  };
}
