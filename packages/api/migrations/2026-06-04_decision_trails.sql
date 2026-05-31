-- Persistent decision-trail store. Every audited scoring call inserts one row.
-- See packages/api/app/decision_trail/ for the producer side.

CREATE TABLE IF NOT EXISTS decision_trails (
    execution_id    uuid        PRIMARY KEY,
    module          text        NOT NULL,
    module_version  text,
    started_at      timestamptz NOT NULL,
    duration_ms     float8,
    inputs          jsonb       NOT NULL,
    trail           jsonb       NOT NULL,
    scored_output   jsonb
);

-- Recent-first audit browsing per module is the dominant access pattern.
CREATE INDEX IF NOT EXISTS decision_trails_module_started_at
    ON decision_trails (module, started_at DESC);

-- Free-text search inside the trail jsonb (limits, sources, advisories) uses
-- the standard GIN index. Cheap enough at the volumes we'll see in Phase 1.
CREATE INDEX IF NOT EXISTS decision_trails_trail_gin
    ON decision_trails USING gin (trail);

COMMENT ON TABLE decision_trails IS
  'Audit trail for every scoring call: stitched SQL + HTTP + step-level events.';
