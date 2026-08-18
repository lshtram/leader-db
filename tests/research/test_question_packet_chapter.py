import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from leaders_db.research.chapter_analysis_models import ResolvedChapterAnalysis
from leaders_db.research.question_packet_chapter import (
    ChapterQuestionPhaseManifest,
    _inside,
    run_chapter_question_review,
    run_chapter_question_writing,
    validate_chapter_question_review,
    validate_chapter_question_writing,
)
from leaders_db.research.question_packet_chapter_models import QuestionReviewReopenStopManifest
from leaders_db.research.question_packet_prompts import load_question_packet_prompts
from leaders_db.research.question_packet_writer import (
    DiagnosticQuestionAnswer,
    EvidenceReopenRequest,
)
from leaders_db.research.question_packet_writer_prompt import project_predecessor_answer
from tests.research.test_single_pass_chapter_analysis import _result

ROOT = Path.cwd()
PROFILES = ROOT / "configs/research-models.yaml"


def _package(analysis_hash: str = "0" * 64):
    packets = tuple(
        SimpleNamespace(
            question_id=f"4B.{number}",
            coverage=SimpleNamespace(required_evidence_ids=()),
            model_dump=lambda mode="json", number=number: {"number": number},
        )
        for number in range(1, 11)
    )
    return SimpleNamespace(
        chapter_id="4B",
        packets=packets,
        selected_analysis_sha256=analysis_hash,
        model_dump=lambda mode="json": {"chapter_id": "4B", "analysis": analysis_hash},
    )


def _answer(question_id: str) -> DiagnosticQuestionAnswer:
    return DiagnosticQuestionAnswer(
        question_id=question_id,
        answer="A sufficiently detailed evidence answer for the requested question.",
        evidence_dispositions=(),
    )


def _write_request_manifest(output_dir: Path, packet, predecessor: dict) -> None:
    prompts, prompt_hash = load_question_packet_prompts(
        ROOT / "configs/question-packet-prompts.yaml"
    )
    projected, excluded = project_predecessor_answer(packet, predecessor)
    (output_dir / "request-manifest.json").write_text(
        json.dumps(
            {
                "prompt_config_version": prompts.version,
                "prompt_config_sha256": prompt_hash,
                "predecessor_answer_included": bool(projected),
                "predecessor_excluded_evidence_ids": list(excluded),
            }
        )
    )


def _analysis_path(tmp_path: Path) -> Path:
    path = tmp_path / "analysis.json"
    base = _result()
    analysis = ResolvedChapterAnalysis(
        chapter_id="4B",
        answers=tuple(
            answer.model_copy(update={"question_id": f"4B.{number}"})
            for number, answer in enumerate(base.corrected_answers, start=1)
        ),
        evidence=(),
        omitted_candidate_ids=(),
        draft=base.draft.model_copy(update={"chapter_id": "4B"}),
        critique=base.critique.model_copy(update={"chapter_id": "4B"}),
    )
    path.write_text(analysis.model_dump_json())
    return path


def test_chapter_writing_calls_each_question_once(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_writer(**kwargs):
        packet = kwargs["packet"]
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True)
        answer = _answer(packet.question_id)
        (output_dir / "output.json").write_text(answer.model_dump_json())
        (output_dir / "prompt.txt").write_text("prompt")
        calls.append(packet.question_id)
        return answer, {"functional_gate": "pass"}

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        fake_writer,
    )
    output_dir = tmp_path / "writing"
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    path = run_chapter_question_writing(
        project_root=ROOT,
        package=package,
        output_dir=output_dir,
        approved_analysis_path=analysis_path,
        profile_name="openai-terra-candidate",
        profiles_path=PROFILES,
    )
    manifest = ChapterQuestionPhaseManifest.model_validate_json(path.read_text())

    assert calls == [f"4B.{number}" for number in range(1, 11)]
    assert manifest.question_count == 10
    assert manifest.phase_gate == "pass"
    with pytest.raises(ValueError, match="already in use"):
        run_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=output_dir,
            approved_analysis_path=analysis_path,
            profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )

    tampered = manifest.model_copy(update={"package_sha256": "1" * 64})
    path.write_text(tampered.model_dump_json())
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_question_answer",
        lambda packet, answer: {"functional_gate": "pass"},
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.build_question_writer_prompt",
        lambda packet, prompts, predecessor: "prompt",
    )
    with pytest.raises(ValueError, match="does not match current inputs"):
        validate_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=output_dir,
            approved_analysis_path=analysis_path,
            profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )


