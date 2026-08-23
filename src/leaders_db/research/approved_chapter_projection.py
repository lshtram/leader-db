"""Build judge projections from approved full-corpus ruler packages."""

from __future__ import annotations

import hashlib
import json
from math import ceil
from pathlib import Path

from .approved_ruler_package import load_approved_ruler_package
from .chapter_analysis_models import LensAnswer, ResolvedChapterAnalysis
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
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_chapter_models import QuestionUnavailableArtifact
from .question_packet_writer import DiagnosticQuestionAnswer


def build_approved_chapter_projection(
    dossier: RulerEvidenceDossier,
    *,
    chapter_id: str,
    dossier_path: Path,
    approval_manifest_path: Path,
    project_root: Path,
    target_year: int,
    question_answers: tuple[DiagnosticQuestionAnswer, ...] | None = None,
    question_handoff_path: Path | None = None,
    question_package_path: Path | None = None,
    question_package_preflight_path: Path | None = None,
    cohort_preflight_path: Path | None = None,
    approved_cohort_preflight_sha256: str | None = None,
    unavailable_questions: tuple[QuestionUnavailableArtifact, ...] = (),
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
    input_answers = analysis.answers if question_answers is None else question_answers
    answer_ids = tuple(item.question_id for item in input_answers)
    unavailable_ids = tuple(item.question_id for item in unavailable_questions)
    if (
        set(answer_ids) & set(unavailable_ids)
        or tuple(item for item in question_ids if item in set(answer_ids)) != answer_ids
        or tuple(item for item in question_ids if item in set(unavailable_ids)) != unavailable_ids
        or len(answer_ids) + len(unavailable_ids) != 10
    ):
        raise ValueError("reviewed selection requires one answer or unavailable record per lens")
    if (question_answers is None) != (question_handoff_path is None):
        raise ValueError("reviewed question selection requires its handoff binding")
    if question_handoff_path is not None:
        _validate_question_handoff(
            root=root,
            path=question_handoff_path,
            chapter_id=chapter_id,
            answers=question_answers,
            unavailable_questions=unavailable_questions,
        )
    package_evidence = _load_question_package_evidence(
        chapter_id=chapter_id,
        package_path=question_package_path,
        preflight_path=question_package_preflight_path,
        cohort_preflight_path=cohort_preflight_path,
        approved_cohort_preflight_sha256=approved_cohort_preflight_sha256,
        iso3=dossier.iso3,
    )
    cited_ids = (
        {
            evidence_id
            for answer in analysis.answers
            for evidence_id in (
                answer.supporting_evidence_ids
                + answer.contrary_or_qualifying_evidence_ids
            )
        }
        if question_answers is None
        else {
            item.evidence_id
            for answer in question_answers
            for item in answer.evidence_dispositions
        }
    )
    available_evidence: dict[str, BoundEvidence] = {
        item.evidence_id: item for item in corpus.evidence
    }
    for item in package_evidence:
        existing = available_evidence.get(item.evidence_id)
        if existing is not None and existing != item:
            raise ValueError("question package evidence conflicts with approved corpus")
        available_evidence[item.evidence_id] = item
    if cited_ids - set(available_evidence):
        raise ValueError("reviewed answer cites evidence absent from bound inputs")
    selected_evidence = tuple(
        item for item in available_evidence.values() if item.evidence_id in cited_ids
    )
    id_map = {
        item.evidence_id: f"E{index:06d}"
        for index, item in enumerate(selected_evidence, start=1)
    }
    selected_answers = (
        analysis.answers
        if question_answers is None
        else tuple(_lens_answer(item, id_map=id_map) for item in question_answers)
    )
    evidence = tuple(
        _convert_evidence(item, id_map[item.evidence_id])
        for item in selected_evidence
    )
    mapping_answers = (
        analysis.answers
        if question_answers is None
        else tuple(
            _lens_answer(
                item,
                id_map={
                    entry.evidence_id: entry.evidence_id
                    for entry in item.evidence_dispositions
                },
            )
            for item in question_answers
        )
    )
    selected_analysis = analysis.model_copy(update={"answers": mapping_answers})
    mappings = _mappings(selected_evidence, id_map, question_ids, selected_analysis)
    if question_answers is not None:
        evidence_by_id = {item.evidence_id: item for item in selected_evidence}
        existing = {(item.evidence_id, item.methodology_id) for item in mappings}
        additions = tuple(
            EvidenceQuestionMapping(
                evidence_id=id_map[item.evidence_id],
                methodology_id=answer.question_id,
                relation="context",
                relevance=_bounded_transport_text(
                    evidence_by_id[item.evidence_id].fact_summary, limit=250
                ),
            )
            for answer in question_answers
            for item in answer.evidence_dispositions
            if item.role == "limitation_only"
            and (id_map[item.evidence_id], answer.question_id) not in existing
        )
        mappings = tuple(
            sorted(
                (*mappings, *additions),
                key=lambda item: (item.methodology_id, item.evidence_id, item.relation),
            )
        )
    coverage = _coverage(question_ids, mappings)
    answer_by_id = {item.question_id: item for item in selected_answers}
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
        if question_id in answer_by_id
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
            "schema_version": (
                "ruler_chapter_projection_v3" if unavailable_questions
                else "ruler_chapter_projection_v2"
            ),
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
                "question_handoff_path": (
                    _relative(root, question_handoff_path)
                    if question_handoff_path is not None
                    else None
                ),
                "question_handoff_sha256": (
                    _digest(question_handoff_path)
                    if question_handoff_path is not None
                    else None
                ),
                "question_package_path": (
                    _relative(root, question_package_path)
                    if question_package_path is not None
                    else None
                ),
                "question_package_sha256": (
                    _digest(question_package_path)
                    if question_package_path is not None
                    else None
                ),
                "question_package_preflight_path": (
                    _relative(root, question_package_preflight_path)
                    if question_package_preflight_path is not None
                    else None
                ),
                "question_package_preflight_sha256": (
                    _digest(question_package_preflight_path)
                    if question_package_preflight_path is not None
                    else None
                ),
                "cohort_preflight_path": (
                    _relative(root, cohort_preflight_path)
                    if cohort_preflight_path is not None
                    else None
                ),
                "cohort_preflight_sha256": (
                    _digest(cohort_preflight_path)
                    if cohort_preflight_path is not None
                    else None
                ),
            },
            "approved_question_answers": answers,
            "unavailable_question_lenses": [
                {
                    "question_id": item.question_id,
                    "reason": item.reason,
                    "adjudication_sha256": item.adjudication_sha256,
                    "confidence_effect": item.confidence_effect,
                }
                for item in unavailable_questions
            ],
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


