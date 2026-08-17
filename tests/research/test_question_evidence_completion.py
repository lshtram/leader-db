from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from leaders_db.research.question_evidence_completion import (
    EvidenceCompletionConfig,
    EvidenceCompletionItem,
    load_evidence_completion,
)
from leaders_db.research.question_evidence_packet_models import (
    ChapterQuestionEvidencePackage,
    CompactEvidenceCandidate,
    EvidenceCoverageItem,
    EvidenceDisposition,
    QuestionCoverageChecklist,
    QuestionEvidencePacket,
    _ids_digest,
)
from leaders_db.research.question_packet_chapter_models import (
    ChapterQuestionArtifact,
    ChapterQuestionPhaseManifest,
)
from leaders_db.research.question_packet_expansion import expand_question_evidence_package
from leaders_db.research.question_packet_prompts import load_question_packet_prompts
from leaders_db.research.question_packet_writer import (
    DiagnosticQuestionAnswer,
    EvidenceReopenRequest,
    build_question_writer_prompt,
    normalize_optional_reopen_requests,
)
from tests.research.test_corpus_mapping_review import _evidence


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _source_run(root: Path) -> tuple[Path, Path, ChapterQuestionEvidencePackage]:
    source_run = root / "research/runs/failed-v1"
    source_run.mkdir(parents=True)
    exact = _evidence("E-1", "Required fact").model_copy(
        update={"question_ids": tuple(f"4B.{number}" for number in range(1, 11))}
    )
    optional = _evidence("E-2", "Potentially material fact").model_copy(
        update={"question_ids": ("4B.1",), "polarity": "adverse"}
    )
    judge_path = source_run / "judge-package.json"
    judge_path.write_text(
        json.dumps({"evidence": [exact.model_dump(mode="json"), optional.model_dump(mode="json")]})
    )
    packets = tuple(
        _packet(exact, optional if number == 1 else None, number)
        for number in range(1, 11)
    )
    package = ChapterQuestionEvidencePackage(
        chapter_id="4B",
        source_package_sha256=_digest(judge_path),
        selection_manifest_sha256="1" * 64,
        selected_analysis_sha256="2" * 64,
        question_catalogue_sha256="3" * 64,
        complete_ledger_evidence_count=2,
        complete_ledger_ids_sha256=_ids_digest(("E-1", "E-2")),
        packets=packets,
        chapter_candidate_ids=("E-1", "E-2"),
        complete_ledger_dispositions=(
            EvidenceDisposition(
                evidence_id="E-1",
                direct_question_ids=exact.question_ids,
                sibling_chapter_question_ids=(),
                disposition="direct",
            ),
            EvidenceDisposition(
                evidence_id="E-2",
                direct_question_ids=("4B.1",),
                sibling_chapter_question_ids=(),
                disposition="direct",
            ),
        ),
    )
    package_path = source_run / "question-packages/4B/package.json"
    package_path.parent.mkdir(parents=True)
    package_path.write_text(package.model_dump_json(indent=2) + "\n")
    writing_path = _writing_phase(source_run, package)
    preflight_path = source_run / "preflight-manifest.json"
    preflight_path.write_text(
        json.dumps(
            {
                "release_id": "failed-v1",
                "question_packages": [
                    {
                        "chapter_id": "4B",
                        "path": str(package_path),
                        "sha256": _digest(package_path),
                    }
                ],
            }
        )
    )
    return preflight_path, writing_path, package


