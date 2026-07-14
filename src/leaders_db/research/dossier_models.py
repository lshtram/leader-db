"""Validated handoff artifacts for one ruler-period evidence dossier."""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CoverageStatus = Literal[
    "covered",
    "partially_covered",
    "no_evidence_found",
    "not_applicable",
    "research_blocked",
]
EvidenceRelation = Literal["supports", "contradicts", "mitigates", "context"]
EvidenceId = Annotated[str, Field(pattern=r"^E[0-9]{3,}$")]


class DossierEvidence(BaseModel):
    """One deduplicated cited claim reusable across questions."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: EvidenceId
    claim: str = Field(min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    publication_date: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_confidence: str = Field(min_length=1)
    source_confidence_reason: str = Field(min_length=1)
    final_evidence_use: Literal["final_evidence", "context", "discovery_only"]
    period_fit: str = Field(min_length=1)
    ruler_attribution: str = Field(min_length=1)
    contrary_evidence: tuple[str, ...] = ()


class EvidenceQuestionMapping(BaseModel):
    """Many-to-many link from one evidence item to one methodology question."""

    model_config = ConfigDict(extra="ignore")

    evidence_id: EvidenceId
    methodology_id: str
    relation: EvidenceRelation
    relevance: str = Field(min_length=1)


class QuestionCoverage(BaseModel):
    """Terminal evidence-coverage disposition for one selected question."""

    model_config = ConfigDict(extra="ignore")

    methodology_id: str
    status: CoverageStatus
    evidence_ids: tuple[EvidenceId, ...] = ()
    reason: str = Field(min_length=1)


class DossierUsage(BaseModel):
    """Provider usage fields without an unrestricted structured-output object."""

    model_config = ConfigDict(extra="ignore")

    input_tokens: int | Literal["unknown_not_exposed_by_tool"]
    cached_input_tokens: int | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    uncached_input_tokens: int | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    cache_write_input_tokens: int | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    output_tokens: int | Literal["unknown_not_exposed_by_tool"]
    reasoning_output_tokens: int | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    total_tokens: int | Literal["unknown_not_exposed_by_tool"]
    estimated_cost_usd: float | Literal["unknown_not_exposed_by_tool"]
    payg_equivalent_cost_usd_lower: float | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    payg_equivalent_cost_usd_upper: float | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    codex_equivalent_credits_lower: float | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    codex_equivalent_credits_upper: float | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    parallel_search_cost_usd: float | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    actual_billed_cost_usd: float | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    pricing_version: int | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    pricing_sha256: str | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    pricing_effective_date: str | Literal["unknown_not_exposed_by_tool"] = (
        "unknown_not_exposed_by_tool"
    )
    cost_certainty: Literal["exact", "range", "unknown"] = "unknown"

    @model_validator(mode="after")
    def _validate_token_counters(self) -> DossierUsage:
        counters = (
            self.input_tokens,
            self.cached_input_tokens,
            self.uncached_input_tokens,
            self.cache_write_input_tokens,
            self.output_tokens,
            self.reasoning_output_tokens,
            self.total_tokens,
        )
        if any(isinstance(value, int) and value < 0 for value in counters):
            raise ValueError("token counters cannot be negative")
        return self


class DossierLocalPrior(BaseModel):
    """Parent-produced local-prior provenance echoed into the handoff."""

    model_config = ConfigDict(extra="ignore")

    methodology_id: str
    status: str
    summary: str
    artifact_path: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DossierRunProfile(BaseModel):
    """Auditable execution metadata exposed by the worker."""

    model_config = ConfigDict(extra="ignore")

    provider_profile: str
    provider: str
    model: str
    workflow_mode: str = "direct_search_chapter_loop_v1"
    formatter_provider_profile: str | None = None
    formatter_provider: str | None = None
    formatter_model: str | None = None
    reviewer_provider_profile: str | None = None
    reviewer_provider: str | None = None
    reviewer_model: str | None = None
    research_notebook_path: str | None = None
    research_notebook_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    local_evidence_calls: tuple[str, ...] = ()
    searches_attempted: tuple[str, ...] = ()
    sources_visited: tuple[str, ...] = ()
    source_mix_note: str = Field(min_length=1)
    usage: DossierUsage
    research_usage: DossierUsage | None = None
    reviewer_usage: DossierUsage | None = None
    formatter_usage: DossierUsage | None = None


class RulerEvidenceDossier(BaseModel):
    """Complete non-score-bearing evidence handoff for one ruler-period."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["ruler_evidence_dossier_v2"]
    job_key: str
    run_key: str
    iso3: str = Field(min_length=3, max_length=3)
    country_name: str
    ruler_id: str
    ruler_year_id: int
    ruler_name: str
    period_start_year: int
    period_end_year: int
    methodology_ids: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[DossierEvidence, ...]
    mappings: tuple[EvidenceQuestionMapping, ...]
    coverage: tuple[QuestionCoverage, ...]
    unresolved_gaps: tuple[str, ...] = ()
    completed_queries: tuple[str, ...] = ()
    normalization_warnings: tuple[str, ...] = ()
    local_priors: tuple[DossierLocalPrior, ...] = Field(min_length=1)
    run_profile: DossierRunProfile

    @model_validator(mode="after")
    def _validate_references_and_scope(self) -> RulerEvidenceDossier:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        known = set(evidence_ids)
        selected = set(self.methodology_ids)
        if {item.methodology_id for item in self.local_priors} != selected:
            raise ValueError("local-prior provenance must cover every selected methodology ID")
        coverage_ids = [item.methodology_id for item in self.coverage]
        if set(coverage_ids) != selected or len(coverage_ids) != len(selected):
            raise ValueError("coverage must contain each selected methodology ID exactly once")
        for mapping in self.mappings:
            if mapping.evidence_id not in known or mapping.methodology_id not in selected:
                raise ValueError("mapping references unknown evidence or methodology ID")
        for item in self.coverage:
            if not set(item.evidence_ids).issubset(known):
                raise ValueError("coverage references an unknown evidence ID")
        return self


