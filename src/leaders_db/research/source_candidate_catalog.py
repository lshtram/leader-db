"""Durable candidate-source catalogue recovered from researcher handoffs."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceCandidate(BaseModel):
    """One discovered source, before evidence acceptance or rejection."""

    model_config = ConfigDict(extra="ignore", validate_default=True)

    url: str = Field(min_length=8)
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    access_status: Literal[
        "unopened", "opened", "accepted", "rejected", "access_blocked"
    ]
    chapter_ids: tuple[str, ...] = ()
    likely_topics: tuple[str, ...] = ()
    discovery_query: str = "unknown_not_recorded"

    @field_validator("chapter_ids")
    @classmethod
    def _valid_chapters(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {f"{index}B" for index in range(1, 9)}
        if not value or not set(value).issubset(allowed):
            raise ValueError("candidate chapter IDs must contain only 1B through 8B")
        return tuple(sorted(set(value)))


class SourceCandidateCatalog(BaseModel):
    """Deduplicated candidate universe for one ruler-period run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ruler_source_candidate_catalog_v1"] = (
        "ruler_source_candidate_catalog_v1"
    )
    candidates: tuple[SourceCandidate, ...]


def recover_source_candidate_catalog(notebook: str) -> SourceCandidateCatalog:
    """Recover and merge valid machine-readable candidate lines."""

    candidates: dict[str, SourceCandidate] = {}
    evidence_urls = _evidence_urls(notebook)
    evidence_routes = _evidence_routes(notebook)
    active_chapter: str | None = None
    for line in notebook.splitlines():
        chapter_match = re.fullmatch(r"--- CHAPTER RESEARCH ([1-8]B) ---", line)
        if chapter_match is not None:
            active_chapter = chapter_match.group(1)
            continue
        if not line.startswith("SOURCE_CANDIDATE_JSON:"):
            continue
        try:
            payload = json.loads(line.partition(":")[2].strip())
            if isinstance(payload, dict) and not payload.get("chapter_ids"):
                canonical = _canonical_url(str(payload.get("url", "")))
                inferred = evidence_routes.get(canonical, ())
                if not inferred and active_chapter is not None:
                    inferred = (active_chapter,)
                payload["chapter_ids"] = inferred
            candidate = SourceCandidate.model_validate(payload)
        except (json.JSONDecodeError, ValueError):
            continue
        key = _canonical_url(candidate.url)
        if not key:
            continue
        candidate = candidate.model_copy(update={"url": key})
        if candidate.access_status == "accepted" and key not in evidence_urls:
            candidate = candidate.model_copy(update={"access_status": "opened"})
        prior = candidates.get(key)
        candidates[key] = candidate if prior is None else _merge(prior, candidate)
    return SourceCandidateCatalog(
        candidates=tuple(sorted(candidates.values(), key=lambda item: item.url))
    )


def write_source_candidate_catalog(notebook: str, output_path: Path) -> Path:
    """Atomically merge new candidate lines into the durable universe."""

    catalog = recover_source_candidate_catalog(notebook)
    existing = _load_catalog(output_path)
    merged = {item.url: item for item in existing.candidates}
    for candidate in catalog.candidates:
        prior = merged.get(candidate.url)
        merged[candidate.url] = candidate if prior is None else _merge(prior, candidate)
    catalog = SourceCandidateCatalog(
        candidates=tuple(sorted(merged.values(), key=lambda item: item.url))
    )
    return _write_catalog(catalog, output_path)


def seed_source_candidate_catalog(
    seed_paths: tuple[Path, ...], output_path: Path
) -> Path:
    """Merge validated prior catalogues into one new run catalogue."""

    existing = _load_catalog(output_path)
    merged: dict[str, SourceCandidate] = {
        candidate.url: candidate for candidate in existing.candidates
    }
    for seed_path in seed_paths:
        catalog = SourceCandidateCatalog.model_validate_json(
            seed_path.read_text(encoding="utf-8")
        )
        for candidate in catalog.candidates:
            prior = merged.get(candidate.url)
            merged[candidate.url] = (
                candidate if prior is None else _merge(prior, candidate)
            )
    catalog = SourceCandidateCatalog(
        candidates=tuple(sorted(merged.values(), key=lambda item: item.url))
    )
    return _write_catalog(catalog, output_path)


