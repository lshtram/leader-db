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
    source_locator: str = Field(default="unknown_not_recorded", min_length=1)
    canonical_fact_key: str = Field(default="unknown_not_recorded", min_length=1)
    source_type: str = Field(min_length=1)
    source_confidence: str = Field(min_length=1)
    source_confidence_reason: str = Field(min_length=1)
    final_evidence_use: Literal["final_evidence", "context", "discovery_only"]
    period_fit: str = Field(min_length=1)
    ruler_attribution: str = Field(min_length=1)
    contrary_evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_final_evidence_auditability(self) -> DossierEvidence:
        """Require new final-evidence writers to provide an auditable locator/key."""

        if self.final_evidence_use != "final_evidence":
            return self
        explicit_locator = "source_locator" in self.model_fields_set
        explicit_key = "canonical_fact_key" in self.model_fields_set
        if not explicit_locator and not explicit_key:
            return self
        generic_locators = {
            "unknown_not_recorded",
            "gateway_only",
            "locator_missing",
            "underlying_source_missing",
            "release page",
            "article",
            "section page",
            "document index",
        }
        if not explicit_locator or self.source_locator.strip().casefold() in generic_locators:
            raise ValueError("final evidence requires a precise source locator")
        if not explicit_key or self.canonical_fact_key == "unknown_not_recorded":
            raise ValueError("final evidence requires a canonical fact key")
        return self


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


class EvidenceEnvironmentAssessment(BaseModel):
    """Cited assessment of the conditions under which ruler evidence was produced."""

    model_config = ConfigDict(extra="forbid")

    criticism_possible: str = Field(min_length=1)
    censorship_and_self_censorship: str = Field(min_length=1)
    safe_reporting_channels: str = Field(min_length=1)
    official_statistics_reliability: str = Field(min_length=1)
    languages_and_archives_searched: tuple[str, ...] = Field(min_length=1)
    source_concentration: str = Field(min_length=1)
    duplicate_event_risk: str = Field(min_length=1)
    complaint_volume_interpretation: str = Field(min_length=1)
    relevant_denominators: str = Field(min_length=1)
    inherited_conditions_shocks_and_authority: str = Field(min_length=1)
    chapter_specific_biases: tuple[str, ...] = Field(min_length=1)
    supporting_evidence_ids: tuple[EvidenceId, ...]

    @model_validator(mode="after")
    def _unique_support(self) -> EvidenceEnvironmentAssessment:
        if len(self.supporting_evidence_ids) != len(set(self.supporting_evidence_ids)):
            raise ValueError("evidence-environment support IDs must be unique")
        return self


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
    llm_usage_profile_path: str | None = None
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
    evidence_environment: EvidenceEnvironmentAssessment
    run_profile: DossierRunProfile

    @model_validator(mode="after")
    def _validate_references_and_scope(self) -> RulerEvidenceDossier:
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        canonical_facts: set[tuple[str, str, str]] = set()
        canonical_keys: set[str] = set()
        for item in self.evidence:
            if {"source_locator", "canonical_fact_key"}.issubset(item.model_fields_set):
                fact = (
                    item.url.strip(),
                    item.source_locator.strip().casefold(),
                    " ".join(item.claim.split()).casefold(),
                )
                if fact in canonical_facts:
                    raise ValueError("duplicate canonical source-locator-claim fact")
                canonical_facts.add(fact)
                if item.canonical_fact_key in canonical_keys:
                    raise ValueError("canonical fact keys must be unique")
                canonical_keys.add(item.canonical_fact_key)
        known = set(evidence_ids)
        _validate_environment_support(self.evidence_environment, known)
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


