"""Human-readable display names for criterion IDs, source IDs, and data gaps.

Single source of truth (server side) for the Natural Language Display Spec: every
internal criterion ID (``solar_transmission``, ``wf_likelihood``, ``ta_population``)
and data-source ID (``epa_ejscreen``, ``hifld_transmission``) maps to a label a
buyer can read. Used by the scoring engines (to enrich API responses and humanize
confidence statements / data-gap messages) and by the PDF export. The frontend
mirrors this registry in ``packages/web/src/lib/display-names.ts``.

IDs remain in the API response for programmatic use; the display fields are added
alongside them.
"""

from __future__ import annotations

from typing import Any

# ─── Criterion display names ───────────────────────────────────────────────────
# id -> {"name": <label>, "description": <one line>}
CRITERION_DISPLAY: dict[str, dict[str, str]] = {
    # Solar siting — scored
    "solar_transmission": {"name": "Transmission proximity",
        "description": "Distance to nearest high-voltage transmission line and substation"},
    "solar_ghi": {"name": "Solar resource (GHI)",
        "description": "Annual solar irradiance from NREL PVWatts"},
    "solar_slope": {"name": "Terrain slope",
        "description": "Ground slope percentage from USGS 3DEP elevation data"},
    "solar_road": {"name": "Road access",
        "description": "Distance to nearest paved road"},
    "solar_aspect": {"name": "Terrain aspect",
        "description": "Compass orientation of the ground surface"},
    "solar_land_cover": {"name": "Land cover type",
        "description": "Land use classification — barren and grassland preferred over cropland"},
    "solar_soil": {"name": "Soil buildability",
        "description": "Soil drainage and structural suitability from USDA SSURGO"},
    "solar_ej": {"name": "Environmental Justice",
        "description": "Proximity to disadvantaged communities (EPA EJScreen)"},
    # Solar siting — exclusions
    "excl_protected": {"name": "Protected areas",
        "description": "Federal or state protected land (USGS PAD-US GAP 1-2)"},
    "excl_wetlands": {"name": "Wetlands",
        "description": "NWI-designated wetland or hydric soil indicator"},
    "excl_critical_habitat": {"name": "Critical habitat",
        "description": "USFWS-designated critical habitat for threatened/endangered species"},
    "excl_flood": {"name": "Flood zone",
        "description": "FEMA high-risk flood zone (V-zone)"},
    "excl_steep": {"name": "Steep slope",
        "description": "Ground slope exceeds 20%"},
    "excl_urban": {"name": "Developed land",
        "description": "NLCD high-intensity developed land (classes 23-24)"},
    # Hazard — wildfire
    "wf_likelihood": {"name": "Wildfire burn probability",
        "description": "Annual probability of wildfire reaching this location"},
    "wf_fuel_proximity": {"name": "Distance to burnable fuel",
        "description": "Proximity to burnable vegetation from LANDFIRE fuel models"},
    "wf_canopy": {"name": "Canopy cover (defensible space)",
        "description": "Vegetation density within defensible space buffers"},
    "wf_slope": {"name": "Terrain slope (fire behavior)",
        "description": "Slope affects fire spread rate and intensity"},
    "wf_structure": {"name": "Building vulnerability",
        "description": "Structure type and construction from USACE National Structure Inventory"},
    # Hazard — flood
    "fl_zone": {"name": "FEMA flood zone",
        "description": "Designated flood zone from the National Flood Hazard Layer"},
    "fl_depth": {"name": "Estimated flood depth",
        "description": "Computed from base flood elevation minus ground elevation"},
    "fl_historical": {"name": "Historical flood events",
        "description": "Past disaster declarations and peak streamflow records"},
    "fl_hydrology": {"name": "Hydrological exposure",
        "description": "Proximity to waterways and catchment characteristics"},
    "fl_building": {"name": "Building damage estimate",
        "description": "Structure-specific damage from HAZUS depth-damage functions"},
    # Trade area
    "ta_population": {"name": "Population density",
        "description": "Census ACS population within drive-time catchment"},
    "ta_competitive_gap": {"name": "Competitive density",
        "description": "Same-category business count and nearest competitor distance"},
    "ta_income": {"name": "Household income",
        "description": "Median household income from Census ACS"},
    "ta_daytime": {"name": "Daytime population",
        "description": "Employment-based daytime population from LEHD or ACS commuter data"},
    "ta_accessibility": {"name": "Drive-time accessibility",
        "description": "Isochrone-based catchment area from OpenRouteService"},
    "ta_complementary": {"name": "Complementary businesses",
        "description": "Foot-traffic-generating businesses nearby"},
    "ta_flood": {"name": "Flood zone exposure",
        "description": "FEMA flood zone designation for the site"},
}

