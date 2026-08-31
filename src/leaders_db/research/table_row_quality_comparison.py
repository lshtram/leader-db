"""One-call quality comparison for exact statistical-table rows."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

import tiktoken
import yaml
from pydantic import BaseModel, ConfigDict, Field

from leaders_db.conversational_evidence.judging import CODEX_INPUT_CHARACTER_LIMIT
from leaders_db.evidence_funnel.execution_schema import make_strict_response_schema

from .citation_table_rows import resolve_table_line, table_line_spans
from .corpus_reader_runner import execute_json_model
from .model_profiles import load_research_model_profiles


class TableValueInterpretation(BaseModel):
    """One interpreted value with its exact table meaning and citations."""

    model_config = ConfigDict(extra="forbid")

    value_percent: float
    population: str = Field(min_length=3)
    column_meaning: str = Field(min_length=3)
    statistic: str = Field(min_length=3)
    unit_of_measure: str = Field(min_length=3)
    citation_line_ids: tuple[str, ...] = Field(min_length=1)


class TableRowQualityOutput(BaseModel):
    """The single model result used by the deterministic quality gate."""

    model_config = ConfigDict(extra="forbid")

    owner_occupied: TableValueInterpretation
    rented_total: TableValueInterpretation
    jewish_total: TableValueInterpretation
    arab_total: TableValueInterpretation
    limitations: tuple[str, ...] = Field(min_length=1)
    ruler_causal_attribution: Literal["none", "present"]
    summary: str = Field(min_length=30)


def prepare_table_row_quality_request(
    *, project_root: Path, config_path: Path, profiles_path: Path
) -> dict:
    """Reconstruct the bounded prompt and its complete preflight metadata."""

    config_bytes = config_path.read_bytes()
    config = yaml.safe_load(config_bytes)
    measurement_path = project_root / config["measurement_path"]
    measurement = json.loads(measurement_path.read_text())
    extraction_path = project_root / measurement["extraction_path"]
    if sha256(extraction_path.read_bytes()).hexdigest() != measurement["extraction_sha256"]:
        raise ValueError("table-row extraction hash differs from Task 1")
    predecessor_path = project_root / measurement["predecessor_verified_evidence_path"]
    if sha256(predecessor_path.read_bytes()).hexdigest() != measurement[
        "predecessor_verified_evidence_sha256"
    ]:
        raise ValueError("table-row predecessor hash differs from Task 1")
    extraction = json.loads(extraction_path.read_text())
    if extraction.get("source_id") != config["source_id"]:
        raise ValueError("table-row quality source identity mismatch")
    units = {row["unit"]: row["text"] for row in extraction["units"]}
    rendered: list[str] = []
    line_bindings: list[dict] = []
    for selection in config["units"]:
        unit = selection["unit"]
        spans = {
            span.line_number: span
            for span in table_line_spans(config["source_id"], unit, units[unit])
        }
        for line_number in selection["line_numbers"]:
            if line_number not in spans:
                raise ValueError("configured table-row quality line does not exist")
            span = spans[line_number]
            line_id = f"U{unit}-L{line_number}"
            exact = resolve_table_line(
                units[unit], span, expected_source_id=config["source_id"], expected_unit=unit
            )
            rendered.append(f"[{line_id}] {exact}")
            line_bindings.append({
                "line_id": line_id,
                "span": span.model_dump(mode="json"),
                "exact_text": exact,
            })
    prompt_path = project_root / "configs/table-row-quality-prompts.yaml"
    prompt_bytes = prompt_path.read_bytes()
    template = yaml.safe_load(prompt_bytes)["template"]
    prompt = template.format(
        source_id=config["source_id"],
        source_title=config["source_title"],
        lines="\n".join(rendered),
    )
    profile_name = config["profile_name"]
    profile = load_research_model_profiles(profiles_path).profiles[profile_name]
    estimated_tokens = len(tiktoken.get_encoding("o200k_base").encode(prompt))
    if len(prompt) > int(CODEX_INPUT_CHARACTER_LIMIT * 0.9):
        raise ValueError("table-row quality request exceeds character safety margin")
    if profile.context_window is None or estimated_tokens + 4_000 > int(
        profile.context_window * 0.9
    ):
        raise ValueError("table-row quality request exceeds context safety margin")
    return {
        "config": config,
        "profile": profile,
        "profile_name": profile_name,
        "prompt": prompt,
        "estimated_input_tokens": estimated_tokens,
        "line_bindings": line_bindings,
        "config_sha256": sha256(config_bytes).hexdigest(),
        "prompt_config_sha256": sha256(prompt_bytes).hexdigest(),
        "profiles_sha256": sha256(profiles_path.read_bytes()).hexdigest(),
        "measurement_path": measurement_path,
        "measurement_sha256": sha256(measurement_path.read_bytes()).hexdigest(),
        "extraction_path": extraction_path,
        "extraction_sha256": measurement["extraction_sha256"],
        "predecessor_path": predecessor_path,
        "predecessor_sha256": measurement["predecessor_verified_evidence_sha256"],
    }


def run_table_row_quality_comparison(
    *, project_root: Path, config_path: Path, profiles_path: Path, output_dir: Path
) -> Path:
    """Execute exactly one bounded Codex call and persist a reconstructable gate."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("table-row quality output directory is already in use")
    request = prepare_table_row_quality_request(
        project_root=project_root, config_path=config_path, profiles_path=profiles_path
    )
    profile = request["profile"]
    if profile.execution_surface != "codex" or profile.provider != "openai":
        raise ValueError("table-row quality comparison requires OpenAI Codex subscription")
    execute_json_model(
        project_root, profile, request["prompt"], TableRowQualityOutput, output_dir
    )
    return finalize_table_row_quality_comparison(
        project_root=project_root,
        config_path=config_path,
        profiles_path=profiles_path,
        output_dir=output_dir,
    )


