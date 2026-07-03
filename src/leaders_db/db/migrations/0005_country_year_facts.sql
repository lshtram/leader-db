CREATE TABLE country_year_facts (
    id INTEGER PRIMARY KEY,
    country_year_id INTEGER NOT NULL REFERENCES country_years(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    year SMALLINT NOT NULL,
    field_key TEXT NOT NULL,
    field_label TEXT NOT NULL,
    value_type TEXT NOT NULL,
    selected_value_text TEXT,
    selected_value_number REAL,
    selected_value_json TEXT,
    selected_entity_table TEXT,
    selected_entity_id INTEGER,
    candidate_values_json TEXT NOT NULL DEFAULT '[]',
    selection_rule TEXT NOT NULL,
    adjudication_status TEXT NOT NULL,
    confidence_score SMALLINT,
    agreement_score REAL,
    authority_score REAL,
    specificity_score REAL,
    temporal_fit_score REAL,
    quality_signals_json TEXT NOT NULL DEFAULT '{}',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    rationale TEXT NOT NULL,
    review_reason TEXT,
    research_prompt TEXT,
    recommended_next_action TEXT NOT NULL,
    source_slugs_json TEXT NOT NULL DEFAULT '[]',
    source_observation_ids_json TEXT NOT NULL DEFAULT '[]',
    producer TEXT NOT NULL,
    method_version TEXT NOT NULL,
    run_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_year_id, field_key)
);

CREATE INDEX ix_country_year_facts_country_year
    ON country_year_facts(country_id, year);

CREATE INDEX ix_country_year_facts_field_status
    ON country_year_facts(field_key, adjudication_status);

CREATE INDEX ix_country_year_facts_review_queue
    ON country_year_facts(adjudication_status, field_key, year);
