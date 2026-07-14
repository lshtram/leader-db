ALTER TABLE chapter_scores RENAME TO chapter_scores_legacy;

CREATE TABLE chapter_scores (
    id                          INTEGER PRIMARY KEY,
    chapter_id                  TEXT NOT NULL,
    year                        INTEGER NOT NULL,
    iso3                        TEXT NOT NULL,
    ruler_id                    TEXT,
    ruler_year_id               INTEGER,
    ruler_name                  TEXT,
    score_1_to_10               REAL,
    confidence_score            REAL,
    answer_count                INTEGER NOT NULL DEFAULT 0,
    answered_count              INTEGER NOT NULL DEFAULT 0,
    missing_count               INTEGER NOT NULL DEFAULT 0,
    direct_count                INTEGER NOT NULL DEFAULT 0,
    proxy_count                 INTEGER NOT NULL DEFAULT 0,
    method_version              TEXT NOT NULL,
    run_key                     TEXT,
    job_key                     TEXT,
    calibration_batch_id        TEXT,
    plausible_score_lower       REAL,
    plausible_score_upper       REAL,
    manual_review_required      BOOLEAN NOT NULL DEFAULT FALSE,
    judgment_json               TEXT NOT NULL DEFAULT '{}',
    created_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chapter_id, year, ruler_year_id, method_version)
);

INSERT INTO chapter_scores (
    id, chapter_id, year, iso3, ruler_id, ruler_name, score_1_to_10,
    confidence_score, answer_count, answered_count, missing_count, direct_count,
    proxy_count, method_version
)
SELECT
    id, chapter_id, year, iso3, ruler_id, ruler_name, score_1_to_10,
    confidence_score, answer_count, answered_count, missing_count, direct_count,
    proxy_count, method_version
FROM chapter_scores_legacy;

DROP TABLE chapter_scores_legacy;

CREATE INDEX IF NOT EXISTS ix_chapter_scores_chapter_year
    ON chapter_scores(chapter_id, year);
CREATE INDEX IF NOT EXISTS ix_chapter_scores_iso3_year
    ON chapter_scores(iso3, year);
CREATE INDEX IF NOT EXISTS ix_chapter_scores_ruler_name_year
    ON chapter_scores(ruler_name, year);
CREATE INDEX IF NOT EXISTS ix_chapter_scores_job_key
    ON chapter_scores(job_key);
CREATE INDEX IF NOT EXISTS ix_chapter_scores_ruler_year
    ON chapter_scores(ruler_year_id, year);
