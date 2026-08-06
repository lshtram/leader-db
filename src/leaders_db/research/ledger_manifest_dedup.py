"""Deterministic cleanup for mechanically recovered ledger duplicates."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def collapse_recovered_url_duplicates(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    """Merge routing from incomplete recovered rows into complete URL owners."""

    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return manifest, 0
    owners_by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if (
            isinstance(entry, dict)
            and str(entry.get("url", "")).startswith(("http://", "https://"))
            and all(
                str(entry.get(field, "")).strip() for field in ("claim", "locator")
            )
        ):
            owners_by_url[str(entry["url"])].append(entry)
    retained: list[Any] = []
    collapsed = 0
    for entry in entries:
        if not isinstance(entry, dict):
            retained.append(entry)
            continue
        recovered_url = _recovered_key_url(str(entry.get("canonical_fact_key", "")))
        owners = owners_by_url.get(recovered_url, [])
        owner = owners[0] if len(owners) == 1 else None
        if owner is None or owner is entry:
            retained.append(entry)
            continue
        _merge_identifiers(owner, entry, "chapter_ids")
        _merge_identifiers(owner, entry, "methodology_ids")
        collapsed += 1
    if collapsed == 0:
        return manifest, 0
    normalized = dict(manifest)
    normalized["entries"] = retained
    return normalized, collapsed


def _recovered_key_url(key: str) -> str:
    if not key.startswith("recovered:http") or "|" not in key:
        return ""
    return key.removeprefix("recovered:").rsplit("|", maxsplit=1)[0]


def _merge_identifiers(owner: dict[str, Any], duplicate: dict[str, Any], field: str) -> None:
    existing = owner.get(field)
    additional = duplicate.get(field)
    if not isinstance(existing, list) or not isinstance(additional, list):
        return
    owner[field] = sorted({str(item) for item in existing + additional})


__all__ = ["collapse_recovered_url_duplicates"]