def read_source_candidate_catalog(path: Path) -> SourceCandidateCatalog:
    """Read a catalogue, returning empty only when it has not been created."""

    return _load_catalog(path)


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in {"fbclid", "gclid", "outputtype"}
        )
    )
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def _load_catalog(path: Path) -> SourceCandidateCatalog:
    if not path.exists():
        return SourceCandidateCatalog(candidates=())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != "ruler_source_candidate_catalog_v1"
            or not isinstance(payload.get("candidates"), list)
        ):
            raise ValueError("catalogue payload is not an object with candidates")
        candidates = []
        for item in payload["candidates"]:
            try:
                candidates.append(SourceCandidate.model_validate(item))
            except ValueError:
                if isinstance(item, dict) and not item.get("chapter_ids"):
                    continue
                raise
        return SourceCandidateCatalog(candidates=tuple(candidates))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        raise ValueError(f"existing source candidate catalogue is invalid: {path}") from exc


def _write_catalog(catalog: SourceCandidateCatalog, output_path: Path) -> Path:
    encoded = (
        json.dumps(catalog.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode()
    temporary = output_path.with_suffix(f"{output_path.suffix}.tmp")
    with temporary.open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, output_path)
    return output_path


def _merge(first: SourceCandidate, second: SourceCandidate) -> SourceCandidate:
    rank = {
        "unopened": 0,
        "access_blocked": 1,
        "opened": 2,
        "rejected": 3,
        "accepted": 4,
    }
    preferred = second if rank[second.access_status] >= rank[first.access_status] else first
    return preferred.model_copy(
        update={
            "chapter_ids": tuple(sorted(set(first.chapter_ids) | set(second.chapter_ids))),
            "likely_topics": tuple(
                sorted(set(first.likely_topics) | set(second.likely_topics))
            ),
            "discovery_query": (
                second.discovery_query
                if second.discovery_query != "unknown_not_recorded"
                else first.discovery_query
            ),
        }
    )


def _evidence_urls(notebook: str) -> set[str]:
    urls = set()
    for line in notebook.splitlines():
        if not line.startswith("SOURCE_CLAIM_JSON:"):
            continue
        try:
            payload = json.loads(line.partition(":")[2].strip())
        except json.JSONDecodeError:
            continue
        if not _valid_source_claim(payload):
            continue
        canonical = _canonical_url(str(payload["url"]))
        if canonical:
            urls.add(canonical)
    return urls


def _evidence_routes(notebook: str) -> dict[str, tuple[str, ...]]:
    routes: dict[str, set[str]] = {}
    for line in notebook.splitlines():
        if not line.startswith("SOURCE_CLAIM_JSON:"):
            continue
        try:
            payload = json.loads(line.partition(":")[2].strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        canonical = _canonical_url(str(payload.get("url", "")))
        chapters = payload.get("chapter_ids")
        if not canonical or not isinstance(chapters, list):
            continue
        valid = {str(item) for item in chapters if re.fullmatch(r"[1-8]B", str(item))}
        if valid:
            routes.setdefault(canonical, set()).update(valid)
    return {url: tuple(sorted(chapters)) for url, chapters in routes.items()}


def _valid_source_claim(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    required_text = (
        "provisional_id",
        "canonical_fact_key",
        "claim",
        "locator",
        "url",
    )
    if any(not str(payload.get(field, "")).strip() for field in required_text):
        return False
    if str(payload.get("disposition", "")).casefold() not in {
        "accepted",
        "final_evidence",
    }:
        return False
    chapters = payload.get("chapter_ids")
    methods = payload.get("methodology_ids")
    allowed_chapters = {f"{number}B" for number in range(1, 9)}
    return (
        isinstance(chapters, list)
        and bool(chapters)
        and all(str(item) in allowed_chapters for item in chapters)
        and isinstance(methods, list)
    )


__all__ = [
    "SourceCandidate",
    "SourceCandidateCatalog",
    "read_source_candidate_catalog",
    "recover_source_candidate_catalog",
    "seed_source_candidate_catalog",
    "write_source_candidate_catalog",
]