def finalize_table_row_quality_comparison(
    *, project_root: Path, config_path: Path, profiles_path: Path, output_dir: Path
) -> Path:
    """Reconstruct and persist the gate without making another model call."""

    request = prepare_table_row_quality_request(
        project_root=project_root, config_path=config_path, profiles_path=profiles_path
    )
    profile = request["profile"]
    if (output_dir / "prompt.txt").read_text() != request["prompt"]:
        raise ValueError("saved table-row quality prompt does not reconstruct")
    result = TableRowQualityOutput.model_validate_json(
        (output_dir / "output.json").read_text()
    )
    saved_schema = json.loads((output_dir / "schema.json").read_text())
    expected_schema = TableRowQualityOutput.model_json_schema()
    make_strict_response_schema(expected_schema)
    if saved_schema != expected_schema:
        raise ValueError("saved table-row quality schema differs from current contract")
    gate, failures = _quality_gate(result, request["config"], request["line_bindings"])
    usage = _completed_usage(output_dir / "events.jsonl")
    compact_characters = sum(len(item["exact_text"]) for item in request["line_bindings"])
    paragraph_characters = json.loads(request["measurement_path"].read_text())[
        "known_fact_measurement"
    ]["like_for_like_paragraph_characters"]
    schema_characters = len(json.dumps(saved_schema, ensure_ascii=False, sort_keys=True))
    fixed_request_characters = len(request["prompt"]) - compact_characters
    compact_request_characters = len(request["prompt"]) + schema_characters
    paragraph_request_characters = (
        fixed_request_characters + paragraph_characters + schema_characters
    )
    manifest = {
        "schema_version": "table_row_quality_comparison_v1",
        "production_status": "diagnostic_only",
        "status": gate,
        "model_calls": 1,
        "api_key_used": False,
        "profile": request["profile_name"],
        "model": profile.model,
        "estimated_input_tokens": request["estimated_input_tokens"],
        "maximum_output_tokens": 4_000,
        "actual_input_tokens": usage["input_tokens"],
        "actual_cached_input_tokens": usage["cached_input_tokens"],
        "actual_output_tokens": usage["output_tokens"],
        "actual_reasoning_output_tokens": usage["reasoning_output_tokens"],
        "config_sha256": request["config_sha256"],
        "prompt_config_sha256": request["prompt_config_sha256"],
        "profiles_sha256": request["profiles_sha256"],
        "measurement_sha256": request["measurement_sha256"],
        "extraction_sha256": request["extraction_sha256"],
        "predecessor_sha256": request["predecessor_sha256"],
        "prompt_sha256": sha256(request["prompt"].encode()).hexdigest(),
        "output_sha256": _payload_sha256(result.model_dump(mode="json")),
        "response_schema_sha256": _payload_sha256(saved_schema),
        "line_bindings": request["line_bindings"],
        "compact_citation_characters": compact_characters,
        "paragraph_baseline_characters": paragraph_characters,
        "citation_payload_reduction_percent": round(
            (1 - compact_characters / paragraph_characters) * 100, 1
        ),
        "compact_serialized_request_characters": compact_request_characters,
        "paragraph_baseline_serialized_request_characters": paragraph_request_characters,
        "serialized_request_size_reduction_percent": round(
            (1 - compact_request_characters / paragraph_request_characters) * 100, 1
        ),
        "gate_failures": failures,
    }
    path = output_dir / "table-row-quality-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return path


