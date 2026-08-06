"""Stable identifiers and materialized JSONL rows."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import FactState, PreparedSource


def fact_id(
    source_sha256: str,
    locator: str,
    start_char: int,
    end_char: int,
    summary: str,
) -> str:
    payload = "\x1f".join(
        (source_sha256, locator, str(start_char), str(end_char), summary.casefold())
    )
    return "F-" + hashlib.sha256(payload.encode()).hexdigest()[:16]


def materialized_state(
    state: FactState, source: PreparedSource
) -> dict[str, Any]:
    value = state.to_dict()
    value["proposal_id"] = value.pop("fact_id")
    value["evidence_id"] = fact_id(
        state.source_sha256,
        state.locator,
        state.start_char,
        state.end_char,
        state.summary,
    ).replace("F-", "E-", 1)
    value["source"] = {
        **source.spec.model_dump(),
        "original_sha256": source.original_sha256,
        "extracted_sha256": source.extracted_sha256,
    }
    return value


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n" for item in values
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


__all__ = ["fact_id", "materialized_state", "write_jsonl"]

