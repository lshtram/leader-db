"""Behavioral tests for the content-first long-document reader experiment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from leaders_db.conversational_evidence.document_reader_experiment import (
    DocumentReaderConfig,
    chunk_units,
    classify_access_response,
    extract_json_object,
    load_document_reader_config,
    render_reader_prompt,
)
from leaders_db.research.model_profiles import load_research_model_profiles


def test_config_routes_every_pack_type_through_shared_guidance() -> None:
    """One config owns source selection, type prompts, and compression targets."""

    config = load_document_reader_config()

    assert len(config.document_pack) == len({item.source_id for item in config.document_pack})
    assert set(config.calibration_document_ids) <= {item.source_id for item in config.document_pack}
    for item in config.document_pack:
        prompt = render_reader_prompt(config, item, reading_brief="Inspect material facts.")
        assert item.document_type in prompt
        assert config.document_type_guidance[item.document_type] in prompt
        assert str(config.summary_target_tokens[item.document_type]) in prompt


def test_config_rejects_format_as_a_reader_quality_failure() -> None:
    """The experiment judges content after normalization, never JSON polish."""

    payload = json.loads(load_document_reader_config().model_dump_json())
    payload["content_acceptance"]["format_errors_are_quality_failures"] = True

    with pytest.raises(ValidationError, match="cannot score formatting"):
        DocumentReaderConfig.model_validate(payload)


def test_reader_ladder_profiles_support_document_reader_role() -> None:
    """Every configured reader/fallback can execute the experimental role."""

    config = load_document_reader_config()
    profiles = load_research_model_profiles(
        config_path := (Path(__file__).resolve().parents[2] / "configs/research-models.yaml")
    )

    assert config_path.is_file()
    for profile_name in (
        *config.reader_ladder,
        config.baseline_reader,
        config.reading_brief_model,
        config.normalizer,
        config.content_auditor,
        config.compiler,
    ):
        assert "document_reader" in profiles.profiles[profile_name].roles


def test_chunking_preserves_units_and_stable_locator_envelopes() -> None:
    """Page or section units remain intact while chunks are formed deterministically."""

    units = ("A" * 40, "B" * 40, "C" * 40)

    chunks = chunk_units(units, target_tokens=20, max_tokens=30)

    assert [chunk.chunk_id for chunk in chunks] == [
        "chunk-0001",
        "chunk-0002",
    ]
    assert [(chunk.start_unit, chunk.end_unit) for chunk in chunks] == [
        (1, 2),
        (3, 3),
    ]
    recovered_units = [unit for chunk in chunks for unit in chunk.text.split("\n\n")]
    assert recovered_units == list(units)


def test_json_recovery_is_best_effort_and_content_neutral() -> None:
    """Markdown wrapping can be repaired without rewriting source-map content."""

    recovered = extract_json_object('Commentary\\n```json\\n{"claim":"kept"}\\n```')

    assert recovered == {"claim": "kept"}
    assert extract_json_object("useful prose but no JSON") is None


@pytest.mark.parametrize(
    ("status", "body", "robots", "expected"),
    (
        (200, b"full document", True, "open_machine_readable"),
        (403, b"please subscribe", True, "paywall_or_login"),
        (403, b"access denied", True, "bot_or_javascript_challenge"),
        (200, b"full document", False, "robots_denied"),
        (503, b"temporarily down", True, "transient_failure"),
        (200, b"enable JavaScript to continue", True, "bot_or_javascript_challenge"),
        (200, b"ERROR 404 missing", True, "unavailable"),
    ),
)
def test_access_classification_does_not_bypass_restrictions(
    status: int,
    body: bytes,
    robots: bool,
    expected: str,
) -> None:
    """Paywalls, robots denial, challenges, and transient errors stay distinct."""

    record = classify_access_response(
        source_id="GOV-001",
        requested_url="https://example.test/document",
        status_code=status,
        final_url="https://example.test/document",
        content_type="text/html",
        sampled_body=body,
        robots_allowed=robots,
    )

    assert record.state == expected
