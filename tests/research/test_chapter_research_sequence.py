import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from leaders_db.conversational_evidence.data import load, questions
from leaders_db.research._codex_worker_setup import WorkerAttempt
from leaders_db.research.chapter_research_sequence import (
    ChapterResearchPromptConfig,
    _chapter_resource_index,
    _compact_chapter_guide,
    build_chapter_research_prompt,
)
from leaders_db.research.chapter_source_discovery import (
    _build_discovery_prompt,
    _build_overview_discovery_prompt,
)
from leaders_db.research.codex_worker import (
    _checkpoint_covers_chapters,
    _recover_consumer_materials,
)
from leaders_db.research.notebook_continuation import (
    _append_current_ledger_manifest,
)
from leaders_db.research.question_lens_presentation import (
    load_question_lens_presentation,
)
from leaders_db.research.research_workflow import ResearchWorkflow


def _workflow() -> ResearchWorkflow:
    return ResearchWorkflow(
        version=1,
        chapter_order=tuple(f"{index}B" for index in range(1, 9)),
        researcher_session_scope="segmented_ruler_period",
        chapter_session_mode="fresh_compact_context",
    )


def _selected_test_lenses() -> tuple[str, str, str]:
    configured = questions()
    first = configured[0]["id"]
    chapter = first.split(".", maxsplit=1)[0]
    same_chapter = next(
        item["id"]
        for item in configured[1:]
        if item["id"].startswith(f"{chapter}.")
    )
    other_chapter = next(
        item["id"]
        for item in configured
        if not item["id"].startswith(f"{chapter}.")
    )
    return first, same_chapter, other_chapter


def test_chapter_prompt_contains_selected_inputs_and_machine_contract() -> None:
    first, second, other = _selected_test_lenses()
    chapter_id = first.split(".", maxsplit=1)[0]
    catalog = load_question_lens_presentation()
    prompt_config = load("chapter_research_prompt.json")
    lens_by_id = {lens.id: lens for lens in catalog.lenses}
    prompt = build_chapter_research_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2022,
            "period_end_year": 2022,
            "input": {
                "question_ids": [first, second, other],
            },
        },
        chapter_id=chapter_id,
        guide="Guide text",
        workflow=_workflow(),
        resource_index=(
            {
                "provisional_id": "R01",
                "url": "https://example.test/source",
                "claim": "Known lead",
            },
        ),
    )

    assert f"Lens presentation version: `{catalog.version}`." in prompt
    assert f"Prompt version: `{prompt_config['version']}`." in prompt
    assert prompt.index("Simple question") < prompt.index("Detailed research question")
    assert f"{first} — {lens_by_id[first].title}" in prompt
    assert f"{second} — {lens_by_id[second].title}" in prompt
    assert f"{other} —" not in prompt
    assert json.dumps([first, second]) in prompt
    assert "SOURCE_CLAIM_JSON:" in prompt
    assert "Known lead" in prompt
    assert "https://example.test/source" in prompt
    assert f"WEB-{chapter_id}-" in prompt
    assert "separate discovery stage has already built" in prompt
    assert "not the primary broad-discovery pass" in prompt
    assert "at least 12" in prompt
    assert "SOURCE_CANDIDATE_JSON" in prompt


def test_discovery_prompt_produces_candidates_without_evidence_extraction() -> None:
    first, second, other = _selected_test_lenses()
    chapter_id = first.split(".", maxsplit=1)[0]

    prompt = _build_discovery_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2023,
            "period_end_year": 2023,
            "input": {"question_ids": [first, second, other]},
        },
        chapter_id=chapter_id,
        guide="Guide text",
        workflow=_workflow(),
    )

    assert "source discovery only" in prompt
    assert "at least 30 distinct documents" in prompt
    assert "SOURCE_CANDIDATE_JSON:" in prompt
    assert "Do not extract evidence claims" in prompt


def test_overview_discovery_explicitly_searches_books_and_syntheses() -> None:
    prompt = _build_overview_discovery_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2023,
            "period_end_year": 2023,
        },
        workflow=_workflow(),
    )

    assert "at least 50 distinct" in prompt
    assert "biographies" in prompt
    assert "scholarly monographs" in prompt
    assert "dissertations and theses" in prompt


