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
import { wildfireLoss, wildfireLossSchema } from "./tools/wildfire-loss.js";

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
  "Assesses wildfire risk for a property location. Returns calibrated risk estimate " +
    "with methodology documentation validated against CAL FIRE damage inspections.",
  wildfireLossSchema.shape,
  async (input) => ({
    content: [{ type: "text", text: JSON.stringify(await wildfireLoss(input), null, 2) }],
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
