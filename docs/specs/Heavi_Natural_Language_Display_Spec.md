# HEAVI NATURAL LANGUAGE DISPLAY SPEC
# Replace Technical IDs with Human-Readable Labels Everywhere

## Problem

The UI displays internal criterion IDs and data source table names instead of natural language:

**Current (technical):**
```
Data gaps (1)
• solar_ej: No data available for Environmental Justice. Tried: epa_ejscreen
```

**Target (natural language):**
```
Data gaps (1)
• Environmental Justice screening data is unavailable at this location.
  The EPA EJScreen tool has been discontinued.
```

This affects: data gap messages, per-criterion score labels, exclusion labels, source attributions, confidence statements, interconnection context, and PDF export. It occurs across all three modules.

## Solution

Create a display name registry that maps every criterion ID, source ID, and gap scenario to human-readable text. Apply it everywhere the UI or PDF renders criterion/source information.

---

## DISPLAY NAME REGISTRY

### Criterion Display Names

**Solar Siting (scored):**

| Criterion ID | Display Name | Short Description |
|---|---|---|
| solar_transmission | Transmission proximity | Distance to nearest high-voltage transmission line and substation |
| solar_ghi | Solar resource (GHI) | Annual solar irradiance from NREL PVWatts |
| solar_slope | Terrain slope | Ground slope percentage from USGS 3DEP elevation data |
| solar_road | Road access | Distance to nearest paved road |
| solar_aspect | Terrain aspect | Compass orientation of the ground surface |
| solar_land_cover | Land cover type | Land use classification — barren and grassland preferred over cropland |
| solar_soil | Soil buildability | Soil drainage and structural suitability from USDA SSURGO |
| solar_ej | Environmental Justice | Proximity to disadvantaged communities (EPA EJScreen) |

**Solar Siting (exclusions):**

| Criterion ID | Display Name | Exclusion Meaning |
|---|---|---|
| excl_protected | Protected areas | Federal or state protected land (USGS PAD-US GAP 1-2) |
| excl_wetlands | Wetlands | NWI-designated wetland or hydric soil indicator |
| excl_critical_habitat | Critical habitat | USFWS-designated critical habitat for threatened/endangered species |
| excl_flood | Flood zone | FEMA high-risk flood zone (V-zone) |
| excl_steep | Steep slope | Ground slope exceeds 20% |
| excl_urban | Developed land | NLCD high-intensity developed land (classes 23-24) |

**Hazard Assessment (wildfire):**

| Criterion ID | Display Name | Short Description |
|---|---|---|
| wf_likelihood | Wildfire burn probability | Annual probability of wildfire reaching this location |
| wf_fuel_proximity | Distance to burnable fuel | Proximity to burnable vegetation from LANDFIRE fuel models |
| wf_canopy | Canopy cover (defensible space) | Vegetation density within defensible space buffers |
| wf_slope | Terrain slope (fire behavior) | Slope affects fire spread rate and intensity |
| wf_structure | Building vulnerability | Structure type and construction from USACE National Structure Inventory |

**Hazard Assessment (flood):**

| Criterion ID | Display Name | Short Description |
|---|---|---|
| fl_zone | FEMA flood zone | Designated flood zone from the National Flood Hazard Layer |
| fl_depth | Estimated flood depth | Computed from base flood elevation minus ground elevation |
| fl_historical | Historical flood events | Past disaster declarations and peak streamflow records |
| fl_hydrology | Hydrological exposure | Proximity to waterways and catchment characteristics |
| fl_building | Building damage estimate | Structure-specific damage from HAZUS depth-damage functions |

**Trade Area:**

| Criterion ID | Display Name | Short Description |
|---|---|---|
| ta_population | Population density | Census ACS population within drive-time catchment |
| ta_competitive_gap | Competitive density | Same-category business count and nearest competitor distance |
| ta_income | Household income | Median household income from Census ACS |
| ta_daytime | Daytime population | Employment-based daytime population from LEHD or ACS commuter data |
| ta_accessibility | Drive-time accessibility | Isochrone-based catchment area from OpenRouteService |
| ta_complementary | Complementary businesses | Foot-traffic-generating businesses nearby |
| ta_flood | Flood zone exposure | FEMA flood zone designation for the site |

### Data Source Display Names