def _packet(exact, optional, number: int) -> QuestionEvidencePacket:
    evidence = (exact,) if optional is None else (exact, optional)
    candidates = tuple(
        CompactEvidenceCandidate(
            evidence_id=item.evidence_id,
            fact_summary=item.fact_summary,
            publisher=item.publisher,
            polarity=item.polarity,
            period_fit=item.period_fit,
            ruler_attribution=item.ruler_attribution,
            limitations=item.limitations,
            question_ids=item.question_ids,
        )
        for item in evidence
    )
    return QuestionEvidencePacket(
        question_id=f"4B.{number}",
        question="Synthetic completion question",
        priority_evidence=(exact,),
        source_routed_priority_evidence_ids=("E-1",),
        candidate_index=candidates,
        direct_evidence_count=len(candidates),
        favorable_evidence_ids=(),
        adverse_evidence_ids=(("E-2",) if optional is not None else ()),
        mixed_or_context_evidence_ids=("E-1",),
        coverage=QuestionCoverageChecklist(
            question_id=f"4B.{number}",
            items=tuple(
                EvidenceCoverageItem(
                    evidence_id=item.evidence_id,
                    requirement=(
                        "must_address" if item.evidence_id == "E-1" else "available_for_reopen"
                    ),
                    carries_attribution=True,
                    carries_period_fit=True,
                    carries_limitations=True,
                )
                for item in evidence
            ),
            required_evidence_ids=("E-1",),
            reopenable_evidence_ids=(("E-2",) if optional is not None else ()),
            favorable_available=False,
            adverse_available=optional is not None,
            mixed_or_context_available=True,
        ),
    )


def _writing_phase(source_run: Path, package: ChapterQuestionEvidencePackage) -> Path:
    artifacts = []
    for number in range(1, 11):
        question_id = f"4B.{number}"
        answer = DiagnosticQuestionAnswer(
            question_id=question_id,
            answer="Synthetic answer grounded in required evidence [E-1].",
            reopen_requests=(
                (
                    EvidenceReopenRequest(
                        evidence_id="E-2", reason="It may materially alter the answer."
                    ),
                )
                if number == 1
                else ()
            ),
            evidence_dispositions=(),
        )
        path = source_run / f"question-writing/4B/questions/{question_id}/accepted-output.json"
        path.parent.mkdir(parents=True)
        path.write_text(answer.model_dump_json(indent=2) + "\n")
        artifacts.append(
            ChapterQuestionArtifact(
                question_id=question_id,
                artifact_path=str(path.relative_to(source_run / "question-writing/4B")),
                artifact_sha256=_digest(path),
                status="pass",
            )
        )
    manifest = ChapterQuestionPhaseManifest(
        schema_version="diagnostic_chapter_question_writing_v1",
        chapter_id="4B",
        profile="openai-luna-candidate",
        model="gpt-5.6-luna",
        package_sha256=sha256(
            json.dumps(
                package.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        profile_config_sha256="5" * 64,
        prompt_config_sha256="6" * 64,
        question_count=10,
        artifacts=tuple(artifacts),
        phase_gate="pass",
    )
    path = source_run / "question-writing/4B/writing-manifest.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return path


@pytest.mark.parametrize(
    ("decision", "required", "adjudicated"),
    [("promote", ("E-1", "E-2"), ()), ("retain_compact", ("E-1",), ("E-2",))],
)
def test_completion_authenticates_every_request_and_partitions_writer_input(
    tmp_path: Path, decision: str, required: tuple[str, ...], adjudicated: tuple[str, ...]
) -> None:
    preflight_path, writing_path, _ = _source_run(tmp_path)
    answer_path = (
        tmp_path
        / "research/runs/failed-v1/question-writing/4B/questions/4B.1/accepted-output.json"
    )
    config = {
        "schema_version": "question_evidence_completion_v1",
        "source_run": "failed-v1",
        "source_release_id": "failed-v1",
        "source_preflight_sha256": _digest(preflight_path),
        "user_authorized": True,
        "chapters": {
            "4B": {
                "question_package_sha256": "0" * 64,
                "writing_manifest_sha256": _digest(writing_path),
                "questions": {
                    "4B.1": {
                        "answer_artifact_sha256": _digest(answer_path),
                        "items": [
                                {
                                    "evidence_id": "E-2",
                                    "decision": decision,
                                    "reason": "Reviewed against the complete question evidence.",
                                }
                        ],
                    }
                },
            }
        },
    }
    package_path = tmp_path / "research/runs/failed-v1/question-packages/4B/package.json"
    config["chapters"]["4B"]["question_package_sha256"] = _digest(package_path)
    config_path = tmp_path / "completion.yaml"
    config_path.write_text(yaml.safe_dump(config))

    receipt = load_evidence_completion(
        project_root=tmp_path, config_path=config_path, active_chapters=("4B",)
    )
    expanded = expand_question_evidence_package(
        package=receipt.package_for("4B"),
        judge_package_path=tmp_path / "research/runs/failed-v1/judge-package.json",
        additions_by_question=receipt.additions_for("4B"),
        retained_by_question=receipt.retained_for("4B"),
    )

    assert expanded.packets[0].coverage.required_evidence_ids == required
    assert expanded.packets[0].coverage.adjudicated_nonmaterial_evidence_ids == adjudicated
    assert "E-2" not in expanded.packets[0].coverage.reopenable_evidence_ids
    if decision == "retain_compact":
        prompts, _ = load_question_packet_prompts(Path("configs/question-packet-prompts.yaml"))
        prompt = build_question_writer_prompt(expanded.packets[0], prompts)
        assert "E-2" not in prompt
        attempted = DiagnosticQuestionAnswer(
            question_id="4B.1",
            answer="A sufficiently detailed synthetic answer using exact evidence [E-1].",
            reopen_requests=(
                EvidenceReopenRequest(
                    evidence_id="E-2",
                    reason="Attempted repeat of an already adjudicated evidence request.",
                ),
            ),
            evidence_dispositions=(),
        )
        normalized, ledger = normalize_optional_reopen_requests(expanded.packets[0], attempted)
        assert normalized.reopen_requests == ()
        assert ledger["rejected_reopen_ids"] == ["E-2"]
    receipt.verify_unchanged()

    answer_path.write_text("{}")
    with pytest.raises(ValueError, match="source changed"):
        receipt.verify_unchanged()


def test_completion_rejects_an_undispositioned_request(tmp_path: Path) -> None:
    preflight_path, writing_path, _ = _source_run(tmp_path)
    config_path = tmp_path / "completion.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "question_evidence_completion_v1",
                "source_run": "failed-v1",
                "source_release_id": "failed-v1",
                "source_preflight_sha256": _digest(preflight_path),
                "user_authorized": True,
                "chapters": {
                    "4B": {
                        "question_package_sha256": _digest(
                            tmp_path / "research/runs/failed-v1/question-packages/4B/package.json"
                        ),
                        "writing_manifest_sha256": _digest(writing_path),
                        "questions": {},
                    }
                },
            }
        )
    )

    with pytest.raises(ValueError, match="invalid question"):
        load_evidence_completion(
            project_root=tmp_path, config_path=config_path, active_chapters=("4B",)
        )


