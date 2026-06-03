# HEAVI METHODOLOGY & DATA PROVENANCE
# Academic Grounding for Criterion Selection, Data Source Hierarchy, and Scoring Methodology

*Working document — June 2026*

---

## Purpose

This document grounds every criterion choice and data source selection in peer-reviewed literature or authoritative agency methodology. It serves three functions:

1. **Product foundation** — the methodology repository is seeded from this document
2. **Investor diligence** — every methodology claim traces to a published source
3. **Output provenance** — every scored assessment cites the relevant literature

The document follows the platform architecture: for each analysis workflow, each criterion has a data tree with provenance at every node.

---

# WORKFLOW 1: SOLAR SITE SUITABILITY

## Methodological Framework

The GIS-based multi-criteria decision analysis (GIS-MCDA) for solar site selection is one of the most extensively studied applications in renewable energy planning. The methodology is well-established across dozens of peer-reviewed studies spanning 15+ years.

### Primary Framework Sources

**Doorga, J.R.S., Rughooputh, S.D.D.V., & Boojhawon, R. (2019).** "Multi-criteria GIS-based modelling approach for the identification of suitable sites for the construction of photovoltaic solar plants." *Renewable and Sustainable Energy Reviews*, 104: 133-146.

Establishes the AHP (Analytic Hierarchy Process) + WLC (Weighted Linear Combination) framework with 9 criteria. Demonstrates that the methodology produces consistent results across sensitivity analyses. This paper provides the structural framework Heavi's solar module follows.

**Charabi, Y. & Gastli, A. (2011).** "PV solar farms site assessment using GIS-based spatial fuzzy multi-criteria evaluation." *Renewable Energy*, 36(9): 2554-2561.

Introduces continuous scoring (fuzzy membership functions) vs binary classification. Demonstrates that aspect and terrain uniformity matter for fixed-tilt installations. Heavi's continuous 0-1 scoring per criterion follows this approach.

**Al-Shammari, S., et al. (2026).** "GIS-based solar suitability assessment across CONUS at 90m resolution using fuzzy AHP." *Renewable Energy* (in press).

The most directly applicable study — US national scale, 90m resolution, 10 criteria. Uses the same federal data sources available to Heavi (NSRDB, 3DEP, NLCD, HIFLD). Validates the criterion set against existing utility-scale installations. Confirms that infrastructure proximity (transmission, roads) dominates over solar resource in regions with uniform irradiance.

**Hernandez, R.R., Hoffacker, M.K., Murphy-Mariscal, M.L., Wu, G.C., & Allen, M.F. (2015).** "Solar energy development impacts on land cover change and protected areas." *PNAS*, 112(44): 13579-13584.

The foundational US study on solar siting exclusion criteria. Evaluated 161 California utility-scale solar installations. Established the standard exclusion framework: protected areas (USGS GAP/PAD-US), wetlands (NWI), steep slope (DEM-derived), developed land (NLCD). Defined infrastructure proximity zones: ≤10km from transmission (≥69 kV, HIFLD), ≤5km from roads (Census TIGER). This paper is the primary provenance for Heavi's exclusion constraint definitions AND the specific federal datasets used.

**Ong, S., Campbell, C., Denholm, P., Margolis, R., & Heath, G. (2013).** "Land-Use Requirements for Solar Power Plants in the United States." NREL/TP-6A20-56290.

Establishes the land-use intensity factors for capacity estimation: 5.0 acres/MW for fixed-tilt, 7.5 for single-axis tracking, 9.0 for two-axis. These are the conversion factors used in Heavi's capacity estimation from buildable acreage.

---

## Scored Criteria

### Criterion: Solar Resource (GHI / Energy Yield)

**Why this criterion:** Solar irradiance is universally the first criterion in every GIS-MCDA solar siting study. It determines the fundamental energy production potential of a site. Doorga et al. (2019) weight it at 18%. Al-Shammari et al. (2026) include it as the highest-priority criterion. However, in regions with uniform irradiance (US Sun Belt, GHI 5.0-6.5 kWh/m²/day), this criterion provides minimal spatial differentiation.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | NREL PVWatts v8 API | Authoritative | Dobos (2014), "PVWatts Version 5 Manual," NREL/TP-6A20-62641. Freeman et al. (2014), "Validation of Multiple Tools for Flat Plate PV Modeling Against Measured Data," NREL/TP-6A20-61497. PVWatts validated against thousands of US installations, median annual accuracy ±5.2% (NREL 2018 study, 199 systems). Uses NSRDB PSM V3 TMY data at 4km resolution. | Hourly simulation → annual kWh, capacity factor, monthly profile. More informative than raw GHI because it accounts for tilt, azimuth, system losses, temperature derating. | ±10% annual accuracy for well-matched systems. Does not model shading, soiling, or microclimate. Nearest TMY station may be 2-5km away. |
| 2 | NREL NSRDB (raw GHI) | Supplementary | Sengupta et al. (2018), "The National Solar Radiation Database (NSRDB)," *Renewable and Sustainable Energy Reviews*, 89: 51-60. | Annual and monthly GHI at 4km grid. Useful as a cross-check or when PVWatts is unavailable. | Raw irradiance, not system output. Does not account for tilt, temperature, or system losses. |

**Weight rationale:** Default weight 0.15 (range 0.10-0.18 in literature). Lower than some studies assign because in the US Sun Belt, GHI is uniformly high and provides minimal differentiation. Weight should increase in regions where GHI varies significantly (Pacific Northwest, Great Lakes).

