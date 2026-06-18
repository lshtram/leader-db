"""LLM strict-JSON schema tests (requirement §10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from leaders_db.llm.schemas import (
    LLMScoreInput,
    LLMScoreOutput,
    ScoreBand,
    band_for_confidence,
)


def _input(**overrides) -> LLMScoreInput:
    payload = dict(
        country_iso3="MEX",
        country_name="Mexico",
        year=2023,
        leader_candidate_name="Andrés Manuel López Obrador",
        category_key="political_freedom",
        rubric_description="0 = fully authoritarian, 10 = fully liberal democracy",
        structured_indicators=["vdem_liberal_democracy=0.45"],
        client_score=6,
        client_note="Functioning but flawed democracy.",
    )
    payload.update(overrides)
    return LLMScoreInput(**payload)


def _output(**overrides) -> LLMScoreOutput:
    payload = dict(
        proposed_score=6,
        confidence=78,
        rationale="External indicators suggest a flawed but functioning democracy.",
        main_supporting_evidence=["V-Dem electoral democracy 0.45"],
        main_contradicting_evidence=["Concerns around judicial independence"],
        human_review_required=False,
        review_reason="",
    )
    payload.update(overrides)
    return LLMScoreOutput(**payload)


def test_input_validates_minimal_required_fields() -> None:
    payload = _input()
    assert payload.country_iso3 == "MEX"
    assert payload.evidence_snippets == []


def test_input_caps_evidence_snippets_at_three() -> None:
    from leaders_db.llm.schemas import EvidenceSnippet

    snippets = [EvidenceSnippet(text=f"snippet {i}", source_label=f"src{i}") for i in range(4)]
    with pytest.raises(ValidationError):
        _input(evidence_snippets=snippets)


def test_output_rejects_extra_fields() -> None:
    # Strict contract: the LLM is forbidden from inventing extra structure.
    with pytest.raises(ValidationError):
        LLMScoreOutput.model_validate(
            {
                "proposed_score": 6,
                "confidence": 78,
                "rationale": "ok",
                "main_supporting_evidence": [],
                "main_contradicting_evidence": [],
                "human_review_required": False,
                "review_reason": "",
                "invented_extra_field": "bad",
            }
        )


def test_output_score_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        _output(proposed_score=11)
    with pytest.raises(ValidationError):
        _output(confidence=-1)


def test_band_for_confidence_returns_correct_band() -> None:
    assert band_for_confidence(100) == ScoreBand.HIGH
    assert band_for_confidence(85) == ScoreBand.HIGH
    assert band_for_confidence(84) == ScoreBand.GOOD
    assert band_for_confidence(70) == ScoreBand.GOOD
    assert band_for_confidence(69) == ScoreBand.MEDIUM
    assert band_for_confidence(50) == ScoreBand.MEDIUM
    assert band_for_confidence(49) == ScoreBand.LOW
    assert band_for_confidence(30) == ScoreBand.LOW
    assert band_for_confidence(29) == ScoreBand.UNRELIABLE
    assert band_for_confidence(0) == ScoreBand.UNRELIABLE


def test_band_for_confidence_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        band_for_confidence(101)
    with pytest.raises(ValueError):
        band_for_confidence(-1)
