import { z } from "zod";

// Wildfire risk is served by the Heavi API v2 combined-hazard endpoint
// (POST /hazard/score-v2), which scores wildfire with the Sonoma vulnerability
// model and carries the data-selection-engine confidence report. This MCP tool
// is a thin client. (Previously it queried PostGIS + re-scored the model
// in-process; that logic now lives behind the v2 endpoint.)
const API_BASE =
  process.env.HEAVI_API_URL ||
  process.env.API_URL ||
  "http://localhost:8000";

const METHODOLOGY_NOTE =
  "Annual risk estimate computed from USFS wildfire likelihood data, a " +
  "vulnerability model validated against CAL FIRE damage inspections " +
  "(AUC 0.76), and USACE structure replacement values. See methodology " +
  "documentation for full data lineage and known limitations.";

// ─── Schema (unchanged for backward compatibility) ─────────────────────────
export const wildfireLossSchema = z.object({
  latitude: z.number().min(-90).max(90).optional().describe("Latitude (WGS84). Either lat+lng or address is required."),
  longitude: z.number().min(-180).max(180).optional().describe("Longitude (WGS84)."),
  address: z.string().optional().describe("Street address (geocoded if lat/lng not provided)."),
  search_radius_m: z
    .number()
    .min(10)
    .max(5000)
    .optional()
    .default(500)
    .describe("Search radius in metres for nearest NSI structure (default 500 m). Reserved; the v2 endpoint uses its own default."),
});
export type WildfireLossInput = z.infer<typeof wildfireLossSchema>;

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

// ─── Tool ─────────────────────────────────────────────────────────────────
export async function wildfireLoss(input: WildfireLossInput) {
  if (input.latitude === undefined && input.longitude === undefined && !input.address) {
    throw new Error("wildfire_loss: must provide either latitude+longitude or address");
  }
  const body: Record<string, unknown> = {};
  if (input.latitude !== undefined && input.longitude !== undefined) {
    body.latitude = input.latitude;
    body.longitude = input.longitude;
  }
  if (input.address) body.address = input.address;

  const res = await fetch(`${API_BASE}/hazard/score-v2`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`wildfire_loss: /hazard/score-v2 failed (${res.status}): ${await res.text()}`);
  }
  const d = (await res.json()) as HazardV2Response;

  return {
    query: d.query,
    wildfire: d.wildfire,
    // Confidence tier + data gaps so the agent can present data quality.
    confidence_tier: d.confidence?.tier,
    confidence_statement: d.confidence?.statement,
    data_gaps: d.confidence?.gaps ?? [],
    confidence: d.confidence,
    methodology_note: METHODOLOGY_NOTE,
  };
}
