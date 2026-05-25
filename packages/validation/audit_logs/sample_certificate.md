# Audit Certificate — `site_suitability` v0.1.0

**Execution ID:** `a8659d0c-b9ca-4cc0-a806-34d37cc6ae2e`  
**Timestamp:** 2026-05-15T17:09:06.724361+00:00  
**Methodology doc version:** `31ca405b9ca6259344eee7d7ec23aebd4544d95fd95334d3fc49c4425e9ff6b0`  
**Duration:** 1070.8 ms  

## Inputs
```json
{
  "latitude": 37.8444,
  "longitude": -122.2509
}
```

## Scored output
```json
{
  "score": 71,
  "factors": {
    "flood_risk": 100,
    "demographics": 75,
    "transit_access": 60,
    "environmental": 100,
    "competition": 20
  },
  "counts": {
    "transit_stops": 3,
    "epa_facilities": 0,
    "pois": 1066,
    "in_flood_zone": false,
    "in_fire_hazard": false,
    "in_census_tract": true
  }
}
```

## Data layers consulted

- `catalog_calfire_fhsz`
- `catalog_census_demographics`
- `catalog_epa_facilities`
- `catalog_fema_flood`
- `catalog_nces_schools`
- `catalog_overture_pois`
- `catalog_transit_stops`

## Queries executed (9)

1. (149.1 ms, 1 rows) layers=['catalog_fema_flood']
   ```sql
   SELECT EXISTS(                   SELECT 1 FROM catalog_fema_flood                   WHERE sfha_tf = 'T' AND ST_Contains(geometry, ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326)))
   ```
2. (102.4 ms, 1 rows) layers=['catalog_transit_stops']
   ```sql
   SELECT COUNT(*) FROM catalog_transit_stops WHERE ST_Intersects(geometry, ST_Transform(ST_Buffer(ST_Transform(ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326), 3857), 1609), 4326))
   ```
3. (101.2 ms, 1 rows) layers=['catalog_census_demographics']
   ```sql
   SELECT to_jsonb(t) - 'geometry' AS props                 FROM catalog_census_demographics t                 WHERE ST_Contains(t.geometry, ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326)) LIMIT 1
   ```
4. (102.2 ms, 1 rows) layers=['catalog_epa_facilities']
   ```sql
   SELECT COUNT(*) FROM catalog_epa_facilities WHERE ST_Intersects(geometry, ST_Transform(ST_Buffer(ST_Transform(ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326), 3857), 1609), 4326))
   ```
5. (104.6 ms, 1 rows) layers=['catalog_calfire_fhsz']
   ```sql
   SELECT EXISTS(                   SELECT 1 FROM catalog_calfire_fhsz                   WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326)))
   ```
6. (78.0 ms, 1 rows) layers=['catalog_overture_pois']
   ```sql
   SELECT COUNT(*) FROM catalog_overture_pois WHERE ST_Intersects(geometry, ST_Transform(ST_Buffer(ST_Transform(ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326), 3857), 1609), 4326))
   ```
7. (80.3 ms, 3 rows) layers=['catalog_nces_schools']
   ```sql
   SELECT to_jsonb(t) - 'geometry' AS props,                            ST_Distance(ST_Transform(t.geometry, 3857),                                        ST_Transform(ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326), 3857)) AS dist_m,       …
   ```
8. (80.4 ms, 3 rows) layers=['catalog_transit_stops']
   ```sql
   SELECT to_jsonb(t) - 'geometry' AS props,                            ST_Distance(ST_Transform(t.geometry, 3857),                                        ST_Transform(ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326), 3857)) AS dist_m,       …
   ```
9. (170.2 ms, 0 rows) layers=['catalog_epa_facilities']
   ```sql
   SELECT to_jsonb(t) - 'geometry' AS props,                            ST_Distance(ST_Transform(t.geometry, 3857),                                        ST_Transform(ST_SetSRID(ST_MakePoint(-122.2509, 37.8444), 4326), 3857)) AS dist_m,       …
   ```

## Attestation

This certificate records the exact inputs, SQL executed, data layers consulted, and scored output for a single module execution. A compliance reviewer can re-run the recorded SQL against the same database snapshot to reproduce the raw inputs to the scoring function, then apply the methodology document (`31ca405b9ca6259344eee7d7ec23aebd4544d95fd95334d3fc49c4425e9ff6b0`) to reproduce the output deterministically.