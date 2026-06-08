# HEAVI MONTH 2 SPRINT
# Methodology Whitepaper + Design Partner Preparation

## Context

Month 1 shipped: geocoding, batch scoring, map UI, PDF export, real LBNL interconnection data. 10-state validation completed: 71% High among greenfield-eligible EIA installations, positive separation in 10/10 states.

Month 2 has two goals:
1. Package the methodology and validation into a publishable whitepaper (builds credibility with technical buyers at near-zero cost)
2. Prepare the product for design partner pilots (precision metric definition, pilot workflow, sample output packages)

---

## DELIVERABLE 1: METHODOLOGY WHITEPAPER

### Title
"Deterministic Validated Solar Site Suitability Assessment: A Multi-Criteria Framework Calibrated Against 6,321 US Solar Installations"

### Purpose
A technical document that:
- Establishes Heavi's methodology as rigorous and transparent
- Publishes validation results across 10 states
- Provides a citable reference for buyers presenting to their IC
- Differentiates from competitors who don't publish their methodology
- Costs nothing but time and builds credibility with technical buyers

### Format
Markdown → PDF (using the existing PDF generation pipeline). 12-15 pages. Written in academic style but accessible to a technical business audience (VP of Site Development, not a GIS PhD).

### Structure

**1. Abstract (0.5 page)**
One paragraph: what the framework does, how it was validated, key results.

"We present a deterministic multi-criteria solar site suitability framework that scores candidate parcels against 14 criteria (8 scored, 6 exclusion) drawn from 31 federal and open data sources. Criterion weights are calibrated per NERC region using constrained optimization against 6,321 EIA Form 860 solar installations. The framework includes a data selection engine that identifies the best available data source for each criterion at each location and reports confidence based on data quality. Validation across 10 US states shows 71% of greenfield-eligible real solar installations score High, with positive discrimination versus random locations in all 10 states."

**2. Introduction (1 page)**
- The solar site selection problem: IRA driving development, 2,060 GW in interconnection queues, developers screening hundreds of parcels
- Current approaches: GIS consultants (slow, expensive), enterprise platforms (require trained analysts), AI answer engines (unauditable)
- Gap: no approach tells you both the answer AND how much to trust it
- What this paper presents: a framework that produces auditable, confidence-rated assessments

**3. Methodology (3-4 pages)**

3.1 Framework Overview
- GIS-based Multi-Criteria Decision Analysis (GIS-MCDA)
- Weighted Linear Combination (WLC) with Analytic Hierarchy Process (AHP) weight derivation
- Two criterion types: scored (weighted) and exclusion (binary pass/fail)
- Reference: Doorga et al. (2019), Al-Shammari et al. (2026), Charabi & Gastli (2011)

3.2 Scored Criteria
Table of 8 scored criteria with: name, weight range from literature, default weight, data source, academic provenance.
- solar_transmission, solar_ghi, solar_slope, solar_road, solar_aspect, solar_land_cover, solar_soil, solar_ej
- For each: one sentence on why it matters, one sentence on the data source, citation

3.3 Exclusion Criteria
Table of 5 exclusion criteria (post-refinement) with: name, threshold, data source, provenance.
- excl_protected (GAP 1-2 only), excl_wetlands, excl_critical_habitat, excl_steep (>20%), excl_urban (NLCD 23-24)
- Rationale for each threshold, especially the GAP refinement and slope threshold

3.4 Data Selection Engine
- Problem: data availability varies by location. Not every source is available everywhere.
- Solution: quality-ordered data trees per criterion. For each criterion, the engine tries sources from highest quality to lowest.
- Example: wetlands criterion tree (NWI PostGIS → NWI REST → SSURGO hydric proxy)
- Confidence scoring: authoritative (1.0), fallback (0.7-0.9), proxy (0.4-0.5), none (0.0)
- Composite confidence with weakest-link exclusion factor

3.5 Regional Weight Calibration
- Problem: fixed weights don't generalize across US geographies
- Solution: constrained optimization (scipy SLSQP) per NERC region
- Training data: EIA Form 860 installations (positive examples) vs matched random locations (negative examples)
- Constraints: weights bounded to literature-supported ranges, sum to 1.0
- Result: 7 NERC-specific weight profiles