@pytest.mark.parametrize("value", [1, 1.0, "true", "1"])
def test_completion_rejects_coerced_authorization(value: object) -> None:
    with pytest.raises(ValidationError, match="explicit boolean authorization"):
        EvidenceCompletionConfig.model_validate(
            {
                "schema_version": "question_evidence_completion_v1",
                "source_run": "failed-v1",
                "source_release_id": "failed-v1",
                "source_preflight_sha256": "0" * 64,
                "user_authorized": value,
                "chapters": {
                    "4B": {
                        "question_package_sha256": "1" * 64,
                        "writing_manifest_sha256": "2" * 64,
                        "questions": {
                            "4B.1": {
                                "answer_artifact_sha256": "3" * 64,
                                "items": [
                                    {
                                        "evidence_id": "E-1",
                                        "decision": "promote",
                                        "reason": "Material exact evidence.",
                                    }
                                ],
                            }
                        },
                    }
                },
            }
        )


def test_exact_evidence_expansion_hashes_and_parses_one_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, package = _source_run(tmp_path)
    judge_path = tmp_path / "research/runs/failed-v1/judge-package.json"
    original_read_bytes = Path.read_bytes
    judge_reads = 0

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal judge_reads
        if path == judge_path:
            judge_reads += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)
    expand_question_evidence_package(
        package=package,
        judge_package_path=judge_path,
        additions_by_question={"4B.1": ("E-2",)},
    )

    assert judge_reads == 1


@pytest.mark.parametrize("reason", ["", " ", "\n\t", "too short"])
def test_completion_rejects_blank_or_insubstantial_reason(reason: str) -> None:
    with pytest.raises(ValidationError, match="20 non-space characters"):
        EvidenceCompletionItem(
            evidence_id="E-1", decision="promote", reason=reason
        )
