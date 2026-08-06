"""Adapt a validated ruler dossier for question-complete chapter analysis."""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from pathlib import Path

from .corpus_judge_package import CorpusJudgePackage, _clusters, _question_index
from .corpus_reader_models import BoundEvidence
from .dossier_models import RulerEvidenceDossier


def build_dossier_analysis_package(dossier_path: Path, output_path: Path) -> Path:
    """Convert dossier evidence without changing its claims, locators, or routing."""

    dossier = RulerEvidenceDossier.model_validate_json(
        dossier_path.read_text(encoding="utf-8")
    )
    routes: dict[str, list[str]] = defaultdict(list)
    relations: dict[str, set[str]] = defaultdict(set)
    for mapping in dossier.mappings:
        routes[mapping.evidence_id].append(mapping.methodology_id)
        relations[mapping.evidence_id].add(mapping.relation)
    evidence = tuple(
        _convert(item, routes[item.evidence_id], relations[item.evidence_id])
        for item in dossier.evidence
        if item.final_evidence_use != "discovery_only" and routes[item.evidence_id]
    )
    clusters = _clusters(evidence, fact_keys={})
    questions = tuple(
        _question_index(methodology_id, evidence, clusters)
        for methodology_id in dossier.methodology_ids
    )
    package = CorpusJudgePackage(
        evidence=evidence,
        clusters=clusters,
        questions=questions,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(package.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def _convert(item, question_ids: list[str], relations: set[str]) -> BoundEvidence:
    excerpt = item.excerpt or item.claim
    url_hash = sha256(item.url.encode()).hexdigest()
    return BoundEvidence(
        evidence_id=item.evidence_id,
        source_id=f"DOSSIER-{url_hash[:16]}",
        url=item.url,
        title=item.title,
        publisher=item.publisher,
        raw_sha256=url_hash,
        fact_summary=item.claim,
        question_ids=tuple(sorted(set(question_ids))),
        polarity=_polarity(relations),
        period_fit=item.period_fit,
        ruler_attribution=item.ruler_attribution,
        limitations=tuple(
            dict.fromkeys((item.source_confidence_reason, *item.contrary_evidence))
        ),
        start_unit=1,
        end_unit=1,
        locator=item.source_locator,
        exact_excerpt=excerpt,
        excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
        verification_status="accepted",
        verification_notes=("Validated upstream RulerEvidenceDossier evidence.",),
    )


def _polarity(relations: set[str]) -> str:
    if len(relations) > 1:
        return "mixed"
    relation = next(iter(relations), "context")
    return {
        "supports": "favorable",
        "contradicts": "adverse",
        "qualifies": "mixed",
        "context": "context",
    }.get(relation, "context")


__all__ = ["build_dossier_analysis_package"]
