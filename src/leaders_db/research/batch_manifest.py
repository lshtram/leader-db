"""Load and validate frozen ruler-year research batch manifests."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .local_prior_slice import LocalPriorSliceCase, list_local_prior_slice_cases


class ResearchBatchCase(BaseModel):
    """One exact, resolved ruler-year identity frozen into a research batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ruler_year_id: int = Field(gt=0)
    ruler_id: int = Field(gt=0)
    iso3: str = Field(pattern=r"^[A-Z]{3}$")
    ruler_name: str = Field(min_length=1)


class ResearchBatchManifest(BaseModel):
    """Versioned, hash-verified collection of resolved ruler-year cases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["research_batch_manifest_v1"] = "research_batch_manifest_v1"
    version: Literal[1]
    batch_id: str = Field(min_length=1)
    year: int = Field(ge=1800, le=2200)
    rationale: str = Field(min_length=1)
    resolved_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[ResearchBatchCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> ResearchBatchManifest:
        """Reject duplicate country, ruler, or ruler-year identities."""

        _reject_duplicates(self.cases, field="ruler_year_id")
        _reject_duplicates(self.cases, field="ruler_id")
        _reject_duplicates(self.cases, field="iso3")
        return self


def load_batch_manifest(path: Path) -> ResearchBatchManifest:
    """Load a batch manifest and verify its canonical resolved-content hash."""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"could not load research batch manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("research batch manifest root must be a mapping")
    manifest = ResearchBatchManifest.model_validate(payload)
    actual_hash = compute_resolved_content_sha256(manifest)
    if actual_hash != manifest.resolved_content_sha256:
        raise ValueError(
            "research batch manifest resolved-content hash mismatch: "
            f"expected {manifest.resolved_content_sha256}, computed {actual_hash}"
        )
    return manifest


def compute_resolved_content_sha256(manifest: ResearchBatchManifest) -> str:
    """Hash canonical identity-bearing content independently of YAML presentation."""

    canonical = {
        "schema_version": manifest.schema_version,
        "version": manifest.version,
        "year": manifest.year,
        "cases": [
            case.model_dump(mode="json")
            for case in sorted(
                manifest.cases,
                key=lambda item: (item.iso3, item.ruler_year_id),
            )
        ],
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def validate_batch_manifest_cases(
    bind: Engine | Session,
    manifest: ResearchBatchManifest,
) -> tuple[LocalPriorSliceCase, ...]:
    """Resolve every frozen case and require exact, research-eligible identity matches."""

    current_cases = list_local_prior_slice_cases(bind, year=manifest.year)
    by_ruler_year_id = {
        case.ruler_year_id: case
        for case in current_cases
        if case.ruler_year_id is not None
    }
    validated: list[LocalPriorSliceCase] = []
    for expected in manifest.cases:
        actual = by_ruler_year_id.get(expected.ruler_year_id)
        if actual is None:
            raise ValueError(
                f"batch case ruler_year_id={expected.ruler_year_id} is unavailable for "
                f"year={manifest.year}"
            )
        _validate_exact_identity(expected, actual, expected_year=manifest.year)
        if not actual.identity_research_eligible:
            reason = actual.identity_block_reason or "unknown_identity_block"
            raise ValueError(
                f"batch case ruler_year_id={expected.ruler_year_id} is not research eligible: "
                f"{reason}"
            )
        validated.append(actual)
    return tuple(validated)


def _reject_duplicates(cases: tuple[ResearchBatchCase, ...], *, field: str) -> None:
    values: list[Any] = [getattr(case, field) for case in cases]
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate batch case {field} values: {duplicates}")


def _validate_exact_identity(
    expected: ResearchBatchCase,
    actual: LocalPriorSliceCase,
    *,
    expected_year: int,
) -> None:
    comparisons = {
        "year": (actual.year, expected_year),
        "iso3": (actual.iso3, expected.iso3),
        "ruler_id": (actual.leader_id, expected.ruler_id),
        "ruler_name": (actual.leader_name, expected.ruler_name),
    }
    mismatches = [
        f"{field}: expected={expected_value!r}, actual={actual_value!r}"
        for field, (actual_value, expected_value) in comparisons.items()
        if actual_value != expected_value
    ]
    if mismatches:
        raise ValueError(
            f"batch case ruler_year_id={expected.ruler_year_id} identity mismatch: "
            + "; ".join(mismatches)
        )
