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
    review_template: str = Field(min_length=100)

    @model_validator(mode="after")
    def validate_placeholders(self) -> QuestionPacketPrompts:
        shared = {"{question_id}", "{question}", "{exact_evidence}", "{candidate_index}"}
        writer = shared | {"{predecessor_answer}"}
        if not all(placeholder in self.writer_template for placeholder in writer):
            raise ValueError("writer prompt omits a required placeholder")
        if not all(
            placeholder in self.review_template
            for placeholder in shared | {"{candidates}"}
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


__all__ = ["QuestionPacketPrompts", "load_question_packet_prompts"]
