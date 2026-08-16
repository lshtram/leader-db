from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from leaders_db.research.chapter_judge_models import RulerChapterJudgment
from leaders_db.research.chapter_judge_prompt import build_chapter_judge_prompt
from leaders_db.research.chapter_judge_worker import (
    _normalize_evidence_reference_lists,
    _normalize_judgment_envelope,
    _normalize_lens_lists,
    _write_null_recovery_queue,
)
from tests.research.test_chapter_judge_worker import _evaluation


def test_file_backed_prompt_rejects_outside_path_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projection = SimpleNamespace(
        job_key="dossier:test:2023:AAA:1",
        iso3="AAA",
        ruler_id="1",
        ruler_year_id=1,
        ruler_name="Ruler",
        period_start_year=2023,
        period_end_year=2023,
    )
    hashed = False

    def forbidden_hash(path: Path) -> str:
        nonlocal hashed
        hashed = True
        return "0" * 64

    monkeypatch.setattr(
        "leaders_db.research.chapter_judge_prompt._file_sha256", forbidden_hash
    )
    with pytest.raises(ValueError, match="chapter-inputs"):
        build_chapter_judge_prompt(
            {
                "job_key": "chapter-judge:test:2023:1B",
                "run_key": "test",
                "target_year": 2023,
                "input": {"chapter_id": "1B", "unavailable_dossiers": []},
            },
            project_root=tmp_path / "project",
            guide_text="guide",
            projections=((tmp_path / "outside.json", projection),),
            embed_projections=False,
        )
    assert not hashed


def test_normalize_lens_lists_preserves_supported_weak_overlap_as_note() -> None:
    evaluation = {
        "supported_lenses": ["4B.1", "4B.1", "4B.2"],
        "missing_or_weak_lenses": [
            "4B.2",
            "4B.2",
            "4B.3",
            "weak source diversity",
        ],
        "manual_review_reason": "Review sparse evidence.",
    }

    _normalize_lens_lists(
        evaluation, valid_methodology_ids={"4B.1", "4B.2", "4B.3"}
    )

    assert evaluation["supported_lenses"] == ["4B.1", "4B.2"]
    assert evaluation["missing_or_weak_lenses"] == ["4B.3"]
    assert "Partially supported but weak lenses: 4B.2" in evaluation[
        "manual_review_reason"
    ]
    assert evaluation["manual_review_reason"].count("4B.2") == 1
    assert "weak source diversity" in evaluation["manual_review_reason"]


def test_null_judgment_is_normalized_to_release_blocking_review() -> None:
    evaluation = {
        "score_1_to_10": None,
        "insufficient_evidence_reason": "Attribution remains insufficient.",
        "manual_review_required": False,
        "manual_review_reason_type": None,
        "manual_review_reason": None,
    }

    _normalize_judgment_envelope(evaluation)

    assert evaluation["manual_review_required"] is True
    assert evaluation["manual_review_reason_type"] == "recoverable_null"
    assert "Release is blocked" in evaluation["manual_review_reason"]
    assert evaluation["plausible_score_range"] == {"lower": 1, "upper": 10}


def test_normalize_lens_lists_recovers_descriptive_lens_prefixes() -> None:
    evaluation = {
        "supported_lenses": ["2B.1 defensive conduct"],
        "missing_or_weak_lenses": [
            "2B.4 civilian protection, proportionality, and attribution",
            "2B.10: durable end-state change",
        ],
    }

    _normalize_lens_lists(
        evaluation, valid_methodology_ids={"2B.1", "2B.4", "2B.10"}
    )

    assert evaluation["supported_lenses"] == ["2B.1"]
    assert evaluation["missing_or_weak_lenses"] == ["2B.4", "2B.10"]
    assert "civilian protection" in evaluation["manual_review_reason"]