def _validate_environment_support(
    environment: EvidenceEnvironmentAssessment, known_evidence_ids: set[str]
) -> None:
    """Keep current dossier producer requirements outside the shared legacy type."""

    if not environment.supporting_evidence_ids:
        raise ValueError("current dossier evidence environment requires cited support")
    if not set(environment.supporting_evidence_ids).issubset(known_evidence_ids):
        raise ValueError("evidence environment references an unknown evidence ID")


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

    downgraded_evidence = _downgrade_unauditable_final_evidence(evidence, warnings)

    id_map: dict[str, list[str]] = {}
    deduplicated_evidence: list[object] = []
    canonical_fact_ids: dict[tuple[str, str, str], str] = {}
    canonical_keys: set[str] = set()
    for item in evidence:
        if not isinstance(item, dict):
            deduplicated_evidence.append(item)
            continue
        old_id = str(item.get("evidence_id", f"missing-{len(deduplicated_evidence) + 1}"))
        fact = _canonical_source_locator_claim(item)
        existing_id = canonical_fact_ids.get(fact) if fact is not None else None
        if existing_id is not None:
            id_map.setdefault(old_id, []).append(existing_id)
            retained = next(
                entry
                for entry in deduplicated_evidence
                if isinstance(entry, dict) and entry.get("evidence_id") == existing_id
            )
            _merge_duplicate_fact_metadata(retained, item, warnings)
            warnings.append(
                f"duplicate canonical fact {old_id!r} merged into {existing_id}"
            )
            continue
        new_id = f"E{len(deduplicated_evidence) + 1:03d}"
        id_map.setdefault(old_id, []).append(new_id)
        if len(id_map[old_id]) > 1:
            warnings.append(
                f"duplicate evidence ID {old_id!r} remains ambiguous; references apply to each"
            )
        if old_id != new_id:
            warnings.append(f"evidence ID {old_id!r} normalized to {new_id}")
        item["evidence_id"] = new_id
        canonical_key = str(item.get("canonical_fact_key", "")).strip()
        if canonical_key and canonical_key in canonical_keys:
            item["canonical_fact_key"] = "|".join(fact) if fact is not None else canonical_key
            warnings.append(
                f"duplicate canonical fact key for {old_id!r} replaced by its source fact key"
            )
        canonical_keys.add(str(item.get("canonical_fact_key", "")).strip())
        deduplicated_evidence.append(item)
        if fact is not None:
            canonical_fact_ids[fact] = new_id

    normalized["evidence"] = deduplicated_evidence
    evidence = deduplicated_evidence

    _ensure_evidence_environment(normalized, evidence, warnings)

    selected = set(methodology_ids)
    mappings = _normalize_mappings(normalized.get("mappings"), id_map, selected, warnings)
    _normalize_context_only_mappings(evidence, downgraded_evidence, mappings, warnings)
    _infer_local_prior_mappings(evidence, mappings, selected, warnings)
    coverage = _normalize_coverage(
        normalized.get("coverage"), methodology_ids, id_map, mappings, warnings
    )
    _retain_unmapped_evidence_as_chapter_context(evidence, mappings, selected, warnings)
    _normalize_environment_support(
        normalized.get("evidence_environment"), id_map, evidence, warnings
    )
    normalized.update(
        mappings=mappings,
        coverage=coverage,
        normalization_warnings=list(dict.fromkeys(warnings)),
    )
    return normalized


def _downgrade_unauditable_final_evidence(
    evidence: list[object], warnings: list[str]
) -> set[int]:
    """Retain useful claims without treating an imprecisely located claim as final."""

    generic_locators = {
        "unknown_not_recorded",
        "gateway_only",
        "locator_missing",
        "underlying_source_missing",
        "release page",
        "article",
        "section page",
        "document index",
    }
    downgraded: set[int] = set()
    for item in evidence:
        if not isinstance(item, dict) or item.get("final_evidence_use") != "final_evidence":
            continue
        locator = str(item.get("source_locator", "")).strip().casefold()
        canonical_key = str(item.get("canonical_fact_key", "")).strip()
        if locator and locator not in generic_locators and canonical_key not in {
            "",
            "unknown_not_recorded",
        }:
            continue
        item["final_evidence_use"] = "context"
        downgraded.add(id(item))
        warnings.append(
            f"unauditable final evidence {item.get('evidence_id', 'unknown')} retained as context"
        )
    return downgraded