def test_chapter_prompt_config_rejects_a_missing_runtime_field() -> None:
    configured = deepcopy(load("chapter_research_prompt.json"))
    configured["template"] = configured["template"].replace(
        "{selected_lenses_json}", ""
    )

    with pytest.raises(ValidationError, match="interpolation fields"):
        ChapterResearchPromptConfig.model_validate(configured)


@pytest.mark.parametrize(
    "invalid_suffix",
    ("{}", "{chapter_id!r}", "{chapter_id:>10}", "{chapter_id.value}"),
)
def test_chapter_prompt_config_rejects_unsupported_formatting(
    invalid_suffix: str,
) -> None:
    configured = deepcopy(load("chapter_research_prompt.json"))
    configured["template"] += invalid_suffix

    with pytest.raises(ValidationError, match="formatting syntax"):
        ChapterResearchPromptConfig.model_validate(configured)


def test_chapter_prompt_interpolates_selected_chapter_only() -> None:
    first, second, other = _selected_test_lenses()
    chapter_id = first.split(".", maxsplit=1)[0]
    prompt = build_chapter_research_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2022,
            "period_end_year": 2022,
            "input": {"question_ids": [first, second, other]},
        },
        chapter_id=chapter_id,
        guide="Guide text",
        workflow=_workflow(),
    )

    assert f"{first} —" in prompt
    assert f"{second} —" in prompt
    assert f"{other} —" not in prompt
    assert json.dumps([first, second]) in prompt


def test_chapter_prompt_excludes_judge_only_guide_sections() -> None:
    prompt = build_chapter_research_prompt(
        job={
            "ruler_name": "Test Ruler",
            "country_name": "Test Country",
            "period_start_year": 2022,
            "period_end_year": 2022,
            "input": {"question_ids": ["5B.1"]},
        },
        chapter_id="5B",
        guide=(
            "## Ten Evidence Lenses\n1. **5B.1** — Research question.\n\n"
            "## Researcher Evidence Plan\nUse primary records.\n\n"
            "## Chapter Judge and Lens Weighting\nJudge-only token hog."
        ),
        workflow=_workflow(),
    )

    assert "Use primary records" in prompt
    assert "Judge-only token hog" not in prompt


@pytest.mark.parametrize(
    "heading",
    (
        "## Researcher Guidance",
        "## Researcher Evidence Plan",
        "## Researcher Workflow and Evidence Themes",
    ),
)
def test_compact_guide_extracts_supported_researcher_sections(heading: str) -> None:
    guide = (
        "# Guide\n\n"
        "## Ten Evidence Lenses\n"
        "editorial lens catalogue\n\n"
        f"{heading}\n"
        "researcher-only guidance\n\n"
        "## Chapter Judge and Lens Weighting\n"
        "judge-only guidance"
    )
    compact = _compact_chapter_guide(guide)

    assert compact == f"{heading}\nresearcher-only guidance"


