"""Versioned paragraph-labeled prompt construction for corpus reading."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .corpus_extraction import load_validated_extraction, render_reader_unit
from .corpus_reading_plan import CorpusReadingPlan, ReadingBatch

_PLACEHOLDERS = {
    "ruler_name",
    "period_start_year",
    "period_end_year",
    "questions",
    "documents",
}


class CorpusReaderPrompts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    reader_template: str = Field(min_length=100)

    @field_validator("reader_template")
    @classmethod
    def validate_placeholders(cls, value: str) -> str:
        missing = {f"{{{name}}}" for name in _PLACEHOLDERS if f"{{{name}}}" not in value}
        if missing:
            raise ValueError(f"corpus reader template lacks placeholders: {sorted(missing)}")
        return value


class RenderedCorpusReaderPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt: str
    prompt_config_version: int
    prompt_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    questions_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    character_count: int = Field(gt=0)
    estimated_tokens: int = Field(gt=0)


def load_corpus_reader_prompts(path: Path) -> tuple[CorpusReaderPrompts, str]:
    raw = path.read_bytes()
    config = CorpusReaderPrompts.model_validate(yaml.safe_load(raw))
    return config, sha256(raw).hexdigest()


def build_corpus_reader_prompt(
    *,
    acquisition_dir: Path,
    plan: CorpusReadingPlan,
    batch: ReadingBatch,
    prompts_path: Path,
    questions_path: Path,
) -> RenderedCorpusReaderPrompt:
    """Render one existing reader call with stable paragraph labels."""

    prompts, config_hash = load_corpus_reader_prompts(prompts_path)
    documents = {item.source_id: item for item in plan.documents}
    sections = []
    for source_id in batch.source_ids:
        document = documents[source_id]
        rows = load_validated_extraction(
            acquisition_dir / str(document.extracted_path),
            expected_source_id=source_id,
            expected_raw_sha256=str(document.raw_sha256),
        )
        start, end = batch.unit_ranges[source_id]
        selected = tuple(item for item in rows if start <= int(item["unit"]) <= end)
        if tuple(int(item["unit"]) for item in selected) != tuple(
            range(start, end + 1)
        ):
            raise ValueError(f"corpus reader source range is incomplete: {source_id}")
        rendered = []
        for item in selected:
            text = item["text"]
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"corpus reader source range contains an empty unit: {source_id}"
                )
            unit_rendering = render_reader_unit(source_id, item)
            if unit_rendering:
                rendered.append(unit_rendering)
        if not rendered:
            raise ValueError(f"corpus reader source range contains no text: {source_id}")
        sections.append(
            f"SOURCE {source_id}\nTITLE: {document.title}\nURL: {document.url}\n"
            + "\n\n".join(rendered)
        )
    questions_bytes = questions_path.read_bytes()
    questions = json.loads(questions_bytes)
    prompt = prompts.reader_template.format(
        ruler_name=plan.ruler_name,
        period_start_year=plan.period_start_year,
        period_end_year=plan.period_end_year,
        questions=json.dumps(questions, ensure_ascii=False),
        documents="\n\n--- DOCUMENT ---\n\n".join(sections),
    )
    return RenderedCorpusReaderPrompt(
        prompt=prompt,
        prompt_config_version=prompts.version,
        prompt_config_sha256=config_hash,
        questions_sha256=sha256(questions_bytes).hexdigest(),
        prompt_sha256=sha256(prompt.encode()).hexdigest(),
        character_count=len(prompt),
        estimated_tokens=len(tiktoken.get_encoding("o200k_base").encode(prompt)),
    )


def write_reader_request_manifest(
    path: Path,
    rendered: RenderedCorpusReaderPrompt,
    profile_name: str,
    profile_config_sha256: str,
    model: str,
    schema_type: type[BaseModel],
    reader_output_dir: Path,
) -> Path:
    """Persist or validate the exact request binding before model execution."""

    schema = schema_type.model_json_schema()
    make_strict_response_schema(schema)
    payload = {
        "schema_version": "corpus_reader_request_v1",
        "profile": profile_name,
        "profile_config_sha256": profile_config_sha256,
        "model": model,
        "response_schema_sha256": _payload_sha256(schema),
        **rendered.model_dump(exclude={"prompt"}),
    }
    if path.is_file():
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise ValueError("persisted corpus reader request binding differs")
    else:
        if (reader_output_dir / "output.json").exists():
            raise ValueError("reader output exists without a trusted request binding")
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    saved_prompt = reader_output_dir / "prompt.txt"
    if saved_prompt.is_file() and saved_prompt.read_text(encoding="utf-8") != rendered.prompt:
        raise ValueError("saved corpus reader prompt differs from request binding")
    output_exists = (reader_output_dir / "output.json").is_file()
    if output_exists and not saved_prompt.is_file():
        raise ValueError("reader output exists without its saved prompt")
    saved_schema = reader_output_dir / "schema.json"
    if output_exists and (
        not saved_schema.is_file()
        or json.loads(saved_schema.read_text(encoding="utf-8")) != schema
    ):
        raise ValueError("reader output schema differs from request binding")
    return path


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = [
    "CorpusReaderPrompts",
    "RenderedCorpusReaderPrompt",
    "build_corpus_reader_prompt",
    "load_corpus_reader_prompts",
    "write_reader_request_manifest",
]