---

### Criterion: Terrain Slope

**Why this criterion:** Slope directly affects construction cost and feasibility. Steep terrain requires more grading, increases erosion risk, and may preclude standard racking systems. Identified as a top-3 criterion in virtually every solar siting study. The Kermanshah province study (Doorga 2019 review) identified slope as THE primary criterion.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USGS 3DEP DEM | Authoritative | Gesch et al. (2018), "The 3D Elevation Program—Summary of Program Direction," USGS Fact Sheet 2018-3029. 1/3 arc-second (~10m) national coverage, continuously updated. The standard US elevation dataset cited in every CONUS-scale solar study. | Slope in degrees/percent computed from DEM via finite differences. | 10m resolution misses micro-terrain features. Urban areas may have artifacts from built structures. |

**Weight rationale:** Default weight 0.15 (range 0.11-0.17). Consistently high across all studies. Exclusion threshold at 15% is moderate; literature ranges 3% (conservative, Hernandez et al. 2015) to 20% (permissive). NREL technical reports typically use 5-10%.

---

### Criterion: Terrain Aspect

**Why this criterion:** South-facing terrain (150-210°) receives maximum annual insolation in the northern hemisphere. Charabi & Gastli (2011) demonstrated that aspect significantly affects energy yield for fixed-tilt installations, less so for tracking systems.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USGS 3DEP DEM | Authoritative | Same as slope. Aspect computed from the same DEM. | Dominant aspect in degrees. Deviation from 180° (south) as a scoring input. | Aspect is meaningless on flat terrain (slope < 1°). Must be suppressed when slope is negligible. |

**Weight rationale:** Default weight 0.10 (range 0.08-0.12). Lower weight because tracking systems eliminate aspect sensitivity. Weight should be zero for single-axis or dual-axis tracking installations.

---

### Criterion: Transmission Proximity

**Why this criterion:** Interconnection cost is often the largest variable cost in solar development and the primary project-kill factor. Hernandez et al. (2015) established ≤10km from ≥69 kV lines as the development zone. Multiple studies confirm that grid proximity dominates site economics when solar resource is uniform.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | HIFLD Electric Power Transmission Lines | Authoritative | Homeland Infrastructure Foundation-Level Data (HIFLD), maintained by DHS/CISA. 52,244 segments nationally. Hernandez et al. (2015) used HIFLD data. The standard US transmission line dataset used in energy infrastructure studies. | Distance to nearest line with voltage classification. | Does not indicate available capacity, interconnection queue position, or planned upgrades. Voltage classification may be incomplete for some lines. |
| 2 | OSM Power Substations (PostGIS cache) | Authoritative | OpenStreetMap contributors. 16,725 substations across CA/TX/AZ/NV/FL/NC. Substations are the actual point of interconnection, not transmission lines. | Distance to nearest substation with name and voltage where tagged. | Cache limited to 6 states. Tags (voltage, name) inconsistently populated. |
| 3 | OSM Power Substations (Overpass on-demand) | Fallback | Same OSM data queried live via Overpass API for locations outside the 6-state cache. | Same data, higher latency (2-5s), works for any US location. | Overpass API can timeout under load. Rate limits apply. |

**Weight rationale:** Default weight 0.25 (range 0.10-0.45). The Kern County validation used 0.45 because GHI is uniform there and grid proximity is the dominant differentiator, consistent with the Al-Shammari et al. (2026) finding that infrastructure proximity dominates in uniform-irradiance regions. The literature range of 0.10-0.16 reflects studies where irradiance varies more. Geography-dependent weight adjustment is recommended.

---

### Criterion: Road Proximity

**Why this criterion:** Construction access and ongoing maintenance require road access. Hernandez et al. (2015) established ≤5km from classified roads as the development zone. Doorga et al. (2019) weight it at 12%.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | Census TIGER Primary/Secondary Roads | Authoritative | US Census Bureau TIGER/Line files. The standard US road dataset. Hernandez et al. (2015) used TIGER roads. | Distance to nearest primary (S1100 Interstate) or secondary (S1200 US/State Highway) road. | Does not include local roads. New construction may not be reflected. |
| 2 | OpenStreetMap Roads (Overpass) | Fallback | OSM road network. More complete for local roads but less authoritative classification. | Distance to nearest classified road. | Classification quality varies by region. |

**Weight rationale:** Default weight 0.12 (range 0.10-0.14). Consistently included across studies. Lower weight than transmission because road construction cost is typically much lower than gen-tie line cost.

---

### Criterion: Land Cover

**Why this criterion:** Land cover determines both suitability (agricultural land = fewer conflicts) and regulatory complexity (forest conversion, prime farmland). Hernandez et al. (2015) found that most California solar installations displaced scrubland/shrubland, with significant biodiversity implications. Al-Shammari et al. (2026) use NLCD as a primary criterion.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | MRLC NLCD 2021 | Authoritative | Yang et al. (2018), "A New Generation of the United States National Land Cover Database," *Remote Sensing of Environment*, 209: 64-76. 30m resolution, 16 land cover classes. The standard US land cover dataset used in every CONUS-scale study. Hernandez et al. (2015) classified solar installations by NLCD cover type. | Land cover class at parcel location. Scoring: Cultivated crops/hay = favorable (0.8-1.0), Barren = favorable (0.9), Grassland/shrub = moderate (0.6-0.7), Forest = unfavorable (0.2-0.3), Developed = excluded (0.0). | 30m resolution. 2-3 year update cycle. Does not capture recent land use changes. |