def test_d_style_machine_record_survives_parent_ledger_merge(
    tmp_path: Path,
) -> None:
    attempt_dir = tmp_path / "job" / "attempts" / "001-current"
    trusted_dir = tmp_path / "job" / "trusted" / "001-current"
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
    attempt = WorkerAttempt(
        attempt_dir=attempt_dir,
        trusted_dir=trusted_dir,
        result_path=attempt_dir / "dossier.json",
        schema_path=trusted_dir / "schema.json",
        prompt_path=attempt_dir / "prompt.txt",
        pending_path=attempt_dir / "pending.json",
        events_path=trusted_dir / "events.jsonl",
        existing_candidate=None,
        local_priors=(),
        local_prior_provenance=(),
    )
    record = {
        "title": "Primary record",
        "publisher": "Example Court",
        "publication_date": "2022-06-01",
        "url": "https://example.test/judgment",
        "claim": "The court issued a final finding.",
        "locator": "paragraph 42",
        "provisional_id": "WEB-7B-001",
        "canonical_fact_key": ("https://example.test/judgment|paragraph 42|final finding"),
        "underlying_fact_key": "example-final-finding",
        "disposition": "final_evidence",
        "chapter_ids": ["7B"],
        "methodology_ids": ["7B.1", "7B.6"],
        "source_type": "legal",
        "source_confidence": "high",
        "source_confidence_reason": "Opened final judgment.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target period",
        "ruler_attribution": "direct",
        "contrary_evidence": [],
        "lenses": ["7B.1", "7B.6"],
    }
    notebook = "SOURCE_CLAIM_JSON: " + json.dumps(record, separators=(",", ":"))

    merged = _append_current_ledger_manifest(notebook, attempt)

    manifest = json.loads(
        (attempt_dir / "research-ledger-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["entries"] == [record]
    assert record["canonical_fact_key"] in merged
    assert record["locator"] in merged
    assert record["methodology_ids"] == manifest["entries"][0]["methodology_ids"]


def test_candidate_resources_do_not_require_an_evidence_manifest(tmp_path: Path) -> None:
    attempt_dir = tmp_path / "job" / "attempts" / "001-current"
    trusted_dir = tmp_path / "job" / "trusted" / "001-current"
    attempt_dir.mkdir(parents=True)
    trusted_dir.mkdir(parents=True)
    attempt = WorkerAttempt(
        attempt_dir=attempt_dir,
        trusted_dir=trusted_dir,
        result_path=attempt_dir / "dossier.json",
        schema_path=trusted_dir / "schema.json",
        prompt_path=attempt_dir / "prompt.txt",
        pending_path=attempt_dir / "pending.json",
        events_path=trusted_dir / "events.jsonl",
        existing_candidate=None,
        local_priors=(),
        local_prior_provenance=(),
    )
    (attempt_dir / "source-candidate-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": "ruler_source_candidate_catalog_v1",
                "candidates": [
                    {
                        "url": "https://example.test/book",
                        "title": "A book",
                        "publisher": "University Press",
                        "document_type": "book",
                        "access_status": "unopened",
                        "chapter_ids": ["5B"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    resources = _chapter_resource_index(attempt, "5B")

    assert resources[0]["title"] == "A book"


def test_completed_chapter_checkpoint_prevents_research_replay(tmp_path: Path) -> None:
    notebook = (
        "initial\n\n--- CHAPTER RESEARCH 1B ---\nfirst\n\n--- CHAPTER RESEARCH 2B ---\nsecond"
    )
    checkpoint = (
        tmp_path / "events.jsonl",
        notebook,
        tmp_path / "notebook.md",
        "notebook-hash",
        "events-hash",
    )
    workflow = _workflow()
    job = {"input": {"question_ids": ["1B.1", "2B.1"]}}

    assert _checkpoint_covers_chapters(checkpoint, job=job, workflow=workflow)
    assert not _checkpoint_covers_chapters(
        (checkpoint[0], notebook.replace("2B", "3B"), *checkpoint[2:]),
        job=job,
        workflow=workflow,
    )


def test_recovered_checkpoint_copies_consumer_materials(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    prior_attempt = job_dir / "attempts" / "001-prior"
    current_attempt = job_dir / "attempts" / "002-current"
    prior_trusted = job_dir / "trusted" / "001-prior"
    current_trusted = job_dir / "trusted" / "002-current"
    for path in (prior_attempt, current_attempt, prior_trusted, current_trusted):
        path.mkdir(parents=True)
    attempt = WorkerAttempt(
        attempt_dir=current_attempt,
        trusted_dir=current_trusted,
        result_path=current_attempt / "dossier.json",
        schema_path=current_trusted / "schema.json",
        prompt_path=current_attempt / "prompt.txt",
        pending_path=current_attempt / "pending.json",
        events_path=current_trusted / "events.jsonl",
        existing_candidate=None,
        local_priors=(),
        local_prior_provenance=(),
    )
    checkpoint = (
        prior_trusted / "events.jsonl",
        (
            "notebook\n\n--- CHAPTER RESEARCH 1B ---\nchapter\n\n"
            "--- RESEARCH LEDGER MANIFEST ---\n"
            '{"schema_version":"ruler_research_ledger_manifest_v1",'
            '"entries":[{"canonical_fact_key":"fact-1"}]}'
        ),
        prior_trusted / "research-notebook-8B.md",
        "notebook-hash",
        "events-hash",
    )

    _recover_consumer_materials(checkpoint, attempt=attempt)

    assert (current_attempt / "research-ledger-manifest.json").is_file()
    assert (current_attempt / "research-chapter-1B.md").read_text() == "chapter"
