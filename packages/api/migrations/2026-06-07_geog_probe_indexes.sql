-- Selection-engine probe performance fix (Heavi Platform Build Spec, Phase 5).
--
-- The PostGIS source-availability probe in app/data_repository_check.py ran
--     WHERE ST_DWithin(t.geometry::geography, point::geography, radius)
-- The per-row geometry::geography cast is not index-sargable, so the planner
-- fell back to a sequential scan + per-row geography distance computation. On
-- the two largest probed tables this dominated the per-location wall time:
--
--     nwi_wetlands  (solar_wetlands_ca, 44,573 rows)        ~50.2 s  (82%)
--     hifld_transmission (solar_transmission_lines, 52,244)  ~6.1 s  (10%)
--
-- Fix: materialise a `geog geography` column alongside the raw geometry and
-- index it with GiST. The probe now references `t.geog` directly, so ST_DWithin
-- is index-sargable. The original `geometry` column and its index are left
-- untouched — other queries still use them.
--
-- After this migration the same probe at (35.35, -119.05) drops to
--     nwi_wetlands ~1.2 s, hifld_transmission ~1.2 s, total ~7.3 s.

ALTER TABLE solar_wetlands_ca
    ADD COLUMN IF NOT EXISTS geog geography(Geometry, 4326);
UPDATE solar_wetlands_ca SET geog = geometry::geography WHERE geog IS NULL;
CREATE INDEX IF NOT EXISTS idx_solar_wetlands_ca_geog
    ON solar_wetlands_ca USING GIST (geog);

ALTER TABLE solar_transmission_lines
    ADD COLUMN IF NOT EXISTS geog geography(Geometry, 4326);
UPDATE solar_transmission_lines SET geog = geometry::geography WHERE geog IS NULL;
CREATE INDEX IF NOT EXISTS idx_solar_transmission_geog
    ON solar_transmission_lines USING GIST (geog);

ANALYZE solar_wetlands_ca;
ANALYZE solar_transmission_lines;

COMMENT ON COLUMN solar_wetlands_ca.geog IS
    'Pre-computed geography of geometry, GiST-indexed, for the index-sargable '
    'ST_DWithin availability probe. Raw geometry column retained for other use.';
COMMENT ON COLUMN solar_transmission_lines.geog IS
    'Pre-computed geography of geometry, GiST-indexed, for the index-sargable '
    'ST_DWithin availability probe. Raw geometry column retained for other use.';
