CREATE TABLE IF NOT EXISTS research_jobs (
    id                  INTEGER PRIMARY KEY,
    job_key             TEXT NOT NULL UNIQUE,
    run_key             TEXT NOT NULL,
    job_type            TEXT NOT NULL,
    target_year         INTEGER NOT NULL,
    period_start_year   INTEGER,
    period_end_year     INTEGER,
    iso3                TEXT,
    country_name        TEXT,
    ruler_id            TEXT,
    ruler_name          TEXT,
    question_id         TEXT,
    provider_profile    TEXT NOT NULL,
    provider            TEXT NOT NULL,
    model               TEXT NOT NULL,
    status              TEXT NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 100,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 3,
    claimed_by          TEXT,
    claimed_at          DATETIME,
    lease_expires_at    DATETIME,
    heartbeat_at        DATETIME,
    checkpoint_json     TEXT NOT NULL DEFAULT '{}',
    input_json          TEXT NOT NULL DEFAULT '{}',
    result_path         TEXT,
    error_json          TEXT NOT NULL DEFAULT '{}',
    quarantine_reason   TEXT,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at        DATETIME,
    CHECK (job_type IN ('dossier_researcher', 'question_judge')),
    CHECK (status IN (
        'pending', 'claimed', 'running', 'completed', 'failed',
        'retryable', 'quarantined', 'cancelled'
    )),
    CHECK (attempt_count >= 0),
    CHECK (max_attempts >= 1)
);

CREATE INDEX IF NOT EXISTS ix_research_jobs_claim_queue
    ON research_jobs (run_key, job_type, status, priority, created_at);

CREATE INDEX IF NOT EXISTS ix_research_jobs_lease
    ON research_jobs (status, lease_expires_at);

CREATE INDEX IF NOT EXISTS ix_research_jobs_ruler_year
    ON research_jobs (iso3, target_year, ruler_id);

CREATE INDEX IF NOT EXISTS ix_research_jobs_question_year
    ON research_jobs (question_id, target_year);

CREATE TABLE IF NOT EXISTS research_job_events (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,
    worker_id   TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_research_job_events_job_time
    ON research_job_events (job_id, created_at, id);

CREATE TABLE IF NOT EXISTS research_job_dependencies (
    job_id              INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    depends_on_job_id   INTEGER NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, depends_on_job_id),
    CHECK (job_id <> depends_on_job_id)
);

CREATE INDEX IF NOT EXISTS ix_research_job_dependencies_parent
    ON research_job_dependencies (depends_on_job_id, job_id);
