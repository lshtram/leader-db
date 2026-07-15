"""Small artifact and usage helpers shared by Codex workers."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .costing import load_research_pricing, price_usage
from .dossier_models import (
    DossierEvidence,
    DossierLocalPrior,
    DossierUsage,
    EvidenceQuestionMapping,
    QuestionCoverage,
)


def read_codex_usage(events_path: Path) -> DossierUsage | None:
    """Read final exposed usage counters from a Codex JSONL log."""

    if not events_path.is_file():
        return None
    usage: dict[str, Any] | None = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
    if usage is None:
        return None
    input_tokens = int(usage.get("input_tokens", 0))
    cached_input_tokens = int(usage.get("cached_input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    reasoning_output_tokens = int(usage.get("reasoning_output_tokens", 0))
    if min(input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens) < 0:
        raise ValueError("token counters cannot be negative")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")
    if reasoning_output_tokens > output_tokens:
        raise ValueError("reasoning output tokens cannot exceed output tokens")
    return DossierUsage(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        uncached_input_tokens=input_tokens - cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=input_tokens + output_tokens,
        estimated_cost_usd="unknown_not_exposed_by_tool",
    )


def price_codex_usage(
    usage: DossierUsage, *, provider: str, model: str
) -> DossierUsage:
    """Attach the checked-in rate-card equivalent to trusted Codex counters."""

    pricing_path = Path(__file__).parents[3] / "configs" / "research-pricing.yaml"
    pricing = load_research_pricing(pricing_path)
    priced = price_usage(
        usage,
        provider=provider,
        model=model,
        pricing=pricing,
        parallel_searches=0,
    )
    return priced.model_copy(
        update={
            "pricing_sha256": sha256(pricing_path.read_bytes()).hexdigest(),
            "pricing_effective_date": pricing.effective_date,
        }
    )


def find_previous_candidate(job_dir: Path, *, attempt_dir: Path) -> dict[str, Any] | None:
    """Find the most information-preserving completed formatter candidate."""

    paths = tuple((job_dir / "attempts").glob("*/dossier.pending.json")) + tuple(
        (job_dir / "attempts").glob("*/dossier.json")
    )
    candidates: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for path in sorted(paths, reverse=True):
        if path.parent == attempt_dir:
            continue
        marker = job_dir / "trusted" / path.parent.name / "formatter-complete.marker"
        if not marker.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            score = _candidate_integrity_score(payload)
            if score is None:
                continue
            candidates.append(
                (*score, str(path), payload)
            )
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[:4])[4]


def _candidate_integrity_score(payload: dict[str, Any]) -> tuple[int, int, int] | None:
    """Score only structurally valid, internally linked formatter candidates."""

    raw_evidence = payload.get("evidence")
    raw_mappings = payload.get("mappings")
    raw_coverage = payload.get("coverage")
    raw_methodology_ids = payload.get("methodology_ids")
    has_list_contract = all(
        isinstance(value, list)
        for value in (raw_evidence, raw_mappings, raw_coverage, raw_methodology_ids)
    )
    if not has_list_contract:
        return None
    try:
        evidence = tuple(DossierEvidence.model_validate(item) for item in raw_evidence)
        mappings = tuple(EvidenceQuestionMapping.model_validate(item) for item in raw_mappings)
        coverage = tuple(QuestionCoverage.model_validate(item) for item in raw_coverage)
    except (ValidationError, TypeError):
        return None
    declared_ids = {item.evidence_id for item in evidence}
    selected = {str(item) for item in raw_methodology_ids}
    mappings_valid = not any(
        item.evidence_id not in declared_ids or item.methodology_id not in selected
        for item in mappings
    )
    coverage_ids = [item.methodology_id for item in coverage]
    coverage_valid = (
        len(coverage_ids) == len(selected)
        and set(coverage_ids) == selected
        and not any(
            evidence_id not in declared_ids
            for item in coverage
            for evidence_id in item.evidence_ids
        )
    )
    if (
        len(declared_ids) != len(evidence)
        or not selected
        or not mappings_valid
        or not coverage_valid
    ):
        return None
    linked_ids = {item.evidence_id for item in mappings}
    return len(linked_ids), len(coverage_ids), len(evidence)


def write_local_priors(
    job_dir: Path, local_priors: tuple[dict[str, Any], ...]
) -> tuple[DossierLocalPrior, ...]:
    """Persist and hash the exact locally extracted prior package."""

    path = job_dir / "local-priors.json"
    encoded = json.dumps(local_priors, indent=2, sort_keys=True).encode()
    with path.open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    digest = sha256(encoded).hexdigest()
    return tuple(
        DossierLocalPrior(
            methodology_id=str(item.get("methodology_id")),
            status=str(item.get("status")),
            summary=(
                f"status={item.get('status')}; local_fact_count="
                f"{len(item.get('local_facts', []))}; "
                f"mapping_note={item.get('mapping_note')}; "
                f"missing_reason={item.get('missing_or_empty_reason')}"
            ),
            artifact_path=str(path),
            artifact_sha256=digest,
        )
        for item in local_priors
    )


__all__ = [
    "find_previous_candidate",
    "price_codex_usage",
    "read_codex_usage",
    "write_local_priors",
]