def _lens_answer(answer: DiagnosticQuestionAnswer, *, id_map: dict[str, str]) -> LensAnswer:
    return LensAnswer(
        question_id=answer.question_id,
        answer=_rewrite_citations(answer.answer, id_map),
        supporting_evidence_ids=tuple(
            item.evidence_id for item in answer.evidence_dispositions if item.role == "supporting"
        ),
        contrary_or_qualifying_evidence_ids=tuple(
            item.evidence_id
            for item in answer.evidence_dispositions
            if item.role == "contrary_or_qualifying"
        ),
        limitations_and_gaps=tuple(
            _rewrite_citations(item, id_map) for item in answer.limitations_and_gaps
        ),
    )


def _rewrite_citations(text: str, id_map: dict[str, str]) -> str:
    rewritten = text
    for source_id in sorted(id_map, key=len, reverse=True):
        rewritten = rewritten.replace(source_id, id_map[source_id])
    return rewritten


def _validate_question_handoff(
    *, root: Path, path: Path, chapter_id: str, answers: tuple,
    unavailable_questions: tuple[QuestionUnavailableArtifact, ...] = (),
) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = payload.get("questions")
    expected_ids = {f"{chapter}B.{number}" for chapter in range(1, 9) for number in range(1, 11)}
    if (
        payload.get("schema_version") != "question_judge_handoff_v1"
        or payload.get("question_count") != 80
        or not isinstance(questions, dict)
        or set(questions) != expected_ids
    ):
        raise ValueError("question judge handoff inventory is invalid")
    for answer in answers:
        item = questions[answer.question_id]
        answer_path = Path(item["answer_path"])
        resolved = (
            answer_path.resolve()
            if answer_path.is_absolute()
            else (root / answer_path).resolve()
        )
        if not resolved.is_relative_to(root):
            raise ValueError("question judge handoff answer escapes project root")
        raw = resolved.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item.get("answer_sha256"):
            raise ValueError("question judge handoff answer hash differs")
        if DiagnosticQuestionAnswer.model_validate_json(raw) != answer:
            raise ValueError("reviewed answer differs from question judge handoff")
        if not answer.question_id.startswith(f"{chapter_id}."):
            raise ValueError("reviewed answer belongs to a different chapter")
    for unavailable in unavailable_questions:
        item = questions[unavailable.question_id]
        artifact_path = Path(item.get("unavailable_path", ""))
        resolved = (
            artifact_path.resolve()
            if artifact_path.is_absolute()
            else (root / artifact_path).resolve()
        )
        if (
            not resolved.is_relative_to(root)
            or hashlib.sha256(resolved.read_bytes()).hexdigest()
            != item.get("unavailable_sha256")
            or QuestionUnavailableArtifact.model_validate_json(resolved.read_text())
            != unavailable
            or not unavailable.question_id.startswith(f"{chapter_id}.")
        ):
            raise ValueError("unavailable lens differs from question judge handoff")


