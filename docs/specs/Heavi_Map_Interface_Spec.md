# HEAVI MAP INTERFACE SPECIFICATION
# Map-Based Delivery Surface Using MapLibre GL JS

## Purpose

The current web UI uses a form → text results pattern. A spatial analysis product needs to deliver results ON a map — parcels color-coded by score, constraint layers as toggleable overlays, click-to-inspect detail panels. This is the delivery surface that Atlas, Aino, and every serious spatial analysis product provides.

The map interface is not a separate product. It replaces the current text-only results with a map-first experience. Every scored assessment should be VIEWABLE on a map.

---

## Technology Stack

### MapLibre GL JS
- Open-source fork of Mapbox GL v1 — same rendering quality, no per-load pricing
- React integration via **react-map-gl** v7 (supports both Mapbox and MapLibre via the mapLib prop)
- Install: `pnpm add maplibre-gl react-map-gl`

### Basemap Tiles
Use OpenFreeMap (free, no API key):
```
style: "https://tiles.openfreemap.org/styles/liberty"
```
Alternative: MapTiler free tier if OpenFreeMap is slow or unavailable.

### GeoJSON Layers
All constraint overlays and scored results rendered as GeoJSON sources + layers on the MapLibre map. No tile server needed — the data volumes are small enough for client-side rendering.

---

## Shared Map Component

Build a reusable `<HeaviMap>` component that all three products share:

```tsx
interface HeaviMapProps {
  // Core
  center: [number, number];     // [lng, lat] initial center
  zoom: number;                 // initial zoom
  
  // Scored points/parcels
  scoredFeatures?: GeoJSON.FeatureCollection;  // points or polygons with score properties
  scoreColorField?: string;     // which property to color by (default: "score")
  scoreColorScale?: "suitability" | "risk" | "tradearea";  // color palette selection
  
  // Constraint overlays (toggleable)
  constraintLayers?: ConstraintLayer[];
  
  // Interaction
  onFeatureClick?: (feature: GeoJSON.Feature) => void;  // fires when user clicks a scored point
  selectedFeature?: GeoJSON.Feature | null;              // currently selected feature (for highlight)
  
  // Detail panel
  detailPanel?: React.ReactNode;  // rendered in a sidebar when a feature is selected
}

interface ConstraintLayer {
  id: string;
  name: string;                  // display name in layer toggle
  geojson: GeoJSON.FeatureCollection;
  style: LayerStyle;             // fill color, opacity, outline
  visible: boolean;              // initially visible?
  category: string;              // "environmental" | "infrastructure" | "hazard" | "administrative"
}
```

### Color Scales

Three color scales matching the three products:

**Suitability (Energy):** Green → Yellow → Red
- Score ≥ 0.70: `#22c55e` (green, High)
- Score 0.40–0.69: `#eab308` (amber, Moderate)
- Score < 0.40: `#ef4444` (red, Low)
- Excluded: `#6b7280` (gray, hatched pattern)

**Risk (Hazard):** Red → Yellow → Green (inverted — low risk is good)
- High risk: `#ef4444` (red)
- Moderate risk: `#eab308` (amber)
- Low risk: `#22c55e` (green)

**Trade Area (Locations):** Blue → Purple → Teal
- Strong: `#06b6d4` (teal)
- Moderate: `#8b5cf6` (purple)
- Weak: `#64748b` (slate)

### Layer Toggle Panel

A floating panel (top-right or bottom-left) with toggleable layers:
```
☑ Protected Areas (PAD-US)
☑ Flood Zones (NFHL)
☐ Wetlands (NWI)
☐ Transmission Lines
☐ Substations
☑ EIA Solar Installations
```

Each toggle shows/hides the corresponding GeoJSON layer. Layers grouped by category (Environmental, Infrastructure, Hazard).

### Click-to-Inspect

