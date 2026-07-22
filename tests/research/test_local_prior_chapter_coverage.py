from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from leaders_db.db.engine import init_database
from leaders_db.research._codex_worker_setup import collect_local_priors
from leaders_db.research.dossier_notebook_prompt import build_research_notebook_prompt
from leaders_db.research.dossier_prompt import build_dossier_prompt
from leaders_db.research.local_prior_package import compact_local_priors
from leaders_db.research.local_prior_schema import (
    LOCAL_PRIOR_MAPPINGS,
    LocalPriorPeriod,
    LocalStructuredPriorRequest,
    mapping_for_methodology_id,
)
from leaders_db.research.local_structured_prior import build_local_structured_prior
from leaders_db.research.research_workflow import ResearchWorkflow

CHAPTER_FACTS = (
    ("1B.1", "nuclear_total_inventory", "fas"),
    ("2B.1", "state_based_conflict_events", "ucdp"),
    ("3B.1", "pts_state_dept_score", "pts"),
    ("4B.1", "electoral_democracy", "vdem"),
    ("5B.1", "gdp_per_capita", "maddison_project"),
    ("6B.1", "hdi", "undp_hdi"),
    ("7B.6", "control_of_corruption", "world_bank_wgi"),
    ("8B.2", "government_effectiveness", "world_bank_wgi"),
)


def test_local_prior_mappings_cover_all_eighty_ruler_lenses_once() -> None:
    mapped = [
        methodology_id
        for mapping in LOCAL_PRIOR_MAPPINGS
        for methodology_id in mapping.methodology_ids
    ]
    expected = {f"{chapter}B.{question}" for chapter in range(1, 9) for question in range(1, 11)}

    assert set(mapped) == expected
    assert len(mapped) == len(set(mapped)) == 80


@pytest.mark.parametrize(("methodology_id", "field_key", "source_slug"), CHAPTER_FACTS)
def test_build_local_prior_loads_each_chapter_fact_family(
    database_url: str,
    methodology_id: str,
    field_key: str,
    source_slug: str,
) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_scope(engine)
    _insert_fact(engine, field_key=field_key, source_slug=source_slug)

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id=methodology_id,
            iso3="NZL",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "evidence_found"
    assert [fact.field_key for fact in artifact.local_facts] == [field_key]
    assert artifact.local_facts[0].source_slugs == [source_slug]
    assert artifact.mapping_note


def test_compact_local_priors_deduplicates_repeated_facts_across_lenses() -> None:
    fact = _fact_payload("gni_per_capita", "undp_hdi")
    priors = tuple(
        _prior_payload(f"{chapter}.{question}", fact)
        for chapter in ("5B", "6B")
        for question in range(1, 11)
    )

    package = compact_local_priors(priors)

    assert package.schema_version == "ruler_local_evidence_package_v3"
    assert package.source_prior_count == 20
    assert package.unique_fact_count == 1
    assert len(package.longitudinal_signals) == 1
    assert package.facts[0].fact_id == "LF001"
    assert package.facts[0].locator == "local-prior:5B.1"
    assert len(package.facts[0].candidate_methodology_ids) == 20
    assert package.facts[0].chapter_ids == ("5B", "6B")
    assert [chapter.fact_ids for chapter in package.chapters] == [
        ("LF001",),
        ("LF001",),
    ]


def test_compact_local_priors_preserves_explicit_empty_and_error_states() -> None:
    priors = (
        _prior_payload(
            "1B.1",
            None,
            status="no_evidence_found",
            reason="Mapped fields are empty.",
            instructions=("Search the named gap.",),
        ),
        _prior_payload(
            "2B.1",
            None,
            status="not_applicable",
            reason="Country-year is outside the included scope.",
        ),
        _prior_payload(
            "3B.1",
            None,
            status="error",
            reason="Database extraction failed.",
            instructions=("Repair local extraction before relying on the handoff.",),
        ),
    )

    package = compact_local_priors(priors)

    assert package.unique_fact_count == 0
    assert package.status_counts == {
        "no_evidence_found": 1,
        "not_applicable": 1,
        "error": 1,
    }
    assert package.methodology_statuses == {
        "1B.1": "no_evidence_found",
        "2B.1": "not_applicable",
        "3B.1": "error",
    }
    assert package.no_evidence_methodology_ids == ("1B.1",)
    assert package.not_applicable_methodology_ids == ("2B.1",)
    assert package.error_methodology_ids == ("3B.1",)
    error_disposition = package.methodology_dispositions["3B.1"]
    assert package.disposition_reasons[error_disposition.reason_id or ""] == (
        "Database extraction failed."
    )
    assert package.disposition_instruction_sets[error_disposition.instruction_set_id or ""] == (
        "Repair local extraction before relying on the handoff.",
    )