def codex_dossier_json_schema() -> dict[str, Any]:
    """Return the strict-output variant required by Codex response schemas."""

    schema = RulerEvidenceDossier.model_json_schema()
    _remove_server_owned_usage_fields(schema)
    _require_every_property(schema)
    return schema


def _remove_server_owned_usage_fields(schema: dict[str, Any]) -> None:
    usage = schema.get("$defs", {}).get("DossierUsage", {})
    properties = usage.get("properties")
    if not isinstance(properties, dict):
        return
    model_fields = {"input_tokens", "output_tokens", "total_tokens", "estimated_cost_usd"}
    for field_name in tuple(properties):
        if field_name not in model_fields:
            properties.pop(field_name)
    run_profile = schema.get("$defs", {}).get("DossierRunProfile", {})
    run_properties = run_profile.get("properties")
    if isinstance(run_properties, dict):
        for field_name in (
            "workflow_mode",
            "formatter_provider_profile",
            "formatter_provider",
            "formatter_model",
            "reviewer_provider_profile",
            "reviewer_provider",
            "reviewer_model",
            "research_notebook_path",
            "research_notebook_sha256",
            "research_usage",
            "reviewer_usage",
            "formatter_usage",
        ):
            run_properties.pop(field_name, None)


def normalize_dossier_candidate(
    candidate: dict[str, Any], *, methodology_ids: tuple[str, ...]
) -> dict[str, Any]:
    """Repair harmless LLM handoff inconsistencies while retaining audit warnings."""

    normalized = deepcopy(candidate)
    raw_warnings = normalized.get("normalization_warnings")
    warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []
    evidence = normalized.get("evidence")
    if not isinstance(evidence, list):
        return normalized

    id_map: dict[str, list[str]] = {}
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict):
            continue
        old_id = str(item.get("evidence_id", f"missing-{index}"))
        new_id = f"E{index:03d}"
        id_map.setdefault(old_id, []).append(new_id)
        if len(id_map[old_id]) > 1:
            warnings.append(
                f"duplicate evidence ID {old_id!r} remains ambiguous; references apply to each"
            )
        if old_id != new_id:
            warnings.append(f"evidence ID {old_id!r} normalized to {new_id}")
        item["evidence_id"] = new_id

    selected = set(methodology_ids)
    mappings = _normalize_mappings(normalized.get("mappings"), id_map, selected, warnings)
    _infer_local_prior_mappings(evidence, mappings, selected, warnings)
    coverage = _normalize_coverage(
        normalized.get("coverage"), methodology_ids, id_map, mappings, warnings
    )
    normalized["mappings"] = mappings
    normalized["coverage"] = coverage
    normalized["normalization_warnings"] = list(dict.fromkeys(warnings))
    return normalized


