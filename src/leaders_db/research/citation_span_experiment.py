"""Bounded paragraph-span reader experiment over one frozen source slice."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from leaders_db.conversational_evidence.judging import CODEX_INPUT_CHARACTER_LIMIT
from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .citation_span_validation import apply_span_corrections
from .citation_spans import CitationSpan, paragraph_spans, resolve_citation_span
from .corpus_reader_runner import execute_json_model
from .model_profiles import load_research_model_profiles


class SpanFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_summary: str = Field(min_length=10)
    question_ids: tuple[str, ...] = Field(min_length=1)
    polarity: Literal["favorable", "adverse", "mixed", "exculpatory", "context"]
    period_fit: str = Field(min_length=10)
    ruler_attribution: str = Field(min_length=10)
    limitations: tuple[str, ...] = ()
    span_ids: tuple[str, ...] = Field(min_length=1)


class SpanReaderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: tuple[SpanFact, ...] = Field(min_length=1)
    slice_limitations: tuple[str, ...] = ()


class BoundSpanFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact: SpanFact
    spans: tuple[CitationSpan, ...]
    exact_excerpts: tuple[str, ...]

    @model_validator(mode="after")
    def validate_alignment(self) -> BoundSpanFact:
        if len(self.spans) != len(self.exact_excerpts):
            raise ValueError("bound span facts must preserve span/excerpt alignment")
        return self


class SpanComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factual_accuracy: Literal["pass", "fail"]
    material_coverage: Literal["pass", "fail"]
    balance: Literal["pass", "fail"]
    routing_and_attribution: Literal["pass", "fail"]
    locator_fidelity: Literal["pass", "fail"]
    material_omissions: tuple[str, ...] = ()
    rationale: str = Field(min_length=30)


def run_span_reader_experiment(
    *,
    project_root: Path,
    extraction_path: Path,
    baseline: dict,
    corrections_path: Path,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Run one paragraph-addressed reader call and bind exact substrings."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("citation-span experiment output directory is already in use")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("citation-span experiment requires OpenAI Codex subscription")
    corrected_baseline = apply_span_corrections(baseline, corrections_path)
    source_id = _required_string(corrected_baseline, "source_id")
    title = _required_string(corrected_baseline, "title")
    start_unit = _required_integer(corrected_baseline, "start_unit")
    end_unit = _required_integer(corrected_baseline, "end_unit")
    question_ids = tuple(corrected_baseline.get("question_ids", ()))
    limitations = corrected_baseline.get("limitations", ())
    if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
        raise ValueError("citation-span baseline limitations are invalid")
    baseline_requirements = (
        _required_string(corrected_baseline, "fact_summary"),
        *limitations,
    )
    extraction = json.loads(extraction_path.read_text())
    selected = _selected_units(extraction, source_id, start_unit, end_unit)
    allowed_question_ids = {
        f"{chapter}B.{question}" for chapter in range(1, 9) for question in range(1, 11)
    }
    if not question_ids or not set(question_ids).issubset(allowed_question_ids):
        raise ValueError("citation-span experiment question IDs are invalid")
    labels = {}
    rendered = []
    for unit, text in selected.items():
        for number, span in enumerate(paragraph_spans(unit, text), start=1):
            label = f"U{unit}-P{number}"
            labels[label] = (span, text)
            rendered.append(f"[{label}] {resolve_citation_span(text, span)}")
    if not rendered:
        raise ValueError("citation-span experiment source range contains no text spans")
    config_path = project_root / "configs/citation-span-prompts.yaml"
    config_bytes = config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    prompt = config["reader_template"].format(
        questions=json.dumps(question_ids),
        baseline_requirements=json.dumps(baseline_requirements, ensure_ascii=False),
        source_id=source_id,
        title=title,
        spans="\n\n".join(rendered),
    )
    tokens = _estimate_tokens(prompt)
    if len(prompt) > int(CODEX_INPUT_CHARACTER_LIMIT * 0.9):
        raise ValueError("citation-span experiment exceeds character safety margin")
    if profile.context_window is None or tokens + 12_000 > int(profile.context_window * 0.9):
        raise ValueError("citation-span experiment exceeds context safety margin")
    output = execute_json_model(project_root, profile, prompt, SpanReaderOutput, output_dir)
    allowed_questions = set(question_ids)
    bound = []
    for fact in output.facts:
        if not set(fact.question_ids).issubset(allowed_questions):
            raise ValueError("span reader introduced an unknown question ID")
        if len(fact.span_ids) != len(set(fact.span_ids)) or not set(fact.span_ids).issubset(labels):
            raise ValueError("span reader introduced an invalid or duplicate span ID")
        spans = tuple(labels[label][0] for label in fact.span_ids)
        excerpts = tuple(
            resolve_citation_span(labels[label][1], labels[label][0]) for label in fact.span_ids
        )
        bound.append(BoundSpanFact(fact=fact, spans=spans, exact_excerpts=excerpts))
    manifest = {
        "schema_version": "citation_span_reader_experiment_v2",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": profile_name,
        "model": profile.model,
        "source_id": source_id,
        "unit_range": [start_unit, end_unit],
        "question_ids": list(question_ids),
        "prompt_config_sha256": sha256(config_bytes).hexdigest(),
        "profile_config_sha256": sha256(profiles_path.read_bytes()).hexdigest(),
        "extraction_sha256": sha256(extraction_path.read_bytes()).hexdigest(),
        "baseline_sha256": _payload_hash(baseline),
        "corrected_baseline_sha256": _payload_hash(corrected_baseline),
        "corrections_sha256": sha256(corrections_path.read_bytes()).hexdigest(),
        "title": title,
        "baseline_requirements": list(baseline_requirements),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "output_sha256": _payload_hash(output.model_dump(mode="json")),
        "response_schema_sha256": _saved_schema_hash(output_dir, SpanReaderOutput),
        "estimated_input_tokens": tokens,
        "fact_count": len(bound),
        "bound_facts": [item.model_dump(mode="json") for item in bound],
    }
    path = output_dir / "span-reader-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def run_span_quality_comparison(
    *,
    project_root: Path,
    baseline: dict,
    corrections_path: Path,
    reader_manifest_path: Path,
    extraction_path: Path,
    reader_profile_name: str,
    output_dir: Path,
    profile_name: str,
    profiles_path: Path,
) -> Path:
    """Independently compare the bounded baseline and paragraph-span result once."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("span comparison output directory is already in use")
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("span comparison requires OpenAI Codex subscription")
    from .citation_span_validation import validate_span_reader_experiment

    corrected_baseline = apply_span_corrections(baseline, corrections_path)
    trusted_reader = validate_span_reader_experiment(
        project_root=project_root,
        manifest_path=reader_manifest_path,
        extraction_path=extraction_path,
        baseline=baseline,
        corrections_path=corrections_path,
        expected_profile_name=reader_profile_name,
        profiles_path=profiles_path,
    )
    config_bytes = (project_root / "configs/citation-span-prompts.yaml").read_bytes()
    config = yaml.safe_load(config_bytes)
    prompt = config["review_template"].format(
        baseline=json.dumps(corrected_baseline, ensure_ascii=False),
        experimental=json.dumps(trusted_reader["bound_facts"], ensure_ascii=False),
    )
    tokens = _estimate_tokens(prompt)
    if len(prompt) > int(CODEX_INPUT_CHARACTER_LIMIT * 0.9):
        raise ValueError("span comparison exceeds character safety margin")
    if profile.context_window is None or tokens + 8_000 > int(profile.context_window * 0.9):
        raise ValueError("span comparison exceeds context safety margin")
    comparison = execute_json_model(project_root, profile, prompt, SpanComparison, output_dir)
    dimensions = (
        comparison.factual_accuracy,
        comparison.material_coverage,
        comparison.balance,
        comparison.routing_and_attribution,
        comparison.locator_fidelity,
    )
    quality_gate = (
        "pass"
        if all(item == "pass" for item in dimensions) and not comparison.material_omissions
        else "fail"
    )
    manifest = {
        "schema_version": "citation_span_comparison_v2",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": profile_name,
        "model": profile.model,
        "baseline_sha256": _payload_hash(baseline),
        "corrected_baseline_sha256": _payload_hash(corrected_baseline),
        "corrections_sha256": sha256(corrections_path.read_bytes()).hexdigest(),
        "reader_manifest_sha256": sha256(reader_manifest_path.read_bytes()).hexdigest(),
        "prompt_config_sha256": sha256(config_bytes).hexdigest(),
        "profile_config_sha256": sha256(profiles_path.read_bytes()).hexdigest(),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "output_sha256": _payload_hash(comparison.model_dump(mode="json")),
        "response_schema_sha256": _saved_schema_hash(output_dir, SpanComparison),
        "estimated_input_tokens": tokens,
        "quality_gate": quality_gate,
    }
    path = output_dir / "span-comparison-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def _payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def _estimate_tokens(text: str) -> int:
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def _required_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"citation-span baseline {key} is invalid")
    return value