def test_null_recovery_queue_reuses_existing_judgment_fields(tmp_path: Path) -> None:
    evaluation = SimpleNamespace(
        score_1_to_10=None,
        manual_review_reason_type="recoverable_null",
        dossier_job_key="dossier:test",
        iso3="NZL",
        ruler_year_id=12,
        ruler_name="Test Ruler",
        chapter_id="4B",
        insufficient_evidence_reason="Relevant conduct was not recovered.",
        missing_or_weak_lenses=("4B.2", "4B.6"),
        manual_review_reason="Research the ruler's response to constraints.",
    )
    batch = SimpleNamespace(
        job_key="chapter-judge:test:4B",
        chapter_id="4B",
        evaluations=(evaluation,),
    )
    projection = SimpleNamespace(job_key="dossier:test", evidence=(1, 2, 3))
    path = tmp_path / "null-recovery.json"

    _write_null_recovery_queue(batch, projections=((tmp_path, projection),), path=path)

    payload = json.loads(path.read_text())
    assert payload["request_count"] == 1
    assert payload["requests"][0] == {
        "chapter_id": "4B",
        "current_evidence_count": 3,
        "dossier_job_key": "dossier:test",
        "iso3": "NZL",
        "maximum_research_rounds": 1,
        "missing_or_weak_lenses": ["4B.2", "4B.6"],
        "next_action": "request_user_authorized_research_return",
        "reason": "Relevant conduct was not recovered.",
        "requested_follow_up": "Research the ruler's response to constraints.",
        "ruler_name": "Test Ruler",
        "ruler_year_id": 12,
        "runs_automatically": False,
    }


def test_normalize_evidence_references_drops_unknown_id_without_guessing() -> None:
    evaluation = {
        "decisive_positive_evidence": [
            {"evidence_id": "E001", "explanation": "Valid."},
            {"evidence_id": "E999", "explanation": "Unknown."},
        ],
        "decisive_negative_evidence": [],
        "contrary_evidence": [],
        "manual_review_required": False,
        "manual_review_reason_type": None,
        "manual_review_reason": None,
    }

    _normalize_evidence_reference_lists(evaluation, valid_evidence_ids={"E001"})

    assert evaluation["decisive_positive_evidence"] == [
        {"evidence_id": "E001", "explanation": "Valid."}
    ]
    assert evaluation["manual_review_required"] is True
    assert evaluation["manual_review_reason_type"] == "projection_integrity"
    assert "E999" in evaluation["manual_review_reason"]


def test_manual_review_requires_stable_reason_type() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["manual_review_required"] = True
    evaluation["manual_review_reason"] = "Attribution could move the score."

    with pytest.raises(ValueError, match="reason type"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["manual_review_reason_type"] = "material_attribution"
    judgment = RulerChapterJudgment.model_validate(evaluation)

    assert judgment.manual_review_reason_type == "material_attribution"


def test_numeric_judgment_requires_half_point_and_cannot_be_recoverable_null() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.2)

    with pytest.raises(ValueError, match=r"multiple of 0\.5"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["manual_review_required"] = True
    evaluation["manual_review_reason_type"] = "recoverable_null"
    evaluation["manual_review_reason"] = "More research may change the score."

    with pytest.raises(ValueError, match="cannot use recoverable_null"):
        RulerChapterJudgment.model_validate(evaluation)


def test_numeric_judgment_requires_traceable_decisive_evidence() -> None:
    evaluation = _evaluation(job_key="dossier", iso3="NZL", score=7.0)
    evaluation["decisive_positive_evidence"] = []
    evaluation["decisive_negative_evidence"] = []

    with pytest.raises(ValueError, match="requires decisive cited web evidence"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["decisive_local_evidence"] = [
        {
            "local_evidence_id": "LF001",
            "explanation": "Country-level structured context.",
            "harmless_extra_field": "accepted by the tolerant receiver",
        }
    ]
    with pytest.raises(ValueError, match="requires decisive cited web evidence"):
        RulerChapterJudgment.model_validate(evaluation)

    evaluation["score_1_to_10"] = None
    evaluation["insufficient_evidence_reason"] = "No discriminating evidence."
    evaluation["plausible_score_range"] = {"lower": 1, "upper": 10}
    judgment = RulerChapterJudgment.model_validate(evaluation)

    assert judgment.score_1_to_10 is None
