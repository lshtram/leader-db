"""Build judge projections from approved full-corpus ruler packages."""

from __future__ import annotations

import hashlib
import json
from math import ceil
from pathlib import Path

from .approved_ruler_package import load_approved_ruler_package
from .chapter_analysis_models import ResolvedChapterAnalysis
from .chapter_projection import (
    CONSERVATIVE_BYTES_PER_TOKEN,
    RulerChapterProjection,
    build_ruler_chapter_projection,
)
from .corpus_judge_package import CorpusJudgePackage
from .corpus_reader_models import BoundEvidence
from .dossier_models import (
    DossierEvidence,
    EvidenceQuestionMapping,
    QuestionCoverage,
    RulerEvidenceDossier,
)


def build_approved_chapter_projection(
    dossier: RulerEvidenceDossier,
    *,
    chapter_id: str,
    dossier_path: Path,
    approval_manifest_path: Path,
    project_root: Path,
    target_year: int,
) -> RulerChapterProjection:
    """Project reviewed answers and their complete chapter evidence index for judging."""

    root = project_root.resolve()
    approval = load_approved_ruler_package(
        approval_manifest_path, project_root=root
    )
    _validate_identity(dossier, dossier_path, approval)
    if approval.target_year != target_year:
        raise ValueError("approved ruler package target year differs from judge job")
    selected = next(item for item in approval.chapters if item.chapter_id == chapter_id)
    corpus = CorpusJudgePackage.model_validate_json(
        (root / approval.corpus_package_path).read_text(encoding="utf-8")
    )
    analysis = ResolvedChapterAnalysis.model_validate_json(
        (root / selected.analysis_path).read_text(encoding="utf-8")
    )
    question_ids = tuple(f"{chapter_id}.{index}" for index in range(1, 11))
    cited_ids = {
        evidence_id
        for answer in analysis.answers
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    selected_evidence = tuple(
        item
        for item in corpus.evidence
        if item.evidence_id in cited_ids
    )
    id_map = {
        item.evidence_id: f"E{index:06d}"
        for index, item in enumerate(selected_evidence, start=1)
    }
    evidence = tuple(
        _convert_evidence(item, id_map[item.evidence_id])
        for item in selected_evidence
    )
    mappings = _mappings(selected_evidence, id_map, question_ids, analysis)
    coverage = _coverage(question_ids, mappings)
    answer_by_id = {item.question_id: item for item in analysis.answers}
    answers = tuple(
        {
            "question_id": answer.question_id,
            "answer": answer.answer,
            "supporting_evidence_ids": tuple(
                id_map[item] for item in answer.supporting_evidence_ids
            ),
            "contrary_or_qualifying_evidence_ids": tuple(
                id_map[item] for item in answer.contrary_or_qualifying_evidence_ids
            ),
            "limitations_and_gaps": answer.limitations_and_gaps,
        }
        for question_id in question_ids
        for answer in (answer_by_id[question_id],)
    )
    base = build_ruler_chapter_projection(
        dossier,
        chapter_id=chapter_id,
        source_dossier_path=Path(dossier_path.name),
        source_dossier_sha256=_digest(dossier_path),
    )
    payload = base.model_dump(mode="json")
    payload.update(
        {
            "schema_version": "ruler_chapter_projection_v2",
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "mappings": [item.model_dump(mode="json") for item in mappings],
            "coverage": [item.model_dump(mode="json") for item in coverage],
            "contextual_discovery_only_evidence_ids": [],
            "approved_corpus_provenance": {
                "approval_manifest_path": _relative(root, approval_manifest_path),
                "approval_manifest_sha256": _digest(approval_manifest_path),
                "corpus_package_path": approval.corpus_package_path,
                "corpus_package_sha256": approval.corpus_package_sha256,
                "reading_plan_path": approval.reading_plan_path,
                "reading_plan_sha256": approval.reading_plan_sha256,
                "analysis_path": selected.analysis_path,
                "analysis_sha256": selected.analysis_sha256,
                "review_path": selected.review_path,
                "review_sha256": selected.review_sha256,
                "review_binding_path": selected.review_binding_path,
                "review_binding_sha256": selected.review_binding_sha256,
            },
            "approved_question_answers": answers,
        }
    )
    payload["estimated_input_tokens"] = 1
    preliminary = RulerChapterProjection.model_validate(payload)
    encoded = json.dumps(
        preliminary.model_dump(mode="json", exclude={"estimated_input_tokens"}),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload["estimated_input_tokens"] = ceil(
        len(encoded) / CONSERVATIVE_BYTES_PER_TOKEN
    )
    return RulerChapterProjection.model_validate(payload)


def _convert_evidence(item: BoundEvidence, evidence_id: str) -> DossierEvidence:
    final_use = "context" if item.polarity == "context" else "final_evidence"
    return DossierEvidence(
        evidence_id=evidence_id,
        claim=_bounded_transport_text(item.fact_summary, limit=800),
        url=item.url,
        title=item.title or item.url,
        publisher=item.publisher or "unknown publisher",
        publication_date="unknown_not_recorded",
        excerpt=_bounded_transport_text(item.exact_excerpt, limit=800),
        source_locator=item.locator,
        canonical_fact_key=f"{item.source_id}:{item.excerpt_sha256}",
        source_type="verified_corpus_document",
        source_confidence="verified",
        source_confidence_reason=(
            "Exact passage was code-bound and independently checked against the source."
        ),
        final_evidence_use=final_use,
        period_fit=item.period_fit,
        ruler_attribution=item.ruler_attribution,
        contrary_evidence=item.limitations,
    )


def _bounded_transport_text(text: str, *, limit: int) -> str:
    """Bound repeated judge text while preserving an audited corpus locator."""

    if len(text) <= limit:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    marker = f"\n[... TRANSPORT ELISION sha256={digest} ...]\n"
    half = (limit - len(marker)) // 2
    return text[:half] + marker + text[-half:]


def _mappings(evidence, id_map, question_ids, analysis):
    routed: dict[str, set[str]] = {item.evidence_id: set() for item in evidence}
    answer_relation: dict[tuple[str, str], str] = {}
    for item in evidence:
        routed[item.evidence_id].update(set(item.question_ids) & set(question_ids))
    for answer in analysis.answers:
        overlap = set(answer.supporting_evidence_ids) & set(
            answer.contrary_or_qualifying_evidence_ids
        )
        for evidence_id in answer.supporting_evidence_ids:
            routed[evidence_id].add(answer.question_id)
            answer_relation[(evidence_id, answer.question_id)] = (
                "context" if evidence_id in overlap else "supports"
            )
        for evidence_id in answer.contrary_or_qualifying_evidence_ids:
            routed[evidence_id].add(answer.question_id)
            answer_relation[(evidence_id, answer.question_id)] = (
                "context" if evidence_id in overlap else "contradicts"
            )
    return tuple(
        EvidenceQuestionMapping(
            evidence_id=id_map[item.evidence_id],
            methodology_id=question_id,
            relation=answer_relation.get((item.evidence_id, question_id), "context"),
            relevance=_bounded_transport_text(item.fact_summary, limit=250),
        )
        for item in evidence
        for question_id in sorted(routed[item.evidence_id])
    )


def _coverage(question_ids, mappings):
    return tuple(
        QuestionCoverage(
            methodology_id=question_id,
            status="covered" if evidence_ids else "research_blocked",
            evidence_ids=evidence_ids,
            reason=(
                "Approved full-corpus evidence is available."
                if evidence_ids
                else "The approved analysis records no cited corpus evidence for this lens."
            ),
        )
        for question_id in question_ids
        for evidence_ids in (
            tuple(
                dict.fromkeys(
                    item.evidence_id
                    for item in mappings
                    if item.methodology_id == question_id
                )
            ),
        )
    )


def _validate_identity(dossier, dossier_path, approval) -> None:
    if (
        approval.dossier_job_key != dossier.job_key
        or approval.iso3 != dossier.iso3
        or approval.ruler_year_id != dossier.ruler_year_id
        or approval.ruler_name != dossier.ruler_name
        or approval.dossier_sha256 != _digest(dossier_path)
    ):
        raise ValueError("approved ruler package differs from dossier dependency")


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("approval manifest must remain inside the project")
    return str(resolved.relative_to(root))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["build_approved_chapter_projection"]