def _normalize_mappings(
    raw: object,
    id_map: dict[str, list[str]],
    selected: set[str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict):
            warnings.append("non-object evidence mapping was ignored")
            continue
        evidence_ids = id_map.get(str(item.get("evidence_id")), [])
        methodology_id = str(item.get("methodology_id", ""))
        if not evidence_ids or methodology_id not in selected:
            warnings.append("mapping with unknown evidence or question was ignored")
            continue
        relation = str(item.get("relation", "context"))
        if relation not in {"supports", "contradicts", "mitigates", "context"}:
            relation = "context"
            warnings.append("unknown mapping relation was normalized to context")
        for evidence_id in evidence_ids:
            key = (evidence_id, methodology_id, relation)
            if key in seen:
                continue
            seen.add(key)
            mappings.append(
                {
                    "evidence_id": evidence_id,
                    "methodology_id": methodology_id,
                    "relation": relation,
                    "relevance": str(
                        item.get("relevance") or "Relevant contextual evidence."
                    ),
                }
            )
    return mappings


def _infer_local_prior_mappings(
    evidence: list[object],
    mappings: list[dict[str, Any]],
    selected: set[str],
    warnings: list[str],
) -> None:
    """Expose exact local-prior lens records when a formatter omits their links."""

    mapped = {
        (str(item["evidence_id"]), str(item["methodology_id"])) for item in mappings
    }
    for item in evidence:
        if not isinstance(item, dict):
            continue
        locator = str(item.get("url", ""))
        prefix = "local-prior:"
        if not locator.startswith(prefix):
            continue
        methodology_id = locator.removeprefix(prefix)
        evidence_id = str(item.get("evidence_id", ""))
        key = (evidence_id, methodology_id)
        if methodology_id not in selected or key in mapped:
            continue
        mappings.append(
            {
                "evidence_id": evidence_id,
                "methodology_id": methodology_id,
                "relation": "context",
                "relevance": "Mapping inferred from the exact local-prior lens locator.",
            }
        )
        mapped.add(key)
        warnings.append(
            f"{methodology_id} mapping for {evidence_id} was inferred from its "
            "local-prior locator"
        )


def _normalize_coverage(
    raw: object,
    methodology_ids: tuple[str, ...],
    id_map: dict[str, list[str]],
    mappings: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw if isinstance(raw, list) else ():
        if not isinstance(item, dict):
            continue
        methodology_id = str(item.get("methodology_id"))
        if methodology_id in by_id:
            warnings.append(f"duplicate {methodology_id} coverage row used the latest value")
        by_id[methodology_id] = item
    output: list[dict[str, Any]] = []
    allowed = {
        "covered",
        "partially_covered",
        "no_evidence_found",
        "not_applicable",
        "research_blocked",
    }
    for methodology_id in methodology_ids:
        item = by_id.get(methodology_id, {})
        raw_evidence_ids = item.get("evidence_ids")
        evidence_id_values = (
            raw_evidence_ids if isinstance(raw_evidence_ids, (list, tuple)) else ()
        )
        evidence_ids = [
            normalized_id
            for value in (str(entry) for entry in evidence_id_values)
            if value in id_map
            for normalized_id in id_map[value]
        ]
        status = str(item.get("status", "no_evidence_found"))
        if status not in allowed:
            status = "partially_covered" if evidence_ids else "no_evidence_found"
            warnings.append(f"{methodology_id} coverage wording was normalized")
        if evidence_ids and status in {"no_evidence_found", "not_applicable", "research_blocked"}:
            status = "partially_covered"
            warnings.append(
                f"{methodology_id} retained contextual evidence despite its original status"
            )
        if not evidence_ids and status in {"covered", "partially_covered"}:
            status = "no_evidence_found"
            warnings.append(f"{methodology_id} coverage status lacked evidence and was downgraded")
        mapped = {
            entry["evidence_id"]
            for entry in mappings
            if entry["methodology_id"] == methodology_id
        }
        for evidence_id in evidence_ids:
            if evidence_id not in mapped:
                mappings.append(
                    {
                        "evidence_id": evidence_id,
                        "methodology_id": methodology_id,
                        "relation": "context",
                        "relevance": "Mapping inferred from the worker's coverage reference.",
                    }
                )
                warnings.append(
                    f"{methodology_id} mapping for {evidence_id} was inferred from coverage"
                )
        output.append(
            {
                "methodology_id": methodology_id,
                "status": status,
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "reason": str(item.get("reason") or "No explicit coverage explanation supplied."),
            }
        )
    return output


def _require_every_property(node: object) -> None:
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["required"] = list(properties)
            node["additionalProperties"] = False
        for value in node.values():
            _require_every_property(value)
    elif isinstance(node, list):
        for value in node:
            _require_every_property(value)


__all__ = [
    "RulerEvidenceDossier",
    "codex_dossier_json_schema",
    "normalize_dossier_candidate",
]
