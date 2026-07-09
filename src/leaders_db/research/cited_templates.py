"""Template builders for cited manual/internet evaluation records."""

from __future__ import annotations

from typing import Any

from .cited_calibration import RUBRIC_VERSION_BY_METHODOLOGY_ID
from .registry import get_question_spec_by_methodology_id


def build_cited_evaluation_template(
    *,
    methodology_id: str,
    year: int,
    iso3: str,
    country_name: str,
    leader_name: str | None = None,
    period_label: str | None = None,
) -> dict[str, Any]:
    """Return a valid starter record for a cited/manual evaluation."""

    spec = get_question_spec_by_methodology_id(methodology_id)
    if spec is None or spec.evidence_strategy != "internet_manual":
        raise ValueError(f"unsupported cited methodology_id: {methodology_id!r}")
    rubric_version = RUBRIC_VERSION_BY_METHODOLOGY_ID.get(
        methodology_id,
        f"{methodology_id.lower().replace('.', '')}_v1",
    )
    return {
        "methodology_id": methodology_id,
        "year": year,
        "iso3": iso3.upper(),
        "country_name": country_name,
        "leader_name": leader_name,
        "leader_id": None,
        "leader_resolution": None,
        "period_start_year": None,
        "period_end_year": None,
        "period_label": period_label,
        "prompt_context": spec.text,
        "verdict": "insufficient_evidence",
        "evidence_quality": "manual_review_required",
        "confidence": "manual_review_required",
        "manual_review_reason": "Replace with the reason review is needed.",
        "score_1_to_10": None,
        "confidence_score": None,
        "claims": [
            {
                "claim": "Replace with a concise source-backed claim.",
                "support": "Replace with a short evidence summary.",
            }
        ],
        "answer_payload": {
            "calibration": _base_calibration_template(methodology_id, year, rubric_version)
            | _question_specific_calibration_template(methodology_id)
        },
        "candidate_structured_observation": {},
        "citations": [
            {
                "url": "https://example.test/source",
                "title": "Replace with source title",
                "quote": "Replace with a short supporting quote or excerpt.",
                "evidence_role": "citation",
                "source_confidence": "medium_high",
                "source_confidence_reason": (
                    "Replace with the registry-based confidence reason for this "
                    "source and claim type."
                ),
                "source_type": "media",
                "final_evidence_use": "final_evidence",
            }
        ],
        "caveats": [],
    }


def _base_calibration_template(
    methodology_id: str, year: int, rubric_version: str
) -> dict[str, Any]:
    return {
        "rubric_version": rubric_version,
        "calibration_batch_id": f"{methodology_id.lower().replace('.', '')}_{year}_batch",
        "calibrated_against": [
            "Replace with ruler / country / year labels judged in the same batch."
        ],
        "severity_band": "none",
        "state_responsibility": "unclear",
        "accountability_level": "partial",
        "information_environment": "unclear",
        "period_fit": "unclear",
        "source_mix": ["media"],
        "structured_prior_summary": "Replace with structured-source prior or not_available.",
        "contrary_evidence": [],
        "score_rationale": "Replace with why the score fits the rubric anchor.",
        "lower_anchor_rejected": "Replace with why one point lower is too harsh.",
        "higher_anchor_rejected": "Replace with why one point higher is too generous.",
        "visibility_bias_check": "Replace with how reporting volume was handled.",
        "repression_silence_check": "Replace with how missing evidence was handled.",
        "population_scale_check": "Replace with how scale/prevalence was handled.",
        "source_type_check": "Replace with source-mix limitations.",
        "recency_check": "Replace with target-period fit assessment.",
        "subagent_calibration_check": "Replace with comparison-batch check.",
    }


def _question_specific_calibration_template(methodology_id: str) -> dict[str, Any]:
    if methodology_id == "4B.1":
        return {
            "electoral_system_status": "unclear",
            "incumbent_acceptance_of_loss": "unclear",
            "contestability_constraints": ["none_found"],
        }
    if methodology_id == "4B.2":
        return {
            "manipulation_status": "unclear",
            "entrenchment_channels": ["unclear"],
            "institutional_remedy_status": "unclear",
        }
    if methodology_id == "4B.3":
        return {
            "tolerance_status": "unclear",
            "opposition_tolerance_channels": ["unclear"],
            "remedy_or_accountability_status": "unclear",
        }
    return {}


__all__ = ["build_cited_evaluation_template"]
