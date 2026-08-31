"""Hash-bound decisions for completing evidence before a fresh writing run."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter_models import ChapterQuestionPhaseManifest
from .question_packet_writer import DiagnosticQuestionAnswer


class EvidenceCompletionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    decision: Literal["promote", "retain_compact"]
    reason: str = Field(min_length=1)

    @field_validator("reason", mode="before")
    @classmethod
    def require_substantive_reason(cls, value: object) -> object:
        if not isinstance(value, str) or len("".join(value.split())) < 20:
            raise ValueError("evidence completion reason must contain 20 non-space characters")
        return value.strip()


class QuestionEvidenceCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    items: tuple[EvidenceCompletionItem, ...] = Field(min_length=1)

    @field_validator("items")
    @classmethod
    def unique_items(
        cls, items: tuple[EvidenceCompletionItem, ...]
    ) -> tuple[EvidenceCompletionItem, ...]:
        ids = [item.evidence_id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence completion IDs must be unique")
        return items


class ChapterEvidenceCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    writing_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    questions: dict[str, QuestionEvidenceCompletion]


class EvidenceCompletionConfig(BaseModel):
    """An explicit decision for every accepted reopen request in one failed run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["question_evidence_completion_v1"]
    source_run: str
    source_release_id: str
    source_preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_authorized: Literal[True]
    chapters: dict[str, ChapterEvidenceCompletion]

    @field_validator("user_authorized", mode="before")
    @classmethod
    def require_literal_authorization(cls, value: object) -> object:
        if type(value) is not bool or value is not True:
            raise ValueError("evidence completion requires explicit boolean authorization")
        return value

    @field_validator("chapters")
    @classmethod
    def valid_chapters(
        cls, chapters: dict[str, ChapterEvidenceCompletion]
    ) -> dict[str, ChapterEvidenceCompletion]:
        if not chapters:
            raise ValueError("evidence completion must contain affected chapters")
        for chapter_id, chapter in chapters.items():
            expected = {f"{chapter_id}.{number}" for number in range(1, 11)}
            if not chapter.questions or not set(chapter.questions).issubset(expected):
                raise ValueError("evidence completion contains an invalid question")
        return chapters


@dataclass(frozen=True)
class EvidenceCompletionReceipt:
    config_path: Path
    config_sha256: str
    source_run: Path
    source_preflight_path: Path
    source_preflight_sha256: str
    source_release_id: str
    packages: dict[str, ChapterQuestionEvidencePackage]
    decisions: dict[str, tuple[EvidenceCompletionItem, ...]]
    protected_paths: dict[Path, str]

    def additions_for(self, chapter_id: str) -> dict[str, tuple[str, ...]]:
        return {
            question_id: tuple(
                item.evidence_id for item in items if item.decision == "promote"
            )
            for question_id, items in self.decisions.items()
            if question_id.startswith(f"{chapter_id}.")
        }

    def retained_for(self, chapter_id: str) -> dict[str, tuple[str, ...]]:
        return {
            question_id: tuple(
                item.evidence_id
                for item in items
                if item.decision == "retain_compact"
            )
            for question_id, items in self.decisions.items()
            if question_id.startswith(f"{chapter_id}.")
        }

    def package_for(self, chapter_id: str) -> ChapterQuestionEvidencePackage:
        try:
            return self.packages[chapter_id]
        except KeyError as exc:
            raise ValueError(f"evidence completion does not bind {chapter_id}") from exc

    def verify_unchanged(self) -> None:
        changed = any(
            _digest(path.read_bytes()) != expected
            for path, expected in self.protected_paths.items()
        )
        if changed:
            raise ValueError("evidence completion source changed during preflight")

    def manifest_details(self) -> list[dict]:
        return [
            {
                "question_id": question_id,
                "items": [item.model_dump(mode="json") for item in items],
            }
            for question_id, items in sorted(self.decisions.items())
        ]


def load_evidence_completion(
    *, project_root: Path, config_path: Path, active_chapters: tuple[str, ...]
) -> EvidenceCompletionReceipt:
    """Authenticate and load one complete decision over a failed writing run."""

    root = project_root.resolve()
    config_path = config_path.resolve()
    if not config_path.is_relative_to(root) or not config_path.is_file():
        raise ValueError("evidence completion config is outside the project")
    config_bytes = config_path.read_bytes()
    config = EvidenceCompletionConfig.model_validate(yaml.safe_load(config_bytes))
    if set(config.chapters) != set(active_chapters):
        raise ValueError("evidence completion must bind every active chapter")
    source_run, preflight_path, package_rows = _load_source(config, root, active_chapters)
    protected = {
        config_path: _digest(config_bytes),
        preflight_path: config.source_preflight_sha256,
    }
    packages: dict[str, ChapterQuestionEvidencePackage] = {}
    decisions: dict[str, tuple[EvidenceCompletionItem, ...]] = {}
    observed_questions: set[str] = set()
    for chapter_id in active_chapters:
        package, chapter_decisions, chapter_paths = _load_chapter(
            source_run=source_run,
            chapter_id=chapter_id,
            chapter=config.chapters[chapter_id],
            package_row=package_rows[chapter_id],
        )
        packages[chapter_id] = package
        decisions.update(chapter_decisions)
        observed_questions.update(chapter_decisions)
        protected.update(chapter_paths)
    configured_questions = {
        question_id for chapter in config.chapters.values() for question_id in chapter.questions
    }
    if configured_questions != observed_questions:
        raise ValueError("evidence completion does not exactly cover requested questions")
    return EvidenceCompletionReceipt(
        config_path=config_path,
        config_sha256=_digest(config_bytes),
        source_run=source_run,
        source_preflight_path=preflight_path,
        source_preflight_sha256=config.source_preflight_sha256,
        source_release_id=config.source_release_id,
        packages=packages,
        decisions=decisions,
        protected_paths=protected,
    )


