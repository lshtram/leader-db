"""Apply chapter-specific no-search curation to one complete hybrid ruler run."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .artifacts import CHAPTERS, write_json
from .curation import curate_saturation_run
from .runner import _read_json


def curate_full_run(
    *,
    project_root: Path,
    output_dir: Path,
    researcher_name: str = "gpt-5.4-mini",
) -> dict[str, object]:
    """Curate every chapter and activate a reversible curated dossier."""

    raw_path = output_dir / "dossier-uncurated.json"
    active_path = output_dir / "dossier.json"
    if not raw_path.exists():
        raw_path.write_bytes(active_path.read_bytes())
    source = _read_json(raw_path)
    identity = source["identity"]
    ledger = _read_json(output_dir / "evidence-ledger.json")
    chapter_curations: dict[str, dict[str, Any]] = {}
    for chapter_id in CHAPTERS:
        selected = [
            record
            for record in ledger
            if chapter_id in record["chapters"]
            and record["final_evidence_use"] != "discovery_only"
        ]
        if not selected:
            chapter_curations[chapter_id] = {
                "chapter_id": chapter_id,
                "records": [],
                "summary": {
                    "retained": 0,
                    "context": 0,
                    "dropped": 0,
                    "remaining_concerns": ["No accepted evidence was available."],
                },
            }
            continue
        work = output_dir / "chapter-curation" / chapter_id
        write_json(work / "evidence-ledger.json", selected)
        chapter_curations[chapter_id] = curate_saturation_run(
            project_root=project_root,
            output_dir=work,
            ruler=str(identity["ruler"]),
            year=int(identity["year"]),
            chapter_id=chapter_id,
            researcher_name=researcher_name,
        )
    curated, report = apply_chapter_curations(source, chapter_curations)
    write_json(output_dir / "dossier-curated.json", curated)
    write_json(active_path, curated)
    write_json(output_dir / "curation-summary.json", report)
    return report


def apply_chapter_curations(
    source: dict[str, Any],
    chapter_curations: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, object]]:
    """Filter dossier evidence and mappings from complete curation dispositions."""

    dispositions = {
        (chapter_id, str(record["evidence_id"])): str(record["disposition"])
        for chapter_id, curation in chapter_curations.items()
        for record in curation["records"]
    }
    kept_mappings = []
    kept_lenses: dict[str, list[str]] = {}
    for mapping in source["mappings"]:
        evidence_id = str(mapping["evidence_id"])
        lenses = [
            lens
            for lens in mapping["lenses"]
            if dispositions.get((lens.partition(".")[0], evidence_id)) != "drop"
        ]
        if lenses:
            kept_mappings.append({"evidence_id": evidence_id, "lenses": lenses})
            kept_lenses[evidence_id] = lenses
    evidence = []
    for record in source["evidence"]:
        evidence_id = str(record["evidence_id"])
        lenses = kept_lenses.get(evidence_id)
        if not lenses:
            continue
        evidence.append(
            {
                **record,
                "lenses": lenses,
                "chapters": sorted({lens.partition(".")[0] for lens in lenses}),
            }
        )
    curated = {
        **source,
        "schema_version": "hybrid_experiment_dossier_v3_curated",
        "evidence": evidence,
        "mappings": kept_mappings,
        "curation": {
            "method": "chapter_specific_no_search_source_family_curation",
            "research_added": False,
        },
    }
    chapters = {}
    for chapter_id in CHAPTERS:
        chapter_records = [
            record
            for record in evidence
            if chapter_id in record["chapters"]
        ]
        urls = {record["canonical_url"] for record in chapter_records}
        domains = {_domain(record["canonical_url"]) for record in chapter_records}
        mapped_lenses = sorted(
            {
                lens
                for record in chapter_records
                for lens in record["lenses"]
                if lens.startswith(chapter_id)
            }
        )
        families = Counter(
            str(record["source_family"])
            for record in chapter_curations[chapter_id]["records"]
            if record["disposition"] != "drop"
        )
        chapters[chapter_id] = {
            "distinct_urls": len(urls),
            "domains": len(domains),
            "source_families": len(families),
            "top_source_families": families.most_common(5),
            "mapped_lenses": mapped_lenses,
            "curation_summary": chapter_curations[chapter_id]["summary"],
        }
    report = {
        "schema_version": "full-ruler-curation-summary-v1",
        "raw_evidence_records": len(source["evidence"]),
        "curated_evidence_records": len(evidence),
        "dropped_evidence_records": len(source["evidence"]) - len(evidence),
        "chapters": chapters,
    }
    return curated, report


def _domain(url: str) -> str:
    return url.partition("//")[2].partition("/")[0].lower().removeprefix("www.")


__all__ = ["apply_chapter_curations", "curate_full_run"]
