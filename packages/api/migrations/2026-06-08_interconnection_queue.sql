-- Interconnection queue (Heavi Month-1 Sprint, Feature 4).
--
-- ISO/RTO interconnection queues give solar developers context on grid
-- congestion and competition near a candidate site. This table holds a
-- normalized queue across ISOs; the per-site interconnection context is derived
-- from it plus EIA Form 860 (existing capacity) at scoring time.
--
-- DATA PROVENANCE: loaded from LBNL "Queued Up" 2025 (Lawrence Berkeley National
-- Laboratory's aggregated national ISO/RTO + utility interconnection queue),
-- file data/interconnection/LBNL_Ix_Queue_Data_File_thru2025.xlsx, filtered to
-- active solar requests (load_interconnection_queue.py). The LBNL file has no
-- coordinates, so each project is placed at its county centroid (5-digit FIPS →
-- Census 2024 county gazetteer). Rows are flagged data_source='lbnl_queued_up_2025'.
-- The API output states the context is informational (county-centroid precision),
-- not an interconnection study.

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
    'Normalized ISO/RTO + utility interconnection queue from LBNL "Queued Up" 2025, '
    'filtered to active solar requests (see load_interconnection_queue.py). Projects '
    'are placed at county-centroid precision (FIPS → Census gazetteer) — informational '
    'context, not an interconnection study.';