**4. Data Sources (1-2 pages)**
Table of all data sources used, grouped by category:
- Solar resource: NREL PVWatts v8, NREL NSRDB
- Terrain: USGS 3DEP
- Infrastructure: HIFLD transmission, OSM substations, EIA Form 860
- Environmental: USFWS NWI, USFWS Critical Habitat, USGS PAD-US, EPA EJScreen
- Land/soil: MRLC NLCD 2021, USDA SSURGO
- Interconnection: LBNL Queued Up 2025 (4,426 active solar projects)

For each: provider, coverage, resolution, vintage, known limitations.

**5. Validation (3-4 pages)**

5.1 Validation Design
- Ground truth: EIA Form 860 operating solar installations
- Metric: percentage scoring High (≥0.70) among greenfield-eligible installations
- Comparison: EIA installations vs matched random rural locations
- Coverage: 10 states across 5 NERC regions (TX, AZ, NC, NV, FL, CA, GA, CO, IN, OH)
- Sample: 15 EIA + 15 random per state = 300 total locations

5.2 Results
Full 10-state results table from the validation:
- Per-state: EIA %High, random %High, separation, confidence distribution
- National: 71% High among greenfield-eligible, +0.122 mean separation, 10/10 positive separation

5.3 Exclusion Analysis
- 28% of EIA installations excluded by design (rooftop/carport/campus on NLCD 23-24, wetland overlap)
- These are installation types the greenfield screening tool is not designed for
- Among 108 non-excluded installations: 71% High

5.4 Confidence Distribution
- Per-state confidence tier distribution
- Discussion of NWI wetland data gap affecting confidence nationally
- Honest documentation of data limitations

**6. Interconnection Context (1 page)**
- LBNL Queued Up dataset integration: 4,426 active solar projects
- Informational context (not a power-flow study): existing capacity, queue activity, ISO coverage
- County-centroid precision documented

**7. Known Limitations (1 page)**
Honest documentation:
- NWI wetlands: national REST service degraded, SSURGO proxy used outside loaded geographies
- FSim wildfire likelihood: NIFC historical frequency as proxy outside loaded geographies
- EJScreen: static 2024 data, EPA tool discontinued
- Interconnection: informational queue data, not capacity analysis or power-flow study
- Batch throughput: limited by API rate limits on free-tier data sources
- Validation: recall metric only; precision metric requires design partner feedback
- Single-founder engineering: methodology designed and implemented by a single person

**8. Conclusion (0.5 page)**
Summary of contributions: deterministic framework, confidence scoring, regional calibration, 10-state validation. Future work: precision metric from pilot data, expansion to additional modules (hazard, trade area), national data loading for remaining gaps.

**9. References**
All cited papers in standard academic format.

### Implementation

This is a DOCUMENT, not code. Generate it as a markdown file, then convert to a polished PDF using the existing reportlab pipeline (or a markdown → PDF tool like pandoc).

The whitepaper should be:
- Professional but not overly academic (accessible to VPs, not just PhDs)
- Honest about limitations (this builds trust)
- Data-dense (tables, numbers, specific metrics — not vague claims)
- Citable (proper references that a buyer could verify)

### Acceptance Criteria
1. Whitepaper generated as PDF, 12-15 pages
2. All 10-state validation results included with per-state table
3. All 14 criteria documented with academic citations
4. Data selection engine and confidence scoring explained clearly
5. Known limitations section is honest and specific
6. References section includes all cited papers
7. PDF is visually professional (not a raw markdown dump)

---

## DELIVERABLE 2: PRECISION METRIC FRAMEWORK

### Problem
Current validation measures RECALL: "what percentage of real solar installations does the tool identify as suitable?" This doesn't answer the developer's question: "of the sites your tool scores High, what percentage would I actually want to develop?"

Precision requires ground truth from a domain expert reviewing Heavi's output — which means it requires design partner pilots. But we can define the framework now so it's ready to measure during pilots.

### Framework

**Definition:**
Precision = (High-scored sites that pass developer review) / (total High-scored sites)

**What "pass developer review" means:**
The design partner's site development team reviews each High-scored parcel and classifies it as:
- **Would pursue**: the parcel is genuinely suitable for development consideration
- **Would not pursue**: the parcel has a flaw the tool didn't catch (wrong zoning, terrain issue not visible in 30m DEM, community opposition, grid constraint, etc.)
- **Already known**: the parcel is already in the developer's pipeline (validates the tool)

