# ruff: noqa: E501  (academic citations + provenance strings stay legible inline)
"""Seed for methodology_criteria — Heavi Platform Build Spec Phase 2.

31 criteria across 3 workflows, transcribed from Heavi_Methodology_Data_
Provenance.md. Each criterion's data_tree encodes the literal hierarchy from
the provenance document; the academic_sources list cites the papers that
establish the criterion's inclusion + weight.

Run `python -m app.methodology_seed` to upsert. Idempotent.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")


# ─── Tree-node helpers ────────────────────────────────────────────────────

def alt(source_id: str, quality: str, confidence: float, provides: str,
        provenance: str) -> dict[str, Any]:
    """Alternative node: a same-information source at a quality tier."""
    return {
        "source_id":        source_id,
        "relationship":     "alternative",
        "quality":          quality,           # 'authoritative' | 'fallback' | 'proxy'
        "confidence_value": confidence,
        "provides":         provides,
        "provenance":       provenance,
    }


def comp(source_id: str, confidence: float, role: str, missing_impact: str,
         missing_confidence: float, provenance: str, quality: str = "authoritative",
         ) -> dict[str, Any]:
    """Component node: a required input to a multi-source computation."""
    return {
        "source_id":          source_id,
        "relationship":       "component",
        "quality":            quality,
        "confidence_value":   confidence,
        "role":               role,
        "missing_impact":     missing_impact,
        "missing_confidence": missing_confidence,
        "provenance":         provenance,
    }


def supp(source_id: str, role: str, provenance: str) -> dict[str, Any]:
    """Supplementary node: enhances confidence if present, no degradation if missing."""
    return {
        "source_id":        source_id,
        "relationship":     "supplementary",
        "quality":          "supplementary",
        "confidence_value": None,
        "role":             role,
        "provenance":       provenance,
    }


def cite(author: str, year: int, title: str, journal: str | None = None,
         volume: str | None = None, pages: str | None = None,
         finding: str = "") -> dict[str, Any]:
    return {
        "author":  author, "year": year, "title": title,
        "journal": journal, "volume": volume, "pages": pages,
        "finding": finding,
    }


# ─── Common citations (referenced across multiple criteria) ────────────────

DOORGA_2019 = cite(
    "Doorga, J.R.S., Rughooputh, S.D.D.V., & Boojhawon, R.", 2019,
    "Multi-criteria GIS-based modelling approach for the identification of suitable sites for the construction of photovoltaic solar plants",
    "Renewable and Sustainable Energy Reviews", "104", "133-146",
    "Establishes the AHP + WLC framework for GIS-MCDA solar siting.",
)
HERNANDEZ_2015 = cite(
    "Hernandez, R.R., Hoffacker, M.K., Murphy-Mariscal, M.L., Wu, G.C., & Allen, M.F.", 2015,
    "Solar energy development impacts on land cover change and protected areas",
    "PNAS", "112", "13579-13584",
    "Foundational US study of solar siting exclusion criteria using GAP/PAD-US, NWI, NLCD, HIFLD, TIGER.",
)
AL_SHAMMARI_2026 = cite(
    "Al-Shammari, S., et al.", 2026,
    "GIS-based solar suitability assessment across CONUS at 90m resolution using fuzzy AHP",
    "Renewable Energy", None, "in press",
    "Most directly applicable US national study. Confirms infrastructure proximity dominates in uniform-irradiance regions.",
)
CHARABI_GASTLI_2011 = cite(
    "Charabi, Y. & Gastli, A.", 2011,
    "PV solar farms site assessment using GIS-based spatial fuzzy multi-criteria evaluation",
    "Renewable Energy", "36", "2554-2561",
    "Introduces fuzzy continuous scoring; demonstrates aspect matters for fixed-tilt.",
)
ONG_2013 = cite(
    "Ong, S., Campbell, C., Denholm, P., Margolis, R., & Heath, G.", 2013,
    "Land-Use Requirements for Solar Power Plants in the United States",
    "NREL/TP-6A20-56290", None, None,
    "Establishes 5.0 acres/MW fixed-tilt, 7.5 single-axis, 9.0 two-axis land-use factors.",
)
GESCH_2018 = cite(
    "Gesch, D.B., Evans, G.A., Oimoen, M.J., & Arundel, S.", 2018,
    "The 3D Elevation Program—Summary of Program Direction", "USGS Fact Sheet 2018-3029",
    None, None, "3DEP 1/3 arc-second is the standard US elevation dataset.",
)
YANG_2018 = cite(
    "Yang, L., Jin, S., Danielson, P., Homer, C., Gass, L., et al.", 2018,
    "A New Generation of the United States National Land Cover Database",
    "Remote Sensing of Environment", "209", "64-76",
    "Documents NLCD methodology; the standard US land cover dataset.",
)
COWARDIN_1979 = cite(
    "Cowardin, L.M., Carter, V., Golet, F.C., & LaRoe, E.T.", 1979,
    "Classification of Wetlands and Deepwater Habitats of the United States",
    "USFWS FWS/OBS-79/31", None, None,
    "National wetland classification standard used by NWI.",
)
DOBOS_2014 = cite(
    "Dobos, A.P.", 2014,
    "PVWatts Version 5 Manual", "NREL/TP-6A20-62641", None, None,
    "Authoritative PVWatts methodology. ±10% annual accuracy verified against measured systems.",
)
FREEMAN_2014 = cite(
    "Freeman, J., Whitmore, J., Kaffine, L., Blair, N., & Dobos, A.P.", 2014,
    "Validation of Multiple Tools for Flat Plate PV Modeling Against Measured Data",
    "NREL/TP-6A20-61497", None, None,
    "Validates PVWatts against 199 systems; median accuracy ±5.2%.",
)
FINNEY_2011 = cite(
    "Finney, M.A., McHugh, C.W., Grenfell, I.C., Riley, K.L., & Short, K.C.", 2011,
    "A simulation of probabilistic wildfire risk components for the continental United States",
    "Stochastic Environmental Research and Risk Assessment", "25", "973-1000",
    "FSim simulation framework producing the USFS hazard layer.",
)
SYPHARD_2012 = cite(
    "Syphard, A.D., Brennan, T.J., & Keeley, J.E.", 2012,
    "Housing arrangement and location determine the likelihood of housing loss due to wildfire",
    "PLoS ONE", "7", "e33954",
    "Establishes housing density + proximity to wildland as stronger predictors than fire behavior alone.",
)
KRAMER_2018 = cite(
    "Kramer, H.A., Mockrin, M.H., Alexandre, P.M., Stewart, S.I., & Radeloff, V.C.", 2018,
    "Where wildfires destroy buildings in the US relative to the wildland-urban interface",
    "International Journal of Wildland Fire", "27", "329-341",
    "Documents urban-distant structure loss; informs positive distance-to-fuel coefficient.",
)
ROLLINS_2009 = cite(
    "Rollins, M.G.", 2009,
    "LANDFIRE: a nationally consistent vegetation, wildland fire, and fuel assessment",
    "International Journal of Wildland Fire", "18", "235-249",
    "LANDFIRE fuel model + canopy cover methodology at 30 m national.",
)
SCAWTHORN_2006A = cite(
    "Scawthorn, C., et al.", 2006,
    "HAZUS-MH Flood Loss Estimation Methodology. I: Overview and Flood Hazard Characterization",
    "Natural Hazards Review", "7", "60-71",
    "Foundational HAZUS flood loss methodology.",
)
SCAWTHORN_2006B = cite(
    "Scawthorn, C., et al.", 2006,
    "HAZUS-MH Flood Loss Estimation Methodology. II: Damage and Loss Assessment",
    "Natural Hazards Review", "7", "72-81",
    "Depth-damage function methodology.",
)
HUFF_1963 = cite(
    "Huff, D.L.", 1963,
    "A Probabilistic Analysis of Shopping Center Trade Areas",
    "Land Economics", "39", "81-90",
    "Foundational gravity model for retail trade area analysis.",
)
HUFF_1964 = cite(
    "Huff, D.L.", 1964,
    "Defining and Estimating a Trading Area",
    "Journal of Marketing", "28", "34-38",
    "Travel-time-based trade area delineation methodology.",
)
SUAREZ_VEGA_2015 = cite(
    "Suárez-Vega, R., et al.", 2015,
    "A multi-criteria GIS based procedure to solve a network competitive location problem",
    "Applied Geography", "59", "142-153",
    "Multi-criteria extension of Huff incorporating competitive density and demographics.",
)
LIANG_2020 = cite(
    "Liang, Y., et al.", 2020,
    "Calibrating the dynamic Huff model for business analysis using location big data",
    "Transactions in GIS", "24", "680-701",
    "Modern Huff calibration; distance-decay parameter varies by retail category.",
)
LUO_WANG_2003 = cite(
    "Luo, W. & Wang, F.", 2003,
    "Measures of spatial accessibility to health care in a GIS environment",
    "Environment and Planning B", "30", "865-884",
    "Two-step floating catchment area methodology.",
)
SENGUPTA_2018 = cite(
    "Sengupta, M., Xie, Y., Lopez, A., Habte, A., Maclaurin, G., & Shelby, J.", 2018,
    "The National Solar Radiation Database (NSRDB)",
    "Renewable and Sustainable Energy Reviews", "89", "51-60",
    "NSRDB methodology and validation; underlies PVWatts TMY data.",
)


# ─── Criterion seed ────────────────────────────────────────────────────────


def crit(criterion_id, workflow_type, criterion_name, criterion_type, *,
         weight_default=None, weight_min=None, weight_max=None,
         weight_rationale=None, exclusion_threshold=None, exclusion_rationale=None,
         data_tree, academic_sources, confidence_rules=None) -> dict[str, Any]:
    return locals().copy()


SEED: list[dict[str, Any]] = [
    # ═══════════════════════════════════════════════════════════════════════
    # SOLAR SITING — 8 scored + 6 exclusion
    # ═══════════════════════════════════════════════════════════════════════

    # ── Scored ────────────────────────────────────────────────────────────
    crit("solar_ghi", "solar_siting", "Solar Resource (GHI / Energy Yield)", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.18,
         weight_rationale=(
             "Lower than some studies because in the US Sun Belt GHI is uniformly "
             "high and provides minimal differentiation. Weight should increase "
             "in regions where GHI varies significantly."),
         data_tree=[
             alt("nrel_pvwatts_v8", "authoritative", 1.0,
                 "Hourly PV simulation → annual kWh, capacity factor, monthly profile",
                 "Dobos (2014), Freeman et al. (2014). Validated against thousands of US installations, median accuracy ±5.2 % (NREL 2018, 199 systems). Uses NSRDB TMY at 4 km resolution."),
             alt("nrel_nsrdb_ghi", "fallback", 0.7,
                 "Annual and monthly GHI at 4 km grid — useful when PVWatts is unavailable",
                 "Sengupta et al. (2018). Raw irradiance, not system output."),
         ],
         academic_sources=[DOBOS_2014, FREEMAN_2014, SENGUPTA_2018, DOORGA_2019, AL_SHAMMARI_2026],
    ),

    crit("solar_slope", "solar_siting", "Terrain Slope", "scored",
         weight_default=0.15, weight_min=0.11, weight_max=0.17,
         weight_rationale="Consistently high across all studies (top-3 criterion).",
         data_tree=[
             alt("usgs_3dep", "authoritative", 1.0,
                 "Slope in degrees/percent via finite-difference of 1/3 arc-second DEM",
                 "Gesch et al. (2018). 3DEP is the standard US elevation dataset cited in every CONUS-scale solar study."),
         ],
         academic_sources=[GESCH_2018, DOORGA_2019, AL_SHAMMARI_2026, HERNANDEZ_2015],
    ),

    crit("solar_aspect", "solar_siting", "Terrain Aspect", "scored",
         weight_default=0.10, weight_min=0.08, weight_max=0.12,
         weight_rationale=(
             "Lower because tracking systems eliminate aspect sensitivity. "
             "Weight should be zero for single-axis or dual-axis tracking."),
         data_tree=[
             alt("usgs_3dep", "authoritative", 1.0,
                 "Dominant aspect in degrees; deviation from 180° (south) as scoring input",
                 "Charabi & Gastli (2011). Aspect is meaningless on flat terrain (slope <1°) and must be suppressed when slope is negligible."),
         ],
         academic_sources=[CHARABI_GASTLI_2011, GESCH_2018],
    ),

    crit("solar_transmission", "solar_siting", "Transmission Proximity", "scored",
         weight_default=0.25, weight_min=0.10, weight_max=0.45,
         weight_rationale=(
             "Kern County validation used 0.45 because GHI is uniform and grid "
             "proximity dominates differentiation, consistent with Al-Shammari et al. "
             "(2026). Literature range 0.10-0.16 reflects studies where irradiance "
             "varies more. Geography-dependent adjustment recommended."),
         data_tree=[
             alt("hifld_transmission", "authoritative", 1.0,
                 "Distance to nearest transmission line with voltage classification",
                 "HIFLD (DHS/CISA). 52,244 segments. Hernandez et al. (2015) used HIFLD."),
             alt("osm_substations", "authoritative", 1.0,
                 "Distance to nearest substation (PostGIS cache for 6 states)",
                 "OSM contributors. Substations are the actual point of interconnection."),
             alt("osm_substations_overpass", "fallback", 0.7,
                 "Same data via live Overpass for any US location",
                 "Higher latency (2-5 s) and rate limits, but national coverage."),
         ],
         academic_sources=[HERNANDEZ_2015, AL_SHAMMARI_2026, DOORGA_2019],
    ),

    crit("solar_road", "solar_siting", "Road Proximity", "scored",
         weight_default=0.12, weight_min=0.10, weight_max=0.14,
         weight_rationale="Consistently included; lower weight than transmission because road construction is cheaper than gen-tie.",
         data_tree=[
             alt("osm_roads_overpass", "authoritative", 1.0,
                 "Distance to nearest classified road via live Overpass",
                 "OSM contributors. Classification quality varies by region."),
         ],
         academic_sources=[HERNANDEZ_2015, DOORGA_2019],
    ),

    crit("solar_land_cover", "solar_siting", "Land Cover", "scored",
         weight_default=0.10, weight_min=0.08, weight_max=0.12,
         weight_rationale="Moderate weight; primarily differentiates agricultural (preferred) from non-agricultural land.",
         data_tree=[
             alt("nlcd_land_cover", "authoritative", 1.0,
                 "NLCD class at parcel location (16 classes, 30 m, 2021)",
                 "Yang et al. (2018). The standard US land cover dataset; Hernandez et al. (2015) classified solar installations by NLCD cover type."),
         ],
         academic_sources=[YANG_2018, HERNANDEZ_2015, AL_SHAMMARI_2026],
    ),

    crit("solar_soil", "solar_siting", "Soil Suitability", "scored",
         weight_default=0.08, weight_min=0.05, weight_max=0.10,
         weight_rationale="Rarely high weight; soil conditions affect cost but almost never kill a project.",
         data_tree=[
             alt("usda_sda_ssurgo", "authoritative", 1.0,
                 "Drainage class, hydric rating, depth to water table, shrink-swell potential",
                 "USDA NRCS National Cooperative Soil Survey. SDA REST API national, 1:12,000-1:24,000 scale."),
         ],
         academic_sources=[],
         confidence_rules={
             "note": "ORNL OR-SAGE framework cites SSURGO as siting criterion; no single peer-reviewed paper is the definitive source.",
         },
    ),

    crit("solar_ej", "solar_siting", "Environmental Justice", "scored",
         weight_default=0.05, weight_min=0.00, weight_max=0.05,
         weight_rationale="Included for regulatory awareness, not as a primary siting criterion. Weight should increase for federally-funded or -permitted projects.",
         data_tree=[
             alt("epa_ejscreen", "authoritative", 1.0,
                 "EJ index percentiles + demographic index at block group",
                 "EPA EJScreen 2024 v2.3. 243,022 block groups. Static snapshot (EPA tool offline since Feb 2025)."),
         ],
         academic_sources=[],
         confidence_rules={
             "note": "Newer addition to siting criteria; driven by Justice40 and state permitting requirements, not foundational literature.",
         },
    ),

    # ── Exclusion ─────────────────────────────────────────────────────────
    crit("excl_protected", "solar_siting", "Protected Areas", "exclusion",
         exclusion_threshold="any overlap with PAD-US polygon",
         exclusion_rationale="Consistent hard exclusion across all studies. National parks, wilderness, conservation easements preclude development.",
         data_tree=[
             alt("usgs_padus", "authoritative", 1.0,
                 "Protected area overlap with name, designation type, GAP status",
                 "Hernandez et al. (2015) used GAP (now PAD-US). 306,082 polygons nationally."),
         ],
         academic_sources=[HERNANDEZ_2015],
    ),

    crit("excl_wetlands", "solar_siting", "Wetlands", "exclusion",
         exclusion_threshold="any overlap with NWI polygon (or hydric flag when proxy)",
         exclusion_rationale="Hernandez et al. (2015) excluded wetlands. OR-SAGE framework treats NWI as a decision layer. Cowardin et al. (1979) classification standard.",
         data_tree=[
             alt("nwi_wetlands", "authoritative", 1.0,
                 "NWI boundaries with Cowardin classification and acreage",
                 "Cowardin et al. (1979). National wetland classification standard. PostGIS-loaded for limited geographies."),
             alt("nwi_wetlands_rest", "authoritative", 1.0,
                 "Same NWI data via on-demand REST service",
                 "USFWS Wetlands MapServer. Service degraded as of June 2026 (HTTP 500 on queries)."),
             alt("usda_sda_ssurgo", "proxy", 0.4,
                 "SSURGO hydric soils flag — indicator of potential wetland",
                 "NRCS. Hydric soil is one of three criteria for jurisdictional wetland delineation (1987 Corps Manual). Proxy only: no boundary geometry, acreage, or Cowardin classification. False positive rate is high on drained/developed land."),
         ],
         academic_sources=[HERNANDEZ_2015, COWARDIN_1979],
    ),

    crit("excl_critical_habitat", "solar_siting", "Critical Habitat (ESA)", "exclusion",
         exclusion_threshold="any overlap with USFWS-designated critical habitat",
         exclusion_rationale="ESA §7 consultation required for federal actions affecting listed species or designated CH.",
         data_tree=[
             alt("usfws_critical_habitat", "authoritative", 1.0,
                 "Overlap with species name and listing status",
                 "USFWS ECOS. 802 designated polygons nationally. Covers only species with formally designated CH."),
         ],
         academic_sources=[],
    ),

    crit("excl_flood", "solar_siting", "Flood Zones (SFHA)", "exclusion",
         exclusion_threshold="any overlap with FEMA SFHA (Zone A* or V*)",
         exclusion_rationale="SFHA zones face permitting restrictions, lender requirements, and physical risk.",
         data_tree=[
             alt("fema_nfhl", "authoritative", 1.0,
                 "Flood zone classification (A, AE, V, VE, X). SFHA = excluded.",
                 "FEMA NFHL. Map currency varies by community."),
         ],
         academic_sources=[],
    ),

    crit("excl_steep", "solar_siting", "Steep Slope", "exclusion",
         exclusion_threshold="slope > 15 % (configurable; literature range 3-20 %)",
         exclusion_rationale="Hernandez et al. (2015) used 3 % (conservative); NREL technical reports 5-10 %; 'Beyond Prime Farmland' (2025) uses 10°. Default 15 % is moderate.",
         data_tree=[
             alt("usgs_3dep", "authoritative", 1.0,
                 "Binary: slope above threshold = excluded",
                 "Same 3DEP DEM as scored slope criterion."),
         ],
         academic_sources=[GESCH_2018, HERNANDEZ_2015],
    ),

    crit("excl_urban", "solar_siting", "Developed / Urban Land", "exclusion",
         exclusion_threshold="NLCD developed classes (21-24); often only 23-24 for distributed solar",
         exclusion_rationale="Hernandez et al. (2015) excluded built-up areas. Al-Shammari et al. (2026) use NLCD developed classes.",
         data_tree=[
             alt("nlcd_land_cover", "authoritative", 1.0,
                 "Binary: developed classes (21-24) = excluded",
                 "Same NLCD as scored land cover criterion."),
         ],
         academic_sources=[YANG_2018, HERNANDEZ_2015, AL_SHAMMARI_2026],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # HAZARD ASSESSMENT — 5 wildfire + 5 flood
    # ═══════════════════════════════════════════════════════════════════════

    # ── Wildfire ──────────────────────────────────────────────────────────
    crit("wf_likelihood", "hazard_assessment", "Wildfire Likelihood (Burn Probability)", "scored",
         weight_default=0.35, weight_min=0.30, weight_max=0.45,
         weight_rationale="Primary hazard signal; the foundation Heavi consumes.",
         data_tree=[
             alt("usfs_fsim", "authoritative", 1.0,
                 "Annual burn probability per 270 m pixel from simulated fire seasons",
                 "Finney et al. (2011). USFS Research Data Archive RDS-2016-0034-2. Uses LANDFIRE 2014 fuels (temporal mismatch with current conditions)."),
         ],
         academic_sources=[FINNEY_2011],
    ),

    crit("wf_fuel_proximity", "hazard_assessment", "Distance to Burnable Fuel", "scored",
         weight_default=0.20, weight_min=0.15, weight_max=0.25,
         weight_rationale="Coffey Park pattern: urban-distant structures still vulnerable via structure-to-structure cascades (Kramer 2018).",
         data_tree=[
             alt("landfire_fuels_canopy", "authoritative", 1.0,
                 "Distance to nearest burnable fuel model from LANDFIRE FBFM40 raster",
                 "Rollins (2009). 30 m national."),
         ],
         academic_sources=[ROLLINS_2009, KRAMER_2018],
    ),

    crit("wf_canopy", "hazard_assessment", "Canopy Cover (Defensible Space)", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.20,
         weight_rationale="Syphard et al. (2012) established canopy cover at 30/100/300 m buffers as significant predictors.",
         data_tree=[
             alt("landfire_fuels_canopy", "authoritative", 1.0,
                 "Canopy cover percentage at 30/100/300 m buffer scales",
                 "Rollins (2009); Syphard et al. (2012) defensible space research."),
         ],
         academic_sources=[ROLLINS_2009, SYPHARD_2012],
    ),

    crit("wf_slope", "hazard_assessment", "Terrain Slope (Fire Behavior)", "scored",
         weight_default=0.10, weight_min=0.05, weight_max=0.15,
         weight_rationale="Upslope fire spread is faster; slope amplifies fire behavior.",
         data_tree=[
             alt("usgs_3dep", "authoritative", 1.0,
                 "Slope in degrees from 3DEP",
                 "Gesch et al. (2018). Same DEM as solar slope criterion."),
         ],
         academic_sources=[GESCH_2018, FINNEY_2011],
    ),

    crit("wf_structure", "hazard_assessment", "Building Characteristics", "scored",
         weight_default=0.20, weight_min=0.15, weight_max=0.25,
         weight_rationale="Occupancy class and construction type drive vulnerability; NSI is the national structure inventory.",
         data_tree=[
             alt("usace_nsi", "authoritative", 1.0,
                 "Occupancy class, foundation, stories, replacement value",
                 "USACE NSI v2. Synthesized centroids (20-100 m positional error)."),
         ],
         academic_sources=[KRAMER_2018, SYPHARD_2012],
    ),

    # ── Flood ─────────────────────────────────────────────────────────────
    crit("fl_zone", "hazard_assessment", "Flood Zone (Regulatory)", "scored",
         weight_default=0.30, weight_min=0.25, weight_max=0.40,
         weight_rationale="Regulatory zone is the foundation of US flood risk assessment.",
         data_tree=[
             alt("fema_nfhl", "authoritative", 1.0,
                 "Flood zone (A, AE, V, VE, X, D), BFE where published",
                 "FEMA NFHL. Map currency varies by community. BFE not available in all zones."),
         ],
         academic_sources=[SCAWTHORN_2006A],
    ),

    crit("fl_depth", "hazard_assessment", "Flood Depth Estimation", "scored",
         weight_default=0.30, weight_min=0.25, weight_max=0.40,
         weight_rationale="Depth at structure drives damage; multi-source computation = BFE − ground − FFH.",
         data_tree=[
             comp("fema_nfhl", 1.0,
                  "provides BFE for depth computation",
                  "cannot compute regulatory depth — fall back to zone-default assumptions",
                  0.4,
                  "FEMA NFHL is the regulatory flood hazard dataset. BFE is the authoritative base flood elevation per Scawthorn et al. (2006)."),
             comp("usgs_3dep", 1.0,
                  "provides ground elevation for depth = BFE − ground − FFH",
                  "cannot compute depth at all",
                  0.0,
                  "USGS 3DEP. Gesch et al. (2018)."),
             comp("usace_nsi", 1.0,
                  "provides first floor height for depth computation",
                  "use occupancy-class default FFH (1 ft slab, 3 ft crawlspace)",
                  0.7,
                  "USACE NSI v2. First floor heights are estimated, not surveyed; errors of 1-3 ft directly affect damage."),
             supp("google_inundation_history",
                  "corroborates or contradicts NFHL-based estimate",
                  "Google Flood Forecasting Initiative. CC-BY-4.0. Satellite flood frequency 1999-2020 at 128 m."),
         ],
         academic_sources=[SCAWTHORN_2006A, SCAWTHORN_2006B, GESCH_2018],
    ),

    crit("fl_historical", "hazard_assessment", "Historical Flood Context", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.20,
         weight_rationale="Observed disasters and NFIP claims ground the prediction in reality.",
         data_tree=[
             alt("openfema_disasters", "authoritative", 1.0,
                 "Disaster declarations by county + NFIP claims by zip code",
                 "OpenFEMA Open Data. NFIP claims have ~0.1° coordinate redaction; reflects insured losses, not total."),
             alt("usgs_peak_flow", "fallback", 0.7,
                 "Peak streamflow magnitude at nearest USGS gauge",
                 "USGS Water Services. Rural areas may have distant gauges."),
         ],
         academic_sources=[],
    ),

    crit("fl_hydrology", "hazard_assessment", "Hydrologic Context (Watershed + Discharge)", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.20,
         weight_rationale="Watershed-level discharge predictions corroborate property-level estimates.",
         data_tree=[
             alt("google_grrr", "authoritative", 1.0,
                 "AI-derived discharge at return periods for nearest river reach",
                 "Google Flood Forecasting Initiative. CC-BY-4.0. HydroBasins framework, 1980-2023."),
             comp("usgs_nhdplus", 1.0,
                  "HUC-12 watershed + flowline + stream order for nearest waterway",
                  "fall back to bbox-extent watershed assignment without flow context",
                  0.4,
                  "USGS National Hydrography. 1:24,000."),
             supp("usgs_peak_flow",
                  "gauge observations for return-period validation",
                  "USGS Water Services. Gauge density varies."),
         ],
         academic_sources=[],
    ),

    crit("fl_building", "hazard_assessment", "Building Damage Estimation", "scored",
         weight_default=0.10, weight_min=0.05, weight_max=0.15,
         weight_rationale="HAZUS DDFs translate depth into damage % by building type.",
         data_tree=[
             comp("hazus_ddfs", 1.0,
                  "depth-damage curves by building type + foundation",
                  "cannot estimate dollar damage",
                  0.0,
                  "FEMA HAZUS reconciled against haz_fl_dept database. 174 rows / 6 occupancy classes."),
             comp("usace_nsi", 1.0,
                  "building type + replacement value for dollar loss",
                  "use national-average building type + value",
                  0.4,
                  "USACE NSI v2. Construction type and value are estimates."),
         ],
         academic_sources=[SCAWTHORN_2006B],
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # TRADE AREA — 7 criteria
    # ═══════════════════════════════════════════════════════════════════════

    crit("ta_population", "trade_area", "Population Coverage", "scored",
         weight_default=0.25, weight_min=0.20, weight_max=0.30,
         weight_rationale="Total population in catchment is the foundational trade-area metric.",
         data_tree=[
             alt("census_acs", "authoritative", 1.0,
                 "Population at tract level via Census ACS API; area-weighted to isochrone",
                 "Census Bureau ACS 5-year. National coverage."),
         ],
         academic_sources=[HUFF_1963, HUFF_1964],
    ),

    crit("ta_competitive_gap", "trade_area", "Competitive Density", "scored",
         weight_default=0.20, weight_min=0.15, weight_max=0.25,
         weight_rationale="Competitive density vs reference benchmark identifies underserved catchments.",
         data_tree=[
             alt("osm_pois", "authoritative", 1.0,
                 "Same-category competitor count + nearest competitor distance from PostGIS cache",
                 "OpenStreetMap contributors. Loaded for Dallas County."),
             alt("osm_pois_overpass", "fallback", 0.7,
                 "Same data via live Overpass for any US location",
                 "Higher latency (2-5 s). Category classification varies by region."),
         ],
         academic_sources=[SUAREZ_VEGA_2015, LIANG_2020],
    ),

    crit("ta_income", "trade_area", "Median Household Income", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.20,
         weight_rationale="Median income is a key purchasing-power proxy.",
         data_tree=[
             alt("census_acs", "authoritative", 1.0,
                 "Median household income (B19013) at tract level",
                 "Census ACS 5-year."),
         ],
         academic_sources=[SUAREZ_VEGA_2015],
    ),

    crit("ta_daytime", "trade_area", "Daytime Population", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.20,
         weight_rationale="Daytime workplace population captures lunch/break/post-work commerce.",
         data_tree=[
             alt("census_lehd", "authoritative", 1.0,
                 "LEHD WAC workplace employment at census block",
                 "Census LEHD/LODES. Loaded for limited geographies."),
             alt("census_acs_commuter", "proxy", 0.4,
                 "ACS commuter count as proxy for daytime activity",
                 "Proxy only — commuter count ≠ workplace population. Tract-level, not block."),
         ],
         academic_sources=[],
    ),

    crit("ta_accessibility", "trade_area", "Accessibility (Drive-Time Isochrones)", "scored",
         weight_default=0.15, weight_min=0.10, weight_max=0.20,
         weight_rationale="Huff (1963) established travel time as the key variable in trade area delineation.",
         data_tree=[
             alt("ors_isochrones", "authoritative", 1.0,
                 "5/10/15 min drive-time polygons via ORS",
                 "OpenRouteService (HeiGIT). Free tier: 500 req/day."),
         ],
         academic_sources=[HUFF_1963, HUFF_1964, LUO_WANG_2003],
    ),

    crit("ta_complementary", "trade_area", "Complementary POI Density", "scored",
         weight_default=0.05, weight_min=0.00, weight_max=0.10,
         weight_rationale="Complementary businesses (anchor tenants, traffic generators) amplify trade area.",
         data_tree=[
             alt("osm_pois", "authoritative", 1.0,
                 "Complementary POI count from PostGIS cache",
                 "OpenStreetMap contributors."),
             alt("osm_pois_overpass", "fallback", 0.7,
                 "Same data via live Overpass",
                 "Higher latency."),
         ],
         academic_sources=[SUAREZ_VEGA_2015],
    ),

    crit("ta_flood", "trade_area", "Flood Risk Context", "scored",
         weight_default=0.05, weight_min=0.00, weight_max=0.10,
         weight_rationale="Trade areas in flood-prone locations face permitting, lender, and continuity risk.",
         data_tree=[
             alt("fema_nfhl", "authoritative", 1.0,
                 "Flood zone classification at site",
                 "FEMA NFHL. Map currency varies."),
         ],
         academic_sources=[],
    ),
]


UPSERT_SQL = """
INSERT INTO methodology_criteria (
    criterion_id, workflow_type, criterion_name, criterion_type,
    weight_default, weight_min, weight_max, weight_rationale,
    exclusion_threshold, exclusion_rationale,
    data_tree, academic_sources, confidence_rules
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12::jsonb, $13::jsonb
)
ON CONFLICT (criterion_id) DO UPDATE SET
    workflow_type = EXCLUDED.workflow_type,
    criterion_name = EXCLUDED.criterion_name,
    criterion_type = EXCLUDED.criterion_type,
    weight_default = EXCLUDED.weight_default,
    weight_min = EXCLUDED.weight_min,
    weight_max = EXCLUDED.weight_max,
    weight_rationale = EXCLUDED.weight_rationale,
    exclusion_threshold = EXCLUDED.exclusion_threshold,
    exclusion_rationale = EXCLUDED.exclusion_rationale,
    data_tree = EXCLUDED.data_tree,
    academic_sources = EXCLUDED.academic_sources,
    confidence_rules = EXCLUDED.confidence_rules
"""


async def seed() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    conn = await asyncpg.connect(url, ssl="require")
    try:
        for c in SEED:
            await conn.execute(
                UPSERT_SQL,
                c["criterion_id"], c["workflow_type"], c["criterion_name"],
                c["criterion_type"], c["weight_default"], c["weight_min"],
                c["weight_max"], c["weight_rationale"],
                c["exclusion_threshold"], c["exclusion_rationale"],
                json.dumps(c["data_tree"]),
                json.dumps(c["academic_sources"]),
                json.dumps(c["confidence_rules"]) if c.get("confidence_rules") else None,
            )
        total = await conn.fetchval("SELECT COUNT(*) FROM methodology_criteria")
        per_wf = await conn.fetch(
            "SELECT workflow_type, criterion_type, COUNT(*) AS n "
            "FROM methodology_criteria GROUP BY workflow_type, criterion_type "
            "ORDER BY workflow_type, criterion_type"
        )
        print(f"  upserted {len(SEED)} criteria; methodology_criteria now has {total}")
        for r in per_wf:
            print(f"    {r['workflow_type']:20s} {r['criterion_type']:10s} {r['n']}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
