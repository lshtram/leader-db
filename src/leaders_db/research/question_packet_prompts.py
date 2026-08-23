"""Versioned prompt configuration for diagnostic question-packet experiments."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuestionPacketPrompts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    writer_template: str = Field(min_length=100)
    final_writer_template: str | None = None
    empty_evidence_instruction: str | None = None
    review_template: str = Field(min_length=100)

    @model_validator(mode="after")
    def validate_placeholders(self) -> QuestionPacketPrompts:
        shared = {"{question_id}", "{question}", "{exact_evidence}", "{candidate_index}"}
        writer = shared | {"{predecessor_answer}"}
        if not all(placeholder in self.writer_template for placeholder in writer):
            raise ValueError("writer prompt omits a required placeholder")
        if self.version >= 14 and (
            self.final_writer_template is None
            or not all(
                placeholder in self.final_writer_template
                for placeholder in writer - {"{candidate_index}"}
            )
        ):
            raise ValueError("final writer prompt omits a required placeholder")
        if self.version >= 16 and not self.empty_evidence_instruction:
            raise ValueError("sparse-evidence prompt instruction is required")
        if not all(
            placeholder in self.review_template for placeholder in shared | {"{candidates}"}
        ):
            raise ValueError("review prompt omits a required placeholder")
        return self


def load_question_packet_prompts(path: Path) -> tuple[QuestionPacketPrompts, str]:
    """Load validated prompts and return their exact configuration hash."""

    raw = path.read_bytes()
    try:
        payload = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid question packet prompt YAML: {path}") from exc
    return QuestionPacketPrompts.model_validate(payload), sha256(raw).hexdigest()


def load_versioned_question_packet_prompts(
    project_root: Path, version: object
) -> tuple[QuestionPacketPrompts, str]:
    """Load the exact saved prompt contract for a trusted historical artifact."""

    if type(version) is not int or version < 1:
        raise ValueError("saved question-packet prompt version is invalid")
    current_path = project_root / "configs/question-packet-prompts.yaml"
    current, current_hash = load_question_packet_prompts(current_path)
    if version == current.version:
        return current, current_hash
    legacy_path = project_root / f"configs/question-packet-prompts-v{version}.yaml"
    if not legacy_path.is_file():
        raise ValueError("saved question-packet prompt version is unavailable")
    legacy, legacy_hash = load_question_packet_prompts(legacy_path)
    if legacy.version != version:
        raise ValueError("saved question-packet prompt file has the wrong version")
    return legacy, legacy_hash


__all__ = [
    "QuestionPacketPrompts",
    "load_question_packet_prompts",
    "load_versioned_question_packet_prompts",
]
