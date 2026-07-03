# Database Schema — Prototype + Research Evidence Store

This document is the authoritative schema reference for the 11 prototype tables
defined in [`../requirements/top-level-requirements.md`](../requirements/top-level-requirements.md)
§7 plus later research-engine persistence migrations. The implementation lives
in [`src/leaders_db/db/models.py`](../../src/leaders_db/db/models.py)
(SQLAlchemy 2.x ORM), and the canonical DDL is the ordered migration set under
[`src/leaders_db/db/migrations/`](../../src/leaders_db/db/migrations/), starting
with `0001_initial.sql` and extended by later files such as
`0002_normalized_observations.sql`. SQL DDL is checked in for clarity and as the
schema change source of truth.

## Conventions

- **SQLite** for the prototype; **PostgreSQL** is the production target (REQ-DB-001).
- Primary keys are surrogate integer `id` columns.
- Foreign keys are explicit (`country_id`, `leader_id`, `source_id`, `ruler_spell_id`, `category_id`, `ruler_year_id`, `parent_id`) and enforced.
- ISO3 is the canonical country key. `leader_aliases.alias` plus `leader_aliases.source_id` form a unique tuple per source.
- Date columns use ISO `YYYY-MM-DD`. Year columns use smallint (1900–2100).
- Confidence and score columns use the integer ranges defined in requirement §11 and §9.

## Tables

### `countries`

Master country list.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | surrogate |
| `iso3` | text NOT NULL UNIQUE | primary key for matching (Stage 3) |
| `country_name` | text NOT NULL | preferred display name |
| `country_name_normalized` | text NOT NULL | lowercased, accent-stripped |
| `region` | text | optional |
| `notes` | text | free-form, e.g. matching problems |

### `country_years`

Per-country-per-year context.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | surrogate |
| `country_id` | integer FK → `countries.id` | |
| `year` | smallint NOT NULL | 1900–2100 |
| `population` | bigint | from WDI |
| `gdp_current_usd` | bigint | from WDI |
| `gdp_per_capita` | real | |
| `included_in_project` | bool | per REQ-SCOPE-003 (population threshold) |
| `inclusion_reason` | text | free-form |
| `source_confidence` | integer 0–100 | per-indicator authority/specificity, aggregated |

UNIQUE(`country_id`, `year`).

### `leaders`

Per-leader identity. Reused across spells and years.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `full_name` | text NOT NULL | preferred display name |
| `normalized_name` | text NOT NULL | lowercased, accent-stripped |
| `birth_date` | date | |
| `death_date` | date | |
| `gender` | text | optional |
| `notes` | text | |

### `leader_aliases`

Alternative spellings, one row per alias-source.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `leader_id` | integer FK → `leaders.id` | |
| `alias` | text NOT NULL | raw spelling from source |
| `source_id` | integer FK → `sources.id` | provenance |

### `ruler_spells`

A leader's tenure in a country, with type metadata.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `leader_id` | integer FK → `leaders.id` | |
| `country_id` | integer FK → `countries.id` | |
| `office_title` | text | e.g. `President`, `PM`, `Supreme Leader` |
| `start_date` | date NOT NULL | |
| `end_date` | date | NULL = ongoing or unknown |
| `source_dataset` | text | `archigos`, `leader_survival`, `reign`, `client_existing`, … |
| `is_actual_ruler` | bool | per REQ-ENT-002 (actual vs formal) |
| `is_formal_leader` | bool | |
| `rule_type` | text | enum: `monarch`, `president`, `prime_minister`, `supreme_leader`, `party_leader`, `military`, `junta`, … |
| `shared_rule_flag` | bool | |
| `disputed_rule_flag` | bool | |
| `confidence_score` | integer 0–100 | per §11 |
| `notes` | text | |

### `ruler_years`

Per-leader-per-country-per-year actual-ruler determination (Stage 4 output).

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `leader_id` | integer FK → `leaders.id` | |
| `country_id` | integer FK → `countries.id` | |
| `year` | smallint NOT NULL | |
| `ruler_spell_id` | integer FK → `ruler_spells.id` | nullable for unresolved years |
| `actual_ruler_status` | text | `actual_ruler`, `formal_only`, `co_ruler`, `disputed` |
| `client_matrix_leader_name` | text | the client matrix's leader string (preserved as-is) |
| `system_selected_leader_name` | text | the system's chosen leader string |
| `match_status` | text | enum per §4: `exact_match`, `name_variant_match`, `different_formal_same_actual`, `multiple_possible_rulers`, `client_only`, `external_only`, `conflict_between_sources`, `manual_review_required` |
| `confidence_score` | integer 0–100 | per §11 |
| `review_status` | text | enum per §14 |
| `review_note` | text | |

UNIQUE(`leader_id`, `country_id`, `year`).

### `ruler_identity_adjudications`

