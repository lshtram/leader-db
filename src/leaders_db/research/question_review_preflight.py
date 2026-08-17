"""Stable zero-call barrier for unresolved writer evidence requests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

from .question_packet_chapter_models import (
    ChapterQuestionPhaseManifest,
    QuestionReviewReopenStopManifest,
    UnresolvedQuestionReopen,
)
from .question_packet_writer import DiagnosticQuestionAnswer

_SNAPSHOT_CAPABILITY = object()


@dataclass(frozen=True)
class QuestionReviewInputSnapshot:
    writing_dir: Path
    _writing_bytes: bytes
    writing_manifest_sha256: str
    _answer_bytes: Mapping[str, bytes]
    _capability: object

    @property
    def writing(self) -> ChapterQuestionPhaseManifest:
        return ChapterQuestionPhaseManifest.model_validate_json(self._writing_bytes)

    @property
    def answers(self) -> Mapping[str, DiagnosticQuestionAnswer]:
        return MappingProxyType(
            {
                question_id: DiagnosticQuestionAnswer.model_validate_json(payload)
                for question_id, payload in self._answer_bytes.items()
            }
        )


def load_review_input_snapshot(
    writing_dir: Path, validated_writing: ChapterQuestionPhaseManifest
) -> QuestionReviewInputSnapshot:
    """Read each trusted writing artifact once and bind its parsed in-memory value."""

    manifest_bytes = (writing_dir / "writing-manifest.json").read_bytes()
    if ChapterQuestionPhaseManifest.model_validate_json(manifest_bytes) != validated_writing:
        raise ValueError("writing manifest changed before review preflight")
    answer_bytes_by_id = {}
    for artifact in validated_writing.artifacts:
        answer_path = _inside(writing_dir, artifact.artifact_path)
        answer_bytes = answer_path.read_bytes()
        if sha256(answer_bytes).hexdigest() != artifact.artifact_sha256:
            raise ValueError("written question answer changed before review preflight")
        DiagnosticQuestionAnswer.model_validate_json(answer_bytes)
        answer_bytes_by_id[artifact.question_id] = answer_bytes
    return QuestionReviewInputSnapshot(
        writing_dir=writing_dir,
        _writing_bytes=manifest_bytes,
        writing_manifest_sha256=sha256(manifest_bytes).hexdigest(),
        _answer_bytes=MappingProxyType(answer_bytes_by_id),
        _capability=_SNAPSHOT_CAPABILITY,
    )


def require_trusted_snapshot(snapshot: QuestionReviewInputSnapshot) -> None:
    if snapshot._capability is not _SNAPSHOT_CAPABILITY:
        raise ValueError("question review input snapshot was not issued by the trusted loader")


def stop_for_reopen_requests(
    output_dir: Path, snapshots: tuple[QuestionReviewInputSnapshot, ...]
) -> None:
    """Persist a zero-call stop and reject review when writing left material gaps."""

    unresolved = tuple(
        UnresolvedQuestionReopen(
            chapter_id=snapshot.writing.chapter_id,
            question_id=question_id,
            answer_artifact_sha256=next(
                item.artifact_sha256
                for item in snapshot.writing.artifacts
                if item.question_id == question_id
            ),
            evidence_ids=tuple(item.evidence_id for item in answer.reopen_requests),
        )
        for snapshot in snapshots
        for question_id, answer in snapshot.answers.items()
        if answer.reopen_requests
    )
    if not unresolved:
        return
    manifest = QuestionReviewReopenStopManifest(
        writing_manifest_sha256s={
            snapshot.writing.chapter_id: snapshot.writing_manifest_sha256
            for snapshot in snapshots
        },
        unresolved=unresolved,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "reopen-stop.json").open("x", encoding="utf-8") as handle:
        handle.write(manifest.model_dump_json(indent=2) + "\n")
    raise RuntimeError(
        f"question review stopped before model calls: {len(unresolved)} answers "
        "contain unresolved writer reopen requests"
    )


def _inside(root: Path, relative: str) -> Path:
    resolved_root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise ValueError("chapter artifact path escapes its phase directory")
    return path


__all__ = [
    "QuestionReviewInputSnapshot",
    "load_review_input_snapshot",
    "require_trusted_snapshot",
    "stop_for_reopen_requests",
]