When the user clicks a scored point/parcel on the map:
1. The point highlights (larger marker, glow effect, or outline pulse)
2. A detail panel slides in from the right (or bottom on mobile)
3. The panel shows the full assessment result: score, rating, confidence, per-criterion breakdown, data gaps, methodology
4. The panel is the SAME data currently shown in the text results — just in a sidebar instead of below the form

---

## Product-Specific Map Experiences

### Energy (/energy)

**Workflow:**
1. User enters coordinates OR uploads a CSV of candidate parcels
2. Map centers on the location(s)
3. User clicks "Score" (single site) or "Score All" (batch)
4. As results come back, parcels appear on the map, color-coded by suitability score
5. Constraint layers are available as toggles
6. User clicks a parcel → detail panel shows score, confidence, per-criterion breakdown

**Map layers available:**
- Scored parcels (points or polygons, color-coded by suitability)
- PAD-US protected areas (fill: light red with diagonal hatch for GAP 1-2, light orange for GAP 3-4)
- FEMA flood zones (fill: light blue with opacity 0.3)
- NWI wetlands (fill: teal with opacity 0.3) — where loaded
- HIFLD transmission lines (line: yellow, width by voltage class)
- Substations (circle markers: orange)
- EIA solar installations (small circle markers: green, for context — "existing solar farms near your candidate")
- NLCD land cover (raster tile overlay if available, or simplified polygon)

**Detail panel on click:**
```
────────────────────────────
PARCEL ASSESSMENT
35.3500, -119.0500
────────────────────────────
SCORE      78 / 100  [High]
CONFIDENCE 95 / 100  [HIGH]
────────────────────────────
"Based on authoritative data 
for all major criteria."

DATA GAPS (1)
• solar_ej: No data available
  for Environmental Justice

PER-CRITERION SCORES
solar_transmission   86
solar_slope          99
solar_ghi            67
solar_aspect        100
solar_road           50
solar_soil          100
solar_land_cover     10
excl_flood          100

EXCLUSIONS
✓ wetlands     pass (nwi_wetlands)
✓ protected    pass (usgs_padus)
✓ steep        pass (usgs_3dep)
✓ urban        pass (nlcd_land_cover)
✓ critical hab pass (usfws_ch)

WEIGHT PROFILE: WECC (calibrated)

METHODOLOGY
14 criteria · 10 citations
[Show full methodology →]
────────────────────────────
```

### Hazard (/hazard)

**Workflow:**
1. User enters an address or coordinates, or uploads a portfolio CSV
2. Map centers on the property/properties
3. User clicks "Assess"
4. Properties appear on the map, color-coded by risk tier
5. Hazard layers available as toggles
6. User clicks a property → detail panel shows wildfire + flood risk, dollar estimates, confidence

**Map layers available:**
- Scored properties (circle markers, color-coded by risk tier)
- FEMA flood zones (fill: graduated blue by zone — V=dark, AE=medium, A=light, X=none)
- FSim wildfire likelihood (if raster tiles available — heat map)
- Fire perimeters (historical FRAP perimeters as red polygons, if loaded)

**Detail panel on click:**
```
────────────────────────────
PROPERTY HAZARD ASSESSMENT
38.4405, -122.7144
────────────────────────────
WILDFIRE        $X,XXX/yr
  damage prob   XX%
  risk tier     [HIGH/MED/LOW]
  
FLOOD           $X,XXX/yr  
  zone          AE
  depth est     X.X ft
  risk tier     [HIGH/MED/LOW]

CONFIDENCE  MODERATE · 65%
"Uses proxy data for 3 criteria"

DATA GAPS (3)
• wf_likelihood: FSim unavailable
• wf_fuel_proximity: LANDFIRE unavailable
• wf_canopy: LANDFIRE unavailable

[Show full methodology →]
────────────────────────────
```

### Locations (/locations)

**Workflow:**
1. User enters a candidate site or uploads multiple
2. Map centers on the site
3. User selects business category and clicks "Score"
4. Site appears on map with isochrone polygons overlaid (5/10/15 min drive times)
5. Competitor POIs appear as small dots within the trade area
6. User clicks the site → detail panel shows trade area score, demographics, competitive analysis

