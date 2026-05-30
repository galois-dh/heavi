import { z } from "zod";

// Flood risk is served by the Heavi API (on-demand FEMA NFHL + USACE NSI + USGS
// 3DEP + HAZUS depth-damage). This MCP tool is a thin client.
const API_BASE =
  process.env.HEAVI_API_URL ||
  process.env.API_URL ||
  "https://heavi-production.up.railway.app";

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

type FloodResponse = {
  natural_language_summary: string;
  query: Record<string, unknown>;
  flood_zone: {
    zone: string | null;
    zone_subtype: string | null;
    static_bfe_ft: number | null;
    in_special_flood_hazard_area: boolean;
    annual_exceedance_probability: number;
    return_period_years: number;
  };
  structure: Record<string, unknown> | null;
  elevation: Record<string, unknown>;
  damage: Record<string, unknown>;
  risk_estimate: {
    annual_risk_estimate_usd: number;
    risk_tier: string;
  };
  methodology_note: string;
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

  const res = await fetch(`${API_BASE}/flood/risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`flood_risk_assessment: /flood/risk failed (${res.status}): ${await res.text()}`);
  }
  const d = (await res.json()) as FloodResponse;

  // Lead with the human-readable summary; pass through the structured detail.
  return {
    natural_language_summary: d.natural_language_summary,
    query: d.query,
    flood_zone: d.flood_zone,
    elevation: d.elevation,
    damage: d.damage,
    risk_estimate: d.risk_estimate,
    structure: d.structure,
    methodology_citation: METHODOLOGY_CITATION,
  };
}
