"""Project approved production artifacts into the public study-site contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from .approved_ruler_package import load_approved_ruler_package
from .chapter_analysis_models import ResolvedChapterAnalysis
from .chapter_judgment_review import READER_EXPOSITION_MARKER
from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .study_site_models import (
    PublicChapter,
    PublicEvidence,
    PublicQuestion,
    PublicRuler,
    StudySiteProjection,
)

CHAPTER_TITLES = {
    "1B": "Nuclear and existential risk",
    "2B": "International peace and aggression",
    "3B": "Domestic safety and violence",
    "4B": "Political freedom",
    "5B": "Economic well-being",
    "6B": "Social well-being",
    "7B": "Integrity and corruption",
    "8B": "Effectiveness",
}


def build_study_site_projection(  # noqa: PLR0912, PLR0915
    *,
    project_root: Path,
    run_dir: Path,
    audit_path: Path | None = None,
    approved_audit_sha256: str | None = None,
) -> StudySiteProjection:
    """Load and validate the complete public projection for one production run."""

    selected_audit = audit_path or run_dir / "publication/score-order-audit.json"
    resolved_audit = selected_audit.resolve()
    if not resolved_audit.is_relative_to(run_dir.resolve()) or not resolved_audit.is_file():
        raise ValueError("publication audit must be a file beneath the selected run")
    audit_digest = _digest(resolved_audit)
    if audit_path is not None and approved_audit_sha256 is None:
        raise ValueError("publication audit override requires an approved SHA-256")
    if approved_audit_sha256 is not None and audit_digest != approved_audit_sha256:
        raise ValueError("publication audit differs from the approved SHA-256")
    audit = _load(resolved_audit)
    if (
        audit.get("schema_version") != "score_order_audit_v1"
        or audit.get("decision") not in {"pass", "pass_with_explicit_nonblocking_flags"}
        or audit.get("publication_allowed") is not True
    ):
        raise ValueError("score/order audit does not permit publication")
    reviewed_path = project_root / audit["reviewed_package_path"]
    if _digest(reviewed_path) != audit["reviewed_package_sha256"]:
        raise ValueError("reviewed judge package hash differs from the publication audit")
    reviewed = _load(reviewed_path)
    evaluations = {
        (item["iso3"], chapter["chapter_id"]): item
        for chapter in reviewed["chapters"]
        for item in chapter["judgment"]["evaluations"]
    }
    handoffs = {
        iso3: _load_bound_handoff(project_root, binding)
        for iso3, binding in audit.get("question_judge_handoffs", {}).items()
    }
    questions = _question_text(project_root)
    rulers = []
    for iso3_dir in sorted((run_dir / "corpus").iterdir()):
        if not iso3_dir.is_dir():
            continue
        approved_model = load_approved_ruler_package(
            iso3_dir / "approved-ruler-package.json", project_root=project_root
        )
        approved = approved_model.model_dump(mode="json")
        if approved["target_year"] != audit["target_year"]:
            raise ValueError("approved ruler target year differs from the audited year")
        if approved["production_run"]["run_id"] != audit["run_id"]:
            raise ValueError("approved ruler package differs from the audited run")
        if approved["pipeline_provenance"] != audit["pipeline_provenance"]:
            raise ValueError("approved ruler provenance differs from the publication audit")
        package = _load(project_root / approved["corpus_package_path"])
        evidence = {
            item["evidence_id"]: PublicEvidence.model_validate(item) for item in package["evidence"]
        }
        for binding in audit.get("supplemental_evidence_packages", {}).get(approved["iso3"], ()):
            for item in _load_bound_public_evidence(project_root, binding):
                existing = evidence.get(item.evidence_id)
                if existing is not None and existing != item:
                    raise ValueError(
                        f"supplemental evidence conflicts with base evidence: {item.evidence_id}"
                    )
                evidence[item.evidence_id] = item
        for item in evidence.values():
            if hashlib.sha256(item.exact_excerpt.encode()).hexdigest() != item.excerpt_sha256:
                raise ValueError(f"evidence excerpt hash mismatch: {item.evidence_id}")
        chapters = []
        cited_ids: set[str] = set()
        for binding in sorted(approved["chapters"], key=lambda item: item["chapter_id"]):
            chapter_id = binding["chapter_id"]
            analysis = ResolvedChapterAnalysis.model_validate_json(
                (project_root / binding["analysis_path"]).read_text(encoding="utf-8")
            )
            expected_questions = {f"{chapter_id}.{index}" for index in range(1, 11)}
            received_questions = {item.question_id for item in analysis.answers}
            if received_questions != expected_questions or len(analysis.answers) != 10:
                raise ValueError(f"{approved['iso3']} {chapter_id} question set is incomplete")
            judgment = evaluations[(approved["iso3"], chapter_id)]
            expected_job_key = (
                f"dossier:{audit['run_id']}:{audit['target_year']}:"
                f"{approved['iso3']}:{approved['ruler_year_id']}"
            )
            if judgment["dossier_job_key"] != expected_job_key:
                raise ValueError("reviewed judgment differs from the approved ruler identity")
            public_questions = []
            selected_answers = (
                _handoff_answers(project_root, handoffs[approved["iso3"]], chapter_id)
                if approved["iso3"] in handoffs
                else [item.model_dump(mode="json") for item in analysis.answers]
            )
            for answer in selected_answers:
                supporting = tuple(
                    item["evidence_id"]
                    for item in answer.get("evidence_dispositions", ())
                    if item["role"] == "supporting"
                ) or tuple(answer.get("supporting_evidence_ids", ()))
                qualifying = tuple(
                    item["evidence_id"]
                    for item in answer.get("evidence_dispositions", ())
                    if item["role"] == "contrary_or_qualifying"
                ) or tuple(answer.get("contrary_or_qualifying_evidence_ids", ()))
                limitation_only = tuple(
                    item["evidence_id"]
                    for item in answer.get("evidence_dispositions", ())
                    if item["role"] == "limitation_only"
                )
                ids = supporting + qualifying + limitation_only
                missing = set(ids) - evidence.keys()
                if missing:
                    raise ValueError(
                        f"{answer['question_id']} cites missing evidence: {sorted(missing)}"
                    )
                cited_ids.update(ids)
                public_questions.append(
                    PublicQuestion(
                        question_id=answer["question_id"],
                        question=questions[answer["question_id"]],
                        answer=answer["answer"],
                        supporting_evidence_ids=supporting,
                        qualifying_evidence_ids=qualifying,
                        limitations_and_gaps=answer["limitations_and_gaps"],
                    )
                )
            if len(public_questions) != 10:
                raise ValueError(f"{approved['iso3']} {chapter_id} does not contain ten questions")
            score_range = judgment["plausible_score_range"]
            summary, exposition = _reader_sections(judgment["chapter_rationale"])
            chapters.append(
                PublicChapter(
                    chapter_id=chapter_id,
                    title=CHAPTER_TITLES[chapter_id],
                    score=judgment["score_1_to_10"],
                    confidence=judgment["confidence_score"],
                    plausible_lower=score_range["lower"],
                    plausible_upper=score_range["upper"],
                    rationale=judgment["chapter_rationale"],
                    summary=summary,
                    exposition=exposition,
                    ruler_attribution=judgment["ruler_attribution"],
                    inherited_baseline_and_constraints=judgment[
                        "inherited_baseline_and_constraints"
                    ],
                    lower_anchor_rejected=judgment["lower_anchor_rejected"],
                    higher_anchor_rejected=judgment["higher_anchor_rejected"],
                    missing_or_weak_lenses=judgment["missing_or_weak_lenses"],
                    manual_review_required=judgment["manual_review_required"],
                    manual_review_reason=judgment["manual_review_reason"],
                    questions=public_questions,
                )
            )
        if {item.chapter_id for item in chapters} != set(CHAPTER_TITLES):
            raise ValueError(f"{approved['iso3']} does not contain all eight chapters")
        mean = sum(item.score for item in chapters) / len(chapters)
        rulers.append(
            PublicRuler(
                iso3=approved["iso3"],
                ruler_name=approved["ruler_name"],
                target_year=approved["target_year"],
                chapters=chapters,
                evidence=[evidence[item] for item in sorted(cited_ids)],
                overall_mean=round(mean, 3),
                shared_rank=0,
            )
        )
    if len(rulers) != 5:
        raise ValueError("five-ruler study requires exactly five approved rulers")
    ranked = _shared_ranks(rulers)
    provenance = audit["pipeline_provenance"]
    return StudySiteProjection(
        run_id=audit["run_id"],
        target_year=audit["target_year"],
        audit_decision=audit["decision"],
        audit_path=str(resolved_audit.relative_to(project_root.resolve())),
        audit_sha256=audit_digest,
        pipeline_version_id=provenance["pipeline_version_id"],
        methodology_version_id=provenance["methodology_version_id"],
        rulers=ranked,
    )


def _shared_ranks(rulers: list[PublicRuler]) -> list[PublicRuler]:
    ordered = sorted(rulers, key=lambda item: (-item.overall_mean, item.ruler_name))
    ranked: list[PublicRuler] = []
    prior: float | None = None
    rank = 0
    for index, item in enumerate(ordered, 1):
        if item.overall_mean != prior:
            rank = index
        ranked.append(item.model_copy(update={"shared_rank": rank}))
        prior = item.overall_mean
    return ranked


def _reader_sections(rationale: str) -> tuple[str, str | None]:
    """Split prospective two-level prose while preserving historical rationales."""

    prefix = f"{READER_EXPOSITION_MARKER}\n"
    if not rationale.startswith(prefix):
        return rationale, None
    summary, separator, exposition = rationale.removeprefix(prefix).partition("\n\n")
    if not separator or not summary or "\n" in summary or not exposition.strip():
        raise ValueError("reader summary/exposition payload is malformed")
    return summary, exposition


def _question_text(project_root: Path) -> dict[str, str]:
    payload = _load(project_root / "src/leaders_db/conversational_evidence/data/questions.json")
    return {
        item["id"]: item["text"] for chapter in payload["chapters"] for item in chapter["questions"]
    }


def safe_public_url(value: str) -> str:
    """Accept only absolute HTTP(S) publisher URLs."""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"unsafe public URL: {value!r}")
    return value


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_bound_handoff(project_root: Path, binding: dict) -> dict:
    path = _confined_path(project_root, binding["path"])
    if _digest(path) != binding["sha256"]:
        raise ValueError("question judge handoff changed after publication audit")
    saved = _load(path)
    if (
        saved.get("schema_version") != "question_judge_handoff_v1"
        or saved.get("question_count") != 80
    ):
        raise ValueError("question judge handoff is incomplete")
    return saved


def _handoff_answers(project_root: Path, handoff: dict, chapter_id: str) -> list[dict]:
    answers = []
    for index in range(1, 11):
        question_id = f"{chapter_id}.{index}"
        binding = handoff["questions"][question_id]
        path = _confined_path(project_root, binding["answer_path"])
        if _digest(path) != binding["answer_sha256"]:
            raise ValueError("selected question answer changed after handoff")
        answer = _load(path)
        if answer.get("question_id") != question_id:
            raise ValueError("selected question answer identity changed")
        answers.append(answer)
    return answers


def _load_bound_public_evidence(project_root: Path, binding: dict) -> list[PublicEvidence]:
    path = _confined_path(project_root, binding["path"])
    if _digest(path) != binding["sha256"]:
        raise ValueError("supplemental evidence package changed after publication audit")
    package = ChapterQuestionEvidencePackage.model_validate_json(path.read_text(encoding="utf-8"))
    found: dict[str, PublicEvidence] = {}
    fields = tuple(PublicEvidence.model_fields)
    for packet in package.packets:
        for bound in packet.priority_evidence:
            payload = bound.model_dump(mode="json")
            item = PublicEvidence.model_validate({key: payload[key] for key in fields})
            existing = found.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError(
                    f"supplemental package contains conflicting evidence: {item.evidence_id}"
                )
            found[item.evidence_id] = item
    return list(found.values())


def _confined_path(project_root: Path, value: str) -> Path:
    root = project_root.resolve()
    path = Path(value)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"artifact path is outside the project root: {value!r}")
    return resolved


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["CHAPTER_TITLES", "build_study_site_projection", "safe_public_url"]