**Weight rationale:** Default weight 0.10 (range 0.08-0.12). Moderate weight; primarily serves as a differentiator between agricultural (preferred) and non-agricultural land.

---

### Criterion: Soil Suitability

**Why this criterion:** Soil properties affect foundation design and construction cost. High shrink-swell clays require engineered foundations. Poor drainage increases stormwater management cost. The ORNL OR-SAGE framework includes SSURGO soil data as a siting criterion.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USDA SDA/SSURGO | Authoritative | USDA Natural Resources Conservation Service. National Cooperative Soil Survey. The authoritative US soils database at 1:12,000 to 1:24,000 scale. Queried via Soil Data Access (SDA) REST API nationally. | Drainage class, hydric rating, hydrologic group, depth to water table, shrink-swell potential, engineering classification. | Urban areas may lack detailed SSURGO coverage (STATSGO fallback at coarser resolution). SDA API returns map unit-level data, not point-specific. |

**Weight rationale:** Default weight 0.08 (range 0.05-0.10). Included in some studies but rarely weighted heavily. Soil conditions affect cost but almost never kill a project. Higher weight for regions with known problem soils (Gulf Coast clays, expansive soils in TX/CO).

---

### Criterion: Environmental Justice

**Why this criterion:** EJ screening is a newer addition to siting criteria, driven by Biden-era federal guidance (Justice40 initiative) and state-level permitting requirements. Not present in the foundational studies (Doorga 2019, Hernandez 2015) but increasingly required for federally-funded or permitted projects.

**Data tree:**

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | EPA EJScreen (2024 data) | Authoritative (archived) | U.S. Environmental Protection Agency. Block group-level environmental burden and demographic indicators. 243,022 block groups loaded from Wayback Machine snapshot (2025-02-06) after EPA tool was taken offline Feb 2025. | EJ index percentiles, demographic index, PM2.5, proximity to hazardous waste, wastewater discharge proximity. | Static 2024 snapshot. Tool discontinued. Data will not update unless EPA restores it. |

**Weight rationale:** Default weight 0.05 (range 0.00-0.05). Included for regulatory awareness, not as a primary siting criterion. Weight should increase for projects seeking federal funding or permits.

---

## Exclusion Criteria (Binary Pass/Fail)

The exclusion criteria below follow the standard established by Hernandez et al. (2015) and confirmed across the literature. Environmental features are treated as hard constraints, not scored criteria.

### Exclusion: Protected Areas

**Provenance:** Hernandez et al. (2015) used USGS GAP (now PAD-US) to identify protected areas. Consistent across all studies as a hard exclusion.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USGS PAD-US v3 | Authoritative | U.S. Geological Survey. 306,082 polygons nationally. The authoritative US protected areas database combining federal, state, and local designations. | Protected area overlap with name, designation type, and GAP status code. | Some conservation easements may permit energy development — easement terms should be verified. |

---

### Exclusion: Wetlands

**Provenance:** Hernandez et al. (2015) excluded wetlands. NWI is the authoritative US wetland mapping source, established by Cowardin et al. (1979). The OR-SAGE framework (ORNL) uses NWI as a "decision layer" — binary suitability determination.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USFWS NWI (PostGIS, where loaded) | Authoritative | Cowardin, V., Carter, V., Golet, F.C., & LaRoe, E.T. (1979). "Classification of Wetlands and Deepwater Habitats of the United States." FWS/OBS-79/31. The national wetland classification standard. NWI data mapped per this system. | Wetland boundaries with Cowardin classification code, area. | Loaded for limited geographies. Coverage is not uniform nationally — NWI mapping is ongoing. |
| 2 | USFWS NWI REST Service | Authoritative | Same NWI data via USFWS web service at fwsprimary.wim.usgs.gov. | Same data on-demand. | Service currently returning HTTP 500 on queries (degraded as of June 2026 retest). Availability is intermittent. |
| 3 | USDA SSURGO Hydric Soils Flag | Proxy | NRCS hydric soils indicator from the soil survey. Hydric soils are one of three required criteria for jurisdictional wetland delineation (hydric soils + hydrophytic vegetation + wetland hydrology per the 1987 Corps Manual). The hydric flag indicates POTENTIAL wetland, not confirmed wetland boundary. | Binary hydric/non-hydric per soil map unit. | Proxy only — identifies soils LIKELY to support wetlands, not delineated wetland boundaries. Does not provide acreage, classification, or boundary geometry. False positive rate: many hydric soils are drained or developed and no longer function as wetlands. |

**Gap note:** NWI national coverage is the single largest data gap in the solar siting workflow. The PostGIS-loaded data covers limited geographies. The REST service is degraded. The SSURGO hydric proxy provides an indicator but not boundaries. This gap must be surfaced in every output where NWI data is unavailable.

---

### Exclusion: Critical Habitat (ESA)

**Provenance:** Endangered Species Act Section 7 requires federal agencies to consult with USFWS before authorizing actions that may affect listed species or critical habitat. Solar projects on federal land or requiring federal permits must undergo this review.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USFWS Critical Habitat (ArcGIS REST) | Authoritative | U.S. Fish and Wildlife Service ECOS. 802 designated critical habitat polygons nationally, queried on-demand. | Overlap with species name and listing status. | Only covers species with formally designated critical habitat. Many listed species lack designated CH. Does not cover state-listed species. |

