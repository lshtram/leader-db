"""Adapters for existing access audits and frozen document extractions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from leaders_db.conversational_evidence.document_reader_experiment import AccessAuditRecord

from .artifacts import sha256_file


class ExtractedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: int = Field(ge=1)
    locator: str = Field(min_length=1)
    text: str


class FrozenExtraction(BaseModel):
    """Existing extraction normalized for funnel acquisition."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: str
    source_id: str = Field(pattern=r"^[A-Z]+-[0-9]{3}$")
    title: str = Field(min_length=1)
    requested_url: str = Field(min_length=1)
    final_url: str = Field(min_length=1)
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    estimated_source_tokens: int = Field(ge=0)
    units: tuple[ExtractedUnit, ...]


def load_access_audit(path: Path) -> tuple[AccessAuditRecord, ...]:
    """Load either a record array or the existing audit envelope."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    records: Any = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("access audit must contain a record array")
    fields = set(AccessAuditRecord.model_fields)
    return tuple(
        AccessAuditRecord.model_validate(
            {key: value for key, value in item.items() if key in fields}
        )
        for item in records
    )


def load_frozen_extractions(
    directory: Path, expected_source_ids: tuple[str, ...]
) -> tuple[FrozenExtraction, ...]:
    """Load the exact configured pack and reject missing or unexpected source IDs."""

    paths = sorted(directory.glob("*.json"))
    loaded = tuple(
        FrozenExtraction.model_validate_json(path.read_text(encoding="utf-8"))
        for path in paths
    )
    loaded_ids = [item.source_id for item in loaded]
    if len(loaded_ids) != len(set(loaded_ids)):
        raise ValueError("frozen extraction directory contains duplicate source IDs")
    found = {item.source_id for item in loaded}
    expected = set(expected_source_ids)
    if found != expected:
        missing = sorted(expected - found)
        unexpected = sorted(found - expected)
        raise ValueError(f"frozen extraction mismatch; missing={missing}, unexpected={unexpected}")
    return loaded


def extraction_artifact_hashes(directory: Path) -> dict[str, str]:
    """Hash each frozen extraction artifact by source ID."""

    result: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_id = payload.get("source_id")
        if not isinstance(source_id, str):
            raise ValueError(f"extraction lacks source_id: {path}")
        if source_id in result:
            raise ValueError(f"duplicate extraction source_id: {source_id}")
        result[source_id] = sha256_file(path)
    return result


__all__ = [
    "ExtractedUnit",
    "FrozenExtraction",
    "extraction_artifact_hashes",
    "load_access_audit",
    "load_frozen_extractions",
]