Durable D3-D5 principal-ruler selection / review queue, one row per included
`country_years` row.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | surrogate |
| `country_year_id` | integer FK → `country_years.id` | UNIQUE, idempotent upsert key |
| `country_id`, `year` | integer / smallint | query-friendly country-year dimensions |
| `selected_ruler_year_id` | integer FK → `ruler_years.id` | nullable when unresolved/research-required |
| `selected_leader_name` | text | nullable display name of selected principal ruler |
| `candidate_ruler_year_ids_json` | text JSON array | all persisted candidate `ruler_years.id` values |
| `candidates_json` | text JSON array | candidate names, titles, source slugs, intervals, flags |
| `classification` / `selection_rule` | text | detailed adjudication class and rule used |
| `review_status` | text | `auto_resolved`, `needs_review`, or `research_required` |
| `confidence_score` | smallint | selected confidence or unresolved minimum where available |
| `confidence_penalties_json`, `warnings_json` | text JSON arrays | audit notes from v1 adjudication |
| `rationale`, `review_reason` | text | why the row was selected or queued |
| `research_prompt` | text | future manual/internet-research question/context for unresolved rows |
| `recommended_next_action` | text | next action from detailed identity coverage |
| `source_slugs_json`, `source_observation_ids_json` | text JSON arrays | source traceability when available |
| `run_id`, `method_version`, `created_at`, `updated_at` | text | reproducibility metadata |

UNIQUE(`country_year_id`). Indexes support (`country_id`, `year`) and
(`review_status`, `classification`).

### `country_year_facts`

Generic adjudicated country-year value table. This is the long-term write
contract for reusable table cells across domains, not just ruler identity. Domain
builders may keep convenient specialized tables, but they should also publish one
row per country-year field here when the value is useful to downstream scoring,
question answering, review queues, or exports.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | surrogate |
| `country_year_id` | integer FK → `country_years.id` | part of idempotent upsert key |
| `country_id`, `year` | integer / smallint | query-friendly dimensions |
| `field_key`, `field_label` | text | stable key such as `principal_ruler`; display label |
| `value_type` | text | `entity_reference`, `number`, `text`, `boolean`, `json`, etc. |
| `selected_value_text`, `selected_value_number`, `selected_value_json` | text / real / JSON text | typed selected value slots; unused slots remain NULL |
| `selected_entity_table`, `selected_entity_id` | text / integer | optional reference to a domain row such as `ruler_years.id` |
| `candidate_values_json` | text JSON array | all candidate values considered for the cell |
| `selection_rule`, `adjudication_status` | text | deterministic rule and `auto_resolved` / `needs_review` / `research_required` status |
| `confidence_score` | smallint | 0-100 confidence when available |
| `agreement_score`, `authority_score`, `specificity_score`, `temporal_fit_score` | real | reusable quality components; nullable until a producer can compute them |
| `quality_signals_json`, `warnings_json` | text JSON | audit signals and warnings that do not fit typed columns yet |
| `rationale`, `review_reason`, `research_prompt`, `recommended_next_action` | text | selection or review context |
| `source_slugs_json`, `source_observation_ids_json` | text JSON arrays | source traceability |
| `producer`, `method_version`, `run_id`, `created_at`, `updated_at` | text | reproducibility metadata |

UNIQUE(`country_year_id`, `field_key`). Indexes support (`country_id`, `year`),
(`field_key`, `adjudication_status`), and review-queue scans by
(`adjudication_status`, `field_key`, `year`). The current first producer is the
D3-D5 ruler adjudication builder, which publishes `field_key = principal_ruler`.

### `score_categories`

Canonical list of scoring categories. Requirement §4 enumerates ten categories in total: 8 active rating categories (nuclear responsibility, international peace, domestic safety, political freedom, economic well-being, social well-being, integrity, effectiveness) and 2 optional/deferred categories (power retention, global influence). The active set is the prototype's scoring scope; the optional categories may be populated in a later iteration.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `category_key` | text NOT NULL UNIQUE | e.g. `political_freedom`, `corruption`, `economic_wellbeing` |
| `category_name` | text NOT NULL | display name |
| `description` | text | |
| `rubric_low` | text | what a low score means |
| `rubric_mid` | text | what a middle score means |
| `rubric_high` | text | what a high score means |

### `ruler_scores`

Per-ruler-year per-category score (Stage 9–11 output).

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `ruler_year_id` | integer FK → `ruler_years.id` | |
| `category_id` | integer FK → `score_categories.id` | |
| `client_score` | integer 0–10 | from the client matrix; preserved as-is |
| `system_proposed_score` | integer 0–10 | from the scoring module |
| `final_score` | integer 0–10 | set by the manual-review workflow (REQ-REF-003) |
| `score_delta_vs_client` | integer | `system_proposed_score - client_score` |
| `confidence_score` | integer 0–100 | per §11 |
| `source_agreement` | text | `high`, `medium_high`, `medium`, `low`, `conflict`, `n/a` |
| `human_review_required` | bool | per §14 priority |
| `rationale_short` | text | ≤ 240 chars |
| `review_status` | text | per §14 |

UNIQUE(`ruler_year_id`, `category_id`).

### `sources`

Provenance registry. One row per dataset (or per dataset-version).

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `source_name` | text NOT NULL | display name |
| `source_type` | text | `academic`, `ngo`, `igo`, `official`, `reference`, `news` |
| `source_url` | text | |
| `version` | text | e.g. `v16`, `2024-Q3` |
| `license_note` | text | |
| `download_date` | date | |
| `coverage_start_year` | smallint | |
| `coverage_end_year` | smallint | |
| `notes` | text | |

