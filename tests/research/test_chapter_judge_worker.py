from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from leaders_db.research.chapter_judge_worker import (
    _find_previous_chapter_candidate,
    _write_chapter_projections,
)
from leaders_db.research.chapter_projection import build_ruler_chapter_projection
from leaders_db.research.dossier_models import RulerEvidenceDossier


def _projections(
    dossiers: tuple[tuple[Path, RulerEvidenceDossier], ...], *, chapter_id: str
) -> tuple:
    return tuple(
        (
            path.with_suffix(".projection.json"),
            build_ruler_chapter_projection(
                dossier,
                chapter_id=chapter_id,
                source_dossier_path=Path(path.name),
                source_dossier_sha256="a" * 64,
            ),
        )
        for path, dossier in dossiers
    )


def test_worker_cannot_fall_back_when_approved_corpus_is_required(
    tmp_path: Path,
) -> None:
    job = _fixture_dossier_job(
        index=1,
        iso3="TST",
        methodology_ids=tuple(f"4B.{i}" for i in range(1, 11)),
    )
    dossier_path = tmp_path / "dossier.json"
    dossier = RulerEvidenceDossier.model_validate(
        _dossier_payload(job, methodology_ids=tuple(f"4B.{i}" for i in range(1, 11)))
    )
    dossier_path.write_text(dossier.model_dump_json(), encoding="utf-8")
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()

    with pytest.raises(ValueError, match="approved corpus package missing"):
        _write_chapter_projections(
            ((dossier_path, dossier),),
            chapter_id="4B",
            attempt_dir=attempt_dir,
            project_root=tmp_path,
            require_approved_corpus=True,
        )


def test_worker_rejects_approved_manifest_changed_after_planning(tmp_path: Path) -> None:
    methodology_ids = tuple(f"4B.{i}" for i in range(1, 11))
    job = _fixture_dossier_job(index=1, iso3="TST", methodology_ids=methodology_ids)
    dossier_path = tmp_path / "dossier.json"
    dossier = RulerEvidenceDossier.model_validate(
        _dossier_payload(job, methodology_ids=methodology_ids)
    )
    dossier_path.write_text(dossier.model_dump_json(), encoding="utf-8")
    manifest_path = tmp_path / "approved.json"
    manifest_path.write_text("planned", encoding="utf-8")
    planned_hash = sha256(manifest_path.read_bytes()).hexdigest()
    manifest_path.write_text("changed", encoding="utf-8")
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()

    with pytest.raises(ValueError, match="changed after planning"):
        _write_chapter_projections(
            ((dossier_path, dossier),),
            chapter_id="4B",
            attempt_dir=attempt_dir,
            project_root=tmp_path,
            approved_packages={
                dossier.job_key: {
                    "path": str(manifest_path),
                    "sha256": planned_hash,
                }
            },
            require_approved_corpus=True,
        )


