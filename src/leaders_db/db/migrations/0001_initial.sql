-- Canonical DDL for the prototype schema.
--
-- This file is the source of truth for the schema. ``src/leaders_db/db/models.py``
-- mirrors it. Keep both in sync. Changes require a new migration under this folder.
--
-- Database engine: SQLite (prototype). PostgreSQL-compatible. ``MONEY`` and
-- other dialect-specific types are avoided in favor of ``INTEGER``, ``REAL``,
-- and ``TEXT``. See docs/database-schema.md.

-- ---------------------------------------------------------------------------
-- Reference / dimension tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS countries (
    id                          INTEGER PRIMARY KEY,
    iso3                        TEXT NOT NULL UNIQUE,
    country_name                TEXT NOT NULL,
    country_name_normalized     TEXT NOT NULL,
    region                      TEXT,
    notes                       TEXT
);

CREATE TABLE IF NOT EXISTS leaders (
    id              INTEGER PRIMARY KEY,
    full_name       TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    birth_date      TEXT,
    death_date      TEXT,
    gender          TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id                   INTEGER PRIMARY KEY,
    source_name          TEXT NOT NULL,
    source_type          TEXT NOT NULL,
    source_url           TEXT,
    version              TEXT,
    license_note         TEXT,
    download_date        TEXT,
    coverage_start_year  INTEGER,
    coverage_end_year    INTEGER,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS score_categories (
    id            INTEGER PRIMARY KEY,
    category_key  TEXT NOT NULL UNIQUE,
    category_name TEXT NOT NULL,
    description   TEXT,
    rubric_low    TEXT,
    rubric_mid    TEXT,
    rubric_high   TEXT
);

-- ---------------------------------------------------------------------------
-- Country-year context
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS country_years (
    id                  INTEGER PRIMARY KEY,
    country_id          INTEGER NOT NULL REFERENCES countries(id),
    year                INTEGER NOT NULL,
    population          INTEGER,
    gdp_current_usd     INTEGER,
    gdp_per_capita      REAL,
    included_in_project INTEGER NOT NULL DEFAULT 0,
    inclusion_reason    TEXT,
    source_confidence   INTEGER,
    UNIQUE(country_id, year)
);

-- ---------------------------------------------------------------------------
-- Leader aliases
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS leader_aliases (
    id        INTEGER PRIMARY KEY,
    leader_id INTEGER NOT NULL REFERENCES leaders(id),
    alias     TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id)
);

-- ---------------------------------------------------------------------------
-- Ruler spells (tenure records)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ruler_spells (
    id                  INTEGER PRIMARY KEY,
    leader_id           INTEGER NOT NULL REFERENCES leaders(id),
    country_id          INTEGER NOT NULL REFERENCES countries(id),
    office_title        TEXT,
    start_date          TEXT NOT NULL,
    end_date            TEXT,
    source_dataset      TEXT NOT NULL,
    is_actual_ruler     INTEGER NOT NULL DEFAULT 1,
    is_formal_leader    INTEGER NOT NULL DEFAULT 0,
    rule_type           TEXT,
    shared_rule_flag    INTEGER NOT NULL DEFAULT 0,
    disputed_rule_flag  INTEGER NOT NULL DEFAULT 0,
    confidence_score    INTEGER,
    notes               TEXT
);

-- ---------------------------------------------------------------------------
-- Ruler years (Stage 4 output)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ruler_years (
    id                          INTEGER PRIMARY KEY,
    leader_id                   INTEGER NOT NULL REFERENCES leaders(id),
    country_id                  INTEGER NOT NULL REFERENCES countries(id),
    year                        INTEGER NOT NULL,
    ruler_spell_id              INTEGER REFERENCES ruler_spells(id),
    actual_ruler_status         TEXT,
    client_matrix_leader_name   TEXT,
    system_selected_leader_name TEXT,
    match_status                TEXT,
    confidence_score            INTEGER,
    review_status               TEXT,
    review_note                 TEXT,
    UNIQUE(leader_id, country_id, year)
);

-- ---------------------------------------------------------------------------
-- Ruler scores (Stage 9–11 output)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ruler_scores (
    id                     INTEGER PRIMARY KEY,
    ruler_year_id          INTEGER NOT NULL REFERENCES ruler_years(id),
    category_id            INTEGER NOT NULL REFERENCES score_categories(id),
    client_score           INTEGER,
    system_proposed_score  INTEGER,
    final_score            INTEGER,
    score_delta_vs_client  INTEGER,
    confidence_score       INTEGER,
    source_agreement       TEXT,
    human_review_required  INTEGER NOT NULL DEFAULT 0,
    rationale_short        TEXT,
    review_status          TEXT,
    UNIQUE(ruler_year_id, category_id)
);

-- ---------------------------------------------------------------------------
-- Source observations (audit backbone)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_observations (
    id                  INTEGER PRIMARY KEY,
    source_id           INTEGER NOT NULL REFERENCES sources(id),
    country_id          INTEGER REFERENCES countries(id),
    leader_id           INTEGER REFERENCES leaders(id),
    year                INTEGER,
    variable_name       TEXT NOT NULL,
    raw_value           TEXT,
    normalized_value    REAL,
    unit                TEXT,
    source_row_reference TEXT,
    confidence          INTEGER,
    notes               TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_obs_source_country_year
    ON source_observations(source_id, country_id, year);
CREATE INDEX IF NOT EXISTS ix_obs_variable_year
    ON source_observations(variable_name, year);

-- ---------------------------------------------------------------------------
-- Validation results (Stage 12 output)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS validation_results (
    id                       INTEGER PRIMARY KEY,
    item_type                TEXT NOT NULL,
    item_id                  INTEGER NOT NULL,
    validation_status        TEXT,
    source_count             INTEGER,
    source_agreement_score   INTEGER,
    source_authority_score   INTEGER,
    temporal_fit_score       INTEGER,
    specificity_score        INTEGER,
    final_confidence_score   INTEGER,
    validation_note          TEXT
);
