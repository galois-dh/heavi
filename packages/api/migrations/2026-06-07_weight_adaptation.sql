-- Geographic weight adaptation (Heavi Weight Adaptation Spec).
--
-- Two new tables:
--   nerc_regions             — NERC reliability-region polygons; a location's
--                              region is found with ST_Contains. Geometry is
--                              loaded by load_nerc_regions.py (US state polygons
--                              dissolved by canonical state→NERC membership).
--   regional_weight_profiles — per-region calibrated criterion weights produced
--                              by the constrained optimization, plus the
--                              metadata (n samples, validation metrics,
--                              weight_changes with reasons, academic_basis).

CREATE TABLE IF NOT EXISTS nerc_regions (
    region    TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    geometry  geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nerc_regions_geom
    ON nerc_regions USING GIST (geometry);

CREATE TABLE IF NOT EXISTS regional_weight_profiles (
    region         TEXT PRIMARY KEY,
    workflow_type  TEXT NOT NULL DEFAULT 'solar_siting',
    weights        JSONB NOT NULL,
    metadata       JSONB NOT NULL,   -- n_eia, n_random, validation, weight_changes, academic_basis
    calibrated_at  TIMESTAMPTZ NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE nerc_regions IS
    'NERC reliability regions as dissolved US-state polygons. '
    'SELECT region FROM nerc_regions WHERE ST_Contains(geometry, ST_Point(lng,lat)).';
COMMENT ON TABLE regional_weight_profiles IS
    'Per-NERC-region calibrated solar-siting criterion weights from constrained '
    'AHP optimization against EIA Form 860 ground truth (see Weight Adaptation Spec).';