---

### Exclusion: Flood Zones

**Provenance:** FEMA NFHL is the standard flood hazard data source. Solar installations in SFHA zones face permitting restrictions, insurance requirements, and physical risk. Consistent exclusion across studies.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | FEMA NFHL (ArcGIS REST) | Authoritative | FEMA National Flood Hazard Layer. On-demand query nationally. | Flood zone classification (A, AE, V, VE, X). SFHA zones = exclusion. | Map currency varies by community. Some maps 10-20+ years old. Pluvial flooding not mapped. |

---

### Exclusion: Steep Slope

**Provenance:** Same 3DEP DEM used for the scored slope criterion. Threshold varies in literature: 3% (Hernandez et al. 2015, conservative), 5-10% (moderate), 15-20% (permissive). The "Beyond Prime Farmland" paper (2025) uses 10°. Default 15% is moderate.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USGS 3DEP DEM | Authoritative | Same as scored slope criterion. | Binary: slope above threshold = excluded. | Same limitations as scored criterion. |

---

### Exclusion: Developed/Urban Land

**Provenance:** Hernandez et al. (2015) excluded built-up areas as a hard constraint. Al-Shammari et al. (2026) use NLCD developed classes (21-24) as an exclusion. Consistent across all studies.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | MRLC NLCD 2021 | Authoritative | Same as scored land cover criterion. Classes 21 (Developed Open Space), 22 (Low Intensity), 23 (Medium Intensity), 24 (High Intensity). | Binary: developed classes = excluded. Thresholding configurable — some analyses exclude only 23-24 (medium/high intensity), keeping 21-22 for distributed solar. | Same limitations as scored criterion. |

---

# WORKFLOW 2: NATURAL HAZARD ASSESSMENT

## Wildfire Risk

### Methodological Framework

**Finney, M.A., McHugh, C.W., Grenfell, I.C., Riley, K.L., & Short, K.C. (2011).** "A simulation of probabilistic wildfire risk components for the continental United States." *Stochastic Environmental Research and Risk Assessment*, 25: 973-1000.

The FSim simulation system that produces the hazard layer Heavi consumes. Probabilistic burn probability from tens of thousands of simulated fire seasons.

**Syphard, A.D., Brennan, T.J., & Keeley, J.E. (2012).** "Housing arrangement and location determine the likelihood of housing loss due to wildfire." *PLoS ONE*, 7(3): e33954.

Establishes that housing density, arrangement, and proximity to wildland vegetation are stronger predictors of wildfire damage than fire behavior characteristics alone. Informs the exposure enrichment features (distance to fuel, canopy cover buffers).

**Kramer, H.A., Mockrin, M.H., Alexandre, P.M., Stewart, S.I., & Radeloff, V.C. (2018).** "Where wildfires destroy buildings in the US relative to the wildland-urban interface and national fire outreach programs." *International Journal of Wildland Fire*, 27(5): 329-341.

Documents the Coffey Park pattern: urban structures distant from wildland fuel destroyed by structure-to-structure ignition cascades. Informs the positive coefficient on distance-to-fuel in Heavi's vulnerability model.

### Criterion: Wildfire Likelihood

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USFS FSim (RDS-2016-0034-2) | Authoritative | Finney et al. (2011). Short et al. (2020, updated 2024). USDA Forest Service Research Data Archive. 270m resolution, CONUS. | Annual burn probability per 270m pixel. | Uses LANDFIRE 2014 fuels — temporal mismatch with current conditions. Does not reflect recent fuel treatments or development. |

### Criterion: Fuel Proximity and Canopy Cover

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USGS/USFS LANDFIRE | Authoritative | Rollins, M.G. (2009). "LANDFIRE: a nationally consistent vegetation, wildland fire, and fuel assessment." *International Journal of Wildland Fire*, 18(3): 235-249. 30m resolution, national. | Fuel model (FBFM40), canopy cover percentage. Distance to nearest burnable fuel computed from fuel model raster. Canopy cover at 30m/100m/300m buffer scales per Syphard et al. (2012) defensible space research. | 30m resolution. Updated periodically but may lag current conditions. |

### Criterion: Building Characteristics

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | USACE National Structure Inventory v2 | Authoritative | U.S. Army Corps of Engineers. National coverage, structure-level. | Occupancy class (33 types), foundation type, stories, construction type, replacement value. | Synthesized centroids (20-100m positional error). Construction type not always populated. First floor heights estimated, not surveyed. |
| 2 | Microsoft Building Footprints | Supplementary | Computer-vision-derived building polygons. Open license. | Building footprint geometry for positional refinement. | Not a substitute for NSI building characteristics. Footprint only, no attributes. |

### Criterion: Terrain (Slope)

Same 3DEP data tree as solar module. Slope affects fire behavior (upslope fire spread is faster).

---

## Flood Risk

### Methodological Framework

**Scawthorn, C., et al. (2006).** "HAZUS-MH Flood Loss Estimation Methodology. I: Overview and Flood Hazard Characterization." *Natural Hazards Review*, 7(2): 60-71.

**Scawthorn, C., et al. (2006).** "HAZUS-MH Flood Loss Estimation Methodology. II: Damage and Loss Assessment." *Natural Hazards Review*, 7(2): 72-81.

The foundational methodology for the HAZUS flood loss model. Establishes the depth-damage function approach: flood depth at structure → damage percentage by building type → dollar loss.

