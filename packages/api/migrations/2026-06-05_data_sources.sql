-- Data Repository (Heavi Platform Refactor Phase 1).
--
-- A structured catalog of every spatial data source the platform can access.
-- Tells the system what data exists, where it works, how to access it, and
-- how reliable it is. Seeded by packages/api/app/data_repository_seed.py.
--
-- See: docs/Heavi_Platform_Refactor_Spec.md (Phase 1)

CREATE TABLE IF NOT EXISTS data_sources (
    source_id      TEXT        PRIMARY KEY,
    name           TEXT        NOT NULL,
    provider       TEXT        NOT NULL,
    description    TEXT,

    -- Access
    access_method  TEXT        NOT NULL,        -- 'postgis_table' | 'rest_api' | 'wms' | 'wfs' | 'file'
    access_config  JSONB       NOT NULL,        -- endpoint/table/query template/auth config

    -- Coverage
    coverage_type  TEXT        NOT NULL,        -- 'national' | 'regional' | 'state' | 'county'
    coverage_states TEXT[],                     -- NULL if national; e.g. ['CA','TX']
    coverage_notes TEXT,

    -- Quality
    resolution     TEXT,                        -- '10m' | '30m' | 'block_group' | 'point' | …
    vintage        TEXT,                        -- '2022' | '2020 TMY' | '1999-2020' | …
    update_frequency TEXT,                      -- 'annual' | 'static' | 'on-demand' | …
    reliability    TEXT        NOT NULL,        -- 'verified' | 'degraded' | 'unavailable'
    last_verified  TIMESTAMPTZ,
    known_gaps     TEXT,

    -- Provenance
    license        TEXT,                        -- 'public_domain' | 'CC-BY-4.0' | 'ODbL' | …
    source_url     TEXT,
    citation       TEXT,

    -- Classification
    data_category  TEXT        NOT NULL,        -- 'solar_resource' | 'terrain' | 'environmental' | …
    applicable_workflows TEXT[],                -- ['solar_siting','hazard_assessment','trade_area']

    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_sources_workflow
    ON data_sources USING GIN (applicable_workflows);

CREATE INDEX IF NOT EXISTS idx_data_sources_category
    ON data_sources (data_category);

COMMENT ON TABLE data_sources IS
    'Heavi Platform Refactor Phase 1 — verified spatial-data catalog.';
