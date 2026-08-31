import json
from pathlib import Path
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest

from leaders_db.research.question_packet_chapter import (
    run_all_chapter_question_review,
    run_all_chapter_question_writing,
)

ROOT = Path.cwd()
PROFILES = ROOT / "configs/research-models.yaml"


def test_concurrent_runner_shares_atomic_failure_coordinator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arrived = Barrier(2)
    published = Barrier(2)
    coordinators = []

    def fake_chapter(**kwargs):
        coordinator = kwargs["call_coordinator"]
        chapter_id = kwargs["package"].chapter_id
        coordinators.append(coordinator)
        arrived.wait()
        if chapter_id == "1B":
            coordinator.publish_failure()
            published.wait()
            raise ValueError("material failure")
        published.wait()
        coordinator.authorize_launch()
        raise AssertionError("late model call was authorized")

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.run_chapter_question_writing",
        fake_chapter,
    )
    packages = (SimpleNamespace(chapter_id="1B"), SimpleNamespace(chapter_id="2B"))

    with pytest.raises(RuntimeError, match="material failure"):
        run_all_chapter_question_writing(
            project_root=ROOT,
            packages=packages,  # type: ignore[arg-type]
            output_root=tmp_path,
            approved_analysis_paths={"1B": tmp_path / "1", "2B": tmp_path / "2"},
            profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
            max_workers=2,
        )
    assert len(coordinators) == 2
    assert coordinators[0] is coordinators[1]


def test_concurrent_review_runner_blocks_launch_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arrived = Barrier(2)
    published = Barrier(2)
    coordinators = []

    def fake_review(**kwargs):
        coordinator = kwargs["call_coordinator"]
        chapter_id = kwargs["package"].chapter_id
        coordinators.append(coordinator)
        arrived.wait()
        if chapter_id == "1B":
            coordinator.publish_failure()
            published.wait()
            raise ValueError("review failure")
        published.wait()
        coordinator.authorize_launch()
        raise AssertionError("late review call was authorized")

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.run_chapter_question_review",
        fake_review,
    )
    packages = (SimpleNamespace(chapter_id="1B"), SimpleNamespace(chapter_id="2B"))
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_chapter_question_writing",
        lambda **kwargs: SimpleNamespace(chapter_id=kwargs["package"].chapter_id),
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.load_review_input_snapshot",
        lambda writing_dir, writing: SimpleNamespace(
            writing_dir=writing_dir,
            writing=writing,
            writing_manifest_sha256="0" * 64,
            answers={},
        ),
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.require_trusted_snapshot",
        lambda snapshot: None,
    )

    with pytest.raises(RuntimeError, match="review failure"):
        run_all_chapter_question_review(
            project_root=ROOT,
            packages=packages,  # type: ignore[arg-type]
            approved_analysis_paths={"1B": tmp_path / "1", "2B": tmp_path / "2"},
            writing_root=tmp_path / "writing",
            output_root=tmp_path / "review",
            profile_name="openai-sol-supervisor",
            writing_profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
            max_workers=2,
        )
    assert len(coordinators) == 2
    assert coordinators[0] is coordinators[1]


def test_integrated_writing_clamps_workers_to_safe_output_reservations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_root = tmp_path / "integrated"
    run_root.mkdir()
    (run_root / "preflight-manifest.json").write_text(
        json.dumps(
            {
                "status": "eligible",
                "config_sha256": "a" * 64,
                "maximum_calls_per_ruler": 250,
                "maximum_input_tokens_per_ruler": 40_000_000,
                "maximum_output_tokens_per_ruler": 1_000_000,
            }
        ),
        encoding="utf-8",
    )
    arrived = Barrier(7)
    lock = Lock()
    active = 0
    peak = 0
    started = 0

    def fake_chapter(**kwargs):
        nonlocal active, peak, started
        with lock:
            started += 1
            sequence = started
            active += 1
            peak = max(peak, active)
        if sequence <= 7:
            arrived.wait()
        with lock:
            active -= 1
        return kwargs["output_dir"] / "writing-manifest.json"

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.run_chapter_question_writing",
        fake_chapter,
    )
    packages = tuple(SimpleNamespace(chapter_id=f"{number}B") for number in range(1, 9))
    analyses = {package.chapter_id: tmp_path / package.chapter_id for package in packages}

    run_all_chapter_question_writing(
        project_root=ROOT,
        packages=packages,  # type: ignore[arg-type]
        output_root=run_root / "question-writing",
        approved_analysis_paths=analyses,
        profile_name="openai-luna-candidate",
        profiles_path=PROFILES,
        max_workers=8,
    )

    assert peak == 7
