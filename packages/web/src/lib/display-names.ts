// Human-readable display names for criterion IDs and data-source IDs.
//
// Frontend mirror of the server registry in
// packages/api/app/display_names.py (Natural Language Display Spec). The API now
// returns display_name / source_display fields alongside IDs and humanized gap
// messages + confidence statements, but the UI also iterates ID-keyed maps
// directly (notably trade-area criteria_scores, which use short keys like
// "population" and plain numbers). This registry is the client-side fallback so
// no technical ID is ever shown to a buyer.

export const CRITERION_DISPLAY: Record<string, string> = {
  // Solar — scored
  solar_transmission: "Transmission proximity",
  solar_ghi: "Solar resource (GHI)",
  solar_slope: "Terrain slope",
  solar_road: "Road access",
  solar_aspect: "Terrain aspect",
  solar_land_cover: "Land cover type",
  solar_soil: "Soil buildability",
  solar_ej: "Environmental Justice",
  // Solar — exclusions
  excl_protected: "Protected areas",
  excl_wetlands: "Wetlands",
  excl_critical_habitat: "Critical habitat",
  excl_flood: "Flood zone",
  excl_steep: "Steep slope",
  excl_urban: "Developed land",
  // Hazard — wildfire
  wf_likelihood: "Wildfire burn probability",
  wf_fuel_proximity: "Distance to burnable fuel",
  wf_canopy: "Canopy cover (defensible space)",
  wf_slope: "Terrain slope (fire behavior)",
  wf_structure: "Building vulnerability",
  // Hazard — flood
  fl_zone: "FEMA flood zone",
  fl_depth: "Estimated flood depth",
  fl_historical: "Historical flood events",
  fl_hydrology: "Hydrological exposure",
  fl_building: "Building damage estimate",
  // Trade area
  ta_population: "Population density",
  ta_competitive_gap: "Competitive density",
  ta_income: "Household income",
  ta_daytime: "Daytime population",
  ta_accessibility: "Drive-time accessibility",
  ta_complementary: "Complementary businesses",
  ta_flood: "Flood zone exposure",
};

export const SOURCE_DISPLAY: Record<string, string> = {
  nrel_pvwatts_v8: "NREL PVWatts v8",
  nrel_nsrdb_ghi: "NREL National Solar Radiation Database",
  usgs_3dep: "USGS 3D Elevation Program",
  hifld_transmission: "HIFLD Transmission Lines",
  osm_substations: "OpenStreetMap Substations",
  osm_substations_overpass: "OpenStreetMap Substations",
  osm_roads_overpass: "OpenStreetMap Roads",
  nlcd_land_cover: "National Land Cover Database 2021",
  usda_sda_ssurgo: "USDA SSURGO Soil Data",
  epa_ejscreen: "EPA EJScreen (discontinued)",
  usgs_padus: "Protected Areas Database (PAD-US)",
  nwi_wetlands: "National Wetlands Inventory",
  nwi_wetlands_rest: "National Wetlands Inventory (REST)",
  usfws_critical_habitat: "Critical Habitat Designations",
  fema_nfhl: "National Flood Hazard Layer",
  usace_nsi: "National Structure Inventory",
  usfs_fsim: "FSim Wildfire Simulation",
  nifc_fire_perimeters: "Historical Fire Perimeters",
  landfire_fuels_canopy: "LANDFIRE Fuel and Canopy",
  landfire_wcs_fuel: "LANDFIRE Fuel Model",
  landfire_wcs_canopy: "LANDFIRE Canopy Cover",
  census_acs: "American Community Survey",
  census_lehd: "LEHD Employment Data",
  census_acs_commuter: "ACS Commuter Flow Estimates",
  osm_pois: "OpenStreetMap Points of Interest",
  osm_pois_overpass: "OpenStreetMap Points of Interest",
  ors_isochrones: "Drive-Time Isochrones",
  hazus_ddfs: "HAZUS Depth-Damage Functions",
  openfema_disasters: "Disaster Declarations",
  usgs_peak_flow: "Peak Streamflow Records",
  solar_eia_installations: "EIA Form 860 Solar Installations",
  lbnl_queued_up: "LBNL Queued Up Interconnection Data",
};

function titleCase(id: string): string {
  return id.replace(/^(solar_|excl_|wf_|fl_|ta_)/, "").replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Display name for a criterion ID. Accepts both full IDs (ta_population) and the
 *  short trade-area keys (population) by trying a `ta_` prefix. */
export function criterionName(id: string | null | undefined): string {
  if (!id) return "—";
  return CRITERION_DISPLAY[id] ?? CRITERION_DISPLAY[`ta_${id}`] ?? titleCase(id);
}

/** Display name for a data-source ID. */
export function sourceName(id: string | null | undefined): string {
  if (!id) return "—";
  return SOURCE_DISPLAY[id] ?? id;
}