**Map layers available:**
- Scored sites (circle markers, color-coded by trade area score)
- Isochrone polygons (5 min = dark, 10 min = medium, 15 min = light — graduated opacity)
- Competitor POIs (small red dots — same-category businesses within the trade area)
- Complementary POIs (small blue dots — foot-traffic generators)
- Census tract boundaries (outline only, for demographic context)

**Detail panel on click:**
```
────────────────────────────
TRADE AREA ASSESSMENT
32.7800, -96.8000
coffee shop
────────────────────────────
SCORE     0.79  [Strong]
CONFIDENCE HIGH · 100%

DEMOGRAPHICS (15-min drive)
  Population    XXX,XXX
  Households     XX,XXX
  Median HHI   $XX,XXX
  Daytime emp   XX,XXX

COMPETITIVE LANDSCAPE
  Same-category    XX nearby
  Nearest          X.X mi
  Complementary    XX nearby

DATA SOURCES
  POIs:       osm_pois (PostGIS)
  Daytime:    census_lehd (block)
  Population: census_acs (tract)
  Flood:      fema_nfhl

[Show full methodology →]
────────────────────────────
```

---

## Page Layout

The map should be the primary element, not a small widget. Layout:

```
┌──────────────────────────────────────────────────────┐
│  HEAVI  [Energy] [Hazard] [Locations]     [Modules]  │
├──────────────┬───────────────────────────────────────┤
│              │                                       │
│  Input       │                                       │
│  Panel       │                MAP                    │
│  (left       │          (fills remaining space)      │
│   sidebar,   │                                       │
│   ~350px)    │                                       │
│              │                                       │
│  ──────────  │                                       │
│              │                                       │
│  Detail      │                                       │
│  Panel       │          ┌─────────────────┐          │
│  (appears    │          │  Layer toggles  │          │
│   on click)  │          └─────────────────┘          │
│              │                                       │
└──────────────┴───────────────────────────────────────┘
```

- Left sidebar (~350px): input form (lat/lng or address, business category, upload CSV), scoring controls
- Map: fills remaining width and full height
- Layer toggles: floating panel inside the map (top-right)
- Detail panel: replaces or slides below the input panel in the left sidebar when a feature is selected

On mobile: map fills viewport, input and detail panels are bottom sheets.

---

## Constraint Layer Data

The constraint layers are rendered from GeoJSON. For the initial implementation, load them ON DEMAND when the user toggles a layer:

### How to get constraint GeoJSON for the map viewport

For each constraint layer, query the API for features within the current map viewport:

```
GET /constraints/{layer_id}?bbox={west},{south},{east},{north}&limit=5000
```

This endpoint queries the PostGIS table for the constraint and returns GeoJSON features within the bounding box. Supported layers:

| layer_id | PostGIS table | Notes |
|---|---|---|
| padus | usgs_padus (via REST) | Query PAD-US for protected areas in viewport |
| nfhl | fema_nfhl (via REST) | Query FEMA NFHL for flood zones in viewport |
| nwi | solar_wetlands_ca | Only available for Kern County |
| transmission | solar_transmission_lines | HIFLD, full national |
| substations | substations_osm_us | 6-state cache |
| eia_solar | solar_eia_installations | National, 6,321 plants |

For external REST sources (PAD-US, NFHL), proxy through the Heavi API to avoid CORS issues:
```
GET /constraints/padus?bbox=-119.5,35.0,-118.5,35.5
→ proxies to https://mapservices.nps.gov/arcgis/rest/services/padus/FeatureServer/0/query
   with geometry={bbox}&geometryType=esriGeometryEnvelope&outFields=*&f=geojson
→ returns GeoJSON
```

For PostGIS sources, query directly:
```sql
SELECT ST_AsGeoJSON(geometry)::json AS geometry, * 
FROM solar_transmission_lines 
WHERE geometry && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
LIMIT 5000
```