**FEMA (2024).** *HAZUS Earthquake Model Technical Manual 6.1.* FEMA P-58.

The authoritative source for depth-damage function tables (haz_fl_dept) and building classification schema.

### Criterion: Flood Zone and Base Flood Elevation

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | FEMA NFHL (ArcGIS REST) | Authoritative | FEMA National Flood Hazard Layer. The regulatory flood hazard dataset for the US. | Flood zone (A, AE, V, VE, X, D), Base Flood Elevation where published (AE, VE zones). | Map currency varies by community. Some maps 10-20+ years old. Pluvial flooding not mapped. BFE not available in all zones (A zones lack published BFE). |

### Criterion: Flood Depth Estimation

This is a multi-source computation, not a single lookup. Depth = BFE - ground elevation - first floor height.

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 (component) | FEMA NFHL | Component | See above. | BFE where published. | Not available in all zones. |
| 2 (component) | USGS 3DEP | Component | See above. | Ground elevation at structure location. | 10m resolution, may not capture micro-topography. |
| 3 (component) | USACE NSI | Component | See above. | First floor height (estimated). | Estimated, not surveyed. Errors of 1-3 feet directly affect damage estimates. |
| 4 (supplementary) | Google Inundation History | Supplementary | Google Flood Forecasting Initiative. CC-BY-4.0. Satellite-derived flood frequency at 128m resolution, 1999-2020. | How often each pixel has been wet. Corroborates or contradicts NFHL-based estimates. | 128m resolution is coarse. Excludes US territory above ~43°N. Does not provide depth, only frequency. |

### Criterion: Damage Estimation

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 (component) | HAZUS DDFs | Component | Scawthorn et al. (2006). FEMA HAZUS Flood Model Technical Manual. Reconciled against haz_fl_dept database (1,260 curves). 174 rows loaded covering 6 occupancy classes. | Structural and contents damage percentage as a function of flood depth by building type and foundation. | Stillwater assumption. Velocity and wave action not modeled. Generic functions, not property-specific. |
| 2 (component) | USACE NSI | Component | See above. | Building type for curve selection. Replacement value for dollar loss. | Construction type and replacement value are estimates. |

### Criterion: Historical Context

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | OpenFEMA Disaster Declarations | Authoritative | FEMA Open Data. Continuously updated. | Disaster declarations by county with type, date, and description. NFIP claims by zip code with paid amounts. | NFIP claims have coordinate redaction (~0.1 degree). Claims data reflects insured losses, not total losses. |
| 2 | USGS Peak-Flow Data | Supplementary | USGS Water Services. Annual peak streamflow at gauge stations nationally. | Peak flow magnitude and frequency at nearest gauge. Return period estimation via flood frequency analysis. | Coverage depends on gauge density. Rural areas may have distant gauges. |

### Criterion: Hydrologic Context

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | Google GRRR | Authoritative | Google Flood Forecasting Initiative. CC-BY-4.0. AI-derived global river discharge estimates (1980-2023) on HydroBasins framework. | Discharge estimates at return periods for nearest river reach. | Requires HydroBasins catchment-ID lookup. AI-derived (model output, not measurement). Coverage and accuracy vary by basin size. |
| 2 | USGS NHDPlus HR | Component | USGS National Hydrography. 1:24,000 scale, national. | HUC-12 watershed boundaries, flowlines with stream order, nearest stream identification. | On-demand REST queries. Large datasets. |
| 3 | USGS Peak-Flow | Supplementary | See above. | Observed peak flows at nearest gauge for return period estimation. | Gauge-based, not continuous spatial coverage. |

---

# WORKFLOW 3: TRADE AREA ANALYSIS

## Methodological Framework

**Huff, D.L. (1963).** "A Probabilistic Analysis of Shopping Center Trade Areas." *Land Economics*, 39(1): 81-90.

**Huff, D.L. (1964).** "Defining and Estimating a Trading Area." *Journal of Marketing*, 28(3): 34-38.

The foundational gravity model for retail trade area analysis. Predicts consumer patronage probability as a function of facility attractiveness and travel time. Still the standard methodology taught in every GIS and retail geography curriculum. Implemented in Esri's Business Analyst and every major retail site selection practice.

**Suárez-Vega, R., et al. (2015).** "A multi-criteria GIS based procedure to solve a network competitive location problem." *Applied Geography*, 59: 142-153.

Multi-criteria extension of the gravity model incorporating competitive density, demographic weighting, and accessibility metrics. The source for Heavi's composite scoring weights.

**Liang, Y., et al. (2020).** "Calibrating the dynamic Huff model for business analysis using location big data." *Transactions in GIS*, 24(3): 680-701.

Modern calibration of Huff model parameters using mobile phone location data across 10 major US cities. Demonstrates that the distance-decay parameter varies by retail category (grocery β≈2.0, department stores β≈1.5).

**Luo, W. & Wang, F. (2003).** "Measures of spatial accessibility to health care in a GIS environment: synthesis and a case study in the Chicago region." *Environment and Planning B*, 30(6): 865-884.

The two-step floating catchment area (2SFCA) method for accessibility measurement. Applicable when the module is used for healthcare facility siting.

### Criterion: Population Coverage

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | Census ACS 5-Year (API) | Authoritative | U.S. Census Bureau. National coverage via api.census.gov. Tables B01001 (population), B11001 (households), B19013 (median income). Area-weighted aggregation within drive-time isochrones. | Population, households, income at tract level for any US location. | 5-year rolling average lags reality by 1-3 years. New development not captured until next release. |

