"""Project approved production artifacts into the public study-site contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from .approved_ruler_package import load_approved_ruler_package
from .chapter_analysis_models import ResolvedChapterAnalysis
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
    *, project_root: Path, run_dir: Path
) -> StudySiteProjection:
    """Load and validate the complete public projection for one production run."""

    audit = _load(run_dir / "publication/score-order-audit.json")
    if not audit.get("publication_allowed"):
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
            item["evidence_id"]: PublicEvidence.model_validate(item)
            for item in package["evidence"]
        }
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
            for answer in sorted(
                analysis.answers, key=lambda item: int(item.question_id.split(".")[1])
            ):
                ids = answer.supporting_evidence_ids + answer.contrary_or_qualifying_evidence_ids
                missing = set(ids) - evidence.keys()
                if missing:
                    raise ValueError(
                        f"{answer.question_id} cites missing evidence: {sorted(missing)}"
                    )
                cited_ids.update(ids)
                public_questions.append(
                    PublicQuestion(
                        question_id=answer.question_id,
                        question=questions[answer.question_id],
                        answer=answer.answer,
                        supporting_evidence_ids=answer.supporting_evidence_ids,
                        qualifying_evidence_ids=answer.contrary_or_qualifying_evidence_ids,
                        limitations_and_gaps=answer.limitations_and_gaps,
                    )
                )
            if len(public_questions) != 10:
                raise ValueError(f"{approved['iso3']} {chapter_id} does not contain ten questions")
            score_range = judgment["plausible_score_range"]
            chapters.append(
                PublicChapter(
                    chapter_id=chapter_id,
                    title=CHAPTER_TITLES[chapter_id],
                    score=judgment["score_1_to_10"],
                    confidence=judgment["confidence_score"],
                    plausible_lower=score_range["lower"],
                    plausible_upper=score_range["upper"],
                    rationale=judgment["chapter_rationale"],
                    ruler_attribution=judgment["ruler_attribution"],
                    inherited_baseline_and_constraints=judgment["inherited_baseline_and_constraints"],
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


def _question_text(project_root: Path) -> dict[str, str]:
    payload = _load(project_root / "src/leaders_db/conversational_evidence/data/questions.json")
    return {
        item["id"]: item["text"]
        for chapter in payload["chapters"]
        for item in chapter["questions"]
    }


def safe_public_url(value: str) -> str:
    """Accept only absolute HTTP(S) publisher URLs."""

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"unsafe public URL: {value!r}")
    return value


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = ["CHAPTER_TITLES", "build_study_site_projection", "safe_public_url"]
