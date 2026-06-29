-- Persisted research question/result layer for dashboard-ready answers.

CREATE TABLE IF NOT EXISTS research_questions (
    id              INTEGER PRIMARY KEY,
    question_id     TEXT NOT NULL UNIQUE,
    chapter_id      TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    answer_type     TEXT NOT NULL,
    category_key    TEXT,
    method_version  TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS research_question_answers (
    id                  INTEGER PRIMARY KEY,
    question_id          TEXT NOT NULL,
    year                INTEGER NOT NULL,
    iso3                TEXT NOT NULL,
    country_name        TEXT NOT NULL,
    ruler_id            TEXT,
    ruler_name          TEXT,
    answer_boolean      INTEGER,
    answer_numeric      REAL,
    answer_text         TEXT,
    answer_json         TEXT NOT NULL DEFAULT '{}',
    score_1_to_10       REAL,
    confidence_score    REAL,
    coverage_status     TEXT NOT NULL,
    evidence_year       INTEGER,
    method_version      TEXT NOT NULL,
    warning_codes_json  TEXT NOT NULL DEFAULT '[]',
    caveats_json        TEXT NOT NULL DEFAULT '[]',
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(question_id) REFERENCES research_questions(question_id),
    UNIQUE(question_id, year, iso3, method_version)
);

CREATE INDEX IF NOT EXISTS ix_research_answers_question_year
    ON research_question_answers(question_id, year);

CREATE INDEX IF NOT EXISTS ix_research_answers_iso3_year
    ON research_question_answers(iso3, year);

CREATE INDEX IF NOT EXISTS ix_research_answers_ruler_name_year
    ON research_question_answers(ruler_name, year);

CREATE INDEX IF NOT EXISTS ix_research_answers_coverage_year
    ON research_question_answers(coverage_status, year);

CREATE TABLE IF NOT EXISTS research_answer_evidence_links (
    id                      INTEGER PRIMARY KEY,
    answer_id               INTEGER NOT NULL,
    source_slug             TEXT NOT NULL,
    source_observation_id   TEXT NOT NULL,
    evidence_role           TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(answer_id) REFERENCES research_question_answers(id) ON DELETE CASCADE,
    UNIQUE(answer_id, source_slug, source_observation_id, evidence_role)
);

CREATE INDEX IF NOT EXISTS ix_research_evidence_source_observation
    ON research_answer_evidence_links(source_slug, source_observation_id);

CREATE INDEX IF NOT EXISTS ix_research_evidence_answer_id
    ON research_answer_evidence_links(answer_id);

CREATE TABLE IF NOT EXISTS chapter_scores (
    id                  INTEGER PRIMARY KEY,
    chapter_id          TEXT NOT NULL,
    year                INTEGER NOT NULL,
    iso3                TEXT NOT NULL,
    ruler_id            TEXT,
    ruler_name          TEXT,
    score_1_to_10       REAL,
    confidence_score    REAL,
    answer_count        INTEGER NOT NULL DEFAULT 0,
    answered_count      INTEGER NOT NULL DEFAULT 0,
    missing_count       INTEGER NOT NULL DEFAULT 0,
    direct_count        INTEGER NOT NULL DEFAULT 0,
    proxy_count         INTEGER NOT NULL DEFAULT 0,
    method_version      TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chapter_id, year, iso3, method_version)
);

CREATE INDEX IF NOT EXISTS ix_chapter_scores_chapter_year
    ON chapter_scores(chapter_id, year);

CREATE INDEX IF NOT EXISTS ix_chapter_scores_iso3_year
    ON chapter_scores(iso3, year);

CREATE INDEX IF NOT EXISTS ix_chapter_scores_ruler_name_year
    ON chapter_scores(ruler_name, year);