### Criterion: Daytime Population

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | Census LEHD/LODES (PostGIS, where loaded) | Authoritative | Census Bureau LEHD Origin-Destination Employment Statistics. Workplace area characteristics (WAC) at census block level. | Daytime employment count by earnings tier within trade area. | Loaded for limited geographies (currently Dallas County). National LODES data available for download by state. |
| 2 | Census ACS Commuter Data (API) | Proxy | ACS table B08301 (means of transportation to work), B08303 (travel time to work). Available nationally via Census API. | Commuter count as a proxy for daytime activity. Less precise than LEHD block-level employment data. | Proxy only — commuter count ≠ workplace population. Does not capture daytime visitors, shoppers, or non-workers. |

### Criterion: Competitive Density

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | OSM POIs (PostGIS, where loaded) | Authoritative | OpenStreetMap contributors. Pre-loaded with category classification. | Same-category competitor count, complementary POI count, nearest competitor distance. Pre-loaded is fastest for repeated queries in the same geography. | Loaded for limited geographies (currently Dallas County). Category classification from OSM tags, may not perfectly match customer's competitive definition. |
| 2 | OSM POIs (Overpass on-demand) | Fallback | Same OSM data queried live via Overpass API. | Same data, works for any location. Higher latency (2-5s per query). | Overpass API can timeout. Rate limits apply. Category classification same as above. |

### Criterion: Accessibility

| Priority | Source | Quality | Provenance | What it provides | Known limitations |
|---|---|---|---|---|---|
| 1 | OpenRouteService Isochrones (API) | Authoritative | OpenRouteService (HeiGIT). Uses OSM road network for drive-time polygon computation. Huff (1963) established travel time as the key variable in trade area delineation. | 5/10/15 minute drive-time polygons. The fundamental spatial unit for trade area analysis. | Free tier: 500 requests/day. OSM road data completeness varies. New roads/construction not reflected. |

---

# KNOWN DATA GAPS (documented honestly)

| Gap | Affected Workflows | Impact | Current Mitigation | Resolution Path |
|---|---|---|---|---|
| NWI Wetlands — national REST service degraded | Solar siting (exclusion), Hazard assessment | Cannot assess wetland overlap for most US locations | SSURGO hydric flag as proxy indicator | Monitor NWI service recovery. Consider state-level NWI downloads for priority states. |
| Census LEHD — limited geography | Trade area (daytime population) | Daytime employment data only for Dallas County | ACS commuter count as proxy | Download LODES WAC files for additional states. |
| OSM POIs — limited pre-loaded geography | Trade area (competitive density) | Pre-loaded POI data only for Dallas County | Overpass on-demand as fallback | Pre-load POI data for additional metro areas. |
| Google Inundation History — northern US excluded | Hazard assessment (flood corroboration) | No satellite flood frequency data above ~43°N | No mitigation — gap is documented in output | Await dataset expansion by Google. |
| EPA EJScreen — discontinued | Solar siting (EJ screening) | Static 2024 data, will not update | Use archived data with vintage disclosure | Monitor for EPA tool restoration under future administration. |
| FSim temporal mismatch — 2014 fuels | Hazard assessment (wildfire likelihood) | Wildfire hazard reflects 2014 fuel conditions | Document vintage in every output | Consume updated FSim products when USFS publishes them. |

---

# DATA SELECTION ENGINE: LOGIC TREE

## Overview

The data selection engine traverses data trees at query time to find the best available data for each criterion at a specific location. It produces both scored results AND a confidence level that reflects the quality of data that was actually available.

## Step 1: Source Resolution (per query, once)

When a query arrives (workflow_type + lat/lng), the engine identifies ALL unique data sources referenced across all criteria for that workflow. Each unique source is queried ONCE and cached for the duration of the request.

**Data source reuse rule:** If the same source_id appears in multiple criteria trees (e.g., usgs_3dep appears in solar_slope, solar_aspect, excl_steep, and fl_depth), it is queried once. The result is reused across all criteria that reference it. This is correct because the same source at the same location returns the same data regardless of which criterion is consuming it.

**Implementation:** Build a source resolution cache at the start of each query:
```
resolved_sources = {}
for criterion in workflow.criteria:
    for node in criterion.data_tree:
        if node.source_id not in resolved_sources:
            resolved_sources[node.source_id] = query_source(node.source_id, lat, lng)
```

## Step 2: Tree Traversal (per criterion)

For each criterion, traverse its data tree using the resolved source cache. The traversal rules depend on the relationship type between nodes:

### Alternative nodes (try in order, use best available)

Nodes are alternatives when they provide the SAME type of information at different quality levels. Identified by quality labels: authoritative → fallback → proxy.

```
For each node in tree (top to bottom):
    result = resolved_sources[node.source_id]
    if result.available:
        selected = node
        break
    else:
        continue
If no node available:
    selected = None (gap)
```

**Example — Wetlands exclusion:**
1. Check NWI PostGIS → if data exists at this location, use it (authoritative boundary)
2. Check NWI REST → if service responds, use it (authoritative boundary)
3. Check SSURGO hydric → always available nationally (proxy indicator)
4. If somehow all fail → gap

The selected node carries its quality label forward into confidence scoring.

### Component nodes (need all, compute together)

Nodes are components when they provide DIFFERENT inputs to a computation. Identified by quality label: component.

