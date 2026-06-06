# HEAVI — PRE-SEED INVESTOR MEMO
## Heaviside Intelligence, Inc.

**Founder:** Danial Hazarika | Wharton MBA (on leave) | Former VP GTM, Felt Maps; VP Enterprise Revenue, Matterport ($10M→$100M); VP Enterprise Revenue, Checkr ($10M→$150M)

**Stage:** Pre-seed | Solo founder | Product live at heavi-web.vercel.app

**Ask:** [To be determined]

---

## One sentence

Heavi produces auditable spatial analysis — not scores, not dashboards, but documented, validated, confidence-rated assessments that tell you both the answer and how much to trust it.

## The problem

Consequential spatial decisions — where to build a solar farm, whether a property portfolio is exposed to wildfire, where to open the next store — require spatial analysis that is currently delivered by one of three channels:

1. **GIS consultants** ($150-300/hr, 4-8 week engagements, methodology locked in their heads)
2. **Enterprise GIS platforms** (Esri, $50-250K/yr licenses, require trained analysts to operate)
3. **AI answer engines** (fast, cheap, unverifiable — you get a number but no way to audit it)

The first two are slow and expensive. The third is fast and cheap but unauditable. None of them tell you how much to trust the answer based on what data was actually available.

## What Heavi builds

A deterministic validated spatial analysis platform with three product experiences:

**Heavi Energy** — Solar site screening for renewable developers. Score candidate parcels against 31 federal data sources. Weights calibrated per NERC region against 6,321 real EIA Form 860 installations. Validated at 52% High nationally (77% among non-excluded parcels).

**Heavi Hazard** — Natural hazard intelligence for CRE investors, lenders, and portfolio managers. Multi-peril property risk assessment (wildfire, flood, earthquake) with per-structure dollar estimates and portfolio aggregation.

**Heavi Locations** — Trade area and site intelligence for retail, QSR, healthcare, and bank-branch expansion. Huff gravity model with Census demographics, competitive density, cannibalization detection.

All three products share a common platform architecture:

- **Data Repository** — 31 verified federal and open data sources with availability checking
- **Methodology Repository** — Every criterion grounded in peer-reviewed literature (Doorga 2019, Hernandez 2015, Huff 1963, Scawthorn 2006, Finney 2011). Academic citations attached to every output.
- **Data Selection Engine** — For each location, finds the best available data for each criterion by traversing quality-ordered data trees. Reports confidence based on what was actually used.
- **Confidence Scoring** — Every output includes a confidence tier (HIGH/MODERATE/LOW/INSUFFICIENT/CANNOT ASSESS) with per-criterion quality breakdown, data gaps, and strongest/weakest data identification. This is the core differentiator: Heavi tells you how much to trust the answer.

## Why now

Three converging tailwinds:

1. **Federal data availability** — NREL, USGS, FEMA, USACE, EPA, Census, and LANDFIRE all publish authoritative spatial data via REST APIs. The data exists; the value is in knowing which sources to use, in what order, for what question.

2. **AI agent delivery** — LLMs can consume Heavi's MCP tools and deliver spatial analysis through conversational interfaces. Heavi is the deterministic engine behind the AI agent — the agent asks questions, Heavi produces auditable answers.

3. **Solar siting demand** — The Inflation Reduction Act triggered a wave of solar development. Developers need to screen hundreds of candidate parcels down to the 15-20 worth sending an interconnection engineer to. The current workflow is a GIS analyst spending 4 months. Heavi does it in minutes.

## Architecture differentiator

GIS platforms sell the kitchen. Data platforms sell ingredients. AI agents produce answers you can't verify. Heavi produces auditable analysis — the output documents exactly which data was used, from which source, at what quality level, backed by which peer-reviewed methodology, with what known limitations.

The confidence scoring system is the product. Every competitor gives you a score. Heavi gives you a score AND tells you:
- Which of the 31 data sources were available at this location
- Which criteria used authoritative data vs proxy data
- Where the data gaps are and what they mean
- The academic citation backing each criterion weight

This is what makes the output usable for board presentations, LP reports, lender due diligence, and regulatory submissions.

## Validation

All metrics are honestly reported with their geographic scope:

