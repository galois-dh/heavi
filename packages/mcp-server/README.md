# Heavi MCP Server

Exposes Heavi's spatial analysis as tools that AI agents (Claude, ChatGPT, etc.)
can call through the [Model Context Protocol](https://modelcontextprotocol.io).
An agent can ask "is this a good site for a solar farm?" or "what's the wildfire
risk at this address?" and get back a structured, confidence-rated assessment.

## Available tools

**Scoring tools** — call the Heavi API (respect `HEAVI_API_URL`):

| Tool | What it does |
|---|---|
| `solar_site_suitability` | Score a parcel for utility-scale solar siting (14 criteria, regional weight calibration, confidence-rated, with interconnection context). |
| `wildfire_risk_assessment` | Assess wildfire risk and expected loss for a property. |
| `flood_risk_assessment` | Assess flood risk for a property. |
| `earthquake_risk_assessment` | Assess seismic/earthquake risk for a property. |
| `trade_area_analysis` | Score a retail/QSR trade area (Huff gravity model, Census demographics, competitive density, drive-time isochrones). |

**Spatial tools** — query the PostGIS catalog directly (need `DATABASE_URL`):

| Tool | What it does |
|---|---|
| `site_suitability` | Generic multi-criteria suitability score for a location. |
| `spatial_query` | Ad-hoc spatial questions, e.g. "all parks within 2km of downtown". |
| `buffer_analysis` | Buffer a GeoJSON geometry by N meters and return intersecting features. |
| `data_layers` | List the available spatial data layers with geometry types and feature counts. |
| `enrich_location` | Profile a coordinate with its containing polygons and nearby features from every layer. |

## How to run it

### Step 1 — Start the Heavi API locally

```bash
cd packages/api
python -m uvicorn app.main:app
```

The API needs a PostGIS database and API keys (`DATABASE_URL`, `NREL_API_KEY`, …);
see `.env.example` at the repo root.

### Step 2 — Point the MCP server at the API

```bash
export HEAVI_API_URL=http://localhost:8000
# the spatial tools also need a PostGIS connection:
export DATABASE_URL=postgresql://...
```

### Step 3 — Install and run the MCP server

```bash
cd packages/mcp-server
pnpm install
pnpm build      # compiles TypeScript to dist/
pnpm start      # runs the stdio MCP server (node dist/index.js)
```

During development use `pnpm dev` (watch mode) instead of `build` + `start`.

### Step 4 — Connect your AI client

For **Claude Desktop**, add the server to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "heavi": {
      "command": "node",
      "args": ["/absolute/path/to/heavi/packages/mcp-server/dist/index.js"],
      "env": {
        "HEAVI_API_URL": "http://localhost:8000",
        "DATABASE_URL": "postgresql://..."
      }
    }
  }
}
```

Restart the client; the Heavi tools then appear and the agent can call them.

## Example usage

**You ask Claude:**

> Is 35.35, -119.05 a good site for a solar farm?

**Claude calls `solar_site_suitability`** and gets back a structured assessment it
can explain:

```json
{
  "score": 78,
  "rating": "High",
  "weight_profile": "WECC (calibrated)",
  "confidence": { "tier": "HIGH", "composite": 0.95 },
  "criteria": {
    "Transmission proximity": { "score": 86, "source": "HIFLD Transmission Lines", "confidence": "HIGH" },
    "Solar resource (GHI)": { "score": 67, "source": "NREL PVWatts v8", "confidence": "HIGH" }
  },
  "interconnection": { "nearest_substation_mi": 1.7, "iso": "CAISO" }
}
```

Claude then answers in plain language — the score, which data backed each
criterion, how confident the result is, and where any gaps are.

## Configuration

The MCP server connects to a local Heavi API instance by default. To point it at
a deployed instance, set the `HEAVI_API_URL` environment variable.
