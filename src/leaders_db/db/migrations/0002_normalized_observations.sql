-- Research-engine normalized evidence store.
--
-- This table stores the source-layer NormalizedObservation contract without
-- rerunning adapters or reading raw files during research queries.

CREATE TABLE IF NOT EXISTS normalized_observations (
    id                       INTEGER PRIMARY KEY,
    source_slug              TEXT NOT NULL,
    observation_id           TEXT NOT NULL,
    observation_family       TEXT NOT NULL,
    indicator_code           TEXT NOT NULL,
    value_json               TEXT NOT NULL,
    value_type               TEXT NOT NULL,
    year                     INTEGER,
    country_code             TEXT,
    country_name             TEXT,
    leader_id                TEXT,
    leader_name              TEXT,
    unit                     TEXT,
    scale                    TEXT,
    source_version           TEXT,
    raw_locator_json         TEXT NOT NULL,
    transform_locator_json   TEXT NOT NULL,
    quality_flags_json       TEXT NOT NULL DEFAULT '[]',
    warnings_json            TEXT NOT NULL DEFAULT '[]',
    extension_json           TEXT NOT NULL DEFAULT '{}',
    scope_json               TEXT NOT NULL DEFAULT '{}',
    created_at               TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_slug, observation_id)
);

CREATE INDEX IF NOT EXISTS ix_norm_obs_source_family_indicator
    ON normalized_observations(source_slug, observation_family, indicator_code);

CREATE INDEX IF NOT EXISTS ix_norm_obs_country_year
    ON normalized_observations(country_code, year);

CREATE INDEX IF NOT EXISTS ix_norm_obs_leader_year
    ON normalized_observations(leader_id, leader_name, year);