def test_compact_local_priors_deduplicates_order_variant_provenance() -> None:
    first = _fact_payload("hdi", "undp_hdi")
    first["source_slugs"] = ["undp_hdi", "world_bank_wdi"]
    first["source_observation_ids"] = ["obs:2", "obs:1"]
    first["warnings"] = ["second", "first"]
    second = {**first}
    second["source_slugs"] = list(reversed(first["source_slugs"]))
    second["source_observation_ids"] = list(reversed(first["source_observation_ids"]))
    second["warnings"] = list(reversed(first["warnings"]))

    package = compact_local_priors((_prior_payload("6B.1", first), _prior_payload("6B.2", second)))

    assert package.unique_fact_count == 1
    assert package.facts[0].source_slugs == ("undp_hdi", "world_bank_wdi")
    assert package.facts[0].source_observation_ids == ("obs:1", "obs:2")
    assert package.facts[0].warnings == ("first", "second")


def test_every_chapter_mapping_contains_its_anchor_fact() -> None:
    for methodology_id, field_key, _source_slug in CHAPTER_FACTS:
        mapping = mapping_for_methodology_id(methodology_id)
        assert mapping is not None
        assert field_key in mapping.field_keys


def test_economic_and_social_lenses_use_question_specific_fields() -> None:
    economic_appointments = mapping_for_methodology_id("5B.2")
    economic_productivity = mapping_for_methodology_id("5B.6")
    social_access = mapping_for_methodology_id("6B.2")
    social_politicization = mapping_for_methodology_id("6B.7")
    economic_trajectory = mapping_for_methodology_id("5B.10")
    political_trajectory = mapping_for_methodology_id("4B.10")

    assert economic_appointments is not None
    assert economic_productivity is not None
    assert social_access is not None
    assert social_politicization is not None
    assert economic_appointments.field_keys == ()
    assert "pwt_human_capital_index" in economic_productivity.field_keys
    assert "under5_mortality" in social_access.field_keys
    assert social_politicization.field_keys == ()
    assert economic_trajectory is not None
    assert "household_consumption_current_usd" in economic_trajectory.field_keys
    assert "gross_fixed_capital_formation_current_usd" in economic_trajectory.field_keys
    assert political_trajectory is not None
    assert "household_consumption_current_usd" not in political_trajectory.field_keys