def _normalize_context_only_mappings(
    evidence: list[object],
    downgraded_evidence: set[int],
    mappings: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    """Prevent retained context records from being represented as directional findings."""

    # The set uses object identity so originally contextual evidence keeps its producer
    # relation; only records downgraded by this normalization lose directional force.
    context_only_ids = {
        str(item.get("evidence_id"))
        for item in evidence
        if isinstance(item, dict) and id(item) in downgraded_evidence
    }
    for mapping in mappings:
        if mapping["evidence_id"] in context_only_ids and mapping["relation"] != "context":
            mapping["relation"] = "context"
            warnings.append(
                f"context-only evidence {mapping['evidence_id']} mapping normalized to context"
            )


def _ensure_evidence_environment(
    normalized: dict[str, Any], evidence: list[object], warnings: list[str]
) -> None:
    """Make an incomplete producer explicit without discarding usable evidence."""

    if isinstance(normalized.get("evidence_environment"), dict) or not evidence:
        return
    first = next((item for item in evidence if isinstance(item, dict)), None)
    if first is None:
        return
    evidence_id = str(first["evidence_id"])
    unknown = (
        "Not assessed by the producer; retain the evidence but lower confidence until "
        "the evidence environment is reviewed."
    )
    normalized["evidence_environment"] = {
        "criticism_possible": unknown,
        "censorship_and_self_censorship": unknown,
        "safe_reporting_channels": unknown,
        "official_statistics_reliability": unknown,
        "languages_and_archives_searched": ["not_recorded_by_producer"],
        "source_concentration": unknown,
        "duplicate_event_risk": unknown,
        "complaint_volume_interpretation": unknown,
        "relevant_denominators": unknown,
        "inherited_conditions_shocks_and_authority": unknown,
        "chapter_specific_biases": ["Evidence environment not assessed by producer"],
        "supporting_evidence_ids": [evidence_id],
    }
    warnings.append("missing evidence environment retained as explicitly unassessed")


def _normalize_environment_references(
    environment: object, id_map: dict[str, list[str]]
) -> None:
    """Apply evidence-ID normalization to the cited environment assessment."""

    if not isinstance(environment, dict):
        return
    raw_support = environment.get("supporting_evidence_ids")
    if not isinstance(raw_support, (list, tuple)):
        return
    environment["supporting_evidence_ids"] = list(
        dict.fromkeys(
            normalized_id
            for value in (str(item) for item in raw_support)
            for normalized_id in id_map.get(value, ())
        )
    )


def _normalize_environment_support(
    environment: object,
    id_map: dict[str, list[str]],
    evidence: list[object],
    warnings: list[str],
) -> None:
    """Normalize environment joins and restore a missing retained-evidence link."""

    _normalize_environment_references(environment, id_map)
    _ensure_environment_support(environment, evidence, warnings)


def _ensure_environment_support(
    environment: object, evidence: list[object], warnings: list[str]
) -> None:
    """Keep a substantive environment assessment joined to retained evidence."""

    if not isinstance(environment, dict):
        return
    support = environment.get("supporting_evidence_ids")
    if isinstance(support, list) and support:
        return
    first = next(
        (
            str(item["evidence_id"])
            for item in evidence
            if isinstance(item, dict) and item.get("evidence_id")
        ),
        None,
    )
    if first is None:
        return
    environment["supporting_evidence_ids"] = [first]
    warnings.append(
        "empty evidence-environment support repaired from retained cited evidence"
    )


def _canonical_source_locator_claim(item: dict[str, Any]) -> tuple[str, str, str] | None:
    if not {"url", "source_locator", "claim"}.issubset(item):
        return None
    return (
        str(item["url"]).strip(),
        str(item["source_locator"]).strip().casefold(),
        " ".join(str(item["claim"]).split()).casefold(),
    )


def _merge_duplicate_fact_metadata(
    retained: dict[str, Any], duplicate: dict[str, Any], warnings: list[str]
) -> None:
    """Retain the stronger duplicate row and preserve all contrary evidence."""

    ignored = {"evidence_id", "canonical_fact_key", "contrary_evidence"}
    differing = sorted(
        key
        for key in set(retained) | set(duplicate)
        if key not in ignored and retained.get(key) != duplicate.get(key)
    )
    contrary_values = [
        str(value)
        for record in (retained, duplicate)
        for value in record.get("contrary_evidence", [])
    ]
    if _evidence_strength(duplicate) > _evidence_strength(retained):
        retained_id = retained["evidence_id"]
        retained_key = retained.get("canonical_fact_key")
        retained.clear()
        retained.update(duplicate)
        retained["evidence_id"] = retained_id
        if retained_key is not None:
            retained["canonical_fact_key"] = retained_key
    retained["contrary_evidence"] = list(dict.fromkeys(contrary_values))
    if differing:
        warnings.append(
            "duplicate canonical fact had conflicting metadata; retained the stronger "
            f"record for fields: {', '.join(differing)}"
        )


def _evidence_strength(item: dict[str, Any]) -> tuple[int, int, int]:
    use_rank = {"discovery_only": 0, "context": 1, "final_evidence": 2}
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    return (
        use_rank.get(str(item.get("final_evidence_use")), -1),
        confidence_rank.get(str(item.get("source_confidence")).casefold(), -1),
        len(str(item.get("excerpt", ""))),
    )


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


def _retain_unmapped_evidence_as_chapter_context(
    evidence: list[object],
    mappings: list[dict[str, Any]],
    selected: set[str],
    warnings: list[str],
) -> None:
    """Keep usable formatter output visible without inventing lens relevance."""

    mapped_ids = {str(item["evidence_id"]) for item in mappings}
    chapter_entry_lenses = tuple(
        sorted(
            (item for item in selected if item.endswith(".1")),
            key=lambda item: int(item.split("B", maxsplit=1)[0]),
        )
    )
    if not chapter_entry_lenses:
        return
    for item in evidence:
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("evidence_id", ""))
        if not evidence_id or evidence_id in mapped_ids:
            continue
        for methodology_id in chapter_entry_lenses:
            mappings.append(
                {
                    "evidence_id": evidence_id,
                    "methodology_id": methodology_id,
                    "relation": "context",
                    "relevance": (
                        "Formatter omitted exact lens routing; retained at the chapter "
                        "boundary for judge-side relevance review."
                    ),
                }
            )
        mapped_ids.add(evidence_id)
        warnings.append(
            f"unmapped evidence {evidence_id} retained as advisory chapter context"
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
        item = by_id.get(methodology_id)
        mapped = {
            entry["evidence_id"]
            for entry in mappings
            if entry["methodology_id"] == methodology_id
        }
        if item is None:
            output.append(
                {
                    "methodology_id": methodology_id,
                    "status": "partially_covered" if mapped else "research_blocked",
                    "evidence_ids": sorted(mapped),
                    "reason": (
                        "Coverage inferred from retained evidence mappings."
                        if mapped
                        else "Formatter supplied no explicit researcher coverage disposition."
                    ),
                }
            )
            warnings.append(
                f"{methodology_id} lacked an explicit coverage disposition"
            )
            continue
        raw_evidence_ids = item.get("evidence_ids")
        evidence_id_values = (
            raw_evidence_ids if isinstance(raw_evidence_ids, (list, tuple)) else ()
        )
        referenced_evidence_ids = {
            normalized_id
            for value in (str(entry) for entry in evidence_id_values)
            if value in id_map
            for normalized_id in id_map[value]
        }
        inferred = referenced_evidence_ids - mapped
        for evidence_id in sorted(inferred):
            mappings.append(
                {
                    "evidence_id": evidence_id,
                    "methodology_id": methodology_id,
                    "relation": "context",
                    "relevance": (
                        "Mapping inferred from the formatter's explicit coverage "
                        "reference."
                    ),
                }
            )
        if inferred:
            mapped.update(inferred)
            warnings.append(
                f"{methodology_id} mappings were inferred from explicit coverage "
                "references"
            )
        evidence_ids = sorted(mapped)
        status = str(item.get("status", "research_blocked"))
        if status not in allowed:
            status = "partially_covered" if evidence_ids else "research_blocked"
            warnings.append(f"{methodology_id} coverage wording was normalized")
        if evidence_ids and status in {"no_evidence_found", "not_applicable", "research_blocked"}:
            status = "partially_covered"
            warnings.append(
                f"{methodology_id} retained contextual evidence despite its original status"
            )
        if not evidence_ids and status in {"covered", "partially_covered"}:
            status = "research_blocked"
            warnings.append(f"{methodology_id} coverage status lacked evidence and was blocked")
        reason = str(item.get("reason") or "").strip()
        generic_missing_reasons = {
            "",
            "no evidence found",
            "no explicit coverage explanation supplied.",
            "no explicit coverage explanation supplied",
            "not enough evidence",
            "insufficient evidence",
        }
        if status == "no_evidence_found" and reason.casefold() in generic_missing_reasons:
            status = "research_blocked"
            reason = "Researcher supplied no search-specific missing-evidence explanation."
            warnings.append(
                f"{methodology_id} unexplained no-evidence status was blocked"
            )
        output.append(
            {
                "methodology_id": methodology_id,
                "status": status,
                "evidence_ids": list(dict.fromkeys(evidence_ids)),
                "reason": reason or "Explicit researcher disposition retained.",
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