def test_chapter_artifact_path_cannot_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    root = tmp_path / "phase"
    root.mkdir()

    with pytest.raises(ValueError, match="escapes"):
        _inside(root, "../outside.json")


def test_chapter_phase_rejects_non_codex_profile_before_calls(monkeypatch, tmp_path: Path) -> None:
    profiles = yaml.safe_load(PROFILES.read_text())
    profiles["profiles"]["api-test"] = {
        **profiles["profiles"]["openai-terra-candidate"],
        "execution_surface": "api",
    }
    path = tmp_path / "profiles.yaml"
    path.write_text(yaml.safe_dump(profiles))
    called = False

    def fake_writer(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        fake_writer,
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="Codex subscription"):
        run_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=tmp_path / "writing",
            approved_analysis_path=analysis_path,
            profile_name="api-test",
            profiles_path=path,
        )
    assert not called


def test_chapter_writing_stops_after_first_failure(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def failing_writer(**kwargs):
        calls.append(kwargs["packet"].question_id)
        raise ValueError("invalid first answer")

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        failing_writer,
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="invalid first answer"):
        run_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=tmp_path / "writing",
            approved_analysis_path=analysis_path,
            profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )
    assert calls == ["4B.1"]


def test_chapter_review_is_separate_and_rejects_changed_writer_output(
    monkeypatch, tmp_path: Path
) -> None:
    writing_dir = tmp_path / "writing"

    def fake_writer(**kwargs):
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True)
        _write_request_manifest(output_dir, kwargs["packet"], kwargs["predecessor_answer"])
        answer = _answer(kwargs["packet"].question_id)
        (output_dir / "output.json").write_text(answer.model_dump_json())
        (output_dir / "prompt.txt").write_text("prompt")
        return answer, {"functional_gate": "pass"}

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        fake_writer,
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_question_answer",
        lambda packet, answer: {"functional_gate": "pass"},
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.build_question_writer_prompt",
        lambda packet, prompts, predecessor: "prompt",
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    run_chapter_question_writing(
        project_root=ROOT,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=analysis_path,
        profile_name="openai-terra-candidate",
        profiles_path=PROFILES,
    )
    request_path = writing_dir / "questions/4B.1/request-manifest.json"
    request = json.loads(request_path.read_text())
    request_path.write_text(
        json.dumps(
            {
                **request,
                "predecessor_answer_included": not request[
                    "predecessor_answer_included"
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="predecessor projection metadata"):
        validate_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=writing_dir,
            approved_analysis_path=analysis_path,
            profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )
    request_path.write_text(json.dumps(request))
    first = writing_dir / "questions/4B.1/output.json"
    first.write_text(json.dumps({"tampered": True}))
    with pytest.raises(ValueError):
        run_chapter_question_review(
            project_root=ROOT,
            package=package,
            approved_analysis_path=analysis_path,
            writing_dir=writing_dir,
            output_dir=tmp_path / "review",
            profile_name="openai-sol-supervisor",
            writing_profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )


def test_chapter_review_calls_each_question_once(monkeypatch, tmp_path: Path) -> None:
    writing_dir = tmp_path / "writing"

    def fake_writer(**kwargs):
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True)
        _write_request_manifest(output_dir, kwargs["packet"], kwargs["predecessor_answer"])
        answer = _answer(kwargs["packet"].question_id)
        (output_dir / "output.json").write_text(answer.model_dump_json())
        (output_dir / "prompt.txt").write_text("prompt")
        return answer, {"functional_gate": "pass"}

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        fake_writer,
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_question_answer",
        lambda packet, answer: {"functional_gate": "pass"},
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.build_question_writer_prompt",
        lambda packet, prompts, predecessor: "prompt",
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    run_chapter_question_writing(
        project_root=ROOT,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=analysis_path,
        profile_name="openai-terra-candidate",
        profiles_path=PROFILES,
    )
    calls = []

    def fake_review(**kwargs):
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True)
        (output_dir / "blind-review-manifest.json").write_text("{}")
        calls.append(kwargs["packet"].question_id)
        return output_dir / "blind-review-manifest.json"

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.run_blind_question_quality_review",
        fake_review,
    )

    def fake_validate(**kwargs):
        payload = json.loads((kwargs["output_dir"] / "blind-review-manifest.json").read_text())
        if payload != {}:
            raise ValueError("child review tampered")
        return {"quality_gate": "pass"}

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_blind_review_artifacts",
        fake_validate,
    )
    path = run_chapter_question_review(
        project_root=ROOT,
        package=package,
        approved_analysis_path=analysis_path,
        writing_dir=writing_dir,
        output_dir=tmp_path / "review",
        profile_name="openai-sol-supervisor",
        writing_profile_name="openai-terra-candidate",
        profiles_path=PROFILES,
    )
    manifest = ChapterQuestionPhaseManifest.model_validate_json(path.read_text())

    assert calls == [f"4B.{number}" for number in range(1, 11)]
    assert manifest.phase_gate == "pass"
    arguments = {
        "project_root": ROOT,
        "package": package,
        "approved_analysis_path": analysis_path,
        "writing_dir": writing_dir,
        "output_dir": tmp_path / "review",
        "profile_name": "openai-sol-supervisor",
        "writing_profile_name": "openai-terra-candidate",
        "profiles_path": PROFILES,
    }
    assert validate_chapter_question_review(**arguments) == manifest

    manifest_path = tmp_path / "review/review-manifest.json"
    tampered = manifest.model_copy(update={"phase_gate": "fail"})
    with pytest.raises(ValueError):
        manifest_path.write_text(tampered.model_dump_json())
        validate_chapter_question_review(**arguments)
    manifest_path.write_text(manifest.model_dump_json())
    (tmp_path / "review/questions/4B.1/blind-review-manifest.json").write_text('{"tampered": true}')
    with pytest.raises(ValueError, match="child review tampered"):
        validate_chapter_question_review(**arguments)