def test_empty_lens_mapping_requests_narrative_evidence(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_scope(engine)

    artifact = build_local_structured_prior(
        engine,
        LocalStructuredPriorRequest(
            methodology_id="5B.2",
            iso3="NZL",
            period=LocalPriorPeriod(year=2020),
        ),
    )

    assert artifact.status == "no_evidence_found"
    assert artifact.local_facts == []
    assert "semantically sufficient" in (artifact.missing_or_empty_reason or "")
    assert "ruler-specific narrative evidence" in (artifact.missing_or_empty_reason or "")


def test_integrity_and_effectiveness_preserve_personal_attribution_boundaries() -> None:
    personal_integrity = mapping_for_methodology_id("7B.3")
    scrutiny_context = mapping_for_methodology_id("7B.6")
    program_identity = mapping_for_methodology_id("8B.1")
    implementation_context = mapping_for_methodology_id("8B.6")

    assert personal_integrity is not None and personal_integrity.field_keys == ()
    assert scrutiny_context is not None
    assert "control_of_corruption" in scrutiny_context.field_keys
    assert program_identity is not None and program_identity.field_keys == ()
    assert implementation_context is not None
    assert "government_effectiveness" in implementation_context.field_keys


def test_political_freedom_lenses_do_not_receive_identical_bundles() -> None:
    elections = mapping_for_methodology_id("4B.1")
    institutions = mapping_for_methodology_id("4B.4")
    media = mapping_for_methodology_id("4B.6")
    trajectory = mapping_for_methodology_id("4B.10")

    assert elections is not None and "eiu_electoral_process_pluralism" in elections.field_keys
    assert institutions is not None and "judicial_constraints" in institutions.field_keys
    assert media is not None and "press_freedom_score" in media.field_keys
    assert trajectory is not None
    assert len(trajectory.field_keys) > len(elections.field_keys)


def test_nuclear_peace_and_safety_lenses_use_semantic_subsets() -> None:
    nuclear_crisis = mapping_for_methodology_id("1B.8")
    nonnuclear_risk = mapping_for_methodology_id("1B.9")
    conflict_choice = mapping_for_methodology_id("2B.2")
    military_burden = mapping_for_methodology_id("2B.8")
    incitement = mapping_for_methodology_id("3B.3")
    physical_abuse = mapping_for_methodology_id("3B.1")

    assert nuclear_crisis is not None
    assert "nuclear_operational_strategic" in nuclear_crisis.field_keys
    assert nonnuclear_risk is not None and nonnuclear_risk.field_keys == ()
    assert conflict_choice is not None
    assert "state_based_conflict_events" in conflict_choice.field_keys
    assert "military_spend_share_gdp" not in conflict_choice.field_keys
    assert military_burden is not None
    assert "military_spend_share_gdp" in military_burden.field_keys
    assert incitement is not None and incitement.field_keys == ()
    assert physical_abuse is not None
    assert "cirights_torture" in physical_abuse.field_keys


def test_worker_local_priors_carry_resolved_ruler_metadata(database_url: str) -> None:
    init_database(database_url)
    engine = create_engine(database_url, future=True)
    _insert_scope(engine)
    _insert_fact(engine, field_key="hdi", source_slug="undp_hdi")

    priors = collect_local_priors(
        engine,
        {
            "iso3": "NZL",
            "ruler_id": "15125",
            "ruler_name": "Jacinda Ardern",
            "period_start_year": 2020,
            "period_end_year": 2020,
            "input": {"question_ids": ["6B.1"]},
        },
    )

    assert priors[0]["leader"] == {
        "name": "Jacinda Ardern",
        "leader_id": 15125,
        "period_label": "2020",
    }


def test_research_prompt_inlines_one_copy_of_cross_chapter_local_fact(
    tmp_path: Path,
) -> None:
    project = Path(__file__).resolve().parents[2]
    fact = _fact_payload("gni_per_capita", "undp_hdi")
    priors = (
        _prior_payload("5B.1", fact),
        _prior_payload("6B.1", fact),
    )
    job = {
        "job_key": "dossier:test",
        "run_key": "test",
        "iso3": "NZL",
        "country_name": "New Zealand",
        "ruler_id": "15125",
        "ruler_name": "Jacinda Ardern",
        "provider_profile": "openai-luna-candidate",
        "provider": "openai",
        "model": "gpt-5.6-luna",
        "period_start_year": 2020,
        "period_end_year": 2020,
        "input": {
            "ruler_year_id": 15125,
            "question_ids": ["5B.1", "6B.1"],
        },
    }

    prompt = build_research_notebook_prompt(
        job,
        project_root=project,
        worker_output_dir=tmp_path,
        local_priors=priors,
        workflow=ResearchWorkflow(
            version=1,
            chapter_order=tuple(f"{index}B" for index in range(1, 9)),
        ),
    )

    # Once in the raw fact register and once in its audited derived-signal lineage.
    assert prompt.count("undp_hdi:NZL:2020:gni_per_capita") == 2
    assert '"unique_fact_count": 1' in prompt
    assert '"candidate_methodology_ids"' in prompt
    assert "local-prior:5B.1" in prompt
    assert "Do not read\nadditional local files during this worker run" in prompt
    assert "Do not call image or image-inspection tools" in prompt
    assert "request elevated permissions" in prompt
    assert "put the complete handoff in the final response" in prompt
    assert "Required methodology (fully inlined" in prompt
    assert (
        "## Required methodology: .agents/skills/ruler-evidence-researcher/SKILL.md" not in prompt
    )
    assert "## Required methodology: docs/methodology/local-first-researcher-guide.md" not in prompt
    assert "## Required methodology: docs/methodology/ranking-evaluation-criteria.md" not in prompt
    assert "## Required methodology: docs/methodology/source-confidence-registry.json" in (prompt)
    assert '"final_evidence_use_values"' in prompt
    assert "build a lightweight\ncandidate pool" in prompt
    assert "not a search-results ceiling" in prompt
    assert "Never request a recency or recent-news filter" in prompt
    assert "establish one cited authority baseline" in prompt
    assert "Chapter 7B still requires a personal" in prompt
    assert "Do not declare a chapter ready merely because it reached a count" in prompt
    assert "work through only the selected chapters and methodology IDs" in prompt
    assert "must not silently expand to its other nine chapter" in prompt
    assert "substantive\nselected-scope handoff" in prompt
    assert "a rejected or malformed Parallel call is\n  a tool failure" in prompt

    formatter_prompt = build_dossier_prompt(
        job,
        project_root=project,
        worker_output_dir=tmp_path,
        local_priors=priors,
        research_notebook="Research handoff.",
    )
    assert formatter_prompt.count("undp_hdi:NZL:2020:gni_per_capita") == 2
    assert '"methodology_statuses"' in formatter_prompt
    assert "Every retained evidence item must appear in at least one `mappings` row" in (
        formatter_prompt
    )
    assert "never concatenate, abbreviate, or combine evidence IDs" in formatter_prompt
    assert "one evidence object per defensible source-claim unit" in formatter_prompt
    assert "do not collapse a report's distinct events" in formatter_prompt
    assert "Set `source_locator` to the precise PDF page/table/figure" in formatter_prompt
    assert "Set `canonical_fact_key` to a stable value" in formatter_prompt
    assert "never recreate the same source-locator-claim fact" in formatter_prompt
    assert "Remove any researcher-written score" in formatter_prompt
    assert "do not perform new research" in formatter_prompt
    assert "Do not search or add facts" in formatter_prompt
    assert "Mapping is many-to-many" in formatter_prompt
    assert "never manufacture" in formatter_prompt
    assert "use `research_blocked`" in formatter_prompt
    assert "same canonical fact key" in formatter_prompt
    assert "every recorded `chapter_ids` chapter" in formatter_prompt


def _insert_scope(engine: object) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO countries (
                    id, iso3, country_name, country_name_normalized
                ) VALUES (1, 'NZL', 'New Zealand', 'new zealand')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO country_years (
                    id, country_id, year, included_in_project
                ) VALUES (1, 1, 2020, 1)
                """
            )
        )


def _insert_fact(engine: object, *, field_key: str, source_slug: str) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                """
                INSERT INTO country_year_facts (
                    country_id, country_year_id, year, field_key, field_label,
                    value_type, selected_value_number, selected_value_text,
                    selected_value_json, candidate_values_json, selection_rule,
                    adjudication_status, source_slugs_json,
                    source_observation_ids_json, confidence_score,
                    quality_signals_json, warnings_json, rationale,
                    recommended_next_action, producer, method_version
                ) VALUES (
                    1, 1, 2020, :field_key, :field_key, 'number', 1.0, NULL,
                    NULL, '[]', 'test_rule', 'selected', :source_slugs,
                    :observation_ids, 80, '{}', '[]', 'Selected fixture fact.',
                    'none', 'test', 'test_v1'
                )
                """
            ),
            {
                "field_key": field_key,
                "source_slugs": json.dumps([source_slug]),
                "observation_ids": json.dumps([f"{source_slug}:NZL:2020:{field_key}"]),
            },
        )


def _fact_payload(field_key: str, source_slug: str) -> dict[str, object]:
    return {
        "year": 2020,
        "field_key": field_key,
        "label": field_key,
        "value": 1.0,
        "value_type": "number",
        "source_slugs": [source_slug],
        "source_observation_ids": [f"{source_slug}:NZL:2020:{field_key}"],
        "confidence": 80,
        "warnings": [],
    }


def _prior_payload(
    methodology_id: str,
    fact: dict[str, object] | None,
    *,
    status: str = "evidence_found",
    reason: str | None = None,
    instructions: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "methodology_id": methodology_id,
        "status": status,
        "local_facts": [] if fact is None else [fact],
        "missing_or_empty_reason": reason,
        "recommended_research_instructions": list(instructions),
    }
