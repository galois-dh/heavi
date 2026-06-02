-- Methodology Repository (Heavi Platform Build Spec Phase 2).
--
-- Structured catalog of academic-literature-backed criteria for each workflow.
-- The data_tree column encodes the logic tree from the provenance document:
-- per-criterion list of (source_id, relationship, quality, confidence_value,
-- provides, provenance) — alternative trees use top-to-bottom priority;
-- component trees additionally carry missing_impact + missing_confidence so
-- the Phase 3 selection engine can degrade gracefully.

CREATE TABLE IF NOT EXISTS methodology_criteria (
    criterion_id        TEXT        PRIMARY KEY,
    workflow_type       TEXT        NOT NULL,        -- 'solar_siting' | 'hazard_assessment' | 'trade_area'
    criterion_name      TEXT        NOT NULL,
    criterion_type      TEXT        NOT NULL,        -- 'scored' | 'exclusion'

    -- Weights (scored only)
    weight_default      FLOAT,
    weight_min          FLOAT,
    weight_max          FLOAT,
    weight_rationale    TEXT,

    -- Exclusion (exclusion only)
    exclusion_threshold TEXT,
    exclusion_rationale TEXT,

    -- Data tree (the core)
    data_tree           JSONB       NOT NULL,

    -- Academic grounding
    academic_sources    JSONB       NOT NULL,

    -- Optional confidence-rule overrides for this criterion
    confidence_rules    JSONB,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_methodology_workflow
    ON methodology_criteria (workflow_type);

COMMENT ON TABLE methodology_criteria IS
    'Heavi Platform Build Spec Phase 2 — academically-grounded criteria + data trees.';
