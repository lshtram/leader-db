"""Strict no-search curation for saturated chapter evidence."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifacts import write_json
from .prompts import saturation_curation
from .runner import _json_answer, _no_search_turn, _read_json


class CuratedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(pattern=r"^E[0-9]{4,}$")
    disposition: Literal["retain", "context", "drop"]
    source_family: str = Field(min_length=1)
    duplicate_of: str | None
    reason: str = Field(min_length=1)


class CurationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retained: int = Field(ge=0)
    context: int = Field(ge=0)
    dropped: int = Field(ge=0)
    remaining_concerns: tuple[str, ...]


class ChapterCuration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    records: tuple[CuratedRecord, ...] = Field(min_length=1)
    summary: CurationSummary

    @model_validator(mode="after")
    def _summary_matches(self) -> ChapterCuration:
        counts = Counter(record.disposition for record in self.records)
        actual = (counts["retain"], counts["context"], counts["drop"])
        expected = (self.summary.retained, self.summary.context, self.summary.dropped)
        if actual != expected:
            raise ValueError("curation summary counts do not match records")
        return self


def curate_saturation_run(
    *,
    project_root: Path,
    output_dir: Path,
    ruler: str,
    year: int,
    chapter_id: str,
    researcher_name: str = "gpt-5.4-mini",
) -> dict[str, object]:
    """Curate one saved ledger once and persist a strict complete disposition."""

    evidence = _read_json(output_dir / "evidence-ledger.json")
    evidence_ids = {str(record["evidence_id"]) for record in evidence}
    matching = _matching_curation(output_dir, evidence_ids)
    if matching is not None:
        normalized = _read_json(matching)
    else:
        version = len(list(output_dir.glob("curation-v*.json"))) + 1
        path = (
            output_dir / "curation.json"
            if not (output_dir / "curation.json").exists()
            else output_dir / f"curation-v{version:02d}.json"
        )
        work = output_dir / f".{path.stem}"
        normalized = _curate(
            project_root=project_root,
            work=work,
            researcher_name=researcher_name,
            prompt=saturation_curation(ruler, year, chapter_id, evidence),
            evidence=evidence,
        )
        write_json(path, normalized)
        matching = path
    value = ChapterCuration.model_validate(normalized)
    warnings = _curation_warnings(value, evidence)
    if not warnings or (matching is not None and matching.stem.endswith("-final")):
        return value.model_dump(mode="json")
    assert matching is not None
    revision_path = matching.with_name(f"{matching.stem}-final.json")
    if revision_path.exists():
        return _read_json(revision_path)
    revised = _curate(
        project_root=project_root,
        work=output_dir / f".{matching.stem}-revision",
        researcher_name=researcher_name,
        prompt=saturation_curation(ruler, year, chapter_id, evidence)
        + "\n\nREQUIRED REVISION\n"
        + "\n".join(warnings),
        evidence=evidence,
    )
    write_json(revision_path, revised)
    return revised


def _matching_curation(output_dir: Path, evidence_ids: set[str]) -> Path | None:
    """Return the newest saved curation that exactly matches the active ledger."""

    candidates = sorted(
        output_dir.glob("curation*.json"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for path in candidates:
        value = ChapterCuration.model_validate(_read_json(path))
        if {record.evidence_id for record in value.records} == evidence_ids:
            return path
    return None


def _curate(
    *,
    project_root: Path,
    work: Path,
    researcher_name: str,
    prompt: str,
    evidence: list[dict[str, object]],
) -> dict[str, object]:
    completed = sorted(work.glob("turn-*.md"))
    raw = (
        _json_answer(completed[-1].read_text(encoding="utf-8"))
        if completed
        else _no_search_turn(
            project_root,
            work,
            researcher_name,
            prompt,
        )
    )
    _normalize_summary(raw)
    value = ChapterCuration.model_validate(raw)
    expected_ids = [str(record["evidence_id"]) for record in evidence]
    actual_ids = [record.evidence_id for record in value.records]
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise ValueError("curation must include every evidence ID exactly once")
    normalized = value.model_dump(mode="json")
    return normalized


def _normalize_summary(value: dict[str, object]) -> None:
    """Derive redundant summary counts from the authoritative dispositions."""

    records = value.get("records")
    summary = value.get("summary")
    if not isinstance(records, list) or not isinstance(summary, dict):
        return
    counts = Counter(
        str(record.get("disposition"))
        for record in records
        if isinstance(record, dict)
    )
    summary.update(
        retained=counts["retain"],
        context=counts["context"],
        dropped=counts["drop"],
    )


def _curation_warnings(
    value: ChapterCuration,
    evidence: list[dict[str, object]] | None = None,
) -> tuple[str, ...]:
    kept = [record for record in value.records if record.disposition != "drop"]
    families = Counter(record.source_family for record in kept)
    if not kept or not families:
        return ()
    family, count = families.most_common(1)[0]
    share = count / len(kept)
    warnings = []
    if share > 0.25:
        warnings.append(
            f"Revise the complete curation because source family {family!r} supplies "
            f"{count}/{len(kept)} retained or context records ({share:.1%}), above "
            "the 25% family ceiling. Prefer synthesis and no more than two "
            "illustrative incidents per repeated mechanism. Return every evidence "
            "ID again."
        )
    if evidence is not None:
        by_id = {str(record["evidence_id"]): record for record in evidence}
        official = sum(
            str(by_id[record.evidence_id].get("source_type"))
            in {"official", "primary", "legal", "official/legal"}
            for record in kept
        )
        official_share = official / len(kept)
        if official_share > 0.67:
            warnings.append(
                f"Revise because official or primary-government material supplies "
                f"{official}/{len(kept)} kept records ({official_share:.1%}), above "
                "the 67% ceiling. Preserve more of the supplied independent outcome, "
                "criticism, distribution, and attribution evidence."
            )
    return tuple(warnings)


__all__ = ["ChapterCuration", "CuratedRecord", "curate_saturation_run"]