| Source ID | Display Name | Provider |
|---|---|---|
| nrel_pvwatts_v8 | NREL PVWatts v8 | National Renewable Energy Laboratory |
| nrel_nsrdb_ghi | NREL National Solar Radiation Database | National Renewable Energy Laboratory |
| usgs_3dep | USGS 3D Elevation Program | U.S. Geological Survey |
| hifld_transmission | HIFLD Transmission Lines | Homeland Infrastructure Foundation-Level Data |
| osm_substations | OpenStreetMap Substations | OpenStreetMap (cached) |
| osm_substations_overpass | OpenStreetMap Substations | OpenStreetMap (on-demand) |
| osm_roads_overpass | OpenStreetMap Roads | OpenStreetMap (on-demand) |
| nlcd_land_cover | National Land Cover Database 2021 | Multi-Resolution Land Characteristics Consortium |
| usda_sda_ssurgo | USDA SSURGO Soil Data | USDA Soil Data Access |
| epa_ejscreen | EPA EJScreen (discontinued) | U.S. Environmental Protection Agency |
| usgs_padus | Protected Areas Database (PAD-US) | U.S. Geological Survey |
| nwi_wetlands | National Wetlands Inventory | U.S. Fish and Wildlife Service |
| nwi_wetlands_rest | National Wetlands Inventory (REST) | U.S. Fish and Wildlife Service |
| usfws_critical_habitat | Critical Habitat Designations | U.S. Fish and Wildlife Service |
| fema_nfhl | National Flood Hazard Layer | Federal Emergency Management Agency |
| usace_nsi | National Structure Inventory | U.S. Army Corps of Engineers |
| usfs_fsim | FSim Wildfire Simulation | U.S. Forest Service |
| nifc_fire_perimeters | Historical Fire Perimeters | National Interagency Fire Center |
| landfire_fuels_canopy | LANDFIRE Fuel and Canopy (loaded) | USGS/USFS LANDFIRE |
| landfire_wcs_fuel | LANDFIRE Fuel Model (on-demand) | USGS/USFS LANDFIRE |
| landfire_wcs_canopy | LANDFIRE Canopy Cover (on-demand) | USGS/USFS LANDFIRE |
| census_acs | American Community Survey | U.S. Census Bureau |
| census_lehd | LEHD Employment Data | U.S. Census Bureau |
| census_acs_commuter | ACS Commuter Flow Estimates | U.S. Census Bureau |
| osm_pois | OpenStreetMap Points of Interest | OpenStreetMap (cached) |
| osm_pois_overpass | OpenStreetMap Points of Interest | OpenStreetMap (on-demand) |
| ors_isochrones | Drive-Time Isochrones | OpenRouteService |
| hazus_ddfs | HAZUS Depth-Damage Functions | FEMA HAZUS |
| openfema_disasters | Disaster Declarations | FEMA OpenFEMA |
| usgs_peak_flow | Peak Streamflow Records | U.S. Geological Survey |
| solar_eia_installations | EIA Form 860 Solar Installations | U.S. Energy Information Administration |
| lbnl_queued_up | LBNL Queued Up Interconnection Data | Lawrence Berkeley National Laboratory |

### Gap Message Templates

Instead of the generic "No data available for {criterion_name}. Tried: {source_id}", use context-specific messages:

| Criterion ID | Gap Message |
|---|---|
| solar_ej | Environmental Justice screening data is unavailable at this location. The EPA EJScreen tool has been discontinued. |
| solar_ghi | Solar irradiance data could not be retrieved from NREL PVWatts. The service may be temporarily unavailable. |
| solar_transmission | Transmission line proximity could not be determined. HIFLD data may not cover this location. |
| solar_slope | Terrain slope could not be computed. USGS elevation data may not be available at this location. |
| solar_land_cover | Land cover classification could not be determined from the National Land Cover Database. |
| solar_soil | Soil data could not be retrieved from USDA SSURGO for this location. |
| wf_likelihood | Wildfire burn probability could not be estimated. Neither FSim simulation data nor NIFC historical fire records are available at this location. |
| wf_fuel_proximity | Fuel model data is unavailable. LANDFIRE data could not be retrieved for this location. |
| wf_canopy | Canopy cover data is unavailable. Neither LANDFIRE nor NLCD vegetation data could be retrieved. |
| fl_zone | FEMA flood zone designation is unavailable at this location. The area may not have been mapped. |
| fl_depth | Flood depth cannot be estimated. Required elevation or flood zone data is missing. |
| ta_accessibility | Drive-time isochrones could not be generated. The routing service may be at capacity. |
| ta_population | Population data could not be retrieved from the Census American Community Survey. |
| ta_daytime | Daytime employment data is unavailable. LEHD coverage does not include this area, and the ACS commuter estimate could not be computed. |

