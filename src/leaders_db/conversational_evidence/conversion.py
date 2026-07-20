"""Deterministically validate and project conversational evidence for judges."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from hashlib import sha256
from pathlib import Path
from typing import Any

from leaders_db.normalize.leader_names import normalize_leader_name
from leaders_db.research.chapter_guides import load_chapter_guide
from leaders_db.research.chapter_projection import (
    RulerChapterProjection,
    build_ruler_chapter_projection,
    estimate_chapter_projection_batch_context,
)
from leaders_db.research.dossier_models import RulerEvidenceDossier

from .data import load, questions

CHAPTERS = tuple(f"{number}B" for number in range(1, 9))


def convert_batch(
    manifest_path: Path,
    batch_dir: Path,
    catalog_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate one batch and write every projection with a resolvable identity."""

    manifest = _object(manifest_path)
    year = int(manifest["year"])
    researcher_name = str(manifest["researcher"])
    researcher = load("researchers.json").get(researcher_name)
    if not isinstance(researcher, dict):
        raise ValueError(f"unknown researcher configuration: {researcher_name}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("batch manifest must contain cases")
    output_dir.mkdir(parents=True, exist_ok=True)
    prior_path = output_dir / "local-priors-unavailable.json"
    _write_json(
        prior_path,
        {
            "status": "not_available",
            "reason": "The conversational collector did not ingest structured local priors.",
        },
    )
    prior_hash = _file_hash(prior_path)
    connection = sqlite3.connect(f"file:{catalog_path}?mode=ro", uri=True)
    reports: list[dict[str, Any]] = []
    try:
        for case in cases:
            reports.append(
                _convert_case(
                    connection,
                    case=case,
                    year=year,
                    batch_id=str(manifest["batch_id"]),
                    researcher_name=researcher_name,
                    researcher=researcher,
                    batch_dir=batch_dir,
                    output_dir=output_dir,
                    prior_path=prior_path,
                    prior_hash=prior_hash,
                )
            )
    finally:
        connection.close()
    chapter_reports = []
    expected_iso3 = [str(case["iso3"]).upper() for case in cases]
    for chapter in CHAPTERS:
        paths = [
            report["projections"][chapter] for report in reports if report["status"] == "ready"
        ]
        missing = [report["iso3"] for report in reports if report["status"] != "ready"]
        projections = tuple(
            RulerChapterProjection.model_validate(_object(Path(path))) for path in paths
        )
        context_estimate = None
        if projections:
            guide_text, _ = load_chapter_guide(chapter)
            prompt_overhead = 5_000 + (len(guide_text.encode("utf-8")) + 2) // 3
            estimate = estimate_chapter_projection_batch_context(
                projections,
                context_ceiling=1_000_000_000,
                prompt_overhead_tokens=prompt_overhead,
            )
            context_estimate = {
                "projection_count": estimate.projection_count,
                "projection_tokens": estimate.projection_tokens,
                "prompt_overhead_tokens": estimate.prompt_overhead_tokens,
                "estimated_input_tokens": estimate.estimated_input_tokens,
                "estimated_20_ruler_input_tokens": round(
                    estimate.projection_tokens * len(cases) / len(projections)
                )
                + estimate.prompt_overhead_tokens,
                "bytes_per_token": estimate.bytes_per_token,
            }
        cohort = {
            "schema_version": "conversational_judge_cohort_v1",
            "batch_id": str(manifest["batch_id"]),
            "year": year,
            "chapter_id": chapter,
            "expected_iso3": expected_iso3,
            "projection_paths": paths,
            "missing_iso3": missing,
            "ready_for_judging": not missing,
            "context_estimate": context_estimate,
        }
        cohort_path = output_dir / "chapters" / f"{chapter}.json"
        _write_json(cohort_path, cohort)
        chapter_reports.append({**cohort, "path": str(cohort_path)})
    report = {
        "schema_version": "conversational_conversion_report_v1",
        "batch_id": str(manifest["batch_id"]),
        "year": year,
        "llm_calls": 0,
        "expected_rulers": len(cases),
        "ready_rulers": sum(item["status"] == "ready" for item in reports),
        "blocked_rulers": sum(item["status"] != "ready" for item in reports),
        "ready_for_judging": all(item["status"] == "ready" for item in reports),
        "rulers": reports,
        "chapters": chapter_reports,
    }
    _write_json(output_dir / "conversion-report.json", report)
    return report


def _convert_case(
    connection: sqlite3.Connection,
    *,
    case: dict[str, Any],
    year: int,
    batch_id: str,
    researcher_name: str,
    researcher: dict[str, Any],
    batch_dir: Path,
    output_dir: Path,
    prior_path: Path,
    prior_hash: str,
) -> dict[str, Any]:
    iso3 = str(case["iso3"]).upper()
    ruler = str(case["ruler"])
    country = str(case["country"])
    source_dir = batch_dir / "outputs" / f"{iso3.lower()}-{year}"
    hybrid = (source_dir / "dossier.json").is_file()
    errors = (
        _validate_hybrid_source(source_dir, ruler=ruler, country=country, year=year)
        if hybrid
        else _validate_source(source_dir, ruler=ruler, country=country, year=year)
    )
    identity = _resolve_identity(connection, iso3=iso3, ruler=ruler, year=year)
    if identity is None:
        errors.append("No exact local ruler_year identity matches this ruler, ISO3, and year.")
    if errors:
        return {"iso3": iso3, "ruler": ruler, "status": "blocked", "errors": errors}
    assert identity is not None
    profile = _object(source_dir / "profile.json")
    if hybrid:
        source_dossier = _object(source_dir / "dossier.json")
        missing_titles = 0
        missing_dates = 0
        dossier = _build_hybrid_dossier(
            iso3=iso3,
            ruler=ruler,
            country=country,
            year=year,
            batch_id=batch_id,
            researcher_name=researcher_name,
            researcher=researcher,
            identity=identity,
            source=source_dossier,
            profile=profile,
            prior_path=prior_path,
            prior_hash=prior_hash,
        )
    else:
        evidence_payload = _object(source_dir / "evidence.json")
        mappings_payload = _object(source_dir / "mappings.json")
        missing_titles = sum(
            not str(item.get("title", "")).strip() for item in evidence_payload["evidence"]
        )
        missing_dates = sum(
            not str(item.get("date", "")).strip() for item in evidence_payload["evidence"]
        )
        dossier = _build_dossier(
            iso3=iso3,
            ruler=ruler,
            country=country,
            year=year,
            batch_id=batch_id,
            researcher_name=researcher_name,
            researcher=researcher,
            identity=identity,
            evidence_payload=evidence_payload,
            mappings_payload=mappings_payload,
            profile=profile,
            prior_path=prior_path,
            prior_hash=prior_hash,
        )
    dossier_path = output_dir / "dossiers" / f"{iso3}-{identity['ruler_year_id']}.json"
    _write_json(dossier_path, dossier.model_dump(mode="json"))
    dossier_hash = _file_hash(dossier_path)
    projection_paths: dict[str, str] = {}
    for chapter in CHAPTERS:
        projection = build_ruler_chapter_projection(
            dossier,
            chapter_id=chapter,
            source_dossier_path=dossier_path,
            source_dossier_sha256=dossier_hash,
        )
        path = output_dir / "projections" / chapter / f"{iso3}-{identity['ruler_year_id']}.json"
        _write_json(path, projection.model_dump(mode="json"))
        projection_paths[chapter] = str(path)
    return {
        "iso3": iso3,
        "ruler": ruler,
        "status": "ready",
        "ruler_id": identity["ruler_id"],
        "ruler_year_id": identity["ruler_year_id"],
        "evidence_records": len(dossier.evidence),
        "mappings": len(dossier.mappings),
        "warnings": [
            *([] if hybrid else [
                "Evidence polarity, source type/confidence, precise locator, and ruler "
                "attribution were not captured; deterministic placeholders preserve "
                "that missingness."
            ]),
            "Structured local priors were not collected and are explicitly unavailable.",
            f"{missing_titles} evidence records use title_not_recorded.",
            f"{missing_dates} evidence records use date_not_recorded.",
        ],
        "dossier_path": str(dossier_path),
        "projections": projection_paths,
    }


def _validate_hybrid_source(
    source_dir: Path, *, ruler: str, country: str, year: int
) -> list[str]:
    errors: list[str] = []
    for name in ("dossier.json", "session.json", "profile.json"):
        if not (source_dir / name).is_file():
            errors.append(f"Missing {name}.")
    if errors:
        return errors
    source = _object(source_dir / "dossier.json")
    identity = source.get("identity")
    if not isinstance(identity, dict) or any(
        identity.get(key) != value
        for key, value in (("ruler", ruler), ("country", country), ("year", year))
    ):
        errors.append("dossier.json identity does not match the manifest.")
    raw_evidence = source.get("evidence")
    raw_mappings = source.get("mappings")
    if not isinstance(raw_evidence, list) or not isinstance(raw_mappings, list):
        errors.append("Hybrid dossier evidence or mappings have the wrong shape.")
        return errors
    ids = [item.get("evidence_id") for item in raw_evidence if isinstance(item, dict)]
    if len(ids) != len(raw_evidence) or len(ids) != len(set(ids)):
        errors.append("Evidence IDs are missing or duplicated.")
    known = set(ids)
    configured = {item["id"] for item in questions()}
    for mapping in raw_mappings:
        if not isinstance(mapping, dict) or mapping.get("evidence_id") not in known:
            errors.append("Hybrid mapping references unknown evidence.")
            continue
        lenses = mapping.get("lenses")
        if not isinstance(lenses, list) or not set(lenses).issubset(configured):
            errors.append("Hybrid mapping contains an unknown evidence lens.")
    return errors


def _validate_source(source_dir: Path, *, ruler: str, country: str, year: int) -> list[str]:
    errors: list[str] = []
    required = ("evidence.json", "mappings.json", "session.json", "profile.json")
    for name in required:
        if not (source_dir / name).is_file():
            errors.append(f"Missing {name}.")
    if errors:
        return errors
    evidence = _object(source_dir / "evidence.json")
    mappings = _object(source_dir / "mappings.json")
    session = _object(source_dir / "session.json")
    expected = {"ruler": ruler, "country": country, "year": year}
    for name, payload in (
        ("evidence.json", evidence),
        ("mappings.json", mappings),
        ("session.json", session),
    ):
        if any(payload.get(key) != value for key, value in expected.items()):
            errors.append(f"{name} identity does not match the manifest.")
    question_ids = tuple(item["id"] for item in questions())
    completed = set(session.get("completed", []))
    if session.get("pending") is not None or not set(question_ids).issubset(completed):
        errors.append("Session has not completed all 80 questions.")
    raw_evidence = evidence.get("evidence")
    raw_mappings = mappings.get("questions")
    if not isinstance(raw_evidence, list) or not isinstance(raw_mappings, dict):
        errors.append("Evidence or mapping payload has the wrong shape.")
        return errors
    ids = [item.get("id") for item in raw_evidence if isinstance(item, dict)]
    if len(ids) != len(raw_evidence) or len(ids) != len(set(ids)):
        errors.append("Evidence IDs are missing or duplicated.")
    known = set(ids)
    if set(raw_mappings) != set(question_ids):
        errors.append("Mappings do not contain exactly the configured 80 questions.")
    for question_id, mapping in raw_mappings.items():
        if not isinstance(mapping, dict) or not mapping.get("evidence_ids"):
            errors.append(f"{question_id} has no evidence mapping.")
            continue
        if not set(mapping["evidence_ids"]).issubset(known):
            errors.append(f"{question_id} references unknown evidence.")
    return errors


def _resolve_identity(
    connection: sqlite3.Connection, *, iso3: str, ruler: str, year: int
) -> dict[str, int] | None:
    rows = connection.execute(
        """
        SELECT ry.id, l.id, l.full_name
        FROM ruler_years AS ry
        JOIN leaders AS l ON l.id = ry.leader_id
        JOIN countries AS c ON c.id = ry.country_id
        WHERE c.iso3 = ? AND ry.year = ?
        """,
        (iso3, year),
    ).fetchall()
    expected_name = normalize_leader_name(ruler)
    rows = [row for row in rows if normalize_leader_name(str(row[2])) == expected_name]
    if len(rows) != 1:
        return None
    return {"ruler_year_id": int(rows[0][0]), "ruler_id": int(rows[0][1])}


def _build_dossier(
    *,
    iso3: str,
    ruler: str,
    country: str,
    year: int,
    batch_id: str,
    researcher_name: str,
    researcher: dict[str, Any],
    identity: dict[str, int],
    evidence_payload: dict[str, Any],
    mappings_payload: dict[str, Any],
    profile: dict[str, Any],
    prior_path: Path,
    prior_hash: str,
) -> RulerEvidenceDossier:
    methodology_ids = tuple(item["id"] for item in questions())
    evidence = [
        {
            "evidence_id": item["id"],
            "claim": item["summary"],
            "url": item["url"],
            "title": str(item.get("title", "")).strip() or "title_not_recorded",
            "publisher": (str(item.get("publisher", "")).strip() or "publisher_not_recorded"),
            "publication_date": (str(item.get("date", "")).strip() or "date_not_recorded"),
            "excerpt": item["summary"],
            "source_type": "unclassified_by_conversational_collector",
            "source_confidence": "not_assessed",
            "source_confidence_reason": (
                "No deterministic source-confidence classification was collected."
            ),
            "final_evidence_use": "context",
            "period_fit": "not_independently_assessed",
            "ruler_attribution": "not_independently_assessed",
        }
        for item in evidence_payload["evidence"]
    ]
    mappings = []
    coverage = []
    for methodology_id in methodology_ids:
        source_mapping = mappings_payload["questions"][methodology_id]
        evidence_ids = tuple(source_mapping["evidence_ids"])
        mappings.extend(
            {
                "evidence_id": evidence_id,
                "methodology_id": methodology_id,
                "relation": "context",
                "relevance": (
                    "The conversational researcher mapped this claim to this evidence "
                    "lens; polarity was not collected."
                ),
            }
            for evidence_id in evidence_ids
        )
        coverage.append(
            {
                "methodology_id": methodology_id,
                "status": "covered",
                "evidence_ids": evidence_ids,
                "reason": source_mapping.get("search_note")
                or "Cited evidence was mapped to this lens.",
            }
        )
    research_usage = profile["research"]["usage"]
    formatter_usage = profile["formatter"]["usage"]
    total_input = int(research_usage["input_tokens"]) + int(formatter_usage["input_tokens"])
    total_output = int(research_usage["output_tokens"]) + int(formatter_usage["output_tokens"])
    return RulerEvidenceDossier.model_validate(
        {
            "schema_version": "ruler_evidence_dossier_v2",
            "job_key": f"dossier:{batch_id}:{year}:{iso3}:{identity['ruler_year_id']}",
            "run_key": batch_id,
            "iso3": iso3,
            "country_name": country,
            "ruler_id": str(identity["ruler_id"]),
            "ruler_year_id": identity["ruler_year_id"],
            "ruler_name": ruler,
            "period_start_year": year,
            "period_end_year": year,
            "methodology_ids": methodology_ids,
            "evidence": evidence,
            "mappings": mappings,
            "coverage": coverage,
            "unresolved_gaps": [
                "Evidence polarity, source confidence, precise locators, period fit, "
                "and ruler attribution require judge-side scrutiny."
            ],
            "completed_queries": [],
            "normalization_warnings": [],
            "local_priors": [
                {
                    "methodology_id": methodology_id,
                    "status": "not_available",
                    "summary": (
                        "The conversational collector did not ingest structured local priors."
                    ),
                    "artifact_path": str(prior_path),
                    "artifact_sha256": prior_hash,
                }
                for methodology_id in methodology_ids
            ],
            "run_profile": {
                "provider_profile": researcher_name,
                "provider": str(researcher["provider"]),
                "model": str(researcher["model"]),
                "workflow_mode": "conversational_evidence_v1",
                "formatter_provider_profile": "luna",
                "formatter_provider": "openai",
                "formatter_model": "luna",
                "source_mix_note": (
                    "Source mix was collected but not independently classified during "
                    "deterministic conversion."
                ),
                "usage": {
                    "input_tokens": total_input,
                    "cached_input_tokens": int(research_usage["cached_input_tokens"])
                    + int(formatter_usage["cached_input_tokens"]),
                    "output_tokens": total_output,
                    "reasoning_output_tokens": int(research_usage["reasoning_output_tokens"])
                    + int(formatter_usage["reasoning_output_tokens"]),
                    "total_tokens": total_input + total_output,
                    "estimated_cost_usd": float(profile["estimated_researcher_cost_usd"]),
                },
            },
        }
    )


def _build_hybrid_dossier(
    *,
    iso3: str,
    ruler: str,
    country: str,
    year: int,
    batch_id: str,
    researcher_name: str,
    researcher: dict[str, Any],
    identity: dict[str, int],
    source: dict[str, Any],
    profile: dict[str, Any],
    prior_path: Path,
    prior_hash: str,
) -> RulerEvidenceDossier:
    methodology_ids = tuple(item["id"] for item in questions())
    excluded = {
        (str(item["evidence_id"]), str(chapter["chapter_id"]))
        for chapter in source["review"]["chapters"]
        for item in chapter.get("remove_or_contextualize", [])
    }
    evidence = [
        {
            "evidence_id": item["evidence_id"],
            "claim": item["claim"],
            "url": item["url"],
            "title": item["title"],
            "publisher": item["publisher"],
            "publication_date": item["publication_date"],
            "excerpt": item["claim"],
            "source_locator": item["locator"],
            "canonical_fact_key": item["canonical_fact_key"],
            "source_type": item["source_type"],
            "source_confidence": item["source_confidence"],
            "source_confidence_reason": item["source_confidence_reason"],
            "final_evidence_use": item["final_evidence_use"],
            "period_fit": item["period_fit"],
            "ruler_attribution": item["ruler_attribution"],
            "contrary_evidence": item.get("contrary_evidence", []),
        }
        for item in source["evidence"]
    ]
    by_lens: dict[str, list[str]] = {methodology_id: [] for methodology_id in methodology_ids}
    mappings = []
    for item in source["mappings"]:
        evidence_id = str(item["evidence_id"])
        for methodology_id in item["lenses"]:
            chapter_id = methodology_id.split(".", maxsplit=1)[0]
            if (evidence_id, chapter_id) in excluded:
                continue
            by_lens[methodology_id].append(evidence_id)
            mappings.append(
                {
                    "evidence_id": evidence_id,
                    "methodology_id": methodology_id,
                    "relation": "context",
                    "relevance": (
                        "The hybrid researcher mapped this reviewed claim to this lens; "
                        "polarity is left for the comparative judge."
                    ),
                }
            )
    coverage = [
        {
            "methodology_id": methodology_id,
            "status": "covered" if by_lens[methodology_id] else "no_evidence_found",
            "evidence_ids": tuple(dict.fromkeys(by_lens[methodology_id])),
            "reason": (
                "Reviewed cited evidence is mapped to this lens."
                if by_lens[methodology_id]
                else "No admissible ruler-attributed evidence remained after review."
            ),
        }
        for methodology_id in methodology_ids
    ]
    usage = profile["usage"]
    total_input = int(usage["input_tokens"])
    total_output = int(usage["output_tokens"])
    gaps = [
        str(gap["gap"])
        for chapter in source["review"]["chapters"]
        for gap in chapter.get("material_gaps", [])
    ]
    return RulerEvidenceDossier.model_validate(
        {
            "schema_version": "ruler_evidence_dossier_v2",
            "job_key": f"dossier:{batch_id}:{year}:{iso3}:{identity['ruler_year_id']}",
            "run_key": batch_id,
            "iso3": iso3,
            "country_name": country,
            "ruler_id": str(identity["ruler_id"]),
            "ruler_year_id": identity["ruler_year_id"],
            "ruler_name": ruler,
            "period_start_year": year,
            "period_end_year": year,
            "methodology_ids": methodology_ids,
            "evidence": evidence,
            "mappings": mappings,
            "coverage": coverage,
            "unresolved_gaps": list(dict.fromkeys(gaps)),
            "completed_queries": [],
            "normalization_warnings": [],
            "local_priors": [
                {
                    "methodology_id": methodology_id,
                    "status": "not_available",
                    "summary": "Structured local priors were not collected in this experiment.",
                    "artifact_path": str(prior_path),
                    "artifact_sha256": prior_hash,
                }
                for methodology_id in methodology_ids
            ],
            "run_profile": {
                "provider_profile": researcher_name,
                "provider": str(researcher["provider"]),
                "model": str(researcher["model"]),
                "workflow_mode": "hybrid_conversational_evidence_v2",
                "formatter_provider_profile": "deterministic_validated_parser",
                "formatter_provider": "local",
                "formatter_model": "none",
                "source_mix_note": (
                    "Rich source metadata and chapter-specific reviewer exclusions "
                    "were preserved during deterministic conversion."
                ),
                "usage": {
                    "input_tokens": total_input,
                    "cached_input_tokens": int(usage["cached_input_tokens"]),
                    "output_tokens": total_output,
                    "reasoning_output_tokens": int(usage["reasoning_output_tokens"]),
                    "total_tokens": total_input + total_output,
                    "estimated_cost_usd": float(profile["estimated_cost_usd"]),
                },
            },
        }
    )


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    pending.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(pending, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("batch_dir", type=Path)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    report = convert_batch(args.manifest, args.batch_dir, args.catalog, args.output_dir)
    print(
        json.dumps(
            {key: report[key] for key in ("ready_rulers", "blocked_rulers", "ready_for_judging")}
        )
    )


if __name__ == "__main__":
    main()
