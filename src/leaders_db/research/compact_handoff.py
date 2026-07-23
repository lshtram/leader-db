"""Deterministic compact handoff from research producers to LLM consumers."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

_ACCOUNTING_MARKERS = (
    "Research accounting:",
    "Research accounting",
    "Evidence accounting:",
    "Source accounting:",
)
_CHAPTER_IDS = {f"{index}B" for index in range(1, 9)}
_LOCAL_STATUSES = {"evidence_found", "no_evidence_found"}
_SOURCE_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MAX_LOCAL_PACKAGES = 1_000
_MAX_LOCAL_FACTS = 100_000
_MAX_LOCAL_PRIOR_BYTES = 10_000_000
_MAX_FACT_LIST_ITEMS = 100
_MAX_OBSERVATION_IDS = 100_000
_MAX_IDENTIFIER_LENGTH = 256
_MAX_SOURCE_SLUGS = 100


class _LocalSummaryBoundsError(ValueError):
    """Internal signal that a compact local summary would be unsafe."""


def build_compact_research_handoff(
    *,
    attempt_dir: Path,
    fallback_notebook: str,
) -> str:
    """Return the ledger plus chapter conclusions without replaying raw notebooks."""

    manifest_path = attempt_dir / "research-ledger-manifest.json"
    if not manifest_path.is_file():
        return fallback_notebook
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback_notebook
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "ruler_research_ledger_manifest_v1"
        or not isinstance(manifest.get("entries"), list)
        or not manifest["entries"]
    ):
        return fallback_notebook

    sections = [
        "Compact research handoff. The parent preserves the complete raw notebook "
        "separately; this consumer receives the authoritative evidence ledger and "
        "chapter accounting conclusions.\n",
        "--- RESEARCH LEDGER MANIFEST ---\n"
        + json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
    ]
    local_disposition = _local_disposition_summary(attempt_dir)
    if local_disposition is not None:
        sections.append(
            "--- LOCAL DATA DISPOSITION AUDIT ---\n"
            + json.dumps(
                local_disposition,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    for path in sorted(attempt_dir.glob("research-chapter-*.md")):
        text = path.read_text(encoding="utf-8")
        starts = [text.rfind(marker) for marker in _ACCOUNTING_MARKERS]
        starts = [offset for offset in starts if offset >= 0]
        conclusion = text[max(starts) :] if starts else text[-5_000:]
        sections.append(f"CHAPTER_CONCLUSION {path.stem}:\n{conclusion.strip()}")
    return "\n\n".join(sections)


def _local_disposition_summary(attempt_dir: Path) -> dict[str, Any] | None:
    """Summarize authoritative local-prior routing without replaying every fact."""

    job_dir = attempt_dir.parent.parent
    local_priors_path = job_dir / "trusted" / attempt_dir.name / "local-priors.json"
    packages = _load_local_packages(local_priors_path)
    return _summarize_local_packages(packages) if packages is not None else None


def _load_local_packages(path: Path) -> list[Any] | None:
    """Load a plausibly bounded local-prior package list."""

    if not path.is_file() or path.stat().st_size > _MAX_LOCAL_PRIOR_BYTES:
        return None
    try:
        packages = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(packages, list) or len(packages) > _MAX_LOCAL_PACKAGES:
        return None
    return packages


def _normalized_local_package(
    package: Any,
) -> tuple[str, str, str, list[Any]] | None:
    """Return bounded routing fields for one valid chapter package."""

    if not isinstance(package, dict):
        return None
    methodology_id = str(package.get("methodology_id", ""))
    chapter_id = methodology_id.split(".", maxsplit=1)[0]
    if chapter_id not in _CHAPTER_IDS:
        return None
    status = str(package.get("status", "unknown"))
    if status not in _LOCAL_STATUSES:
        status = "invalid_or_unresolved"
    disposition = {
        "evidence_found": "retained_as_structured_context",
        "no_evidence_found": "explicit_local_evidence_gap",
        "invalid_or_unresolved": "unresolved_invalid_package",
    }[status]
    facts = package.get("local_facts")
    return chapter_id, status, disposition, facts if isinstance(facts, list) else []


def _summarize_local_packages(packages: list[Any]) -> dict[str, Any] | None:
    """Aggregate validated local routing and disposition counts."""

    status_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    chapter_summaries: dict[str, dict[str, Any]] = {}
    unique_observations: set[str] = set()
    source_slugs: set[str] = set()
    years: list[int] = []
    warning_count = 0
    fact_instances = 0
    try:
        for package in packages:
            normalized = _normalized_local_package(package)
            if normalized is None:
                continue
            chapter_id, status, disposition, facts = normalized
            status_counts[status] += 1
            disposition_counts[disposition] += 1
            chapter = chapter_summaries.setdefault(
                chapter_id,
                {
                    "lens_count": 0,
                    "status_counts": Counter(),
                    "fact_instances": 0,
                    "unique_observation_ids": set(),
                },
            )
            chapter["lens_count"] += 1
            chapter["status_counts"][status] += 1
            if fact_instances + len(facts) > _MAX_LOCAL_FACTS:
                raise _LocalSummaryBoundsError
            fact_instances += len(facts)
            chapter["fact_instances"] += len(facts)
            for fact in facts:
                ids, slugs, year, warnings = _bounded_fact_components(fact)
                normalized_ids = ids
                unique_observations.update(normalized_ids)
                if len(unique_observations) > _MAX_OBSERVATION_IDS:
                    raise _LocalSummaryBoundsError
                chapter["unique_observation_ids"].update(normalized_ids)
                source_slugs.update(slugs)
                if len(source_slugs) > _MAX_SOURCE_SLUGS:
                    raise _LocalSummaryBoundsError
                if year is not None:
                    years.append(year)
                warning_count += warnings
    except _LocalSummaryBoundsError:
        return None

    normalized_chapters = {
        chapter_id: {
            "lens_count": item["lens_count"],
            "status_counts": dict(sorted(item["status_counts"].items())),
            "fact_instances": item["fact_instances"],
            "unique_observation_count": len(item["unique_observation_ids"]),
        }
        for chapter_id, item in sorted(chapter_summaries.items())
        if chapter_id
    }
    return {
        "schema_version": "compact_local_disposition_v1",
        "lens_package_count": sum(status_counts.values()),
        "status_counts": dict(sorted(status_counts.items())),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "fact_instances": fact_instances,
        "unique_observation_count": len(unique_observations),
        "source_slugs": sorted(source_slugs),
        "year_coverage": {
            "minimum": min(years) if years else None,
            "maximum": max(years) if years else None,
        },
        "warning_count": warning_count,
        "chapters": normalized_chapters,
        "disposition_policy": {
            "evidence_found": (
                "Retained as structured context for formatter and judge consumers; "
                "not directional ruler evidence without supported attribution."
            ),
            "no_evidence_found": (
                "Retained as an explicit local-evidence gap; absence is not favorable "
                "or adverse ruler evidence."
            ),
            "invalid_or_unresolved": (
                "Excluded from use and retained only as an unresolved producer defect."
            ),
            "research_handoff": (
                "The complete local package is not replayed in research prompts. "
                "This bounded local-data audit records parent routing decisions."
            ),
        },
    }


def _bounded_fact_components(
    fact: Any,
) -> tuple[set[str], set[str], int | None, int]:
    """Return bounded fact metadata without carrying the fact's value or prose."""

    if not isinstance(fact, dict):
        return set(), set(), None, 0
    raw_ids = fact.get("source_observation_ids", [])
    raw_slugs = fact.get("source_slugs", [])
    raw_warnings = fact.get("warnings", [])
    lists = (raw_ids, raw_slugs, raw_warnings)
    if any(
        not isinstance(items, list) or len(items) > _MAX_FACT_LIST_ITEMS
        for items in lists
    ):
        raise _LocalSummaryBoundsError
    identifiers = {str(item) for item in raw_ids}
    if any(len(item) > _MAX_IDENTIFIER_LENGTH for item in identifiers):
        raise _LocalSummaryBoundsError
    slugs = {
        str(item)
        for item in raw_slugs
        if _SOURCE_SLUG.fullmatch(str(item))
    }
    year = fact.get("year")
    normalized_year = (
        year if isinstance(year, int) and not isinstance(year, bool) else None
    )
    return identifiers, slugs, normalized_year, len(raw_warnings)


__all__ = ["build_compact_research_handoff"]
