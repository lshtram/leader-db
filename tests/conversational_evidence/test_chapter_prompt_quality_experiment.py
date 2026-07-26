"""Focused tests for the deep chapter prompt quality experiment helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts/experiments" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_machine_record_parser_preserves_valid_records_and_reports_bad_json() -> None:
    module = _load_script("analyze_chapter_prompt_v1_v2")
    valid = {
        "title": "Source",
        "publisher": "Publisher",
        "publication_date": "2022-01-01",
        "url": "https://example.test/source",
        "claim": "A material claim.",
        "locator": "p. 1",
        "provisional_id": "WEB-5B-001",
        "canonical_fact_key": "fact",
        "disposition": "final_evidence",
        "chapter_ids": ["5B"],
        "methodology_ids": ["5B.1"],
        "source_type": "report",
        "source_confidence": "high",
        "source_confidence_reason": "Primary report.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target period",
        "ruler_attribution": "authority based",
        "contrary_evidence": "none found",
        "underlying_fact_key": "fact",
        "lenses": ["Resources"],
    }
    text = (
        "Narrative\nSOURCE_CLAIM_JSON:"
        + json.dumps(valid)
        + '\nSOURCE_CLAIM_JSON:{"broken"\n'
    )

    records, errors = module._parse_records(text)

    assert records == [valid]
    assert len(errors) == 1
    assert errors[0].startswith("line 3:")


def test_frozen_evaluator_rubric_does_not_treat_counts_as_quality_targets() -> None:
    module = _load_script("prepare_chapter_prompt_v1_v2_amlo")

    assert module.MODEL == "gpt-5.4-mini"
    assert module.REASONING == "default_not_overridden"
    assert "Counts are diagnostics, not quality targets." in module.EVALUATOR_RUBRIC
    assert "without searching" in module.EVALUATOR_RUBRIC
    assert "without scoring the ruler" in module.EVALUATOR_RUBRIC


def test_v3_changes_only_the_plan_coverage_step() -> None:
    module = _load_script("prepare_chapter_prompt_v2_v3_amlo")
    baseline = (
        "before\n"
        "2. **Plan coverage.** For every selected lens, identify the important favorable, "
        "adverse, disputed, and exculpatory possibilities that research should test."
        "\nafter"
    )

    candidate = module._v3_template(baseline)

    assert candidate.startswith("before\n")
    assert candidate.endswith("\nafter")
    assert module.SOURCE_ECOLOGY_STEP in candidate


def test_review_package_search_log_uses_completed_events_once(tmp_path: Path) -> None:
    module = _load_script("render_best_results_package")
    event = {
        "item": {
            "type": "web_search",
            "query": "primary query",
            "action": {"queries": ["primary query", "second query"]},
        }
    }
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(
            (
                json.dumps({"type": "item.started", **event}),
                json.dumps({"type": "item.completed", **event}),
            )
        ),
        encoding="utf-8",
    )

    searches = module._searches(path)

    assert searches == [
        {"query": "primary query", "queries": ["primary query", "second query"]}
    ]