def test_previous_policy_approved_chapter_result_is_reusable(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    prior = job_dir / "attempts/001-old"
    current = job_dir / "attempts/002-current"
    prior.mkdir(parents=True)
    current.mkdir(parents=True)
    payload = {"evaluations": [{"dossier_job_key": "dossier:test"}]}
    (prior / "chapter-judgment.orphaned.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    (prior / "judge-complete.marker").write_text("complete\n", encoding="utf-8")

    assert _find_previous_chapter_candidate(job_dir, attempt_dir=current) == payload


def _dossier_payload(
    job: dict[str, object], *, methodology_ids: tuple[str, ...]
) -> dict[str, object]:
    evidence = {
        "evidence_id": "E001",
        "claim": "A cited political-freedom fact.",
        "url": "https://example.test/source",
        "title": "Source",
        "publisher": "Publisher",
        "publication_date": "2020-01-01",
        "excerpt": "A relevant excerpt.",
        "source_type": "official",
        "source_confidence": "medium",
        "source_confidence_reason": "Dated primary record.",
        "final_evidence_use": "final_evidence",
        "period_fit": "target_year",
        "ruler_attribution": "Direct ruler-period action.",
        "contrary_evidence": [],
    }
    return {
        "schema_version": "ruler_evidence_dossier_v2",
        "job_key": job["job_key"],
        "run_key": job["run_key"],
        "iso3": job["iso3"],
        "country_name": job["country_name"],
        "ruler_id": job["ruler_id"],
        "ruler_year_id": job["input"]["ruler_year_id"],
        "ruler_name": job["ruler_name"],
        "period_start_year": 2020,
        "period_end_year": 2020,
        "methodology_ids": list(methodology_ids),
        "evidence": [evidence],
        "mappings": [
            {
                "evidence_id": "E001",
                "methodology_id": methodology_id,
                "relation": "context",
                "relevance": "Relevant to the chapter.",
            }
            for methodology_id in methodology_ids
        ],
        "coverage": [
            {
                "methodology_id": methodology_id,
                "status": "partially_covered",
                "evidence_ids": ["E001"],
                "reason": "Fixture evidence.",
            }
            for methodology_id in methodology_ids
        ],
        "unresolved_gaps": [],
        "completed_queries": [],
        "normalization_warnings": [],
        "local_priors": [
            {
                "methodology_id": methodology_id,
                "status": "evidence_found",
                "summary": "Fixture prior.",
                "artifact_path": "tmp/prior.json",
                "artifact_sha256": "0" * 64,
            }
            for methodology_id in methodology_ids
        ],
        "evidence_environment": _evidence_environment(),
        "run_profile": {
            "provider_profile": "fixture",
            "provider": "openai",
            "model": "gpt-fixture",
            "local_evidence_calls": [],
            "searches_attempted": [],
            "sources_visited": [],
            "discovery_search_id": "fixture",
            "source_mix_note": "Fixture source mix.",
            "usage": _unknown_usage(),
        },
    }


def _fixture_dossier_job(
    *, index: int, iso3: str, methodology_ids: tuple[str, ...]
) -> dict[str, object]:
    return {
        "job_key": f"dossier:fixture:2020:{iso3}:{index}",
        "run_key": "fixture-batch",
        "iso3": iso3,
        "country_name": f"Country {iso3}",
        "ruler_id": str(index),
        "ruler_name": f"Ruler {index}",
        "period_start_year": 2020,
        "period_end_year": 2020,
        "input": {
            "ruler_year_id": 100 + index,
            "question_ids": list(methodology_ids),
        },
    }


def _fixture_judge_job(
    *, dossier_job_keys: list[str], methodology_ids: tuple[str, ...]
) -> dict[str, object]:
    return {
        "job_key": "chapter-judge:fixture-batch:2020:4B",
        "run_key": "fixture-batch",
        "job_type": "question_judge",
        "status": "claimed",
        "target_year": 2020,
        "provider_profile": "fixture",
        "provider": "openai",
        "model": "gpt-fixture",
        "input": {
            "chapter_id": "4B",
            "rubric_version": "chapter_4b_v1",
            "methodology_ids": list(methodology_ids),
            "dossier_job_keys": dossier_job_keys,
            "unavailable_dossiers": [],
        },
    }


def _judge_candidate(
    *, dossier_job_keys: list[str], iso3s: tuple[str, ...]
) -> dict[str, object]:
    evaluations = [
            _evaluation(job_key=job_key, iso3=iso3, score=4.0 + index * 3)
            for index, (job_key, iso3) in enumerate(
                zip(dossier_job_keys, iso3s, strict=True)
            )
        ]
    for index, evaluation in enumerate(evaluations):
        evaluation["calibrated_against"] = [dossier_job_keys[1 - index]]
    return {
        "evaluations": evaluations,
        "batch_notes": ["Compared the two fixture rulers using common anchors."],
        "run_profile": {"usage": _unknown_usage()},
    }


def _evaluation(*, job_key: str, iso3: str, score: float) -> dict[str, object]:
    return {
        "dossier_job_key": job_key,
        "iso3": iso3,
        "ruler_id": "model-value-overwritten",
        "ruler_year_id": -1,
        "ruler_name": "model-value-overwritten",
        "period_start_year": 2020,
        "period_end_year": 2020,
        "chapter_id": "4B",
        "rubric_version": "chapter_4b_v1",
        "calibration_batch_id": "batch",
        "calibrated_against": [key for key in (job_key,)],
        "score_1_to_10": score,
        "insufficient_evidence_reason": None,
        "confidence_score": 65,
        "plausible_score_range": {"lower": score - 1, "upper": score + 1},
        "decisive_positive_evidence": [
            {"evidence_id": "E001", "explanation": "Positive fixture evidence."}
        ],
        "decisive_negative_evidence": [],
        "decisive_local_evidence": [],
        "contextual_local_evidence": [],
        "inherited_baseline_and_constraints": "Inherited fixture conditions.",
        "ruler_attribution": "Attributable within the fixture period.",
        "supported_lenses": ["4B.1"],
        "missing_or_weak_lenses": ["4B.2"],
        "contrary_evidence": [],
        "source_mix": "One fixture primary source.",
        "structured_prior_summary": "Fixture prior summary.",
        "bias_assessment": _bias_assessment(),
        "chapter_rationale": "Fits the selected comparative anchor.",
        "lower_anchor_rejected": "Too harsh for the documented record.",
        "higher_anchor_rejected": "Too generous given the evidence gap.",
        "manual_review_required": False,
        "manual_review_reason_type": None,
        "manual_review_reason": None,
        "chapter_specific": [
            {"field": "trajectory", "value": "Stable fixture trajectory."}
        ],
    }


def _batch_for_store(*, job_key: str):
    from leaders_db.research.chapter_judge_models import ChapterJudgmentBatch

    payload = {
        "schema_version": "ruler_chapter_judgment_v1",
        "job_key": job_key,
        "run_key": "expired",
        "chapter_id": "4B",
        "target_year": 2020,
        "rubric_version": "chapter_4b_v1",
        "calibration_batch_id": job_key,
        "evaluations": [_evaluation(job_key="dossier:fixture", iso3="AAA", score=5)],
        "unavailable_dossiers": [],
        "batch_notes": [],
        "run_profile": {
            "provider_profile": "fixture",
            "provider": "openai",
            "model": "fixture",
            "dossier_count": 1,
            "unavailable_dossier_count": 0,
            "usage": _unknown_usage(),
        },
    }
    payload["evaluations"][0]["calibration_batch_id"] = job_key
    return ChapterJudgmentBatch.model_validate(payload)


def _unknown_usage() -> dict[str, str]:
    return {
        "input_tokens": "unknown_not_exposed_by_tool",
        "output_tokens": "unknown_not_exposed_by_tool",
        "total_tokens": "unknown_not_exposed_by_tool",
        "estimated_cost_usd": "unknown_not_exposed_by_tool",
    }


def _assert_tolerant_bias_persistence(completed: dict[str, object], batch: object) -> None:
    assert completed["status"] == "completed"
    assert batch.run_profile.usage.total_tokens == 1500
    assert all(item.confidence_score == 50 for item in batch.evaluations)
    assert all(
        item.bias_assessment.report_volume_not_used_as_severity
        for item in batch.evaluations
    )


def _evidence_environment() -> dict[str, object]:
    return {
        "criticism_possible": "Criticism was possible but the fixture record is thin.",
        "censorship_and_self_censorship": "No censorship conclusion beyond E001.",
        "safe_reporting_channels": "Formal reporting channels existed in the fixture.",
        "official_statistics_reliability": "No statistics are used in this fixture.",
        "languages_and_archives_searched": ["English fixture archive"],
        "source_concentration": "The record is concentrated in one official source.",
        "duplicate_event_risk": "Only one underlying fact is present.",
        "complaint_volume_interpretation": "Volume is not treated as conduct severity.",
        "relevant_denominators": "Population and exposure are not measured here.",
        "inherited_conditions_shocks_and_authority": "Authority is direct in the fixture.",
        "chapter_specific_biases": ["Official-source concentration"],
        "supporting_evidence_ids": ["E001"],
    }


def _bias_assessment() -> dict[str, object]:
    return {
        "material_biases": [
            {
                "bias": "Official-source concentration",
                "supporting_evidence_ids": ["E001"],
                "likely_direction": "favors_ruler",
                "interpretation_effect": "The official claim receives limited weight.",
            }
        ],
        "confidence_and_range_effect": "Confidence is lower and the range is wider.",
        "remaining_uncertainty": "Independent corroboration remains absent.",
        "report_volume_not_used_as_severity": True,
        "no_blanket_regime_correction": True,
    }