```
components = {}
for node in tree where node.quality == "component":
    result = resolved_sources[node.source_id]
    if result.available:
        components[node.source_id] = result
    else:
        missing.append(node.source_id)

supplementary = {}
for node in tree where node.quality == "supplementary":
    result = resolved_sources[node.source_id]
    if result.available:
        supplementary[node.source_id] = result

If all components available:
    compute criterion from components + supplementary
    quality = "complete"
If some components available:
    compute partial result with available components
    quality = "partial" 
    note which components are missing and how that degrades the result
If no components available:
    gap
```

**Example — Flood depth estimation:**
- FEMA NFHL (BFE): component → if missing, cannot compute regulatory depth, fall back to inundation frequency
- USGS 3DEP (ground elevation): component → if missing, cannot compute depth at all
- USACE NSI (first floor height): component → if missing, use default FFH (1ft slab, 3ft crawlspace) with quality note
- Google Inundation History: supplementary → enhances confidence if available, no degradation if missing

If BFE is missing but 3DEP and NSI are available: depth cannot be computed from regulatory data. The engine reports "BFE not published for this zone — depth estimate uses default assumptions" and quality = "partial."

## Step 3: Confidence Scoring

Every criterion receives a confidence level based on what data was actually used:

### Per-Criterion Confidence

| Data Quality | Confidence Level | Numeric | Meaning |
|---|---|---|---|
| Authoritative source available | HIGH | 1.0 | Best available data for this criterion at this location |
| Fallback source used | MODERATE | 0.7 | Same data type, higher latency or less reliable access path |
| Proxy source used | LOW | 0.4 | Different data type used as an indicator. Provides directional signal but not the same information. |
| Partial components available | LOW | 0.3-0.6 | Some inputs to a multi-source computation are missing. Result is computed with defaults or assumptions. Scale based on which components are missing. |
| No data available | NONE | 0.0 | Criterion cannot be assessed. Excluded from scoring. |

### Per-Criterion Confidence Rules (specific cases)

**Wetlands exclusion:**
- NWI boundary data available → HIGH (1.0). Provides delineated wetland boundary with Cowardin classification and acreage.
- SSURGO hydric flag used as proxy → LOW (0.4). Provides "soil is hydric" which INDICATES potential wetland but does not provide boundary, acreage, or classification. A non-hydric result does NOT confirm absence of wetlands (false negatives possible). A hydric result does NOT confirm jurisdictional wetland (false positives common on drained/developed land).
- No wetland data → NONE (0.0). Wetland exclusion not assessed. Output must state: "Wetland constraint screening was not performed for this location due to data unavailability."

**Flood depth:**
- All 3 components available → HIGH (1.0)
- BFE missing, ground elev + FFH available → LOW (0.4). Depth computed from zone-default assumptions, not published BFE.
- Ground elevation missing → NONE (0.0). Cannot compute depth.
- NSI FFH missing → MODERATE (0.7). Use occupancy-class default FFH with quality note.
- Google Inundation available as supplement → no change to confidence level, but noted as corroboration: "satellite flood history [supports/contradicts] the NFHL-based estimate."

**Daytime population:**
- Census LEHD available → HIGH (1.0). Block-level workplace employment.
- ACS commuter proxy used → LOW (0.4). Tract-level commuter count is a weaker indicator of actual daytime activity.

### Composite Confidence (per assessment)

The overall assessment confidence aggregates per-criterion confidence, weighted by criterion importance:

```
scored_confidence = Σ(criterion_weight × criterion_confidence) / Σ(criterion_weight)
```

For exclusion criteria, the composite is scaled by the **weakest** exclusion check — because a single missed fatal flaw invalidates the assessment. The cost of overlooking a wetland, critical-habitat, or protected-area constraint at site-commitment is asymmetric: better to mark the whole assessment as degraded than to imply a clean bill of health when one of the screens used proxy data.

```
worst_exclusion_confidence = min(exclusion_confidences)
exclusion_factor = 0.5 + 0.5 × worst_exclusion_confidence
composite_confidence = scored_confidence × exclusion_factor
```

This maps:

| Worst exclusion | Quality        | Factor | Composite at scored=0.95 |
|---|---|---|---|
| 1.0 | authoritative | 1.00 | 0.95 → HIGH |
| 0.7 | fallback      | 0.85 | 0.81 → MODERATE |
| 0.4 | proxy         | 0.70 | 0.66 → MODERATE |
| 0.0 | gap           | 0.50 | 0.48 → LOW |

**Revised 2026-06-06.** The earlier formula (`composite × (1 − 0.3 × NONE_count/total)`) penalised only NONE-confidence exclusion criteria, so a SSURGO-proxy wetland check looked identical to an authoritative NWI check in the composite — masking the gap. The revised weakest-link formula propagates a single proxy exclusion into the assessment-level confidence, which surfaces the gap honestly and creates real differentiation across locations with different data availability.

**Statement language follows the driver.** When the worst exclusion has a registered remediation note (e.g. wetlands → SSURGO proxy), the statement leads with the specific advisory:

> "Wetland exclusion screening used SSURGO hydric soils as proxy rather than NWI boundary data. Recommend field delineation before committing. Composite confidence is MODERATE (scored 0.95 × exclusion factor 0.70 = 0.66)."

The driver-specific remediation library lives in `data_selection._EXCLUSION_PROXY_GUIDANCE`; adding a new exclusion's guidance is a one-line change.

### Confidence Tiers (reported in output)

