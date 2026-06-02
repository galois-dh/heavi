-- Phase 1 update (Heavi Platform Build Spec).
--
-- Adds coverage_geometry per the new spec table definition. applicable_workflows
-- and coverage_states are KEPT for backwards compatibility with the prior
-- /data-sources?workflow= endpoint; the canonical workflow→source mapping now
-- comes from methodology_criteria.data_tree[].source_id (Phase 2).

ALTER TABLE data_sources
    ADD COLUMN IF NOT EXISTS coverage_geometry geometry(Polygon, 4326);

CREATE INDEX IF NOT EXISTS idx_data_sources_coverage_geom
    ON data_sources USING GIST (coverage_geometry);

COMMENT ON COLUMN data_sources.coverage_geometry IS
    'Optional polygon delimiting where the source has data. NULL = everywhere '
    'for national APIs. Populated for regional / county sources.';