### New API endpoints needed:

```
GET /constraints/{layer_id}?bbox={w},{s},{e},{n}&limit=5000
```

Returns GeoJSON FeatureCollection for the requested constraint layer within the bounding box.

---

## Implementation Sequence

| Step | What | Depends On |
|---|---|---|
| 1 | Install maplibre-gl + react-map-gl, build shared `<HeaviMap>` component with basemap rendering | Nothing |
| 2 | Build scored feature layer with color-coded points and click-to-inspect | Step 1 |
| 3 | Build detail panel sidebar with score/confidence/criterion display | Step 2 |
| 4 | Build constraint layer toggles + on-demand loading | Step 1 |
| 5 | Build GET /constraints/{layer_id} API endpoint | Nothing (parallel) |
| 6 | Wire into /energy page: replace text-only results with map + sidebar | Steps 1-5 |
| 7 | Wire into /hazard page | Step 6 (same pattern) |
| 8 | Wire into /locations page with isochrone polygons | Step 6 |
| 9 | Mobile responsive: bottom sheet panels | Steps 6-8 |

Steps 1-5 can be built as a standalone map component before wiring into any product page.

---

## Design Direction

The map interface should feel like a professional spatial analysis tool, not a consumer web map. Design references: Atlas AI, Planet Explorer.

**Dark theme** (consistent with current Heavi dark UI):
- Basemap: use a dark-style tile layer (OpenFreeMap dark or MapTiler dark matter)
- Scored features: bright, saturated colors against the dark basemap
- Constraint overlays: semi-transparent fills with crisp outlines
- Sidebar: same dark card style as current results UI
- Typography: same font stack as current site

**Map controls:**
- Zoom +/- buttons (bottom-right)
- Geocoder search (top-left, inside map) — for jumping to an address
- Scale bar (bottom-left)
- Layer toggle panel (top-right)
- No rotation/pitch (keep 2D — this is an analysis tool, not a 3D viewer)

**Interaction polish:**
- Hover on scored feature: cursor changes, feature highlights with subtle glow
- Click on scored feature: feature gets a bright outline ring, detail panel slides in
- Pan/zoom: constraint layers load lazily as the viewport changes (debounced fetch)
- Loading state: skeleton shimmer on the detail panel while scoring API call is in progress

---

## Acceptance Criteria

### Shared Component
1. `<HeaviMap>` renders a MapLibre map with OpenFreeMap (or MapTiler) dark basemap
2. Scored features render as color-coded circles (energy: green/amber/red, hazard: red/amber/green, locations: teal/purple/slate)
3. Clicking a scored feature fires onFeatureClick and highlights the feature
4. Layer toggle panel shows/hides constraint layers
5. Constraint layers load on-demand when toggled (not pre-loaded)

### Energy Map
6. /energy page shows map filling the right side, input form in left sidebar
7. Scoring a site places a color-coded marker on the map at the scored location
8. Clicking the marker opens the detail panel with score, confidence, per-criterion breakdown
9. Constraint layers (PAD-US, transmission, substations) render when toggled
10. Multiple scored locations from CSV upload all render simultaneously

### Hazard Map
11. /hazard page follows same layout
12. Assessed properties render color-coded by risk tier
13. Click opens detail panel with wildfire + flood scores
14. FEMA flood zones render as semi-transparent overlay when toggled

### Locations Map
15. /locations page follows same layout
16. Scored sites render color-coded by trade area score
17. Isochrone polygons (5/10/15 min) render as graduated overlays around the scored site
18. Competitor POIs render as small markers within the trade area

### API
19. GET /constraints/transmission?bbox=... returns GeoJSON for transmission lines in viewport
20. GET /constraints/padus?bbox=... returns GeoJSON for protected areas in viewport
21. GET /constraints/eia_solar?bbox=... returns GeoJSON for EIA installations in viewport

### Responsive
22. On viewport < 768px, map fills screen, panels become bottom sheets