### `source_observations`

Raw and normalized observations from each source. The audit backbone.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `source_id` | integer FK → `sources.id` | |
| `country_id` | integer FK → `countries.id` | nullable for sources that aren't country-keyed |
| `leader_id` | integer FK → `leaders.id` | nullable for non-leader-keyed sources |
| `year` | smallint | nullable for non-year-keyed sources |
| `variable_name` | text NOT NULL | canonical name from the indicator catalog |
| `raw_value` | text | preserved as-is |
| `normalized_value` | real | 0–1 or 0–10 per the indicator catalog |
| `unit` | text | |
| `source_row_reference` | text | row/col locator in the original file |
| `confidence` | integer 0–100 | per §11 |
| `notes` | text | |

INDEX on (`source_id`, `country_id`, `year`), INDEX on (`variable_name`, `year`).

### `normalized_observations`

Research-engine evidence store mirroring the source-layer
`NormalizedObservation` contract. Introduced by
`0002_normalized_observations.sql` so research queries can read normalized
evidence from SQLite without rerunning adapters or opening raw files.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | surrogate |
| `source_slug` | text NOT NULL | source id slug, e.g. `ucdp` |
| `observation_id` | text NOT NULL | source-stable observation id |
| `observation_family` | text NOT NULL | normalized evidence family |
| `indicator_code` | text NOT NULL | concept/indicator key |
| `value_json` | text NOT NULL | JSON-encoded `NormalizedObservation.value` |
| `value_type` | text NOT NULL | `numeric`, `categorical`, `text`, `boolean`, `json`, or `missing` |
| `year` | integer | optional common time dimension |
| `country_code` / `country_name` | text | optional common entity dimension |
| `leader_id` / `leader_name` | text | optional common leader dimension |
| `unit`, `scale`, `source_version` | text | source metadata |
| `raw_locator_json` | text NOT NULL | JSON `RawLocator`, including source URL/path/row references |
| `transform_locator_json` | text NOT NULL | JSON `TransformLocator` |
| `quality_flags_json` | text NOT NULL | JSON array |
| `warnings_json` | text NOT NULL | JSON array of structured source warnings |
| `extension_json` | text NOT NULL | JSON extension payload |
| `scope_json` | text NOT NULL | generic dimension snapshot for research scope |
| `created_at` | text | insert timestamp |

UNIQUE(`source_slug`, `observation_id`). Indexes support source/family/indicator,
country-year, and leader-year filters.

### `validation_results`

Per-item validation record. Stage 12 output.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `item_type` | text NOT NULL | `ruler_year` or `ruler_score` |
| `item_id` | integer NOT NULL | FK-by-convention to `ruler_years.id` or `ruler_scores.id` |
| `validation_status` | text | `match`, `alias_match`, `conflict`, `missing`, `low_confidence`, `high_delta` |
| `source_count` | integer | number of independent sources supporting the item |
| `source_agreement_score` | integer 0–100 | per §11 |
| `source_authority_score` | integer 0–100 | per §11 |
| `temporal_fit_score` | integer 0–100 | per §11 |
| `specificity_score` | integer 0–100 | per §11 |
| `final_confidence_score` | integer 0–100 | the 0.35/0.25/0.25/0.15 weighted score |
| `validation_note` | text | |

## Critical Invariants

These are enforced by the schema and the surrounding code:

1. **Client matrix is a validation/test reference, not ground truth and not evidence.** `ruler_scores.client_score` is set once from the client xlsx and never overwritten by scoring code. `system_proposed_score` is the system's value. `final_score` is set only by the manual-review workflow. `score_delta_vs_client` is always computed as `system_proposed_score - client_score`. The client matrix is not counted in `source_observations`, source-agreement confidence, or source-authority confidence. (REQ-REF-001, REQ-REF-003, REQ-REF-004, REQ-DB-003)
2. **Source provenance is mandatory.** Every `ruler_scores` row has an associated `validation_results` row that records the contributing source count and the four confidence components.
3. **No silent leader overwrite.** `ruler_years` always carries both `client_matrix_leader_name` and `system_selected_leader_name` as separate strings. The `match_status` column records how they compare.
4. **One ruler-year per (leader, country, year).** UNIQUE(`leader_id`, `country_id`, `year`) on `ruler_years`. Multiple leaders for the same `(country, year)` are allowed (shared rule); what is not allowed is one leader appearing twice for the same `(country, year)`.
5. **Idempotent re-ingestion.** All ingest paths are written so re-running them with the same source files in `data/raw/<source>/` produces the same rows in `source_observations` and `ruler_spells`.

## Schema Changes

- New columns → new migration `0002_*.sql`. Never edit `0001_initial.sql` after first commit.
- New tables → new migration `0002_*.sql`.
- ORM models and the SQL DDL must stay in sync. Update both in the same commit.
- Document the schema change in `docs/reviews/<date>-<slug>.md` for any non-trivial migration.