| Module | Metric | Value | Geography | Notes |
|---|---|---|---|---|
| Solar | % of real EIA installations scoring High | 52% nationally | 5 states (TX, AZ, NC, NV, FL) | 77% among non-excluded parcels. Regional weights calibrated per NERC region. |
| Solar | EIA-vs-random separation | Positive in 5/5 states | TX, AZ, NC, NV, FL | Real solar farms consistently score higher than random locations. |
| Wildfire | AUC-ROC | 0.76 | Sonoma County, CA | Logistic regression calibrated against CAL FIRE DINS. |
| Flood | Discrimination ratio | 16× | Lee County, FL (Hurricane Ian) | High-risk scores correlate with actual NFIP claims. |
| Trade Area | % of Starbucks scoring Strong | 96.7% | Dallas County, TX | Professionally selected sites outperform random. |

**What we don't yet claim:** Multi-geography validation across all modules. Solar is validated in 5 states. Wildfire, flood, and trade area are validated in single geographies. Expanding validation coverage is the next priority.

## Market

Three beachheads with distinct buyers:

1. **Solar site origination** (lead wedge) — VP Site Development at solar/wind developers. Displaces a 4-month GIS analyst workflow with a minutes-scale automated screen. TAM: ~200 utility-scale developers × $100-500K/yr = $20-100M.

2. **CRE portfolio risk** — VP Acquisitions, Chief Risk Officer at institutional investors, REITs, commercial lenders. Displaces consulting engagements and manual FEMA lookups. TAM: ~2,000 institutional investors × $50-200K/yr = $100-400M.

3. **Retail site selection** — VP Real Estate Expansion at chains (QSR, retail, healthcare, banking). Displaces Esri Business Analyst and consulting. TAM: ~5,000 multi-location businesses × $25-100K/yr = $125-500M.

## Go-to-market

Three delivery channels:

1. **Web platform** — heavi-web.vercel.app. Self-service for smaller customers and design partner pilots.
2. **API** — For integration into customer workflows, data pipelines, and internal tools.
3. **MCP / AI agent** — Heavi's tools are consumable by LLM agents. A developer can say "score this parcel" and get a complete assessment through a conversational interface. This is the distribution moat.

Initial outbound targets identified from a 2,000-transcript sales call analysis: MSCI (portfolio spatial risk), Mission Critical RE/Edged Energy (manual site screening), Foundry Commercial/VIA ONE (spatial analysis without GIS expertise), 21+ companies with documented Esri dissatisfaction.

## Technical stack

- **Backend:** Python/FastAPI on Railway
- **Frontend:** Next.js on Vercel
- **Database:** Supabase PostGIS (Pro tier)
- **Data Sources:** 31 federal and open sources (NREL, USGS, FEMA, USACE, Census, LANDFIRE, NIFC, USFWS, EPA, OSM)
- **Methodology:** Peer-reviewed GIS-MCDA framework with constrained AHP weight optimization

## Founder-market fit

Danial's background uniquely positions him at the intersection of enterprise sales, spatial data, and insurance/risk:

- **Enterprise GTM:** Scaled Checkr from $10M to $150M and Matterport from $10M to $100M (driving profitability). Knows how to sell to enterprise buyers.
- **Spatial data:** Matterport (spatial data company) + Felt Maps (GIS platform) = deep understanding of how spatial analysis is used, bought, and valued.
- **Actuarial foundation:** Farmers Insurance actuarial pricing background. Understands how risk models are built, validated, and trusted.
- **Wharton MBA** (on leave): Analytical rigor applied to market strategy.

## Current state and next steps

**Live now:** Three product experiences with map-based UI, data selection engine, confidence scoring, methodology documentation, MCP tools. All deployed and functional.

**Next 90 days:**
1. Design partner pilots (2-3 energy developers for solar siting)
2. Multi-geography validation (expand wildfire/flood/trade area beyond single-geography)
3. Map-based delivery surface polish (batch upload, portfolio views, PDF export)
4. Load additional national datasets (FSim raster nationally, Census LEHD beyond Dallas)

**Next 6 months:**
1. First paying customers from design partner conversions
2. Expand to wind siting (similar methodology, different criteria weights)
3. Build out the data moat (more sources, more geographies, more validation)
