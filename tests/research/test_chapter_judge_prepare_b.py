from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.chapter_judge_worker import (
    _ensure_bias_assessment,
    _prepare_batch,
)
from leaders_db.research.dossier_models import RulerEvidenceDossier
from tests.research.test_chapter_judge_worker import (
    _dossier_payload,
    _fixture_dossier_job,
    _fixture_judge_job,
    _judge_candidate,
    _projections,
)


def test_prepare_batch_deduplicates_repeated_dossier_evaluation(tmp_path: Path) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_jobs = [
        _fixture_dossier_job(index=index, iso3=iso3, methodology_ids=methodology_ids)
        for index, iso3 in enumerate(("AAA", "BBB"), start=1)
    ]
    dossiers = tuple(
        (
            tmp_path / f"dossier-{index}.json",
            RulerEvidenceDossier.model_validate(
                _dossier_payload(job, methodology_ids=methodology_ids)
            ),
        )
        for index, job in enumerate(dossier_jobs, start=1)
    )
    candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    candidate["evaluations"].append(json.loads(json.dumps(candidate["evaluations"][0])))

    batch = _prepare_batch(
        candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
            methodology_ids=methodology_ids,
        ),
        dossiers=dossiers,
        projections=_projections(dossiers, chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert len(batch.evaluations) == 2

    null_duplicate_candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    first = null_duplicate_candidate["evaluations"][0]
    first["score_1_to_10"] = None
    first["insufficient_evidence_reason"] = "The admissible record is incomplete."
    first["plausible_score_range"] = {"lower": 1, "upper": 10}
    duplicate_null = json.loads(json.dumps(first))
    duplicate_null["insufficient_evidence_reason"] = (
        "The projection contains only contextual fragments."
    )
    null_duplicate_candidate["evaluations"].append(duplicate_null)

    batch = _prepare_batch(
        null_duplicate_candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
            methodology_ids=methodology_ids,
        ),
        dossiers=dossiers,
        projections=_projections(dossiers, chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert len(batch.evaluations) == 2
    assert "contextual fragments" in batch.evaluations[0].insufficient_evidence_reason

    conflicting = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    duplicate = json.loads(json.dumps(conflicting["evaluations"][0]))
    duplicate["score_1_to_10"] = 2
    conflicting["evaluations"].append(duplicate)
    with pytest.raises(ValueError, match="conflicting duplicate"):
        _prepare_batch(
            conflicting,
            job=_fixture_judge_job(
                dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
                methodology_ids=methodology_ids,
            ),
            dossiers=dossiers,
            projections=_projections(dossiers, chapter_id="4B"),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )

    placeholder_candidate = _judge_candidate(
        dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
        iso3s=("AAA", "BBB"),
    )
    placeholder = json.loads(json.dumps(placeholder_candidate["evaluations"][0]))
    placeholder["score_1_to_10"] = None
    placeholder["insufficient_evidence_reason"] = (
        "Duplicate placeholder not intended for processing."
    )
    placeholder_candidate["evaluations"].append(placeholder)

    batch = _prepare_batch(
        placeholder_candidate,
        job=_fixture_judge_job(
            dossier_job_keys=[str(job["job_key"]) for job in dossier_jobs],
            methodology_ids=methodology_ids,
        ),
        dossiers=dossiers,
        projections=_projections(dossiers, chapter_id="4B"),
        rubric_version="chapter_4b_v1",
        events_path=tmp_path / "events.jsonl",
    )

    assert len(batch.evaluations) == 2


def test_bias_assessment_drops_out_of_projection_references() -> None:
    evaluation = {
        "bias_assessment": {
            "material_biases": [
                {
                    "bias": "Reporting visibility",
                    "supporting_evidence_ids": ["E001", "E999"],
                    "likely_direction": "uncertain",
                    "interpretation_effect": "Confidence only.",
                }
            ]
        }
    }

    _ensure_bias_assessment(evaluation, valid_evidence_ids={"E001"})

    assert evaluation["bias_assessment"]["material_biases"][0]["supporting_evidence_ids"] == [
        "E001"
    ]

    missing_assessment: dict[str, object] = {}
    _ensure_bias_assessment(missing_assessment, valid_evidence_ids={"E001"})
    assert missing_assessment["bias_assessment"]["report_volume_not_used_as_severity"] is True
    assert missing_assessment["bias_assessment"]["no_blanket_regime_correction"] is True


def test_bias_assessment_remains_explicit_when_projection_has_no_evidence() -> None:
    evaluation = {}

    _ensure_bias_assessment(evaluation, valid_evidence_ids=set())

    assert evaluation["bias_assessment"]["material_biases"] == []
    assert evaluation["bias_assessment"]["report_volume_not_used_as_severity"] is True
    assert evaluation["bias_assessment"]["no_blanket_regime_correction"] is True


def test_prepare_batch_rejects_all_null_multi_ruler_result(tmp_path: Path) -> None:
    methodology_ids = tuple(f"4B.{index}" for index in range(1, 11))
    dossier_jobs = [
        _fixture_dossier_job(index=index, iso3=iso3, methodology_ids=methodology_ids)
        for index, iso3 in enumerate(("AAA", "BBB"), start=1)
    ]
    dossiers = tuple(
        (
            tmp_path / f"dossier-{index}.json",
            RulerEvidenceDossier.model_validate(
                _dossier_payload(job, methodology_ids=methodology_ids)
            ),
        )
        for index, job in enumerate(dossier_jobs, start=1)
    )
    dossier_keys = [str(job["job_key"]) for job in dossier_jobs]
    candidate = _judge_candidate(dossier_job_keys=dossier_keys, iso3s=("AAA", "BBB"))
    for evaluation in candidate["evaluations"]:
        evaluation["score_1_to_10"] = None
        evaluation["insufficient_evidence_reason"] = "Local inputs were inaccessible."
        evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}

    with pytest.raises(ValueError, match="all-null comparative batch"):
        _prepare_batch(
            candidate,
            job=_fixture_judge_job(dossier_job_keys=dossier_keys, methodology_ids=methodology_ids),
            dossiers=dossiers,
            projections=_projections(dossiers, chapter_id="4B"),
            rubric_version="chapter_4b_v1",
            events_path=tmp_path / "events.jsonl",
        )
