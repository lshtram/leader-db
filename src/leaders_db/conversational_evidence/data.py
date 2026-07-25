"""Load collector-owned data files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

DATA_DIR = Path(__file__).with_name("data")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfiguredQuestion(_StrictModel):
    id: str
    text: str
    registry_key: str | None = None


class ConfiguredQuestionRegistry(_StrictModel):
    category: str
    question_code_prefix: str
    question_key_prefix: str
    concept_key: str


class ConfiguredChapter(_StrictModel):
    id: str
    registry: ConfiguredQuestionRegistry
    questions: tuple[ConfiguredQuestion, ...]


class QuestionCatalog(_StrictModel):
    schema_version: str
    chapter_ids: tuple[str, ...]
    lens_numbers: tuple[int, ...]
    chapters: tuple[ConfiguredChapter, ...]

    @model_validator(mode="after")
    def require_complete_unique_structure(self) -> QuestionCatalog:
        if (
            not self.chapter_ids
            or len(self.chapter_ids) != len(set(self.chapter_ids))
            or not self.lens_numbers
            or len(self.lens_numbers) != len(set(self.lens_numbers))
        ):
            raise ValueError("configured chapter IDs and lens numbers must be unique")
        if tuple(chapter.id for chapter in self.chapters) != self.chapter_ids:
            raise ValueError("chapters must match the configured chapter IDs")
        configured = [
            question
            for chapter in self.chapters
            for question in chapter.questions
        ]
        expected_ids = {
            f"{chapter_id}.{lens_number}"
            for chapter_id in self.chapter_ids
            for lens_number in self.lens_numbers
        }
        configured_ids = {question.id for question in configured}
        if configured_ids != expected_ids:
            raise ValueError("question IDs must match the configured chapter/lens grid")
        if len(configured) != len({question.id for question in configured}):
            raise ValueError("question IDs must be unique")
        resolved_registry_keys = [
            question.registry_key
            or (
                f"ruler_{chapter.registry.question_key_prefix}_"
                f"{question.id.split('.', maxsplit=1)[1]}"
            )
            for chapter in self.chapters
            for question in chapter.questions
        ]
        if len(resolved_registry_keys) != len(set(resolved_registry_keys)):
            raise ValueError("resolved question registry keys must be unique")
        return self


def load(name: str) -> dict[str, Any]:
    """Load one JSON data file."""

    value = json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


@lru_cache(maxsize=1)
def question_catalog() -> QuestionCatalog:
    """Return the validated ruler-quality question catalogue."""

    return QuestionCatalog.model_validate(load("questions.json"))


def questions() -> list[dict[str, str]]:
    """Return all questions in their configured order."""

    return [
        question.model_dump(exclude_none=True)
        for chapter in question_catalog().chapters
        for question in chapter.questions
    ]
