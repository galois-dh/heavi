import { z } from "zod";

// Earthquake risk is served by the Heavi API (on-demand USGS ASCE 7-22 Design
// Maps + USGS 3DEP + USACE NSI + HAZUS fragility curves). Thin MCP client.
const API_BASE =
  process.env.HEAVI_API_URL ||
  process.env.API_URL ||
  "https://heavi-production.up.railway.app";

const METHODOLOGY_CITATION =
  "USGS ASCE 7-22 Design Maps (bedrock PGA at 2% in 50-yr MCEr level), Wald & " +
  "Allen (2007) slope-based VS30 site amplification from USGS 3DEP elevation, " +
  "USACE National Structure Inventory exposure, and FEMA HAZUS 5.1 Earthquake " +
  "Model lognormal fragility curves.";

export const earthquakeRiskAssessmentSchema = z.object({
  latitude: z
    .number()
    .min(-90)
    .max(90)
    .optional()
    .describe("Latitude (WGS84). Either lat+lng or address is required."),
  longitude: z
    .number()
    .min(-180)
    .max(180)
    .optional()
    .describe("Longitude (WGS84)."),
  address: z
    .string()
    .optional()
    .describe("Street address (geocoded if lat/lng not provided)."),
});
export type EarthquakeRiskAssessmentInput = z.infer<
  typeof earthquakeRiskAssessmentSchema
>;

type EarthquakeResponse = {
  natural_language_summary: string;
  query: Record<string, unknown>;
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
  structure: Record<string, unknown> | null;
  damage_state_probabilities: Record<string, unknown>;
  risk_estimate: {
    annual_risk_estimate_usd: number;
    risk_tier: string;
  };
  methodology_note: string;
};

export async function earthquakeRiskAssessment(
  input: EarthquakeRiskAssessmentInput,
) {
  if (
    input.latitude === undefined &&
    input.longitude === undefined &&
    !input.address
  ) {
    throw new Error(
      "earthquake_risk_assessment: provide latitude+longitude or address",
    );
  }
  const body: Record<string, unknown> = {};
  if (input.latitude !== undefined && input.longitude !== undefined) {
    body.latitude = input.latitude;
    body.longitude = input.longitude;
  }
  if (input.address) body.address = input.address;

  const res = await fetch(`${API_BASE}/earthquake/risk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(
      `earthquake_risk_assessment: /earthquake/risk failed (${res.status}): ${await res.text()}`,
    );
  }
  const d = (await res.json()) as EarthquakeResponse;

  return {
    natural_language_summary: d.natural_language_summary,
    query: d.query,
    hazard: d.hazard,
    site: d.site,
    damage_state_probabilities: d.damage_state_probabilities,
    risk_estimate: d.risk_estimate,
    structure: d.structure,
    methodology_citation: METHODOLOGY_CITATION,
  };
}
