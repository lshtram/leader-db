"""Small artifact and usage helpers shared by Codex workers."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .codex_worker_command import read_codex_thread_id
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


def read_distinct_codex_usage(
    event_paths: tuple[Path, ...],
) -> tuple[DossierUsage, ...]:
    """Count cumulative Codex counters once per execution thread.

    Resumed calls emit cumulative snapshots for their shared thread. The largest
    snapshot represents that thread; adding all snapshots repeats earlier turns.
    A historical log without one valid thread identifier remains independent.
    """

    by_thread: dict[str, DossierUsage] = {}
    independent: list[DossierUsage] = []
    for events_path in event_paths:
        usage = read_codex_usage(events_path)
        if usage is None:
            continue
        try:
            thread_key = read_codex_thread_id(events_path)
        except (OSError, UnicodeError, ValueError):
            independent.append(usage)
            continue
        current = by_thread.get(thread_key)
        if current is None or _known_total(usage) > _known_total(current):
            by_thread[thread_key] = usage
    return (*by_thread.values(), *independent)


def _known_total(usage: DossierUsage) -> int:
    return int(usage.total_tokens) if isinstance(usage.total_tokens, int) else -1


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
    candidates: list[tuple[int, int, int, int, str, dict[str, Any]]] = []
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
    candidates.extend(_event_candidates(job_dir))
    if not candidates:
        return None
    selected = max(candidates, key=lambda item: item[:5])[5]
    selected_keys = {
        str(item.get("canonical_fact_key", ""))
        for item in selected.get("evidence", [])
        if isinstance(item, dict)
    }
    recovery_catalog: list[dict[str, Any]] = []
    catalog_keys: set[str] = set()
    for *_, payload in candidates:
        for item in payload.get("evidence", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("canonical_fact_key", "")).strip()
            if not key or key in selected_keys or key in catalog_keys:
                continue
            recovery_catalog.append(item)
            catalog_keys.add(key)
    if not recovery_catalog:
        return selected
    return selected | {"recovery_evidence_catalog": recovery_catalog}


def _json_agent_messages(events_path: Path) -> tuple[dict[str, Any], ...]:
    """Recover every parseable structured formatter response, not only the last."""

    recovered = []
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return ()
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = event.get("item")
        if (
            event.get("type") != "item.completed"
            or not isinstance(item, dict)
            or item.get("type") != "agent_message"
        ):
            continue
        try:
            payload = json.loads(str(item.get("text", "")))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            recovered.append(payload)
    return tuple(recovered)


def _event_candidates(
    job_dir: Path,
) -> list[tuple[int, int, int, int, str, dict[str, Any]]]:
    candidates = []
    for events_path in sorted((job_dir / "trusted").glob("*/codex-events.jsonl")):
        if not (events_path.parent / "formatter-complete.marker").is_file():
            continue
        for index, payload in enumerate(_json_agent_messages(events_path)):
            score = _candidate_integrity_score(payload)
            if score is not None:
                candidates.append(
                    (*score, f"{events_path}#agent-message-{index}", payload)
                )
    return candidates


def _candidate_integrity_score(
    payload: dict[str, Any],
) -> tuple[int, int, int, int] | None:
    """Score parseable candidates, retaining broken links for targeted repair."""

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
    evidence = tuple(
        parsed
        for item in raw_evidence
        if (parsed := _best_effort_validate(DossierEvidence, item)) is not None
    )
    mappings = tuple(
        parsed
        for item in raw_mappings
        if (parsed := _best_effort_validate(EvidenceQuestionMapping, item)) is not None
    )
    coverage = tuple(
        parsed
        for item in raw_coverage
        if (parsed := _best_effort_validate(QuestionCoverage, item)) is not None
    )
    declared_ids = {item.evidence_id for item in evidence}
    selected = {str(item) for item in raw_methodology_ids}
    coverage_ids = [item.methodology_id for item in coverage]
    if not selected:
        return None
    linked_ids = {
        item.evidence_id
        for item in mappings
        if item.evidence_id in declared_ids and item.methodology_id in selected
    }
    covered_selected = {item for item in coverage_ids if item in selected}
    environment = payload.get("evidence_environment")
    raw_support_ids = (
        environment.get("supporting_evidence_ids")
        if isinstance(environment, dict)
        else None
    )
    environment_supported = int(
        isinstance(raw_support_ids, list)
        and any(str(item) in declared_ids for item in raw_support_ids)
    )
    return len(linked_ids), len(covered_selected), len(evidence), environment_supported


def _best_effort_validate(model: Any, item: Any) -> Any | None:
    """Validate one receiver input without rejecting its useful siblings."""

    try:
        return model.model_validate(item)
    except (ValidationError, TypeError):
        return None


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
    "read_distinct_codex_usage",
    "write_local_priors",
]
