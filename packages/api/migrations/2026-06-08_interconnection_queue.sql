-- Interconnection queue (Heavi Month-1 Sprint, Feature 4).
--
-- ISO/RTO interconnection queues give solar developers context on grid
-- congestion and competition near a candidate site. This table holds a
-- normalized queue across ISOs; the per-site interconnection context is derived
-- from it plus EIA Form 860 (existing capacity) at scoring time.
--
-- DATA PROVENANCE: the live ISO queue portals (CAISO RIMS, ERCOT GIS report,
-- PJM, MISO, SPP) require authenticated/interactive downloads that aren't
-- fetchable from this environment. The loader (load_interconnection_queue.py)
-- therefore populates a REPRESENTATIVE / illustrative dataset anchored to real
-- substation coordinates (substations_osm_us) with realistic project profiles.
-- It is clearly flagged (data_source='representative') and the API output states
-- the context is informational, not an interconnection study. Production should
-- replace the loader body with live ISO queue files.

CREATE TABLE IF NOT EXISTS interconnection_queue (
    queue_id                TEXT PRIMARY KEY,
    iso                     TEXT NOT NULL,            -- CAISO, ERCOT, PJM, MISO, SPP
    project_name            TEXT,
    fuel_type               TEXT,                     -- Solar, Wind, Battery, ...
    capacity_mw             FLOAT,
    substation_poi          TEXT,                     -- point of interconnection
    county                  TEXT,
    state                   TEXT,
    status                  TEXT,                     -- Active, Withdrawn, Completed, Suspended
    queue_date              DATE,
    study_phase             TEXT,                     -- Feasibility, System Impact, Facilities
    estimated_cost_millions FLOAT,
    latitude                FLOAT,
    longitude               FLOAT,
    geometry                geometry(Point, 4326),
    data_source             TEXT DEFAULT 'representative',
    loaded_at               TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_queue_geom ON interconnection_queue USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_queue_iso ON interconnection_queue (iso);
CREATE INDEX IF NOT EXISTS idx_queue_status ON interconnection_queue (status);

COMMENT ON TABLE interconnection_queue IS
    'Normalized ISO/RTO interconnection queue. Representative dataset anchored to '
    'real substation coordinates (see load_interconnection_queue.py) — informational '
    'context, not an interconnection study. Replace with live ISO downloads in production.';