# ─── Data source display names ─────────────────────────────────────────────────
# id -> {"name": <label>, "provider": <provider>}
SOURCE_DISPLAY: dict[str, dict[str, str]] = {
    "nrel_pvwatts_v8": {"name": "NREL PVWatts v8",
                        "provider": "National Renewable Energy Laboratory"},
    "nrel_nsrdb_ghi": {"name": "NREL National Solar Radiation Database",
                       "provider": "National Renewable Energy Laboratory"},
    "usgs_3dep": {"name": "USGS 3D Elevation Program", "provider": "U.S. Geological Survey"},
    "hifld_transmission": {"name": "HIFLD Transmission Lines",
                           "provider": "Homeland Infrastructure Foundation-Level Data"},
    "osm_substations": {"name": "OpenStreetMap Substations", "provider": "OpenStreetMap (cached)"},
    "osm_substations_overpass": {"name": "OpenStreetMap Substations",
                                 "provider": "OpenStreetMap (on-demand)"},
    "osm_roads_overpass": {"name": "OpenStreetMap Roads", "provider": "OpenStreetMap (on-demand)"},
    "nlcd_land_cover": {"name": "National Land Cover Database 2021",
                        "provider": "Multi-Resolution Land Characteristics Consortium"},
    "usda_sda_ssurgo": {"name": "USDA SSURGO Soil Data", "provider": "USDA Soil Data Access"},
    "epa_ejscreen": {"name": "EPA EJScreen (discontinued)",
                     "provider": "U.S. Environmental Protection Agency"},
    "usgs_padus": {"name": "Protected Areas Database (PAD-US)",
                   "provider": "U.S. Geological Survey"},
    "nwi_wetlands": {"name": "National Wetlands Inventory",
                     "provider": "U.S. Fish and Wildlife Service"},
    "nwi_wetlands_rest": {"name": "National Wetlands Inventory (REST)",
                          "provider": "U.S. Fish and Wildlife Service"},
    "usfws_critical_habitat": {"name": "Critical Habitat Designations",
                               "provider": "U.S. Fish and Wildlife Service"},
    "fema_nfhl": {"name": "National Flood Hazard Layer",
                  "provider": "Federal Emergency Management Agency"},
    "usace_nsi": {"name": "National Structure Inventory",
                  "provider": "U.S. Army Corps of Engineers"},
    "usfs_fsim": {"name": "FSim Wildfire Simulation", "provider": "U.S. Forest Service"},
    "nifc_fire_perimeters": {"name": "Historical Fire Perimeters",
                             "provider": "National Interagency Fire Center"},
    "landfire_fuels_canopy": {"name": "LANDFIRE Fuel and Canopy (loaded)",
                              "provider": "USGS/USFS LANDFIRE"},
    "landfire_wcs_fuel": {"name": "LANDFIRE Fuel Model (on-demand)",
                          "provider": "USGS/USFS LANDFIRE"},
    "landfire_wcs_canopy": {"name": "LANDFIRE Canopy Cover (on-demand)",
                            "provider": "USGS/USFS LANDFIRE"},
    "census_acs": {"name": "American Community Survey", "provider": "U.S. Census Bureau"},
    "census_lehd": {"name": "LEHD Employment Data", "provider": "U.S. Census Bureau"},
    "census_acs_commuter": {"name": "ACS Commuter Flow Estimates",
                            "provider": "U.S. Census Bureau"},
    "osm_pois": {"name": "OpenStreetMap Points of Interest", "provider": "OpenStreetMap (cached)"},
    "osm_pois_overpass": {"name": "OpenStreetMap Points of Interest",
                          "provider": "OpenStreetMap (on-demand)"},
    "ors_isochrones": {"name": "Drive-Time Isochrones", "provider": "OpenRouteService"},
    "hazus_ddfs": {"name": "HAZUS Depth-Damage Functions", "provider": "FEMA HAZUS"},
    "openfema_disasters": {"name": "Disaster Declarations", "provider": "FEMA OpenFEMA"},
    "usgs_peak_flow": {"name": "Peak Streamflow Records", "provider": "U.S. Geological Survey"},
    "solar_eia_installations": {"name": "EIA Form 860 Solar Installations",
                                "provider": "U.S. Energy Information Administration"},
    "lbnl_queued_up": {"name": "LBNL Queued Up Interconnection Data",
                       "provider": "Lawrence Berkeley National Laboratory"},
}

