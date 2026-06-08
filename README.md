# Heavi

**Deterministic, validated spatial site-screening for renewable-energy development.**

Heavi scores candidate land parcels for utility-scale solar suitability against 15 federal
and open data sources, and — unlike an AI answer engine — every result is auditable:
identical inputs always produce identical outputs, each parcel reports which data source
backed each criterion and how confident that source is, and every assessment carries the
peer-reviewed methodology behind its weights.

🔗 **Live demo:** [heavi-web.vercel.app](https://heavi-web.vercel.app) — open, no sign-in required.

> This is a public portfolio build of a working prototype. The deployed demo runs against a
> read-only backend; sign-in has been removed so anyone can try the three product modules.

---

## What it does

Heavi is a single spatial platform with three product surfaces:

- **Heavi Energy** — solar site screening. Score parcels (one location or a CSV batch) against
  14 criteria across 15 federal data sources, see them ranked and color-coded on a map with
  interconnection-queue context, and export audit-ready PDFs.
- **Heavi Hazard** — wildfire and flood risk assessment for property portfolios.
- **Heavi Locations** — trade-area analysis (demographics, competitive density, drive-time
  catchments) for retail/QSR expansion.

### How the solar scoring works (in brief)

Suitability is a weighted linear combination of normalized criterion sub-scores, with five
binary exclusion screens (critical habitat, protected areas, steep slope, developed land,
wetlands). Criterion weights are calibrated **per NERC region** by constrained optimization
against a ground-truth corpus of **6,321 EIA Form 860 operating solar installations**. A data
selection engine picks the best available source per criterion per location and reports a
weakest-link confidence tier — including an explicit "cannot assess" rather than a misleading
default when data is missing. Validation across 10 US states shows **71% recall among
greenfield-eligible installations** with positive discrimination versus matched random land in
all 10 states.

Full details: [docs/whitepaper/Heavi_Solar_Methodology_Whitepaper_Public.pdf](docs/whitepaper/Heavi_Solar_Methodology_Whitepaper_Public.pdf)
(also served at [`/whitepaper.pdf`](https://heavi-web.vercel.app/whitepaper.pdf) on the demo).

---

## Tech stack

**Web** (`packages/web`)
- Next.js 15 (App Router) · React 19 · TypeScript
- Tailwind CSS v4 · MapLibre GL · lucide-react
- Clerk (authentication — retained but unguarded in this public demo)
- jsPDF / html2canvas for client-side exports

**API** (`packages/api`)
- Python · FastAPI · Uvicorn
- PostgreSQL + PostGIS via asyncpg
- ReportLab (PDF generation) · SciPy (per-region weight calibration)

**Other packages**
- `packages/mcp-server` — a Model Context Protocol server exposing Heavi's spatial tools (TypeScript)
- `packages/data-catalog` — loaders for the federal/open datasets (Python)
- `packages/validation` — validation harnesses and methodology generation (Python)

Monorepo managed with **pnpm workspaces**.

### Data sources

15 federal and open datasets feed the solar framework, including NREL PVWatts (solar
resource), USGS 3DEP (terrain), HIFLD (transmission), USGS PAD-US (protected areas), USFWS
(critical habitat / wetlands), MRLC NLCD (land cover), USDA SSURGO (soils), FEMA NFHL (flood),
EIA Form 860 (ground truth), and the LBNL "Queued Up" interconnection queue.

---

## Repository layout

```
packages/
  web/           Next.js front end (the demo)
  api/           FastAPI scoring + PDF backend
  mcp-server/    MCP server exposing the spatial tools
  data-catalog/  Dataset loaders
  validation/    Validation + methodology harnesses
docs/
  whitepaper/    Methodology whitepaper (public summary)
  specs/         Engineering specs written to drive the build (see below)
  validation/    Validation summaries
  sales/         Sample output package (assessment + portfolio PDFs)
```

### About `docs/specs/`

`docs/specs/` holds the written feature specifications that drove this project. Each was
authored as a prompt-style brief and handed to Claude Code, which implemented the feature,
validated it, and recorded results under `docs/validation/`. They're kept in the repo as a
record of how the system was scoped and built.

---

## Running locally

The front end builds and runs standalone:

```bash
pnpm install
cd packages/web
cp .env.example .env.local   # add your own Clerk + API keys
pnpm dev
```

The API requires a PostGIS database loaded with the datasets above plus API keys
(`DATABASE_URL`, `NREL_API_KEY`, …); see `.env.example` at the repo root. Secrets live only in
gitignored `.env` / `.env.local` files and are never committed.

---

## Built with Claude Code

Heavi was designed and built **solo, with [Claude Code](https://claude.com/claude-code)** as
the implementation partner — from the scoring engine and data loaders to the validation
harnesses, PDF pipeline, and this front end. The specs in `docs/specs/` and validation
summaries in `docs/validation/` document that process.

---

*Heavi is a research/portfolio prototype. The scoring is transparent and reproducible, but it
has not been independently audited; assessments are informational and are not a substitute for
an engineering interconnection study or professional site diligence.*
