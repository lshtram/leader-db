"""Legacy review-derived question-packet expansion configuration."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionPacketExpansionConfig(BaseModel):
    """A small, review-bound list of candidates promoted to exact evidence."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    source_review: str
    source_review_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chapters: dict[str, dict[str, tuple[str, ...]]]

    @field_validator("chapters")
    @classmethod
    def validate_additions(
        cls, chapters: dict[str, dict[str, tuple[str, ...]]]
    ) -> dict[str, dict[str, tuple[str, ...]]]:
        for chapter_id, questions in chapters.items():
            expected = {f"{chapter_id}.{number}" for number in range(1, 11)}
            if set(questions) != expected:
                raise ValueError("expansion must cover the chapter's ten questions")
            if any(not ids or len(ids) != len(set(ids)) for ids in questions.values()):
                raise ValueError("each question expansion must contain unique IDs")
        return chapters


def load_question_packet_expansion(
    *, project_root: Path, config_path: Path, chapter_id: str
) -> dict[str, tuple[str, ...]]:
    """Load additions only when their source review manifest is unchanged."""

    config = QuestionPacketExpansionConfig.model_validate(yaml.safe_load(config_path.read_bytes()))
    review_dir = (project_root / "research/runs" / config.source_review).resolve()
    runs_root = (project_root / "research/runs").resolve()
    manifest_path = review_dir / "review-manifest.json"
    if (
        not review_dir.is_relative_to(runs_root)
        or not manifest_path.is_file()
        or sha256(manifest_path.read_bytes()).hexdigest() != config.source_review_manifest_sha256
    ):
        raise ValueError("question expansion source review is missing or changed")
    try:
        additions = config.chapters[chapter_id]
    except KeyError as exc:
        raise ValueError(f"question expansion does not contain {chapter_id}") from exc
    outer = json.loads(manifest_path.read_text())
    artifacts = {item["question_id"]: item for item in outer["artifacts"]}
    if set(artifacts) != set(additions):
        raise ValueError("source review does not contain the expansion questions")
    for question_id, expected_ids in additions.items():
        child_path = review_dir / artifacts[question_id]["artifact_path"]
        if sha256(child_path.read_bytes()).hexdigest() != artifacts[question_id]["artifact_sha256"]:
            raise ValueError("source review child manifest changed")
        child = json.loads(child_path.read_text())
        output_path = child_path.parent / "output.json"
        review = json.loads(output_path.read_text())
        if (
            child["question_id"] != question_id
            or _payload_hash(review) != child["review_sha256"]
            or tuple(review["strongest_omitted_evidence_ids"]) != expected_ids
        ):
            raise ValueError("expansion differs from the source review recommendation")
    return additions


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = ["load_question_packet_expansion"]