def _required_integer(payload: dict, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise ValueError(f"citation-span baseline {key} is invalid")
    return value


def _selected_units(
    extraction: object, source_id: str, start_unit: int, end_unit: int
) -> dict[int, str]:
    if start_unit < 1 or end_unit < start_unit:
        raise ValueError("citation-span experiment source range is invalid")
    if not isinstance(extraction, dict) or extraction.get("source_id") != source_id:
        raise ValueError("citation-span extraction source identity mismatch")
    rows = extraction.get("units")
    if not isinstance(rows, list):
        raise ValueError("citation-span extraction units are invalid")
    units: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("citation-span extraction contains malformed units")
        unit, text = row.get("unit"), row.get("text")
        if type(unit) is not int or unit < 1 or unit in units or not isinstance(text, str):
            raise ValueError("citation-span extraction contains malformed units")
        units[unit] = text
    selected = {unit: units[unit] for unit in range(start_unit, end_unit + 1) if unit in units}
    if len(selected) != end_unit - start_unit + 1:
        raise ValueError("citation-span experiment source range is incomplete")
    return selected


def _saved_schema_hash(output_dir: Path, schema_type: type[BaseModel]) -> str:
    saved = json.loads((output_dir / "schema.json").read_text())
    expected = schema_type.model_json_schema()
    make_strict_response_schema(expected)
    if saved != expected:
        raise ValueError("saved span experiment schema differs from current contract")
    return _payload_hash(saved)


__all__ = [
    "BoundSpanFact",
    "SpanComparison",
    "SpanReaderOutput",
    "run_span_quality_comparison",
    "run_span_reader_experiment",
]