def _load_source(
    config: EvidenceCompletionConfig, root: Path, active_chapters: tuple[str, ...]
) -> tuple[Path, Path, dict[str, dict]]:
    runs_root = (root / "research/runs").resolve()
    source_run = (runs_root / config.source_run).resolve()
    if not source_run.is_relative_to(runs_root) or not source_run.is_dir():
        raise ValueError("evidence completion source run is outside the run store")
    preflight_path = _inside(source_run, source_run / "preflight-manifest.json")
    preflight_bytes = preflight_path.read_bytes()
    if _digest(preflight_bytes) != config.source_preflight_sha256:
        raise ValueError("evidence completion source preflight changed")
    preflight = json.loads(preflight_bytes)
    if preflight.get("release_id") != config.source_release_id:
        raise ValueError("evidence completion source release differs from its preflight")
    package_rows = {item["chapter_id"]: item for item in preflight["question_packages"]}
    if set(package_rows) != set(active_chapters):
        raise ValueError("source preflight does not bind every active chapter")
    return source_run, preflight_path, package_rows


def _load_chapter(
    *,
    source_run: Path,
    chapter_id: str,
    chapter: ChapterEvidenceCompletion,
    package_row: dict,
) -> tuple[
    ChapterQuestionEvidencePackage,
    dict[str, tuple[EvidenceCompletionItem, ...]],
    dict[Path, str],
]:
    package_path = _inside(source_run, Path(package_row["path"]))
    package_bytes = package_path.read_bytes()
    package_digest = _digest(package_bytes)
    if package_digest != package_row["sha256"] or (
        package_digest != chapter.question_package_sha256
    ):
        raise ValueError("evidence completion question package changed")
    package = ChapterQuestionEvidencePackage.model_validate_json(package_bytes)
    if any(packet.evidence_discovery_complete for packet in package.packets):
        raise ValueError("evidence discovery is already complete for this package")
    saved_package_payload_hash = _payload_hash(json.loads(package_bytes))
    writing_path = _inside(
        source_run, source_run / "question-writing" / chapter_id / "writing-manifest.json"
    )
    writing_bytes = writing_path.read_bytes()
    if _digest(writing_bytes) != chapter.writing_manifest_sha256:
        raise ValueError("evidence completion writing manifest changed")
    writing = ChapterQuestionPhaseManifest.model_validate_json(writing_bytes)
    if (
        writing.chapter_id != chapter_id
        or writing.phase_gate != "pass"
        or writing.package_sha256 != saved_package_payload_hash
    ):
        raise ValueError("evidence completion requires a passed writing phase")
    packets = {item.question_id: item for item in package.packets}
    decisions: dict[str, tuple[EvidenceCompletionItem, ...]] = {}
    protected = {package_path: package_digest, writing_path: _digest(writing_bytes)}
    for artifact in writing.artifacts:
        answer_path = _inside(writing_path.parent, writing_path.parent / artifact.artifact_path)
        answer_bytes = answer_path.read_bytes()
        if _digest(answer_bytes) != artifact.artifact_sha256:
            raise ValueError("evidence completion answer artifact changed")
        answer = DiagnosticQuestionAnswer.model_validate_json(answer_bytes)
        request_ids = tuple(item.evidence_id for item in answer.reopen_requests)
        if not request_ids:
            if artifact.question_id in chapter.questions:
                raise ValueError("evidence completion includes a question without requests")
            continue
        try:
            question = chapter.questions[artifact.question_id]
        except KeyError as exc:
            raise ValueError("evidence completion omits a requested question") from exc
        decision_ids = tuple(item.evidence_id for item in question.items)
        reopenable = packets[artifact.question_id].coverage.reopenable_evidence_ids
        if (
            question.answer_artifact_sha256 != artifact.artifact_sha256
            or decision_ids != request_ids
            or not set(decision_ids).issubset(reopenable)
        ):
            raise ValueError("evidence completion differs from accepted reopen requests")
        decisions[artifact.question_id] = question.items
        protected[answer_path] = _digest(answer_bytes)
    if set(chapter.questions) != set(decisions):
        raise ValueError("evidence completion has unused question decisions")
    return package, decisions, protected


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise ValueError("evidence completion artifact is outside its source run")
    return resolved


def _digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = ["EvidenceCompletionReceipt", "load_evidence_completion"]
