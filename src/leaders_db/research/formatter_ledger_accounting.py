"""Deterministic accounting between a research ledger and formatted dossier."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .dossier_models import RulerEvidenceDossier


def validate_formatter_ledger_accounting(
    dossier: RulerEvidenceDossier, *, manifest: dict[str, Any]
) -> None:
    """Reject omitted facts or routing while allowing unambiguous consolidation."""

    expected = {
        str(entry["canonical_fact_key"]): entry
        for entry in manifest.get("entries", [])
        if entry.get("disposition") == "final_evidence"
    }
    emitted = {
        item.canonical_fact_key: item
        for item in dossier.evidence
        if item.final_evidence_use != "discovery_only"
    }
    evidence_key_by_id = {
        evidence_id: item.canonical_fact_key
        for item in dossier.evidence
        if isinstance((evidence_id := getattr(item, "evidence_id", None)), str)
    }
    mapped_methodologies: dict[str, set[str]] = defaultdict(set)
    for mapping in dossier.mappings:
        key = evidence_key_by_id.get(mapping.evidence_id)
        if key:
            mapped_methodologies[key].add(mapping.methodology_id)
    emitted_by_fact: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for key, item in emitted.items():
        url = getattr(item, "url", None)
        locator = getattr(item, "source_locator", None)
        claim = getattr(item, "claim", None)
        if all(isinstance(value, str) and value.strip() for value in (url, locator, claim)):
            emitted_by_fact[_accounting_fact(url, locator, claim)].add(key)

    resolved = {
        key: _resolve_emitted_key(
            key=key,
            entry=entry,
            emitted=emitted,
            emitted_by_fact=emitted_by_fact,
            mapped_methodologies=mapped_methodologies,
        )
        for key, entry in expected.items()
    }
    missing = sorted(key for key, emitted_key in resolved.items() if emitted_key is None)
    if missing:
        raise ValueError("formatter omitted accepted final evidence: " + ", ".join(missing[:5]))

    chapter_failures: dict[str, list[str]] = {}
    lens_failures: dict[str, list[str]] = {}
    for key, entry in expected.items():
        emitted_key = resolved[key]
        actual = mapped_methodologies.get(emitted_key or "", set())
        required = set(entry.get("methodology_ids", []))
        missing_lenses = sorted(required - actual)
        if missing_lenses:
            lens_failures[key] = missing_lenses
        missing_chapters = sorted(
            {item.split(".", maxsplit=1)[0] for item in required}
            - {item.split(".", maxsplit=1)[0] for item in actual}
        )
        if missing_chapters:
            chapter_failures[key] = missing_chapters
    if chapter_failures:
        raise ValueError(
            "formatter dropped accepted chapter routing: "
            + _failure_summary(chapter_failures)
        )
    if lens_failures:
        raise ValueError(
            "formatter dropped accepted lens routing: " + _failure_summary(lens_failures)
        )


def _resolve_emitted_key(
    *,
    key: str,
    entry: dict[str, Any],
    emitted: dict[str, Any],
    emitted_by_fact: dict[tuple[str, str, str], set[str]],
    mapped_methodologies: dict[str, set[str]],
) -> str | None:
    if key in emitted:
        return key
    if not all(str(entry.get(field, "")).strip() for field in ("url", "locator", "claim")):
        return None
    required = set(entry.get("methodology_ids", []))
    candidates = emitted_by_fact.get(
        _accounting_fact(str(entry["url"]), str(entry["locator"]), str(entry["claim"])),
        set(),
    )
    routed = [key for key in candidates if required.issubset(mapped_methodologies[key])]
    return routed[0] if len(routed) == 1 else None


def _accounting_fact(url: str, locator: str, claim: str) -> tuple[str, str, str]:
    return url.strip(), locator.strip().casefold(), " ".join(claim.split()).casefold()


def _failure_summary(failures: dict[str, list[str]]) -> str:
    return ", ".join(
        f"{key}=>{'/'.join(values)}" for key, values in list(failures.items())[:5]
    )


__all__ = ["validate_formatter_ledger_accounting"]
