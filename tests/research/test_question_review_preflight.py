from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from leaders_db.research.question_packet_chapter import run_all_chapter_question_review
from leaders_db.research.question_packet_chapter_models import (
    ChapterQuestionArtifact,
    ChapterQuestionPhaseManifest,
    QuestionReviewReopenStopManifest,
)
from leaders_db.research.question_packet_writer import (
    DiagnosticQuestionAnswer,
    EvidenceReopenRequest,
)
from leaders_db.research.question_review_preflight import (
    QuestionReviewInputSnapshot,
    load_review_input_snapshot,
    require_trusted_snapshot,
)


def _writing_phase(root: Path, chapter_id: str, *, reopen: bool) -> ChapterQuestionPhaseManifest:
    artifacts = []
    for number in range(1, 11):
        question_id = f"{chapter_id}.{number}"
        answer = DiagnosticQuestionAnswer(
            question_id=question_id,
            answer="A complete synthetic answer for the review preflight boundary.",
            evidence_dispositions=(),
            reopen_requests=(
                (
                    EvidenceReopenRequest(
                        evidence_id="E-REOPEN",
                        reason="This candidate may materially change the final answer.",
                    ),
                )
                if reopen and number == 1
                else ()
            ),
        )
        path = root / chapter_id / "questions" / question_id / "output.json"
        path.parent.mkdir(parents=True)
        path.write_text(answer.model_dump_json())
        artifacts.append(
            ChapterQuestionArtifact(
                question_id=question_id,
                artifact_path=str(path.relative_to(root / chapter_id)),
                artifact_sha256=sha256(path.read_bytes()).hexdigest(),
                status="pass",
            )
        )
    manifest = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_writing_v1",
        chapter_id=chapter_id,
        profile="openai-luna-candidate",
        model="gpt-5.6-luna",
        package_sha256="0" * 64,
        profile_config_sha256="1" * 64,
        prompt_config_sha256="2" * 64,
        question_count=10,
        artifacts=tuple(artifacts),
        phase_gate="pass",
    )
    (root / chapter_id / "writing-manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n"
    )
    return manifest


def test_full_scope_reopen_preflight_stops_every_review_worker(
    monkeypatch, tmp_path: Path
) -> None:
    writing_root = tmp_path / "writing"
    phases = {
        "4B": _writing_phase(writing_root, "4B", reopen=False),
        "5B": _writing_phase(writing_root, "5B", reopen=True),
    }
    packages = tuple(SimpleNamespace(chapter_id=chapter_id) for chapter_id in phases)
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.resolve_integrated_run_budget",
        lambda output_root, tracker: None,
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_chapter_question_writing",
        lambda **kwargs: phases[kwargs["package"].chapter_id],
    )
    called = False

    def forbidden_review(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.run_chapter_question_review",
        forbidden_review,
    )
    output_root = tmp_path / "review"
    with pytest.raises(RuntimeError, match="stopped before model calls"):
        run_all_chapter_question_review(
            project_root=Path.cwd(),
            packages=packages,
            approved_analysis_paths={
                chapter_id: tmp_path / f"{chapter_id}.json" for chapter_id in phases
            },
            writing_root=writing_root,
            output_root=output_root,
            profile_name="openai-luna-candidate",
            writing_profile_name="openai-luna-candidate",
            profiles_path=Path("configs/research-models.yaml"),
        )
    assert not called
    stop = QuestionReviewReopenStopManifest.model_validate_json(
        (output_root / "reopen-stop.json").read_text()
    )
    assert stop.review_calls_launched == 0
    assert tuple(stop.writing_manifest_sha256s) == ("4B", "5B")
    assert [(item.question_id, item.evidence_ids) for item in stop.unresolved] == [
        ("5B.1", ("E-REOPEN",))
    ]


def test_forged_review_snapshot_is_rejected(tmp_path: Path) -> None:
    writing_root = tmp_path / "writing"
    writing = _writing_phase(writing_root, "4B", reopen=False)
    forged = QuestionReviewInputSnapshot(
        writing_dir=writing_root / "4B",
        _writing_bytes=writing.model_dump_json().encode(),
        writing_manifest_sha256="0" * 64,
        _answer_bytes={},
        _capability=object(),
    )
    with pytest.raises(ValueError, match="trusted loader"):
        require_trusted_snapshot(forged)


def test_trusted_snapshot_payload_cannot_be_mutated(tmp_path: Path) -> None:
    writing_root = tmp_path / "writing"
    writing = _writing_phase(writing_root, "4B", reopen=True)
    snapshot = load_review_input_snapshot(writing_root / "4B", writing)

    mutable_answer = snapshot.answers["4B.1"]
    mutable_answer.reopen_requests = ()
    mutable_writing = snapshot.writing
    mutable_writing.chapter_id = "FORGED"

    assert snapshot.answers["4B.1"].reopen_requests[0].evidence_id == "E-REOPEN"
    assert snapshot.writing.chapter_id == "4B"