---

## WHERE TO APPLY

### 1. Web UI — Data Gaps Section
Replace the current format:
```
• solar_ej: No data available for Environmental Justice. Tried: epa_ejscreen
```
With:
```
• Environmental Justice screening data is unavailable at this location.
  The EPA EJScreen tool has been discontinued.
```

### 2. Web UI — Per-Criterion Score Labels
Replace:
```
solar_transmission    86
solar_ghi             67
solar_slope           99
```
With:
```
Transmission proximity    86
Solar resource (GHI)      67
Terrain slope             99
```

### 3. Web UI — Exclusion Labels
Replace:
```
critical_habitat    pass · usfws_critical_habitat
protected           pass · usgs_padus
steep               pass · usgs_3dep
```
With:
```
Critical habitat      pass · U.S. Fish and Wildlife Service
Protected areas       pass · USGS PAD-US
Steep slope           pass · USGS 3D Elevation Program
```

### 4. Web UI — Confidence Statements
Replace source IDs in confidence statements with display names. Current:
```
"Proxy or partial data was used for: scored: wf_likelihood."
```
Target:
```
"Proxy or partial data was used for wildfire burn probability."
```

### 5. Web UI — Interconnection Context
Already uses natural language. No changes needed.

### 6. PDF Export
Apply the same display name mappings to the PDF. Criterion names, source names, gap messages — all should use natural language in the PDF output.

### 7. API Responses
Add a `display_name` field alongside the existing criterion IDs in the JSON response. The ID fields remain for programmatic use; the display names are for rendering.

```json
{
  "criteria_scores": {
    "solar_transmission": {
      "score": 86,
      "display_name": "Transmission proximity",
      "source": "hifld_transmission",
      "source_display": "HIFLD Transmission Lines",
      "confidence": "HIGH"
    }
  },
  "gaps": [
    {
      "criterion": "solar_ej",
      "display_name": "Environmental Justice",
      "message": "Environmental Justice screening data is unavailable at this location. The EPA EJScreen tool has been discontinued.",
      "tried": ["epa_ejscreen"]
    }
  ]
}
```

---

## Implementation

Create a single `display_names.py` (or equivalent frontend mapping) that all rendering code references:

```python
CRITERION_DISPLAY = {
    "solar_ej": {"name": "Environmental Justice", "description": "..."},
    "solar_transmission": {"name": "Transmission proximity", "description": "..."},
    ...
}

SOURCE_DISPLAY = {
    "epa_ejscreen": {"name": "EPA EJScreen (discontinued)", "provider": "U.S. EPA"},
    "hifld_transmission": {"name": "HIFLD Transmission Lines", "provider": "DHS HIFLD"},
    ...
}

GAP_MESSAGES = {
    "solar_ej": "Environmental Justice screening data is unavailable...",
    ...
}

def get_criterion_display(criterion_id):
    return CRITERION_DISPLAY.get(criterion_id, {"name": criterion_id, "description": ""})

def get_source_display(source_id):
    return SOURCE_DISPLAY.get(source_id, {"name": source_id, "provider": ""})

def get_gap_message(criterion_id):
    return GAP_MESSAGES.get(criterion_id, f"Data unavailable for {get_criterion_display(criterion_id)['name']}.")
```

The frontend reads these mappings (either from the API response's display_name fields, or from a client-side mapping file).

---

## Acceptance Criteria

1. Kern County solar assessment: per-criterion labels show "Transmission proximity", "Solar resource (GHI)", etc. — not "solar_transmission", "solar_ghi"
2. Kern County data gaps show "Environmental Justice screening data is unavailable at this location. The EPA EJScreen tool has been discontinued." — not "solar_ej: No data available..."
3. Exclusion labels show "Protected areas · USGS PAD-US" — not "protected · usgs_padus"
4. Sonoma County hazard assessment: wildfire criteria show "Wildfire burn probability", "Distance to burnable fuel" — not "wf_likelihood", "wf_fuel_proximity"
5. Dallas trade area: criteria show "Population density", "Competitive density", "Drive-time accessibility" — not "ta_population", "ta_competitive_gap", "ta_accessibility"
6. PDF export uses the same natural language labels
7. Confidence statements reference criterion display names, not IDs
8. API responses include display_name fields alongside IDs
9. All three modules (/energy, /hazard, /locations) updated
10. No technical IDs visible in the UI anywhere a buyer would see them
