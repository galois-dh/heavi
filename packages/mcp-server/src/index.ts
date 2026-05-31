#!/usr/bin/env node

import { config } from "dotenv";
import { existsSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// Load .env from the monorepo root.
// When compiled: __dirname = packages/mcp-server/dist → 3 levels up
// Fallback: try relative to cwd, then absolute path
const __dirname = dirname(fileURLToPath(import.meta.url));
const candidates = [
  resolve(__dirname, "..", "..", "..", ".env"),
  resolve(process.cwd(), ".env"),
];
for (const candidate of candidates) {
  if (existsSync(candidate)) {
    config({ path: candidate });
    break;
  }
}

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { shutdown } from "./db.js";
import { spatialQuery, spatialQuerySchema } from "./tools/spatial-query.js";
import { siteSuitability, siteSuitabilitySchema } from "./tools/site-suitability.js";
import { bufferAnalysis, bufferAnalysisSchema } from "./tools/buffer-analysis.js";
import { dataLayers } from "./tools/data-layers.js";
import { enrichLocation, enrichLocationSchema } from "./tools/enrich-location.js";
import { wildfireLoss, wildfireLossSchema } from "./tools/wildfire-risk-assessment.js";
import {
  solarSiteSuitability,
  solarSiteSuitabilitySchema,
} from "./tools/solar-site-suitability.js";
import {
  floodRiskAssessment,
  floodRiskAssessmentSchema,
} from "./tools/flood-risk-assessment.js";
import {
  earthquakeRiskAssessment,
  earthquakeRiskAssessmentSchema,
} from "./tools/earthquake-risk-assessment.js";
import {
  tradeAreaAnalysis,
  tradeAreaAnalysisSchema,
} from "./tools/trade-area-analysis.js";

const server = new McpServer({
  name: "heavi",
  version: "0.1.0",
});

// --- Tools ---

server.tool(
  "spatial_query",
  "Translate a natural language spatial query into PostGIS SQL, execute it, and return GeoJSON results. " +
    "Use this for ad-hoc questions like 'show me all parks within 2km of downtown'.",
  spatialQuerySchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await spatialQuery(input), null, 2) }],
  }),
);

server.tool(
  "site_suitability",
  "Analyze a location for site suitability. Accepts coordinates and criteria weights, " +
    "scores the location based on proximity to features in all available data layers.",
  siteSuitabilitySchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await siteSuitability(input), null, 2) }],
  }),
);

server.tool(
  "buffer_analysis",
  "Find all features within a given distance of a geometry. " +
    "Accepts a GeoJSON geometry and buffer distance in meters, returns intersecting features.",
  bufferAnalysisSchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await bufferAnalysis(input), null, 2) }],
  }),
);

server.tool(
  "data_layers",
  "List all available spatial data layers in the catalog with their geometry types and feature counts.",
  {},
  async () => ({
    content: [{ type: "text", text: JSON.stringify(await dataLayers(), null, 2) }],
  }),
);

server.tool(
  "enrich_location",
  "Enrich a point location by auto-joining all relevant catalog layers. " +
    "Returns a profile with containing polygons and nearby features from every available layer.",
  enrichLocationSchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await enrichLocation(input), null, 2) }],
  }),
);

server.tool(
  "wildfire_risk_assessment",
  "Assesses wildfire risk for a property location. Returns a natural language risk " +
    "summary plus structured risk data with methodology documentation. Validated against " +
    "CAL FIRE damage inspections for Sonoma County wildfires 2017-2020. " +
    "When presenting results: use 'annual risk estimate' not 'expected annualized loss' " +
    "or 'expected annual loss'. Use 'risk assessment methodology' not 'actuarial framework' " +
    "or 'frequency-severity framework'. Use 'damage probability' not 'conditional destruction " +
    "probability'. Lead with the natural_language_summary. The structured data is for " +
    "programmatic consumers.",
  wildfireLossSchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await wildfireLoss(input), null, 2) }],
  }),
);

server.tool(
  "solar_site_suitability",
  "Scores parcels for solar development suitability or discovers candidate sites in a geography. " +
    "Two modes: provide coordinates or an address for scoring (works anywhere with data coverage), " +
    "or specify 'kern' to discover top-ranked parcels in Kern County. Returns multi-criteria " +
    "suitability scores with methodology documentation. Validated against EIA Form 860 solar " +
    "installations. " +
    "When presenting results: lead with the natural_language_summary. Use 'suitability score' not " +
    "technical criterion names. For discover mode, summarize the top results conversationally: " +
    "'I found X high-suitability parcels in Kern County, with the best scoring Y out of 1.0. The " +
    "top site is a Z-acre parcel with estimated capacity of W MW, driven by excellent grid access " +
    "and flat terrain.' Cite Doorga et al. (2019) for the methodology framework.",
  solarSiteSuitabilitySchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await solarSiteSuitability(input), null, 2) }],
  }),
);

server.tool(
  "flood_risk_assessment",
  "Assesses flood risk for any US property. Returns annual risk estimate in dollars " +
    "with FEMA flood zone, depth analysis, and HAZUS-based damage estimates. Works " +
    "nationally — no pre-loading required. " +
    "When presenting results: lead with the natural_language_summary. Use 'annual flood " +
    "risk estimate' not 'expected annual loss'. Mention the FEMA flood zone and whether " +
    "the property is above or below the base flood elevation. Cite HAZUS methodology.",
  floodRiskAssessmentSchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await floodRiskAssessment(input), null, 2) }],
  }),
);

server.tool(
  "earthquake_risk_assessment",
  "Assesses earthquake risk for any US property. Returns annual risk estimate " +
    "with seismic hazard analysis, site amplification, and HAZUS damage state " +
    "probabilities. Uses USGS 2023 National Seismic Hazard Model (served via " +
    "the ASCE 7-22 Design Maps web service). Works nationally — no pre-loading " +
    "required. " +
    "When presenting results: lead with the natural_language_summary. Mention " +
    "the PGA (bedrock and site-adjusted), the NEHRP site class, and the " +
    "building vulnerability (HAZUS type and code level). Cite USGS NSHM and HAZUS.",
  earthquakeRiskAssessmentSchema.shape,
  async (input) => ({
    content: [
      {
        type: "text",
        text: JSON.stringify(await earthquakeRiskAssessment(input), null, 2),
      },
    ],
  }),
);

server.tool(
  "trade_area_analysis",
  "Analyzes trade area demographics, competitive landscape, and accessibility for " +
    "candidate locations. Computes drive-time catchment areas with population, income, " +
    "daytime employment, and competitor density. Supports retail site selection, " +
    "healthcare facility siting, and CRE investment evaluation. Validated against " +
    "Starbucks locations in Dallas (96.7% score Strong). " +
    "When presenting results: lead with the natural_language_summary. Describe the trade " +
    "area in plain language: 'Within a 10-minute drive, there are X people, median income " +
    "$Y, and N competitors.' Mention cannibalization risk if existing locations were provided.",
  tradeAreaAnalysisSchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await tradeAreaAnalysis(input), null, 2) }],
  }),
);

// --- Lifecycle ---

async function main() {
  if (!process.env.DATABASE_URL) {
    console.error("WARNING: DATABASE_URL is not set. Tools will fail to connect to PostGIS.");
  }
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Heavi MCP server running on stdio");
}

process.on("SIGINT", async () => {
  await shutdown();
  process.exit(0);
});

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