**Measurement protocol:**
1. Developer provides 50 candidate parcels (their own screening pipeline)
2. Heavi scores all 50
3. Heavi identifies the top 15 as High
4. Developer's team reviews the 15 High-scored parcels against their own criteria
5. Developer classifies each as would-pursue / would-not-pursue / already-known
6. Precision = (would-pursue + already-known) / 15

**Target:** ≥70% precision (at least 10 of 15 High-scored parcels pass developer review)

### Implementation

Create a design partner pilot template document:

```
HEAVI ENERGY — Design Partner Pilot Agreement

Pilot Duration: 90 days
Pilot Cost: Free

What Heavi Provides:
- Score up to 200 candidate parcels through the solar suitability platform
- Per-parcel PDF assessment with methodology documentation
- Batch results with map visualization and ranked list
- Interconnection context from LBNL queue data
- Weekly check-in calls to capture feedback

What the Design Partner Provides:
- 50-200 candidate parcels currently in their screening pipeline
- Expert review of Heavi's top-scored parcels (would-pursue / would-not-pursue classification)
- Feedback on: which criteria matter most, what's missing, what would make them pay
- A 30-minute call at days 30, 60, and 90

Success Criteria (defined jointly):
- Precision: ≥70% of High-scored parcels pass developer review
- Coverage: Heavi identifies ≥80% of parcels the developer independently selected
- Value: Developer reports time savings vs their current screening workflow

Conversion Discussion:
At day 90, discuss: annual subscription for continued scoring access ($25-50K/year)
```

### Acceptance Criteria
1. Precision metric framework documented in a markdown file
2. Design partner pilot template created as a markdown file (convertible to PDF)
3. Both committed to docs/

---

## DELIVERABLE 3: SAMPLE OUTPUT PACKAGE

### Purpose
Before reaching out to design partners, prepare a sample output package that demonstrates what they'd get. This is the "leave-behind" after a demo call.

### Contents

Generate a sample assessment for a real, recognizable solar development area. Use the area around an existing large-scale solar installation in California (e.g., Topaz Solar Farm area in San Luis Obispo County, or Solar Star in Kern County).

The sample package includes:
1. **Single-site PDF** for one location in the area
2. **Batch PDF** for 10 locations in the area (5 near existing installations + 5 random)
3. **Screenshot of the map UI** showing the batch results color-coded on the map
4. **One-page product overview** summarizing what Heavi Energy does, pricing ($25-50K/yr), and the pilot offer

### Implementation

Score 10 locations near Solar Star (Kern County) using the live product:
- 5 locations near the Solar Star installation (within 10km)
- 5 random agricultural locations in Kern County for comparison
- Generate the batch PDF
- Take a screenshot of the map UI showing all 10 scored locations

Create the one-page product overview as a markdown → PDF:
```
HEAVI ENERGY
Solar Site Screening for Renewable Development

What it does:
Score candidate parcels against 31 federal data sources with documented
methodology, confidence scoring, and interconnection context.

How it works:
Upload parcels (CSV or enter addresses) → automated scoring against 14
criteria → ranked results on a map → PDF export with methodology documentation

What makes it different:
Every assessment tells you the score AND how much to trust it — which
data sources were used, where the gaps are, and the peer-reviewed
methodology backing each criterion.

Validated:
71% of real EIA solar installations score High across 10 US states.
Positive discrimination in all 10 states. Weights calibrated per NERC
region against 6,321 installations.

Pricing:
Design partner pilot: Free for 90 days (up to 200 parcels)
Annual subscription: $25-50K/year (unlimited scoring)

Contact: [Danial's email and phone]
```

### Acceptance Criteria
1. 10-location batch scored near Solar Star, Kern County
2. Batch PDF generated with summary + per-site details
3. Map screenshot captured showing color-coded results
4. One-page product overview PDF generated
5. All materials committed to docs/sales/

---

## BUILD SEQUENCE

| Order | Deliverable | Effort | Who |
|---|---|---|---|
| 1 | Methodology whitepaper | 4-6 hours (Claude Code) | Claude Code generates content + PDF |
| 2 | Precision metric framework + pilot template | 1-2 hours (Claude Code) | Claude Code generates documents |
| 3 | Sample output package | 2-3 hours (Claude Code) | Claude Code scores locations + generates PDFs + screenshots |
| 4 | Design partner outreach | Ongoing (founder) | Danial — using the whitepaper + sample package as materials |

Total Claude Code effort: ~8-11 hours. Can run in a single session.
