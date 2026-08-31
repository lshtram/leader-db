"""Correction and trusted-reload helpers for the citation-span experiment."""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field

from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .citation_spans import paragraph_spans, resolve_citation_span
from .model_profiles import load_research_model_profiles


class SpanCorrection(BaseModel):
    """One explicit correction to a contaminated diagnostic checkpoint."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    original: str = Field(min_length=1)
    corrected: str = Field(min_length=1)
    reason: str = Field(min_length=20)


class SpanCorrections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    corrections: tuple[SpanCorrection, ...]


def apply_span_corrections(baseline: dict, corrections_path: Path) -> dict:
    """Return a corrected copy while preserving the original baseline artifact."""

    config = SpanCorrections.model_validate(yaml.safe_load(corrections_path.read_bytes()))
    corrected = deepcopy(baseline)
    for correction in config.corrections:
        if corrected.get("evidence_id") != correction.evidence_id:
            raise ValueError("span correction evidence identity mismatch")
        if corrected.get("source_id") != correction.source_id:
            raise ValueError("span correction source identity mismatch")
        summary = corrected.get("fact_summary")
        if not isinstance(summary, str) or summary.count(correction.original) != 1:
            raise ValueError("span correction original text is not uniquely present")
        corrected["fact_summary"] = summary.replace(
            correction.original, correction.corrected, 1
        )
    return corrected


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


def validate_span_reader_experiment(
    *,
    project_root: Path,
    manifest_path: Path,
    extraction_path: Path,
    baseline: dict,
    corrections_path: Path,
    expected_profile_name: str,
    profiles_path: Path,
) -> dict:
    """Reconstruct a persisted reader experiment from its frozen inputs."""

    from .citation_span_experiment import BoundSpanFact, SpanReaderOutput

    manifest = json.loads(manifest_path.read_text())
    output_dir = manifest_path.parent
    corrected = apply_span_corrections(baseline, corrections_path)
    source_id = _required_string(corrected, "source_id")
    title = _required_string(corrected, "title")
    start_unit = _required_integer(corrected, "start_unit")
    end_unit = _required_integer(corrected, "end_unit")
    if end_unit < start_unit:
        raise ValueError("trusted span baseline source range is invalid")
    question_ids = tuple(corrected.get("question_ids", ()))
    limitations = corrected.get("limitations", ())
    if not isinstance(limitations, list) or not all(isinstance(item, str) for item in limitations):
        raise ValueError("trusted span baseline limitations are invalid")
    requirements = (_required_string(corrected, "fact_summary"), *limitations)
    profile = load_research_model_profiles(profiles_path).profiles[expected_profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("trusted span reader requires OpenAI Codex subscription")
    extraction = json.loads(extraction_path.read_text())
    if extraction.get("source_id") != source_id:
        raise ValueError("trusted span reader source identity mismatch")
    units = _validated_units(extraction)
    labels, rendered = _render_labels(units, start_unit, end_unit)
    config_path = project_root / "configs/citation-span-prompts.yaml"
    config = yaml.safe_load(config_path.read_bytes())
    prompt = config["reader_template"].format(
        questions=json.dumps(question_ids),
        baseline_requirements=json.dumps(requirements, ensure_ascii=False),
        source_id=source_id,
        title=title,
        spans="\n\n".join(rendered),
    )
    if (output_dir / "prompt.txt").read_text() != prompt:
        raise ValueError("trusted span reader prompt mismatch")
    output = SpanReaderOutput.model_validate_json((output_dir / "output.json").read_text())
    bound = []
    for fact in output.facts:
        if not set(fact.question_ids).issubset(question_ids):
            raise ValueError("trusted span reader contains an unknown question ID")
        if len(fact.span_ids) != len(set(fact.span_ids)) or not set(fact.span_ids) <= labels.keys():
            raise ValueError("trusted span reader contains invalid span IDs")
        spans = tuple(labels[label][0] for label in fact.span_ids)
        excerpts = tuple(
            resolve_citation_span(labels[label][1], labels[label][0])
            for label in fact.span_ids
        )
        bound.append(BoundSpanFact(fact=fact, spans=spans, exact_excerpts=excerpts))
    _validate_schema(output_dir / "schema.json", SpanReaderOutput)
    expected = {
        "schema_version": "citation_span_reader_experiment_v2",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": expected_profile_name,
        "model": profile.model,
        "source_id": source_id,
        "unit_range": [start_unit, end_unit],
        "question_ids": list(question_ids),
        "prompt_config_sha256": file_sha256(config_path),
        "profile_config_sha256": file_sha256(profiles_path),
        "extraction_sha256": file_sha256(extraction_path),
        "baseline_sha256": payload_sha256(baseline),
        "corrected_baseline_sha256": payload_sha256(corrected),
        "corrections_sha256": file_sha256(corrections_path),
        "title": title,
        "baseline_requirements": list(requirements),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "output_sha256": payload_sha256(output.model_dump(mode="json")),
        "response_schema_sha256": payload_sha256(
            json.loads((output_dir / "schema.json").read_text())
        ),
        "estimated_input_tokens": _estimate_tokens(prompt),
        "fact_count": len(bound),
        "bound_facts": [item.model_dump(mode="json") for item in bound],
    }
    if manifest != expected:
        raise ValueError("trusted span reader manifest does not reconstruct")
    return manifest


def validate_span_quality_comparison(
    *,
    project_root: Path,
    manifest_path: Path,
    baseline: dict,
    corrections_path: Path,
    reader_manifest_path: Path,
    extraction_path: Path,
    reader_profile_name: str,
    expected_profile_name: str,
    profiles_path: Path,
) -> dict:
    """Reconstruct a comparison and derive its conclusion from structured dimensions."""

    from .citation_span_experiment import SpanComparison

    reader = validate_span_reader_experiment(
        project_root=project_root,
        manifest_path=reader_manifest_path,
        extraction_path=extraction_path,
        baseline=baseline,
        corrections_path=corrections_path,
        expected_profile_name=reader_profile_name,
        profiles_path=profiles_path,
    )
    manifest = json.loads(manifest_path.read_text())
    output_dir = manifest_path.parent
    profile = load_research_model_profiles(profiles_path).profiles[expected_profile_name]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("trusted span comparison requires OpenAI Codex subscription")
    corrected = apply_span_corrections(baseline, corrections_path)
    config_path = project_root / "configs/citation-span-prompts.yaml"
    config = yaml.safe_load(config_path.read_bytes())
    prompt = config["review_template"].format(
        baseline=json.dumps(corrected, ensure_ascii=False),
        experimental=json.dumps(reader["bound_facts"], ensure_ascii=False),
    )
    if (output_dir / "prompt.txt").read_text() != prompt:
        raise ValueError("trusted span comparison prompt mismatch")
    comparison = SpanComparison.model_validate_json((output_dir / "output.json").read_text())
    _validate_schema(output_dir / "schema.json", SpanComparison)
    dimensions = (
        comparison.factual_accuracy,
        comparison.material_coverage,
        comparison.balance,
        comparison.routing_and_attribution,
        comparison.locator_fidelity,
    )
    gate = (
        "pass"
        if all(value == "pass" for value in dimensions) and not comparison.material_omissions
        else "fail"
    )
    expected = {
        "schema_version": "citation_span_comparison_v2",
        "production_status": "diagnostic_only",
        "api_key_used": False,
        "profile": expected_profile_name,
        "model": profile.model,
        "baseline_sha256": payload_sha256(baseline),
        "corrected_baseline_sha256": payload_sha256(corrected),
        "corrections_sha256": file_sha256(corrections_path),
        "reader_manifest_sha256": file_sha256(reader_manifest_path),
        "prompt_config_sha256": file_sha256(config_path),
        "profile_config_sha256": file_sha256(profiles_path),
        "prompt_sha256": sha256(prompt.encode()).hexdigest(),
        "output_sha256": payload_sha256(comparison.model_dump(mode="json")),
        "response_schema_sha256": payload_sha256(
            json.loads((output_dir / "schema.json").read_text())
        ),
        "estimated_input_tokens": _estimate_tokens(prompt),
        "quality_gate": gate,
    }
    if manifest != expected:
        raise ValueError("trusted span comparison manifest does not reconstruct")
    return manifest


def _validated_units(extraction: dict) -> dict[int, str]:
    rows = extraction.get("units")
    if not isinstance(rows, list):
        raise ValueError("trusted span extraction units are invalid")
    units: dict[int, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("trusted span extraction unit is invalid")
        unit, text = row.get("unit"), row.get("text")
        if type(unit) is not int or unit < 1 or unit in units or not isinstance(text, str):
            raise ValueError("trusted span extraction contains malformed units")
        units[unit] = text
    return units


def _render_labels(
    units: dict[int, str], start_unit: int, end_unit: int
) -> tuple[dict[str, tuple[object, str]], list[str]]:
    labels: dict[str, tuple[object, str]] = {}
    rendered = []
    for unit in range(start_unit, end_unit + 1):
        if unit not in units:
            raise ValueError("trusted span reader source range is incomplete")
        text = units[unit]
        for number, span in enumerate(paragraph_spans(unit, text), start=1):
            label = f"U{unit}-P{number}"
            labels[label] = (span, text)
            rendered.append(f"[{label}] {resolve_citation_span(text, span)}")
    if not rendered:
        raise ValueError("trusted span source range contains no text spans")
    return labels, rendered


def _validate_schema(path: Path, schema_type: type[BaseModel]) -> None:
    saved = json.loads(path.read_text())
    expected = schema_type.model_json_schema()
    make_strict_response_schema(expected)
    if saved != expected:
        raise ValueError("trusted span response schema mismatch")


def _estimate_tokens(text: str) -> int:
    return len(tiktoken.get_encoding("o200k_base").encode(text))


def _required_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"trusted span baseline {key} is invalid")
    return value


def _required_integer(payload: dict, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise ValueError(f"trusted span baseline {key} is invalid")
    return value


__all__ = [
    "SpanCorrection",
    "SpanCorrections",
    "apply_span_corrections",
    "validate_span_quality_comparison",
    "validate_span_reader_experiment",
]
