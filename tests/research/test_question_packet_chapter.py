import json
import shutil
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from leaders_db.research.chapter_analysis_models import ResolvedChapterAnalysis
from leaders_db.research.control_flow import load_question_review_experiment_policy
from leaders_db.research.question_packet_chapter import (
    ChapterQuestionPhaseManifest,
    _inside,
    load_trusted_unavailable_adjudication,
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


def _package(analysis_hash: str = "0" * 64, *, discovery_complete: bool = False):
    packets = tuple(
        SimpleNamespace(
            question_id=f"4B.{number}",
            evidence_discovery_complete=discovery_complete,
            coverage=SimpleNamespace(required_evidence_ids=(), reopenable_evidence_ids=()),
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
                "evidence_discovery_complete": packet.evidence_discovery_complete,
                "reopenable_evidence_ids": list(packet.coverage.reopenable_evidence_ids),
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


def _assert_collect_all_review(monkeypatch, tmp_path: Path, arguments: dict[str, object]) -> None:
    def collect_validate(**kwargs):
        question_id = kwargs["packet"].question_id
        return {
            "quality_gate": "fail" if question_id == "4B.1" else "pass",
            "prompt_config_sha256": sha256(
                (ROOT / "configs/question-packet-prompts.yaml").read_bytes()
            ).hexdigest(),
        }

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_blind_review_artifacts",
        collect_validate,
    )
    policy_path = ROOT / "configs/research-question-review-experiment.yaml"
    collected_path = run_chapter_question_review(
        **{**arguments, "output_dir": tmp_path / "collected-review"},
        experiment_policy=load_question_review_experiment_policy(policy_path),
        experiment_policy_sha256=sha256(policy_path.read_bytes()).hexdigest(),
    )
    collected = ChapterQuestionPhaseManifest.model_validate_json(collected_path.read_text())
    assert collected.question_count == 10
    assert collected.phase_gate == "fail"
    assert [item.status for item in collected.artifacts].count("fail") == 1
    assert (
        validate_chapter_question_review(
            **{**arguments, "output_dir": tmp_path / "collected-review"},
            experiment_policy_path=policy_path,
        )
        == collected
    )


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


def test_chapter_writing_marks_true_zero_lens_unavailable_without_model_call(
    monkeypatch, tmp_path: Path
) -> None:
    calls = []

    def fake_writer(**kwargs):
        calls.append(kwargs["packet"].question_id)
        output_dir = kwargs["output_dir"]
        output_dir.mkdir(parents=True)
        answer = _answer(kwargs["packet"].question_id)
        (output_dir / "output.json").write_text(answer.model_dump_json())
        return answer, {"functional_gate": "pass"}

    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        fake_writer,
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    for index, packet in enumerate(package.packets):
        packet.candidate_index = () if index == 0 else (object(),)
    trust_dir = ROOT / "tmp" / tmp_path.name
    trust_dir.mkdir(parents=True)
    inventory = trust_dir / "inventory.json"
    search = trust_dir / "search.json"
    inventory.write_text(
        json.dumps(
            {
                "schema_version": "question_research_inventory_v1",
                "question_id": "4B.1",
                "source_ids": ["https://example.test/source"],
                "admissible_evidence_ids": [],
            }
        )
    )
    search.write_text(
        json.dumps(
            {
                "schema_version": "question_targeted_search_manifest_v1",
                "question_id": "4B.1",
                "queries": ["targeted query"],
                "inspected_urls": ["https://example.test/source"],
                "saturation_review": "pass",
            }
        )
    )
    review = trust_dir / "review.json"
    review.write_text(
        json.dumps(
            {
                "schema_version": "question_unavailable_independent_review_v1",
                "question_id": "4B.1",
                "research_inventory_sha256": sha256(inventory.read_bytes()).hexdigest(),
                "targeted_search_manifest_sha256": sha256(search.read_bytes()).hexdigest(),
                "admissible_evidence_count": 0,
                "review_gate": "pass",
            }
        )
    )
    packet_hash = sha256(
        json.dumps(
            package.packets[0].model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    adjudication = trust_dir / "adjudication.json"
    adjudication.write_text(
        json.dumps(
            {
                "schema_version": "question_evidence_unavailable_adjudication_v1",
                "question_id": "4B.1",
                "packet_sha256": packet_hash,
                "research_inventory_path": str(inventory.relative_to(ROOT)),
                "research_inventory_sha256": sha256(inventory.read_bytes()).hexdigest(),
                "targeted_search_manifest_path": str(search.relative_to(ROOT)),
                "targeted_search_manifest_sha256": sha256(search.read_bytes()).hexdigest(),
                "independent_review_path": str(review.relative_to(ROOT)),
                "independent_review_sha256": sha256(review.read_bytes()).hexdigest(),
                "targeted_query_count": 1,
                "inspected_source_count": 1,
                "admissible_evidence_count": 0,
                "saturation_review": "pass",
                "decision": "no_admissible_evidence",
            }
        )
    )
    try:
        trusted_adjudication = load_trusted_unavailable_adjudication(
            project_root=ROOT,
            path=adjudication,
            packet=package.packets[0],
        )
        manifest_path = run_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=tmp_path / "writing",
            approved_analysis_path=analysis_path,
            profile_name="openai-terra-candidate",
            profiles_path=PROFILES,
            unavailable_adjudications={"4B.1": trusted_adjudication},
        )
    finally:
        shutil.rmtree(trust_dir)

    manifest = ChapterQuestionPhaseManifest.model_validate_json(manifest_path.read_text())
    assert manifest.artifacts[0].status == "unavailable"
    assert calls == [f"4B.{number}" for number in range(2, 11)]
    unavailable = json.loads(
        (tmp_path / "writing/questions/4B.1/unavailable.json").read_text()
    )
    assert unavailable["model_call_created"] is False


def test_empty_lens_without_saturation_adjudication_stops_before_model_call(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.write_diagnostic_question_answer",
        lambda **kwargs: pytest.fail("model call must not start"),
    )
    analysis_path = _analysis_path(tmp_path)
    package = _package(sha256(analysis_path.read_bytes()).hexdigest())
    package.packets[0].candidate_index = ()
    with pytest.raises(ValueError, match="no trusted saturation adjudication"):
        run_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=tmp_path / "writing",
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
                "predecessor_answer_included": not request["predecessor_answer_included"],
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
    request_path.write_text(json.dumps({**request, "evidence_discovery_complete": True}))
    with pytest.raises(ValueError, match="evidence-discovery metadata"):
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


def test_closed_chapter_writing_rejects_prompt_version_downgrade(
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
    package = _package(sha256(analysis_path.read_bytes()).hexdigest(), discovery_complete=True)
    run_chapter_question_writing(
        project_root=ROOT,
        package=package,
        output_dir=writing_dir,
        approved_analysis_path=analysis_path,
        profile_name="openai-terra-candidate",
        profiles_path=PROFILES,
    )
    manifest_path = writing_dir / "writing-manifest.json"
    manifest = ChapterQuestionPhaseManifest.model_validate_json(manifest_path.read_text())
    frozen_path = ROOT / "configs/question-packet-prompts-v13.yaml"
    frozen_hash = sha256(frozen_path.read_bytes()).hexdigest()
    for artifact in manifest.artifacts:
        request_path = writing_dir / artifact.artifact_path
        request_path = request_path.parent / "request-manifest.json"
        request = json.loads(request_path.read_text())
        request_path.write_text(
            json.dumps(
                {
                    **request,
                    "prompt_config_version": 13,
                    "prompt_config_sha256": frozen_hash,
                }
            )
        )
    manifest_path.write_text(
        manifest.model_copy(update={"prompt_config_sha256": frozen_hash}).model_dump_json()
    )

    with pytest.raises(ValueError, match="closed evidence discovery requires prompt version"):
        validate_chapter_question_writing(
            project_root=ROOT,
            package=package,
            output_dir=writing_dir,
            approved_analysis_path=analysis_path,
            profile_name="openai-terra-candidate",
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
        return {
            "quality_gate": "pass",
            "prompt_config_sha256": sha256(
                (ROOT / "configs/question-packet-prompts.yaml").read_bytes()
            ).hexdigest(),
        }

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

    _assert_collect_all_review(monkeypatch, tmp_path, arguments)
    monkeypatch.setattr(
        "leaders_db.research.question_packet_chapter.validate_blind_review_artifacts",
        fake_validate,
    )

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
