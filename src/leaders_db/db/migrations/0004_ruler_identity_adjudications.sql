CREATE TABLE ruler_identity_adjudications (
    id INTEGER PRIMARY KEY,
    country_year_id INTEGER NOT NULL REFERENCES country_years(id),
    country_id INTEGER NOT NULL REFERENCES countries(id),
    year SMALLINT NOT NULL,
    selected_ruler_year_id INTEGER REFERENCES ruler_years(id),
    selected_leader_name TEXT,
    candidate_ruler_year_ids_json TEXT NOT NULL DEFAULT '[]',
    candidates_json TEXT NOT NULL DEFAULT '[]',
    classification TEXT NOT NULL,
    selection_rule TEXT NOT NULL,
    review_status TEXT NOT NULL,
    confidence_score SMALLINT,
    confidence_penalties_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    rationale TEXT NOT NULL,
    review_reason TEXT,
    research_prompt TEXT,
    recommended_next_action TEXT NOT NULL,
    source_slugs_json TEXT NOT NULL DEFAULT '[]',
    source_observation_ids_json TEXT NOT NULL DEFAULT '[]',
    run_id TEXT,
    method_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_year_id)
);

CREATE INDEX ix_ruler_identity_adjudications_country_year
    ON ruler_identity_adjudications(country_id, year);

CREATE INDEX ix_ruler_identity_adjudications_review_status
    ON ruler_identity_adjudications(review_status, classification);
