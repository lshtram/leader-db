import json
from pathlib import Path

import pytest

from leaders_db.research.question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
)
from leaders_db.research.question_phase_import import (
    apply_trusted_question_phase_imports,
    build_imported_writing_preflight,
    build_question_phase_import_preflight,
    load_imported_writing_authorization,
    run_authorized_imported_chapter_writing,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/runs/five-ruler-2023-luna-sol-v5-release"
TARGET = ROOT / "research/runs/five-ruler-2023-luna-sol-v7-release"


def _require_pre_execution_fixture() -> None:
    target = TARGET / "model-output/PRK/question-writing/7B"
    if target.exists() and any(target.iterdir()):
        pytest.skip("immutable local fixture has advanced beyond writing preflight")


def _inputs() -> tuple[
    dict[tuple[str, str], ChapterQuestionEvidencePackage],
    dict[tuple[str, str], Path],
]:
    packages = {}
    analyses = {}
    for ruler_id in ("CHN", "ISR", "PRK", "RUS", "USA"):
        approved = json.loads(
            (
                ROOT
                / f"research/runs/2023-five-ruler-flow-test-v2/corpus/{ruler_id}"
                / "approved-ruler-package.json"
            ).read_text()
        )
        by_chapter = {
            item["chapter_id"]: ROOT / item["analysis_path"]
            for item in approved["chapters"]
        }
        for number in range(1, 9):
            chapter_id = f"{number}B"
            package_path = (
                TARGET / f"rulers/{ruler_id}/question-packages/{chapter_id}/package.json"
            )
            packages[(ruler_id, chapter_id)] = (
                ChapterQuestionEvidencePackage.model_validate_json(
                    package_path.read_bytes()
                )
            )
            analyses[(ruler_id, chapter_id)] = by_chapter[chapter_id]
    return packages, analyses


def test_import_preflight_reuses_only_complete_trusted_chapters(tmp_path: Path) -> None:
    packages, analyses = _inputs()
    output = tmp_path / "import.json"
    common = dict(
        project_root=ROOT,
        source_run=SOURCE,
        target_run=TARGET,
        packages=packages,
        approved_analysis_paths=analyses,
        profile_name="openai-luna-candidate",
        writing_profile_name="openai-luna-candidate",
        profiles_path=ROOT / "configs/research-models.yaml",
        experiment_policy_path=(
            ROOT / "configs/research-question-review-experiment.yaml"
        ),
    )
    build_question_phase_import_preflight(**common, output_path=output)
    manifest = json.loads(output.read_text())

    assert manifest["imported_writing_chapters"] == 39
    assert manifest["writing_calls_to_execute"] == 10
    assert manifest["imported_review_chapters"] == 16
    assert manifest["review_calls_to_execute"] == 240
    changed = next(
        item
        for item in manifest["rows"]
        if item["ruler_id"] == "PRK" and item["chapter_id"] == "7B"
    )
    assert (changed["writing_action"], changed["review_action"]) == (
        "execute",
        "execute",
    )

    manifest["rows"][0]["writing_source_tree_sha256"] = "0" * 64
    output.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="differs from trusted reconstruction"):
        apply_trusted_question_phase_imports(**common, preflight_path=output)


def test_imported_writing_preflight_measures_only_changed_chapter(
    tmp_path: Path,
) -> None:
    _require_pre_execution_fixture()
    packages, analyses = _inputs()
    output = build_imported_writing_preflight(
        project_root=ROOT,
        import_preflight_path=TARGET / "preflight/question-phase-import.json",
        cohort_preflight_path=TARGET / "cohort-preflight.json",
        source_run=SOURCE,
        target_run=TARGET,
        packages=packages,
        approved_analysis_paths=analyses,
        profile_name="openai-luna-candidate",
        writing_profile_name="openai-luna-candidate",
        profiles_path=ROOT / "configs/research-models.yaml",
        experiment_policy_path=(
            ROOT / "configs/research-question-review-experiment.yaml"
        ),
        maximum_input_tokens=700_000,
        output_path=tmp_path / "writing.json",
    )
    manifest = json.loads(output.read_text())

    assert manifest["status"] == "eligible"
    assert manifest["planned_calls"] == 10
    assert manifest["planned_input_tokens"] == 345_516
    assert manifest["limits"] == {
        "maximum_calls": 10,
        "maximum_input_tokens": 700_000,
        "maximum_output_tokens": 125_000,
    }
    assert {
        (item["iso3"], item["chapter_id"]) for item in manifest["requests"]
    } == {("PRK", "7B")}


def test_imported_writing_executor_requires_exact_authorized_chapter() -> None:
    _require_pre_execution_fixture()
    packages, analyses = _inputs()
    common = dict(
        project_root=ROOT,
        import_preflight_path=TARGET / "preflight/question-phase-import.json",
        cohort_preflight_path=TARGET / "cohort-preflight.json",
        source_run=SOURCE,
        target_run=TARGET,
        packages=packages,
        approved_analysis_paths=analyses,
        profile_name="openai-luna-candidate",
        writing_profile_name="openai-luna-candidate",
        profiles_path=ROOT / "configs/research-models.yaml",
        experiment_policy_path=(
            ROOT / "configs/research-question-review-experiment.yaml"
        ),
    )
    authorization = load_imported_writing_authorization(
        **common,
        writing_preflight_path=TARGET / "preflight/imported-writing-v2.json",
    )

    assert len(authorization.request_sha256s) == 10
    with pytest.raises(ValueError, match="absent from the imported writing"):
        run_authorized_imported_chapter_writing(
            authorization=authorization,
            project_root=ROOT,
            ruler_id="CHN",
            package=packages[("CHN", "1B")],
            approved_analysis_path=analyses[("CHN", "1B")],
            output_root=TARGET / "model-output/CHN/question-writing",
        )