# ─── Gap message templates ─────────────────────────────────────────────────────
# Context-specific, buyer-facing messages for a fully-exhausted criterion tree.
GAP_MESSAGES: dict[str, str] = {
    "solar_ej": "Environmental Justice screening data is unavailable at this location. "
                "The EPA EJScreen tool has been discontinued.",
    "solar_ghi": "Solar irradiance data could not be retrieved from NREL PVWatts. "
                 "The service may be temporarily unavailable.",
    "solar_transmission": "Transmission line proximity could not be determined. "
                          "HIFLD data may not cover this location.",
    "solar_slope": "Terrain slope could not be computed. USGS elevation data may not be "
                   "available at this location.",
    "solar_land_cover": "Land cover classification could not be determined from the "
                        "National Land Cover Database.",
    "solar_soil": "Soil data could not be retrieved from USDA SSURGO for this location.",
    "wf_likelihood": "Wildfire burn probability could not be estimated. Neither FSim "
                     "simulation data nor NIFC historical fire records are available at "
                     "this location.",
    "wf_fuel_proximity": "Fuel model data is unavailable. LANDFIRE data could not be "
                         "retrieved for this location.",
    "wf_canopy": "Canopy cover data is unavailable. Neither LANDFIRE nor NLCD vegetation "
                 "data could be retrieved.",
    "fl_zone": "FEMA flood zone designation is unavailable at this location. The area may "
               "not have been mapped.",
    "fl_depth": "Flood depth cannot be estimated. Required elevation or flood zone data "
                "is missing.",
    "ta_accessibility": "Drive-time isochrones could not be generated. The routing service "
                        "may be at capacity.",
    "ta_population": "Population data could not be retrieved from the Census American "
                     "Community Survey.",
    "ta_daytime": "Daytime employment data is unavailable. LEHD coverage does not include "
                  "this area, and the ACS commuter estimate could not be computed.",
}


# ─── Lookup helpers ────────────────────────────────────────────────────────────


def criterion_display(criterion_id: str | None) -> dict[str, str]:
    if not criterion_id:
        return {"name": "—", "description": ""}
    return CRITERION_DISPLAY.get(criterion_id, {"name": criterion_id, "description": ""})


def criterion_name(criterion_id: str | None) -> str:
    return criterion_display(criterion_id)["name"]


def source_display(source_id: str | None) -> dict[str, str]:
    if not source_id:
        return {"name": "—", "provider": ""}
    return SOURCE_DISPLAY.get(source_id, {"name": source_id, "provider": ""})


def source_name(source_id: str | None) -> str:
    if not source_id:
        return "—"
    return source_display(source_id)["name"]


def gap_message(criterion_id: str | None) -> str:
    """Context-specific gap message, or a generic one using the display name."""
    if criterion_id and criterion_id in GAP_MESSAGES:
        return GAP_MESSAGES[criterion_id]
    return f"{criterion_name(criterion_id)} data is unavailable at this location."


def make_gap(criterion_id: str | None, tried: list[str] | None = None) -> dict[str, Any]:
    """Structured data-gap object for an exhausted criterion (Display Spec §7)."""
    return {
        "criterion": criterion_id,
        "display_name": criterion_name(criterion_id),
        "message": gap_message(criterion_id),
        "tried": tried or [],
    }


def enrich_result(result: dict[str, Any]) -> dict[str, Any]:
    """Add ``display_name`` / ``source_display`` alongside IDs in a scoring result.

    Mutates and returns ``result``. Handles the per-criterion ID-keyed dicts that
    are common to the scoring engines: ``criteria_scores``, ``exclusion_results``,
    and ``confidence.per_criterion`` (plus the hazard per-peril
    ``criteria_confidence`` subsets). Entries that are not dicts (e.g. trade-area
    ``criteria_scores`` of plain numbers) are left untouched — the frontend labels
    those from its mirrored registry.
    """
    def _enrich_map(m: Any) -> None:
        if not isinstance(m, dict):
            return
        for cid, entry in m.items():
            if isinstance(entry, dict):
                entry.setdefault("display_name", criterion_name(cid))
                if "selected_source" in entry:
                    entry.setdefault("source_display", source_name(entry.get("selected_source")))

    _enrich_map(result.get("criteria_scores"))
    _enrich_map(result.get("exclusion_results"))
    conf = result.get("confidence")
    if isinstance(conf, dict):
        _enrich_map(conf.get("per_criterion"))
    # Hazard per-peril confidence subsets.
    for peril_key in ("wildfire", "flood"):
        peril = result.get(peril_key)
        if isinstance(peril, dict):
            _enrich_map(peril.get("criteria_confidence"))
    return result
