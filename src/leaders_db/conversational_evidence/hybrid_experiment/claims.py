"""Strict parsing and deterministic formatting of chapter-wide source claims."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from leaders_db.conversational_evidence.deep_artifacts import canonical_url

_CLAIM_PREFIX = "SOURCE_CLAIM_JSON:"
_REUSE_PREFIX = "REUSE_JSON:"
_MARKDOWN_LIST_PREFIXES = ("- ", "* ", "+ ")


class AcceptedClaim(BaseModel):
    """One accepted, traceable source-claim unit emitted by the researcher."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    publication_date: str = Field(min_length=1)
    url: HttpUrl
    claim: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_confidence: Literal[
        "very_low", "low", "medium_low", "medium", "medium_high", "high"
    ]
    source_confidence_reason: str = Field(min_length=1)
    final_evidence_use: Literal["final_evidence", "context", "discovery_only"]
    period_fit: str = Field(min_length=1)
    ruler_attribution: str = Field(min_length=1)
    contrary_evidence: tuple[str, ...]
    lenses: tuple[str, ...] = Field(min_length=1)

    @field_validator("lenses")
    @classmethod
    def _unique_lenses(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("lenses must be unique")
        return value


class ReusedClaim(BaseModel):
    """Explicit mapping from existing global evidence to the current chapter."""

    model_config = ConfigDict(extra="forbid")

    evidence_ids: tuple[str, ...] = Field(min_length=1)
    lenses: tuple[str, ...] = Field(min_length=1)


class LedgerClaim(AcceptedClaim):
    """Globally identified accepted claim with reconciled mappings."""

    evidence_id: str
    canonical_url: str
    canonical_fact_key: str
    chapters: tuple[str, ...]


def parse_chapter_note(note: str, chapter_id: str) -> tuple[AcceptedClaim, ...]:
    """Parse and validate every accepted source-claim JSON line."""

    claims, _ = _chapter_claim_records(note)
    if not claims:
        raise ValueError(f"{chapter_id} note contains no {_CLAIM_PREFIX} records")
    for claim in claims:
        if any(not lens.startswith(f"{chapter_id}.") for lens in claim.lenses):
            raise ValueError(f"{chapter_id} claim contains a cross-chapter lens")
    return claims


def chapter_parse_errors(note: str) -> tuple[dict[str, object], ...]:
    """Describe malformed claim lines that were excluded from the ledger."""

    _, errors = _chapter_claim_records(note)
    return errors


def parse_reuse(note: str, chapter_id: str) -> tuple[ReusedClaim, ...]:
    """Parse explicit existing-evidence mappings from one chapter note."""

    records = tuple(
        ReusedClaim.model_validate(_line_json(_record_line(line), _REUSE_PREFIX))
        for line in note.splitlines()
        if _record_line(line).startswith(_REUSE_PREFIX)
    )
    for record in records:
        if any(not lens.startswith(f"{chapter_id}.") for lens in record.lenses):
            raise ValueError(f"{chapter_id} reuse contains a cross-chapter lens")
    return records


def parse_follow_up(note: str) -> tuple[AcceptedClaim, ...]:
    """Validate optional grouped follow-up claims and their exact lens IDs."""

    claims = _parse_claim_lines(note)
    allowed = {f"{chapter}B.{lens}" for chapter in range(1, 9) for lens in range(1, 11)}
    for claim in claims:
        if any(lens not in allowed for lens in claim.lenses):
            raise ValueError("follow-up claim contains an invalid lens")
    return claims


def build_ledger(output_dir: Path) -> tuple[LedgerClaim, ...]:
    """Build stable claim IDs from saved chapter notes in guide order."""

    records: dict[str, dict[str, object]] = {}
    id_index: dict[str, str] = {}
    for chapter_number in range(1, 9):
        chapter_id = f"{chapter_number}B"
        path = output_dir / "chapters" / f"{chapter_id}.md"
        if not path.exists():
            continue
        note = path.read_text(encoding="utf-8")
        for claim in parse_chapter_note(note, chapter_id):
            key = _claim_key(claim)
            row = records.get(key)
            if row is None:
                evidence_id = f"E{len(records) + 1:04d}"
                row = {
                    **claim.model_dump(mode="json"),
                    "evidence_id": evidence_id,
                    "canonical_url": canonical_url(str(claim.url)),
                    "canonical_fact_key": key,
                    "chapters": [],
                }
                records[key] = row
                id_index[evidence_id] = key
            _merge(row, chapter_id, claim.lenses)
        for reuse in parse_reuse(note, chapter_id):
            for evidence_id in reuse.evidence_ids:
                key = id_index.get(evidence_id)
                if key is None:
                    raise ValueError(f"{chapter_id} reuses unknown evidence ID {evidence_id}")
                _merge(records[key], chapter_id, reuse.lenses)
    follow_up = output_dir / "follow-up.md"
    if follow_up.exists():
        for claim in parse_follow_up(follow_up.read_text(encoding="utf-8")):
            chapters = sorted({lens.partition(".")[0] for lens in claim.lenses})
            if any(chapter not in {f"{number}B" for number in range(1, 9)} for chapter in chapters):
                raise ValueError("follow-up claim contains an invalid lens")
            key = _claim_key(claim)
            row = records.get(key)
            if row is None:
                evidence_id = f"E{len(records) + 1:04d}"
                row = {
                    **claim.model_dump(mode="json"),
                    "evidence_id": evidence_id,
                    "canonical_url": canonical_url(str(claim.url)),
                    "canonical_fact_key": key,
                    "chapters": [],
                }
                records[key] = row
            for chapter_id in chapters:
                lenses = tuple(lens for lens in claim.lenses if lens.startswith(chapter_id))
                _merge(row, chapter_id, lenses)
    return tuple(LedgerClaim.model_validate(item) for item in records.values())


def ledger_quality(records: tuple[LedgerClaim, ...]) -> dict[str, object]:
    """Report URL, source-family, claim, and exact lens coverage."""

    chapters: dict[str, object] = {}
    for chapter_number in range(1, 9):
        chapter_id = f"{chapter_number}B"
        selected = [
            item
            for item in records
            if chapter_id in item.chapters and item.final_evidence_use != "discovery_only"
        ]
        urls = {item.canonical_url for item in selected}
        domains = Counter(_domain(item.canonical_url) for item in selected)
        lenses = sorted(
            {lens for item in selected for lens in item.lenses if lens.startswith(chapter_id)}
        )
        warnings = []
        if len(urls) < 10:
            warnings.append("fewer_than_10_distinct_urls")
        if len(domains) < 5:
            warnings.append("fewer_than_5_domains")
        if selected and domains.most_common(1)[0][1] / len(selected) > 0.35:
            warnings.append("top_domain_above_35_percent_of_claims")
        if len(lenses) < 10:
            warnings.append("not_all_lenses_explicitly_mapped")
        chapters[chapter_id] = {
            "accepted_claims": len(selected),
            "distinct_urls": len(urls),
            "domains": len(domains),
            "mapped_lenses": lenses,
            "top_domains": domains.most_common(5),
            "warnings": warnings,
        }
    accepted = [item for item in records if item.final_evidence_use != "discovery_only"]
    return {
        "accepted_claims": len(accepted),
        "discovery_only_claims": len(records) - len(accepted),
        "distinct_urls": len({item.canonical_url for item in accepted}),
        "distinct_domains": len({_domain(item.canonical_url) for item in accepted}),
        "chapters": chapters,
    }


def dossier(
    *,
    ruler: str,
    country: str,
    iso3: str,
    year: int,
    records: tuple[LedgerClaim, ...],
    review: dict[str, object],
    notes: dict[str, str],
) -> dict[str, object]:
    """Serialize the validated ledger without a generative formatting turn."""

    dispositions = _review_dispositions(review, records)
    return {
        "schema_version": "hybrid_experiment_dossier_v2",
        "identity": {"ruler": ruler, "country": country, "iso3": iso3, "year": year},
        "evidence": [
            {
                **item.model_dump(mode="json"),
                "review_disposition": dispositions.get(
                    item.evidence_id, {"status": "accepted", "reasons": []}
                ),
            }
            for item in records
        ],
        "mappings": [
            {"evidence_id": item.evidence_id, "lenses": item.lenses}
            for item in records
        ],
        "chapter_notes": notes,
        "review": review,
        "formatting": {
            "method": "deterministic_validated_parser",
            "research_added": False,
            "scores_added": False,
        },
    }


def _line_json(line: str, prefix: str) -> object:
    try:
        return json.loads(line.removeprefix(prefix).strip())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {prefix} JSON: {exc}") from exc


def _record_line(line: str) -> str:
    """Remove conventional list and inline-code wrappers from a record line."""

    stripped = line.lstrip()
    for prefix in _MARKDOWN_LIST_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped.removeprefix(prefix)
            break
    if stripped.startswith("`") and stripped.endswith("`"):
        return stripped[1:-1]
    return stripped


def _parse_claim_lines(note: str) -> tuple[AcceptedClaim, ...]:
    return tuple(
        AcceptedClaim.model_validate(_line_json(_record_line(line), _CLAIM_PREFIX))
        for line in note.splitlines()
        if _record_line(line).startswith(_CLAIM_PREFIX)
    )


def _chapter_claim_records(
    note: str,
) -> tuple[tuple[AcceptedClaim, ...], tuple[dict[str, object], ...]]:
    claims = []
    errors = []
    for line_number, raw_line in enumerate(note.splitlines(), start=1):
        line = _record_line(raw_line)
        if not line.startswith(_CLAIM_PREFIX):
            continue
        try:
            claims.append(
                AcceptedClaim.model_validate(_line_json(line, _CLAIM_PREFIX))
            )
        except (ValueError, TypeError) as exc:
            errors.append(
                {
                    "line_number": line_number,
                    "reason": str(exc),
                    "record_sha256": hashlib.sha256(
                        raw_line.encode("utf-8")
                    ).hexdigest(),
                }
            )
    return tuple(claims), tuple(errors)


def _claim_key(claim: AcceptedClaim) -> str:
    value = "\n".join(
        (canonical_url(str(claim.url)), claim.locator.strip(), claim.claim.strip())
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _merge(row: dict[str, object], chapter_id: str, lenses: tuple[str, ...]) -> None:
    row["chapters"] = sorted(set(row["chapters"]) | {chapter_id})
    row["lenses"] = sorted(set(row["lenses"]) | set(lenses))


def _domain(url: str) -> str:
    return url.split("/", 3)[2].removeprefix("www.")


def _review_dispositions(
    review: dict[str, object], records: tuple[LedgerClaim, ...]
) -> dict[str, dict[str, object]]:
    known = {item.evidence_id for item in records}
    result: dict[str, dict[str, object]] = {}
    chapters = review.get("chapters", [])
    if not isinstance(chapters, list):
        raise ValueError("review chapters must be a list")
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        for removal in chapter.get("remove_or_contextualize", []):
            if not isinstance(removal, dict):
                continue
            evidence_id = str(removal.get("evidence_id", ""))
            if evidence_id not in known:
                raise ValueError(f"review references unknown evidence ID {evidence_id}")
            value = result.setdefault(
                evidence_id,
                {"status": "contextualize_or_remove", "reasons": []},
            )
            value["reasons"].append(
                {
                    "chapter_id": chapter.get("chapter_id"),
                    "reason": removal.get("reason"),
                }
            )
    return result


__all__ = [
    "AcceptedClaim", "LedgerClaim", "ReusedClaim", "build_ledger", "dossier",
    "ledger_quality", "parse_chapter_note", "parse_follow_up", "parse_reuse",
]