| Composite Confidence | Tier | Output Language |
|---|---|---|
| ≥ 0.85 | HIGH | "This assessment is based on authoritative data for all major criteria." |
| 0.65 – 0.84 | MODERATE | "This assessment uses proxy or partial data for [N] criteria. [List criteria with degraded data]. Results are directionally reliable but should be verified for [specific gaps]." |
| 0.40 – 0.64 | LOW | "This assessment has significant data gaps affecting [N] criteria. [List gaps]. Results should be treated as preliminary screening, not definitive assessment." |
| < 0.40 | INSUFFICIENT | "Insufficient data available at this location to produce a reliable assessment. [List what's missing]. Consider alternative data sources or on-site investigation." |

## Step 4: Quality Propagation to Downstream Stages

When one stage's output feeds another stage's computation (cross-stage dependency), the downstream stage inherits the MINIMUM confidence of its inputs.

**Example — LCOE estimation (if implemented):**
LCOE consumes: annual production (from PVWatts, HIGH), adjusted capacity (from buildable area, which depends on wetland exclusion quality), interconnection cost (from transmission/substation query), site prep cost (from soil assessment).

If buildable area used proxy wetland data (LOW, 0.4):
- Buildable acreage may be overstated (wetland area not accurately excluded)
- Capacity estimate inherits LOW confidence
- LCOE inherits LOW confidence for the capacity input
- LCOE output notes: "LCOE estimate has LOW confidence for the capacity input because wetland exclusion used proxy data (SSURGO hydric flag rather than NWI boundaries). Actual buildable area may be smaller if jurisdictional wetlands are present."

**Propagation rule:**
```
stage_confidence = min(
    stage_own_confidence,         # quality of this stage's direct data
    min(upstream_confidences)     # worst confidence of any upstream input
)
```

The stage output includes both its own data quality AND the inherited quality from upstream dependencies, so the reader can see where the weakest link is.

## Step 5: Output Structure

Every scored assessment returns:

```json
{
    "score": 0.78,
    "rating": "High",
    "confidence": {
        "tier": "MODERATE",
        "composite": 0.72,
        "statement": "This assessment uses proxy data for 1 criterion (wetland exclusion). Results are directionally reliable but wetland constraints should be verified via site survey.",
        "per_criterion": {
            "solar_ghi": {"confidence": 1.0, "tier": "HIGH", "source_used": "nrel_pvwatts_v8", "quality": "authoritative"},
            "solar_slope": {"confidence": 1.0, "tier": "HIGH", "source_used": "usgs_3dep", "quality": "authoritative"},
            "excl_wetlands": {"confidence": 0.4, "tier": "LOW", "source_used": "usda_sda_ssurgo", "quality": "proxy", "note": "NWI unavailable, SSURGO hydric flag used as indicator"},
            "excl_protected": {"confidence": 1.0, "tier": "HIGH", "source_used": "usgs_padus", "quality": "authoritative"}
        },
        "gaps": ["NWI wetlands data unavailable at this location — wetland exclusion screening used SSURGO hydric soils as proxy indicator"],
        "strongest_data": ["Solar resource (PVWatts, authoritative)", "Terrain (3DEP, authoritative)", "Transmission (HIFLD, authoritative)"],
        "weakest_data": ["Wetland exclusion (SSURGO proxy — does not provide boundary or acreage)"]
    },
    "methodology": {
        "framework": "GIS-MCDA per Doorga et al. (2019), exclusion criteria per Hernandez et al. (2015)",
        "criteria": [ ... ],
        "citations": [ ... ]
    }
}
```

## Summary: The Complete Logic Flow

```
Query arrives: workflow_type + (lat, lng)
    │
    ├─ Step 1: Resolve all unique data sources for this workflow at this location (query each ONCE)
    │
    ├─ Step 2: For each criterion, traverse data tree using resolved cache
    │   ├─ Alternatives: use best available (authoritative > fallback > proxy)
    │   └─ Components: assemble all available, note missing
    │
    ├─ Step 3: Assign per-criterion confidence based on what was actually used
    │   └─ HIGH (authoritative) / MODERATE (fallback) / LOW (proxy or partial) / NONE (gap)
    │
    ├─ Step 4: Propagate confidence to downstream computations
    │   └─ Downstream confidence ≤ min(upstream confidences)
    │
    ├─ Step 5: Compute composite confidence from weighted criterion confidences + exclusion penalties
    │
    └─ Output: score + confidence tier + per-criterion quality report + methodology documentation
```

---

# VALIDATION APPROACH

Each workflow's scoring methodology must be validated against observed outcomes. The validation approach is workflow-specific:

**Solar siting:** Score known solar installation locations (EIA Form 860). Successful sites should score high. Metric: percentage of real installations scoring High. Current: 97.7% in Kern County (single geography — requires multi-geography validation).

**Wildfire risk:** Score structures with known damage outcomes (CAL FIRE DINS). High-risk scores should correlate with observed damage. Metric: AUC-ROC. Current: 0.76 in Sonoma County (single geography).

**Flood risk:** Score properties in areas with known flood losses (NFIP claims). High-risk scores should correlate with claim frequency/severity. Metric: discrimination ratio. Current: 16x in Lee County (single geography).

**Trade area:** Score known chain locations. Professionally selected sites should score higher than random locations. Metric: percentage scoring Strong. Current: 96.7% of Dallas Starbucks (single geography).

**All validation metrics are single-geography.** Multi-geography validation is required before claiming the methodology generalizes.
