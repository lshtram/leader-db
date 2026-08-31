import json
from pathlib import Path

import pytest

from leaders_db.research.question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
)
from leaders_db.research.question_review_authorization import (
    load_question_review_authorization,
    run_authorized_question_reviews,
)

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "research/runs/five-ruler-2023-luna-sol-v8-release"


def _require_pre_execution_fixture(ruler_id: str, chapter_id: str) -> None:
    target = RUN / f"model-output/{ruler_id}/question-review/{chapter_id}"
    if target.exists() and any(target.iterdir()):
        pytest.skip("immutable local fixture has advanced beyond review preflight")


def _inputs(ruler_id: str):
    approved = json.loads(
        (
            ROOT
            / f"research/runs/2023-five-ruler-flow-test-v2/corpus/{ruler_id}"
            / "approved-ruler-package.json"
        ).read_text()
    )
    paths = {
        item["chapter_id"]: ROOT / item["analysis_path"]
        for item in approved["chapters"]
    }
    packages = tuple(
        ChapterQuestionEvidencePackage.model_validate_json(
            (
                RUN
                / f"rulers/{ruler_id}/question-packages/{number}B/package.json"
            ).read_bytes()
        )
        for number in range(1, 9)
    )
    return packages, paths


def _cohort_inputs():
    packages = {}
    analyses = {}
    for ruler_id in ("CHN", "ISR", "PRK", "RUS", "USA"):
        ruler_packages, paths = _inputs(ruler_id)
        for package in ruler_packages:
            key = (ruler_id, package.chapter_id)
            packages[key] = package
            analyses[key] = paths[package.chapter_id]
    return packages, analyses


def test_review_authorization_reconstructs_exact_inventory_and_rejects_other_order() -> None:
    _require_pre_execution_fixture("USA", "1B")
    packages, paths = _inputs("USA")
    cohort_packages, cohort_paths = _cohort_inputs()
    authorization = load_question_review_authorization(
        project_root=ROOT,
        run_dir=RUN,
        ruler_id="USA",
        packages=packages,
        approved_analysis_paths=paths,
        preflight_path=RUN / "preflight/question-review-v4/USA.json",
        cohort_preflight_path=RUN / "cohort-preflight.json",
        import_preflight_path=RUN / "preflight/question-phase-import.json",
        source_run=ROOT / "research/runs/five-ruler-2023-luna-sol-v7-release",
        cohort_packages=cohort_packages,
        cohort_approved_analysis_paths=cohort_paths,
        profile_name="openai-luna-candidate",
        writing_profile_name="openai-luna-candidate",
        reasoning_effort="high",
        approved_limits={
            "max_calls": 80,
            "max_input_tokens": 8_500_000,
            "max_output_tokens": 1_000_000,
        },
        profiles_path=ROOT / "configs/research-models.yaml",
        experiment_policy_path=(
            ROOT / "configs/research-question-review-experiment.yaml"
        ),
    )

    assert len(authorization.request_sha256s) == 80
    assert authorization.limits == {
        "maximum_calls": 80,
        "maximum_input_tokens": 8_500_000,
        "maximum_output_tokens": 1_000_000,
    }
    with pytest.raises(ValueError, match="ordered chapters"):
        run_authorized_question_reviews(
            authorization=authorization,
            project_root=ROOT,
            packages=tuple(reversed(packages)),
            approved_analysis_paths=paths,
        )


def test_review_authorization_accepts_exact_import_remainder_subset() -> None:
    _require_pre_execution_fixture("RUS", "8B")
    all_packages, paths = _inputs("RUS")
    cohort_packages, cohort_paths = _cohort_inputs()
    packages = (all_packages[-1],)
    authorization = load_question_review_authorization(
        project_root=ROOT,
        run_dir=RUN,
        ruler_id="RUS",
        packages=packages,
        approved_analysis_paths=paths,
        preflight_path=RUN / "preflight/question-review-v4/RUS.json",
        cohort_preflight_path=RUN / "cohort-preflight.json",
        import_preflight_path=RUN / "preflight/question-phase-import.json",
        source_run=ROOT / "research/runs/five-ruler-2023-luna-sol-v7-release",
        cohort_packages=cohort_packages,
        cohort_approved_analysis_paths=cohort_paths,
        profile_name="openai-luna-candidate",
        writing_profile_name="openai-luna-candidate",
        reasoning_effort="high",
        approved_limits={
            "max_calls": 10,
            "max_input_tokens": 1_500_000,
            "max_output_tokens": 125_000,
        },
        profiles_path=ROOT / "configs/research-models.yaml",
        experiment_policy_path=(
            ROOT / "configs/research-question-review-experiment.yaml"
        ),
    )

    assert authorization.chapter_ids == ("8B",)
    assert len(authorization.request_sha256s) == 10
