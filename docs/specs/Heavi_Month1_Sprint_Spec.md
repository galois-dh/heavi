# HEAVI MONTH 1 SPRINT: SOLAR PRODUCT GAPS
# Four Features That Block Design Partner Conversations

## Context

The 90-day goal is 3 design partner pilots with mid-market solar developers. Four product gaps will surface in every first demo and must be closed before outreach begins.

Build in this order (fastest path to a demo-ready product):
1. Address geocoding (quick, makes the demo usable)
2. Batch results on map with ranking (makes the demo visually compelling)
3. PDF export of scored assessment (gives the developer a tangible output)
4. Interconnection proximity intelligence (the biggest value-add, most complex)

---

## FEATURE 1: ADDRESS GEOCODING

### Problem
The current UI requires lat/lng coordinates. Solar developers think in addresses, APNs (Assessor Parcel Numbers), and place names — not coordinates. Asking someone to enter "35.35, -119.05" in a demo is a friction point.

### Solution
Add a geocoding input that accepts:
- Street addresses ("1234 Main St, Bakersfield, CA")
- Place names ("Kern County, CA")
- City/state ("Bakersfield, CA")
- Raw lat/lng (existing behavior, preserved)

Use the Census Bureau geocoder (free, no API key, no rate limits):
```
https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address={address}&benchmark=Public_AR_Current&format=json
```

Falls back to Nominatim (OpenStreetMap geocoder) if Census doesn't match:
```
https://nominatim.openstreetmap.org/search?q={address}&format=json&limit=1
```

### Implementation

Update the input fields on /energy, /hazard, and /locations pages:
- Replace the two separate lat/lng fields with a single text input
- Placeholder: "Enter address, place name, or lat,lng"
- On submit: detect if input looks like coordinates (contains comma + numbers) → use directly. Otherwise → geocode → use result coordinates.
- Show the resolved address below the input after geocoding: "Resolved: 35.3500, -119.0500 (Bakersfield, CA 93312)"
- If geocoding fails: show error "Could not find that location. Try a different address or enter coordinates directly."

### API Change
Add a geocoding utility to the backend:
```
GET /geocode?q={address_or_place}
Returns: {latitude, longitude, formatted_address, source: "census" | "nominatim"}
```

### Acceptance Criteria
1. "Bakersfield, CA" resolves to coordinates near Bakersfield
2. "1600 Pennsylvania Ave, Washington DC" resolves to the White House
3. "35.35, -119.05" is detected as raw coordinates and used directly (no geocoding call)
4. "asdfghjkl" returns a clear error message
5. All three product pages (/energy, /hazard, /locations) use the new unified input
6. The resolved coordinates are shown to the user before scoring

---

## FEATURE 2: BATCH RESULTS ON MAP WITH RANKING

### Problem
The current UI scores one location at a time. Solar developers evaluate 50-200 candidate parcels simultaneously. They need to see ALL results on the map, color-coded by score, with a ranked list in the sidebar.

### Solution
Extend the CSV upload flow to:
1. Accept a CSV with columns: latitude,longitude (or address — geocoded per Feature 1)
2. Score ALL locations through POST /solar/score-v2 (sequentially, with progress indicator)
3. Display all scored locations on the map simultaneously, color-coded by suitability
4. Show a ranked list in the sidebar, sorted by score descending
5. Click any row in the list → map pans to that location, detail panel opens
6. Click any marker on the map → same detail panel opens, list scrolls to that row

### Implementation

**CSV parsing (frontend):**
```
Accept CSV with headers: latitude,longitude
   OR: lat,lng
   OR: address (geocode each row)
   OR: lat,lng,name (optional name column for display)
Validate: reject if >200 rows (batch limit), reject if missing required columns
```

**Batch scoring (API):**
New endpoint:
```
POST /solar/score-v2/batch
Body: { locations: [{latitude, longitude, name?}, ...] }
Returns: { results: [{latitude, longitude, name, score, rating, confidence_tier, ...}, ...] }
```

The batch endpoint calls score_solar_siting for each location sequentially (parallelization is a future optimization). Returns results as they complete (streaming) or all at once when done.

For the initial implementation: score all locations server-side, return the full array when complete. Add a progress endpoint or use SSE (Server-Sent Events) for progress updates if scoring takes >30 seconds.

**Batch timing estimate:** At ~10s per location (post-optimization), 50 locations = ~8 minutes, 200 locations = ~33 minutes. For the design partner demo, keep batches to 20-50 parcels. Document the timing honestly.