def _completed_usage(path: Path) -> dict[str, int]:
    completed = [
        json.loads(line)["usage"]
        for line in path.read_text().splitlines()
        if json.loads(line).get("type") == "turn.completed"
    ]
    if len(completed) != 1:
        raise ValueError("table-row quality run must contain exactly one completed call")
    usage = completed[0]
    required = (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
    )
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in required):
        raise ValueError("table-row quality usage is incomplete")
    return {key: usage[key] for key in required}


def _quality_gate(
    result: TableRowQualityOutput, config: dict, bindings: list[dict]
) -> tuple[str, list[str]]:
    baseline = config["corrected_baseline"]
    allowed_ids = {item["line_id"] for item in bindings}
    expected = (
        (
            "owner_occupied",
            result.owner_occupied,
            baseline["owner_occupied_employment_percent"],
        ),
        (
            "rented_total",
            result.rented_total,
            baseline["rented_total_employment_percent"],
        ),
        (
            "jewish_total",
            result.jewish_total,
            baseline["jewish_total_employment_percent"],
        ),
        (
            "arab_total",
            result.arab_total,
            baseline["arab_total_employment_percent"],
        ),
    )
    failures: list[str] = []
    semantic_gate = config["semantic_gate"]
    for name, item, value in expected:
        if item.value_percent != value:
            failures.append(f"{name} value differs from corrected baseline")
        rules = semantic_gate[name]
        if not _contains_all(item.column_meaning, rules["column_terms"]):
            failures.append(f"{name} column meaning is ambiguous")
        if not _contains_all(item.population, rules["population_terms"]):
            failures.append(f"{name} population label is incomplete")
        if item.statistic.casefold() != baseline["statistic"].casefold() or not (
            item.unit_of_measure.casefold().startswith("percent")
            and baseline["unit_of_measure"].casefold().startswith("percent")
        ):
            failures.append(f"{name} statistic or unit is incorrect")
        if not set(item.citation_line_ids) <= allowed_ids:
            failures.append(f"{name} cites an unknown exact line")
        if not set(rules["required_citation_line_ids"]) <= set(item.citation_line_ids):
            failures.append(f"{name} omits required header, context, or value citations")
    limitations = " ".join(result.limitations).lower()
    if result.ruler_causal_attribution != "none":
        failures.append("ruler-specific causal limitation is missing")
    for terms in semantic_gate["limitation_term_groups"]:
        if not all(str(term).casefold() in limitations for term in terms):
            failures.append(
                "required limitation meaning is missing: " + ", ".join(terms)
            )
    return ("passed" if not failures else "rejected", failures)


def _contains_all(value: str, terms: list[str]) -> bool:
    normalized = value.casefold()
    return all(str(term).casefold() in normalized for term in terms)


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode()).hexdigest()


__all__ = [
    "TableRowQualityOutput",
    "finalize_table_row_quality_comparison",
    "prepare_table_row_quality_request",
    "run_table_row_quality_comparison",
]