def _load_question_package_evidence(
    *,
    chapter_id: str,
    package_path: Path | None,
    preflight_path: Path | None,
    cohort_preflight_path: Path | None,
    approved_cohort_preflight_sha256: str | None,
    iso3: str,
) -> tuple[BoundEvidence, ...]:
    """Load evidence only from one preflight-bound reviewed question package."""

    if (
        package_path is None
        and preflight_path is None
        and cohort_preflight_path is None
        and approved_cohort_preflight_sha256 is None
    ):
        return ()
    if (
        package_path is None
        or preflight_path is None
        or cohort_preflight_path is None
        or approved_cohort_preflight_sha256 is None
    ):
        raise ValueError("reviewed question package requires its cohort trust binding")
    package = ChapterQuestionEvidencePackage.model_validate_json(package_path.read_bytes())
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    cohort = json.loads(cohort_preflight_path.read_text(encoding="utf-8"))
    ruler_rows = [item for item in cohort.get("rulers", ()) if item.get("iso3") == iso3]
    entries = [
        item
        for item in preflight.get("question_packages", ())
        if item.get("chapter_id") == chapter_id
    ]
    if (
        package.chapter_id != chapter_id
        or _digest(cohort_preflight_path) != approved_cohort_preflight_sha256
        or cohort.get("schema_version") != "five_ruler_writing_preflight_v1"
        or cohort.get("status") != "eligible"
        or preflight.get("schema_version") != "integrated_gate_preflight_v1"
        or preflight.get("status") != "eligible"
        or len(ruler_rows) != 1
        or ruler_rows[0].get("integrated_preflight_sha256") != _digest(preflight_path)
        or len(entries) != 1
        or entries[0].get("sha256") != _digest(package_path)
    ):
        raise ValueError("reviewed question package differs from its trusted preflight")
    by_id: dict[str, BoundEvidence] = {}
    for packet in package.packets:
        for item in packet.priority_evidence:
            existing = by_id.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError("question package contains conflicting evidence records")
            by_id[item.evidence_id] = item
    return tuple(by_id.values())


def _convert_evidence(item: BoundEvidence, evidence_id: str) -> DossierEvidence:
    final_use = "context" if item.polarity == "context" else "final_evidence"
    return DossierEvidence(
        evidence_id=evidence_id,
        claim=_bounded_transport_text(item.fact_summary, limit=500),
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