**Map display:**
All scored locations rendered as GeoJSON points on the map, color-coded by the suitability scale (green/amber/red/gray). Markers sized consistently. Selected marker gets the glow ring highlight.

**Sidebar ranked list:**
```
┌─────────────────────────────────────┐
│ BATCH RESULTS (47 of 50 scored)     │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░ 94%          │
├─────────────────────────────────────┤
│ 1. Site A    78/100  High   HIGH    │
│ 2. Site B    72/100  High   MOD     │
│ 3. Site C    65/100  Mod    MOD     │
│ ...                                 │
│ 47. Site X   23/100  Low   MOD      │
│ ── Excluded (3) ──                  │
│ 48. Site Y   Excluded  excl_protected│
│ 49. Site Z   Excluded  excl_steep   │
│ 50. (scoring...)                    │
└─────────────────────────────────────┘
```

Click any row → map pans to that location, detail panel shows full assessment.

**Sort options:** by score (default), by confidence, by name, by distance to transmission.

### Acceptance Criteria
1. Upload a CSV with 10 lat/lng rows → all 10 scored and displayed on map
2. Markers are color-coded (green for High, amber for Moderate, red for Low, gray for Excluded)
3. Ranked list in sidebar shows all results sorted by score
4. Click a list row → map pans to location, detail panel opens
5. Click a map marker → detail panel opens, list highlights the row
6. Progress indicator shows during batch scoring
7. CSV with address column geocodes each row before scoring
8. Excluded sites appear at the bottom of the ranked list with exclusion reason

---

## FEATURE 3: PDF EXPORT OF SCORED ASSESSMENT

### Problem
A solar developer needs to hand a document to their investment committee, their lender, or their landowner. The current output is a web page — not shareable or archivable. The developer needs a PDF.

### Solution
Generate a professional PDF from any scored assessment. The PDF should include everything in the web results plus metadata and methodology documentation.

### PDF Contents

**Single-site PDF (1 page summary + 1-2 pages detail):**

Page 1 — Summary:
```
HEAVI ENERGY — Solar Site Suitability Assessment
Generated: [date]

LOCATION: [address or coordinates]
NERC REGION: [region]

SITE SCORE: 78 / 100 — High
CONFIDENCE: 95 / 100 — HIGH

"This assessment is based on authoritative data for all major criteria."

DATA GAPS:
• solar_ej: No data available for Environmental Justice

EXCLUSION SCREENING:
✓ Protected areas    pass
✓ Wetlands           pass
✓ Critical habitat   pass
✓ Flood zones        pass
✓ Steep slope        pass
✓ Urban land         pass
```

Page 2 — Per-Criterion Detail:
```
SCORED CRITERIA                Weight    Score    Source              Confidence
solar_transmission             0.42      86       hifld_transmission  HIGH
solar_ghi                      0.12      67       nrel_pvwatts_v8     HIGH
solar_slope                    0.14      99       usgs_3dep           HIGH
solar_road                     0.13      50       osm_roads_overpass  HIGH
solar_aspect                   0.08      100      usgs_3dep           HIGH
solar_land_cover               0.04      10       nlcd_land_cover     HIGH
solar_soil                     0.04      100      usda_sda_ssurgo     HIGH
solar_ej                       0.03      —        —                   NONE

WEIGHT PROFILE: WECC (calibrated against 245 EIA Form 860 installations)
```

Page 3 — Methodology:
```
METHODOLOGY DOCUMENTATION

Framework: GIS-based Multi-Criteria Decision Analysis (GIS-MCDA)
  Doorga et al. (2019), Renewable and Sustainable Energy Reviews
  Hernandez et al. (2015), PNAS
  Al-Shammari et al. (2026), Renewable Energy

Weight Calibration: Constrained optimization (scipy SLSQP) within
  literature-supported bounds against EIA Form 860 ground truth.
  Doorga (2019) provides AHP defaults; Al-Shammari (2026) provides
  CONUS-scale validation.

Data Sources: 31 federal and open data sources. Per-criterion
  source selection via data selection engine with quality-ordered
  data trees.

Validation: 52% of EIA installations score High nationally
  (77% among non-excluded parcels). Regional weights calibrated
  per NERC region.

Known Limitations:
  • NWI wetlands data unavailable nationally (SSURGO proxy used)
  • EJScreen data is a static 2024 snapshot (EPA tool discontinued)
  • Scoring does not assess interconnection capacity or queue position
  
DISCLAIMER: This assessment is based on publicly available federal
data and peer-reviewed methodology. It is intended for screening
purposes and does not replace site-specific field investigation,
interconnection studies, or environmental surveys.
```