def test_review_rejects_wrong_approved_analysis_hash(monkeypatch, tmp_path: Path) -> None:
    analysis_path = _analysis_path(tmp_path)
    package = _package("0" * 64)
    writing = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_writing_v1",
        chapter_id="4B",
        profile="openai-terra-candidate",
        model="gpt-5.6-terra",
        package_sha256="0" * 64,
        profile_config_sha256="0" * 64,
        prompt_config_sha256="0" * 64,
        question_count=10,
        artifacts=tuple(
            {
                "question_id": f"4B.{number}",
                "artifact_path": f"questions/4B.{number}/output.json",
                "artifact_sha256": "0" * 64,
                "status": "pass",
            }
            for number in range(1, 11)
        ),
        phase_gate="pass",
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_chapter_question_writing",
        lambda **kwargs: writing,
    )
    writing_dir = tmp_path / "writing"
    writing_dir.mkdir()
    (writing_dir / "writing-manifest.json").write_text(writing.model_dump_json())

    with pytest.raises(ValueError, match="approved analysis hash"):
        run_chapter_question_review(
            project_root=ROOT,
            package=package,
            approved_analysis_path=analysis_path,
            writing_dir=writing_dir,
            output_dir=tmp_path / "review",
            profile_name="openai-sol-supervisor",
            writing_profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )


def test_review_stops_before_calls_when_writer_requested_reopen(
    monkeypatch, tmp_path: Path
) -> None:
    writing_dir = tmp_path / "writing"

    def fake_writer(**kwargs):
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True)
        _write_request_manifest(output_dir, kwargs["packet"], kwargs["predecessor_answer"])
        question_id = kwargs["packet"].question_id
        answer = _answer(question_id)
        if question_id == "4B.1":
            answer = answer.model_copy(
                update={
                    "reopen_requests": (
                        EvidenceReopenRequest(
                            evidence_id="E-REOPEN",
                            reason="This candidate may materially change the final answer.",
                        ),
                    )
                }
            )
        (output_dir / "output.json").write_text(answer.model_dump_json())
        (output_dir / "prompt.txt").write_text("prompt")
        return answer, {"functional_gate": "pass"}

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        fake_writer,
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_question_answer",
        lambda packet, answer: {"functional_gate": "pass"},
    )
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.build_question_writer_prompt",
        lambda packet, prompts, predecessor: "prompt",
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    run_chapter_question_writing(
        project_root=ROOT,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=analysis_path,
        profile_name="openai-terra-candidate",
        profiles_path=PROFILES,
    )
    called = False

    def forbidden_review(**kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.run_blind_question_quality_review",
        forbidden_review,
    )
    review_dir = tmp_path / "review"
    with pytest.raises(RuntimeError, match="stopped before model calls"):
        run_chapter_question_review(
            project_root=ROOT,
            package=package,
            approved_analysis_path=analysis_path,
            writing_dir=writing_dir,
            output_dir=review_dir,
            profile_name="openai-sol-supervisor",
            writing_profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
        )
    assert not called
    stop = QuestionReviewReopenStopManifest.model_validate_json(
        (review_dir / "reopen-stop.json").read_text()
    )
    assert stop.review_calls_launched == 0
    assert stop.unresolved[0].question_id == "4B.1"
    assert stop.unresolved[0].evidence_ids == ("E-REOPEN",)