**Batch PDF (portfolio summary):**
Summary page with the ranked list of all sites, then 1-page detail per site.

### Implementation

Use a Python PDF library on the backend. The existing portfolio PDF (wildfire 15-page format) uses reportlab or similar — extend the same approach.

New endpoint:
```
GET /solar/score-v2/pdf?lat={lat}&lng={lng}
Returns: application/pdf

GET /solar/score-v2/batch/pdf
Body: { locations: [...] }  (same as batch scoring)
Returns: application/pdf (multi-page portfolio)
```

Frontend: add "Export PDF" button next to scored results (single site) and batch results.

### Acceptance Criteria
1. Single-site PDF generates for Kern County (35.35, -119.05)
2. PDF contains: score, confidence, per-criterion breakdown, exclusion results, weight profile, methodology, disclaimer
3. PDF is visually clean and professional (not raw text dump)
4. Batch PDF generates for 5 locations with summary page + per-site detail pages
5. "Export PDF" button visible in web UI after scoring
6. PDF includes the generation date and Heavi branding

---

## FEATURE 4: INTERCONNECTION PROXIMITY INTELLIGENCE

### Problem
Interconnection cost and queue position are the #1 factors in solar project economics. The current solar module scores transmission proximity (distance to nearest line and substation) but provides no information about:
- What capacity is available at the nearest substation
- How congested the interconnection queue is in the area
- What upgrade costs might be expected

Solar developers will ask about this in the first demo. Heavi doesn't need to provide full power-flow studies (PVcase Prospect's domain), but it needs basic interconnection intelligence from publicly available data.

### Data Sources (All Publicly Available)

**ISO/RTO Interconnection Queues:**
Every major US grid operator publishes their interconnection queue as downloadable data:

| ISO/RTO | URL | Format | Coverage |
|---|---|---|---|
| CAISO | https://rimspub.caiso.com/rimsui/logon.do (queue report) | Excel | California |
| ERCOT | https://www.ercot.com/gridinfo/generation (GIS report) | Excel | Texas |
| PJM | https://www.pjm.com/planning/services-requests/interconnection-queues | CSV | Mid-Atlantic, Midwest |
| MISO | https://www.misoenergy.org/planning/generator-interconnection/GI_Queue/ | Excel | Upper Midwest |
| SPP | https://opsportal.spp.org/Studies/GIActive | Web | Central US |
| NYISO | https://www.nyiso.com/interconnections | Excel | New York |
| ISO-NE | https://www.iso-ne.com/system-planning/interconnection-service/ | Web | New England |

These queues contain: project name, fuel type, capacity (MW), substation/POI, status, queue date, estimated cost, study phase.

**EIA Form 860 (Already Loaded):**
solar_eia_installations already has nameplate capacity for every operating generator in the US. This tells you what's already connected at each substation.

**Interconnection.fyi:**
A third-party aggregator that tracks queue data across ISOs with daily updates. May have an API or downloadable dataset.

### What to Build

**NOT a power-flow study.** That requires proprietary grid models and is PVcase's domain.

**Instead: interconnection context for the nearest substation.**

For each scored solar site, add an interconnection section to the output:

```
INTERCONNECTION CONTEXT
Nearest substation: [name] ([distance] mi, [voltage] kV)
Existing capacity at substation: [X] MW connected (from EIA 860)
Queue activity near this substation: [N] projects totaling [X] MW in queue (from ISO data)
Queue status summary: [N] in study, [N] approved, [N] withdrawn
Estimated queue wait: [X-Y] months (based on regional average)

NOTE: This is informational context from public data, not an interconnection study.
Actual capacity availability requires filing an interconnection application with [ISO name].
```

### Implementation

**Step 1: Load ISO queue data into PostGIS.**

Download the queue CSVs/Excel files for CAISO, ERCOT, PJM, MISO, SPP. Parse into a normalized table:

```sql
CREATE TABLE interconnection_queue (
    queue_id TEXT PRIMARY KEY,
    iso TEXT NOT NULL,             -- 'CAISO', 'ERCOT', 'PJM', 'MISO', 'SPP'
    project_name TEXT,
    fuel_type TEXT,                -- 'Solar', 'Wind', 'Battery', etc.
    capacity_mw FLOAT,
    substation_poi TEXT,           -- point of interconnection name
    county TEXT,
    state TEXT,
    status TEXT,                   -- 'Active', 'Withdrawn', 'Completed', 'Suspended'
    queue_date DATE,
    study_phase TEXT,              -- 'Feasibility', 'System Impact', 'Facilities'
    estimated_cost_millions FLOAT, -- where available
    latitude FLOAT,               -- geocoded from substation/county
    longitude FLOAT,
    geometry GEOMETRY(Point, 4326),
    loaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_queue_geom ON interconnection_queue USING GIST (geometry);
CREATE INDEX idx_queue_iso ON interconnection_queue (iso);
CREATE INDEX idx_queue_status ON interconnection_queue (status);
```

**Step 2: For each scored site, compute interconnection context.**

```python
async def get_interconnection_context(pool, lat, lng, radius_km=50):
    """
    Returns interconnection context for the nearest substation area.
    """
    # 1. Find nearest substation (already done in solar scoring)
    nearest_sub = ...  # from source_cache
    
    # 2. Query existing capacity at/near this substation from EIA 860
    existing = await pool.fetch("""
        SELECT SUM(nameplate_capacity_mw) as total_mw, COUNT(*) as plant_count
        FROM solar_eia_installations
        WHERE ST_DWithin(geometry::geography, ST_Point($1, $2)::geography, $3)
    """, lng, lat, radius_km * 1000)
    
    # 3. Query interconnection queue near this substation
    queue = await pool.fetch("""
        SELECT fuel_type, status, capacity_mw, queue_date, project_name
        FROM interconnection_queue
        WHERE ST_DWithin(geometry::geography, ST_Point($1, $2)::geography, $3)
        ORDER BY queue_date DESC
    """, lng, lat, radius_km * 1000)
    
    # 4. Summarize
    active_solar = [q for q in queue if q['fuel_type'] == 'Solar' and q['status'] == 'Active']
    total_queued_mw = sum(q['capacity_mw'] for q in active_solar if q['capacity_mw'])
    
    return {
        "nearest_substation": nearest_sub,
        "existing_capacity_mw": existing[0]['total_mw'],
        "existing_plant_count": existing[0]['plant_count'],
        "queue_projects_nearby": len(active_solar),
        "queue_capacity_mw": total_queued_mw,
        "queue_summary": {
            "active": len([q for q in queue if q['status'] == 'Active']),
            "withdrawn": len([q for q in queue if q['status'] == 'Withdrawn']),
            "completed": len([q for q in queue if q['status'] == 'Completed']),
        },
        "iso": determine_iso(lat, lng),  # from NERC regions
        "note": "Informational context from public data. Actual capacity requires an interconnection application."
    }
```

**Step 3: Add to the solar score-v2 output and web UI.**

The interconnection context appears as a new section in the scored result, below the suitability score and above the per-criterion breakdown.

**Step 4: Add to the map.**

Queue projects rendered as small markers on the map (different color/shape from scored parcels — e.g., small squares or diamonds). This shows the developer where other projects are being proposed, which indicates both competition for grid capacity and validation of the area's attractiveness.

### Acceptance Criteria
1. Queue data loaded for at least 3 ISOs (CAISO, ERCOT, PJM — highest solar volume)
2. POST /solar/score-v2 response includes interconnection_context section
3. Kern County (35.35, -119.05) shows existing EIA capacity and CAISO queue activity near the nearest substation
4. Houston area (29.76, -95.37) shows ERCOT queue activity
5. Web UI displays interconnection context in the detail panel
6. Queue projects visible as map layer (togglable)
7. The output explicitly states "this is informational, not an interconnection study"
8. PDF export includes the interconnection context section

---

## BUILD SEQUENCE

| Order | Feature | Estimated Effort | Why This Order |
|---|---|---|---|
| 1 | Address geocoding | 2-3 hours | Quick win, makes every demo better immediately |
| 2 | Batch map results + ranking | 4-6 hours | Visual impact for multi-parcel demos |
| 3 | PDF export | 4-6 hours | Tangible output developers can take to their IC |
| 4 | Interconnection intelligence | 8-12 hours | Biggest value-add but most complex (data loading + integration) |

Total estimated: 18-27 hours of Claude Code time over ~2 weeks.
