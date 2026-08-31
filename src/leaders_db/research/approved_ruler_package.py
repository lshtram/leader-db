"""Hash-bound approval manifest for a deeply read ruler evidence package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .chapter_analysis_models import (
    ChapterAnalysisQuality,
    ChapterQualityReviewBinding,
    ResolvedChapterAnalysis,
)
from .corpus_judge_package import CorpusJudgePackage
from .corpus_reading_plan import CorpusReadingPlan
from .dossier_models import RulerEvidenceDossier
from .pipeline_provenance import ProductionPipelineProvenance
from .production_run import ProductionRunReference


class ApprovedChapterArtifact(BaseModel):
    """One selected analysis and its independently bound quality review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    analysis_path: str
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_path: str
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_binding_path: str
    review_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SelectedChapterReference(BaseModel):
    """Paths and claimed hashes selected by the upstream review workflow."""

    model_config = ConfigDict(extra="allow", frozen=True)

    chapter_id: str = Field(pattern=r"^[1-8]B$")
    analysis_path: str
    analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_path: str
    review_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    review_binding_path: str
    review_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApprovedSelectionManifest(BaseModel):
    """Minimum upstream selection contract accepted by the approval boundary."""

    model_config = ConfigDict(extra="allow", frozen=True)

    ruler_name: str
    target_year: int
    complete_ruler_safe_for_judge_use: bool
    quality_review_contract: str
    chapters: tuple[SelectedChapterReference, ...]


class ApprovedRulerEvidencePackage(BaseModel):
    """Complete corpus and approved chapter artifacts for one ruler-period."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["approved_ruler_evidence_package_v3"] = (
        "approved_ruler_evidence_package_v3"
    )
    production_run: ProductionRunReference
    pipeline_provenance: ProductionPipelineProvenance
    approval_contract: Literal["independent-full-index-v1"]
    dossier_job_key: str
    iso3: str = Field(min_length=3, max_length=3)
    ruler_year_id: int
    ruler_name: str
    target_year: int
    period_start_year: int
    period_end_year: int
    dossier_path: str
    dossier_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_package_path: str
    corpus_package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reading_plan_path: str
    reading_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reading_manifest_path: str
    reading_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chapters: tuple[ApprovedChapterArtifact, ...]

    @model_validator(mode="after")
    def _complete_chapters(self) -> ApprovedRulerEvidencePackage:
        expected = {f"{index}B" for index in range(1, 9)}
        received = {item.chapter_id for item in self.chapters}
        if received != expected or len(self.chapters) != 8:
            raise ValueError("approved package requires chapters 1B through 8B once")
        return self


class ApprovedPackageReference(BaseModel):
    """Immutable judge-job reference to one approved ruler manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_approved_ruler_package(
    *,
    project_root: Path,
    dossier_path: Path,
    corpus_package_path: Path,
    reading_plan_path: Path,
    reading_manifest_path: Path,
    selection_manifest_path: Path,
    production_run_manifest_path: Path,
    output_path: Path,
) -> Path:
    """Validate and bind a selected complete-ruler package for downstream judging."""

    root = project_root.resolve()
    dossier_path = _inside(root, dossier_path)
    corpus_package_path = _inside(root, corpus_package_path)
    reading_plan_path = _inside(root, reading_plan_path)
    reading_manifest_path = _inside(root, reading_manifest_path)
    selection_manifest_path = _inside(root, selection_manifest_path)
    production_run_manifest_path = _inside(root, production_run_manifest_path)
    from .deep_corpus_release import load_deep_corpus_release, pipeline_provenance
    from .production_run import load_production_run_manifest, production_run_reference

    production_run = load_production_run_manifest(
        production_run_manifest_path, project_root=root
    )
    from .batch_manifest import load_batch_manifest

    production_batch = load_batch_manifest(root / production_run.batch_manifest)
    release_config_path = root / production_run.release_config
    release = load_deep_corpus_release(release_config_path)
    dossier = RulerEvidenceDossier.model_validate_json(
        dossier_path.read_text(encoding="utf-8")
    )
    matching_cases = tuple(
        case
        for case in production_batch.cases
        if case.ruler_year_id == dossier.ruler_year_id
        and case.iso3 == dossier.iso3
        and case.ruler_name == dossier.ruler_name
    )
    if len(matching_cases) != 1:
        raise ValueError("dossier identity is not in the production-run batch")
    corpus = CorpusJudgePackage.model_validate_json(
        corpus_package_path.read_text(encoding="utf-8")
    )
    reading_plan = CorpusReadingPlan.model_validate_json(
        reading_plan_path.read_text(encoding="utf-8")
    )
    _validate_complete_reading_run(reading_plan, reading_manifest_path)
    _validate_corpus_index(corpus)
    _validate_corpus_identity(dossier, corpus, reading_plan)
    corpus_ids = {item.evidence_id for item in corpus.evidence}
    selection = ApprovedSelectionManifest.model_validate_json(
        selection_manifest_path.read_text(encoding="utf-8")
    )
    if (
        selection.ruler_name != dossier.ruler_name
        or not dossier.period_start_year
        <= selection.target_year
        <= dossier.period_end_year
    ):
        raise ValueError("selection manifest differs from the dossier identity or period")
    if not selection.complete_ruler_safe_for_judge_use:
        raise ValueError("selection manifest is not approved for complete-ruler use")
    if selection.quality_review_contract != "independent-full-index-v1":
        raise ValueError("selection manifest lacks the full-index review contract")
    chapters = tuple(
        _validate_chapter(
            root,
            selection_manifest_path.parent,
            item,
            corpus_package_path,
            corpus_ids,
        )
        for item in selection.chapters
    )
    package = ApprovedRulerEvidencePackage(
        production_run=production_run_reference(
            production_run_manifest_path, project_root=root
        ),
        pipeline_provenance=pipeline_provenance(
            release_config_path, release, project_root=root
        ),
        approval_contract="independent-full-index-v1",
        dossier_job_key=dossier.job_key,
        iso3=dossier.iso3,
        ruler_year_id=dossier.ruler_year_id,
        ruler_name=dossier.ruler_name,
        target_year=selection.target_year,
        period_start_year=dossier.period_start_year,
        period_end_year=dossier.period_end_year,
        dossier_path=_relative(root, dossier_path),
        dossier_sha256=_digest(dossier_path),
        corpus_package_path=_relative(root, corpus_package_path),
        corpus_package_sha256=_digest(corpus_package_path),
        reading_plan_path=_relative(root, reading_plan_path),
        reading_plan_sha256=_digest(reading_plan_path),
        reading_manifest_path=_relative(root, reading_manifest_path),
        reading_manifest_sha256=_digest(reading_manifest_path),
        chapters=chapters,
    )
    resolved_output = output_path.resolve()
    if not resolved_output.is_relative_to(root):
        raise ValueError("approved ruler manifest output must remain inside the project")
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(
        package.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return resolved_output


def load_approved_ruler_package(
    path: Path, *, project_root: Path
) -> ApprovedRulerEvidencePackage:
    """Load an approval manifest and revalidate every bound artifact hash."""

    root = project_root.resolve()
    manifest_path = _inside(root, path)
    package = ApprovedRulerEvidencePackage.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    reading_plan_path = _inside(root, root / package.reading_plan_path)
    if _digest(reading_plan_path) != package.reading_plan_sha256:
        raise ValueError("reading plan hash mismatch")
    reading_plan = CorpusReadingPlan.model_validate_json(
        reading_plan_path.read_text(encoding="utf-8")
    )
    reading_manifest_path = _inside(root, root / package.reading_manifest_path)
    if _digest(reading_manifest_path) != package.reading_manifest_sha256:
        raise ValueError("reading manifest hash mismatch")
    _validate_complete_reading_run(reading_plan, reading_manifest_path)
    run_path = _inside(root, root / package.production_run.path)
    if _digest(run_path) != package.production_run.sha256:
        raise ValueError("production-run manifest hash mismatch")
    from .production_run import load_production_run_manifest

    production_run = load_production_run_manifest(run_path, project_root=root)
    if (
        production_run.run_id != package.production_run.run_id
        or production_run.batch_manifest_sha256
        != package.production_run.batch_manifest_sha256
        or production_run.pipeline_provenance != package.pipeline_provenance
    ):
        raise ValueError("approved package differs from its production run")
    from .deep_corpus_release import validate_release_reference

    release = validate_release_reference(
        {
            "path": package.pipeline_provenance.release_path,
            "sha256": package.pipeline_provenance.release_sha256,
        },
        project_root=root,
    )
    if release.pipeline_version_id != package.pipeline_provenance.pipeline_version_id:
        raise ValueError("approved ruler package pipeline version differs from release")
    bound = (
        (package.dossier_path, package.dossier_sha256),
        (package.corpus_package_path, package.corpus_package_sha256),
        (package.reading_plan_path, package.reading_plan_sha256),
        *(
            pair
            for chapter in package.chapters
            for pair in (
                (chapter.analysis_path, chapter.analysis_sha256),
                (chapter.review_path, chapter.review_sha256),
                (chapter.review_binding_path, chapter.review_binding_sha256),
            )
        ),
    )
    for relative, expected in bound:
        artifact = _inside(root, root / relative)
        if _digest(artifact) != expected:
            raise ValueError(f"approved ruler artifact hash mismatch: {relative}")
    dossier = RulerEvidenceDossier.model_validate_json(
        (root / package.dossier_path).read_text(encoding="utf-8")
    )
    corpus_path = root / package.corpus_package_path
    corpus = CorpusJudgePackage.model_validate_json(
        corpus_path.read_text(encoding="utf-8")
    )
    reading_plan = CorpusReadingPlan.model_validate_json(
        (root / package.reading_plan_path).read_text(encoding="utf-8")
    )
    _validate_corpus_index(corpus)
    _validate_corpus_identity(dossier, corpus, reading_plan)
    if (
        package.dossier_job_key != dossier.job_key
        or package.iso3 != dossier.iso3
        or package.ruler_year_id != dossier.ruler_year_id
        or package.ruler_name != dossier.ruler_name
        or not dossier.period_start_year <= package.target_year <= dossier.period_end_year
        or package.period_start_year != dossier.period_start_year
        or package.period_end_year != dossier.period_end_year
    ):
        raise ValueError("approved ruler manifest differs from its bound dossier")
    corpus_ids = {item.evidence_id for item in corpus.evidence}
    for chapter in package.chapters:
        _validate_chapter(
            root,
            root,
            SelectedChapterReference(
                chapter_id=chapter.chapter_id,
                analysis_path=chapter.analysis_path,
                analysis_sha256=chapter.analysis_sha256,
                review_path=chapter.review_path,
                review_sha256=chapter.review_sha256,
                review_binding_path=chapter.review_binding_path,
                review_binding_sha256=chapter.review_binding_sha256,
            ),
            corpus_path,
            corpus_ids,
        )
    return package


def _validate_complete_reading_run(
    reading_plan: CorpusReadingPlan, reading_manifest_path: Path
) -> None:
    """Reject approval unless every planned corpus batch completed exactly once."""

    payload = json.loads(reading_manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "corpus_reading_run_v1":
        raise ValueError("unsupported corpus reading manifest")
    if payload.get("failed_batch_ids"):
        raise ValueError("corpus reading manifest contains failed batches")
    expected = [item.batch_id for item in reading_plan.batches]
    batches = payload.get("batches")
    if not isinstance(batches, list):
        raise ValueError("corpus reading manifest lacks batch results")
    received = [item.get("batch_id") for item in batches if isinstance(item, dict)]
    if received != expected or len(received) != len(set(received)):
        raise ValueError("corpus reading manifest does not exactly cover the plan")
    if any(item.get("status") == "failed" for item in batches):
        raise ValueError("corpus reading manifest contains a failed batch result")
    if any(
        not (reading_manifest_path.parent / item / "verified-evidence.json").is_file()
        for item in expected
    ):
        raise ValueError("corpus reading manifest references missing verified evidence")


def _validate_corpus_index(corpus: CorpusJudgePackage) -> None:
    expected_questions = {
        f"{chapter}B.{question}"
        for chapter in range(1, 9)
        for question in range(1, 11)
    }
    if (
        {item.methodology_id for item in corpus.questions} != expected_questions
        or len(corpus.questions) != 80
    ):
        raise ValueError("corpus package must index all eighty methodology questions")


def _validate_corpus_identity(
    dossier: RulerEvidenceDossier,
    corpus: CorpusJudgePackage,
    reading_plan: CorpusReadingPlan,
) -> None:
    if (
        reading_plan.ruler_name != dossier.ruler_name
        or reading_plan.period_start_year != dossier.period_start_year
        or reading_plan.period_end_year != dossier.period_end_year
    ):
        raise ValueError("corpus reading plan differs from the dossier ruler-period")
    planned_sources = {item.source_id for item in reading_plan.documents}
    corpus_sources = {item.source_id for item in corpus.evidence}
    if not corpus_sources.issubset(planned_sources):
        raise ValueError("corpus evidence includes sources outside its bound reading plan")


def _validate_chapter(
    root: Path,
    artifact_base: Path,
    item: SelectedChapterReference,
    corpus_path: Path,
    corpus_ids: set[str],
) -> ApprovedChapterArtifact:
    chapter_id = item.chapter_id
    analysis_path = _inside(root, artifact_base / item.analysis_path)
    review_path = _inside(root, artifact_base / item.review_path)
    binding_path = _inside(root, artifact_base / item.review_binding_path)
    _expect_hash(analysis_path, item.analysis_sha256)
    _expect_hash(review_path, item.review_sha256)
    _expect_hash(binding_path, item.review_binding_sha256)
    analysis = ResolvedChapterAnalysis.model_validate_json(
        analysis_path.read_text(encoding="utf-8")
    )
    review = ChapterAnalysisQuality.model_validate_json(
        review_path.read_text(encoding="utf-8")
    )
    binding = ChapterQualityReviewBinding.model_validate_json(
        binding_path.read_text(encoding="utf-8")
    )
    cited = {
        evidence_id
        for answer in analysis.answers
        for evidence_id in (
            answer.supporting_evidence_ids
            + answer.contrary_or_qualifying_evidence_ids
        )
    }
    expected_questions = {f"{chapter_id}.{index}" for index in range(1, 11)}
    if (
        analysis.chapter_id != chapter_id
        or {item.question_id for item in analysis.answers} != expected_questions
        or len(analysis.answers) != 10
        or review.chapter_id != chapter_id
        or {item.question_id for item in review.lens_quality} != expected_questions
        or len(review.lens_quality) != 10
        or not review.safe_for_judge_use
        or binding.chapter_id != chapter_id
        or binding.analysis_sha256 != _digest(analysis_path)
        or binding.review_sha256 != _digest(review_path)
        or binding.judge_package_sha256 != _digest(corpus_path)
        or not cited.issubset(corpus_ids)
    ):
        raise ValueError(f"approved chapter artifacts do not reconcile: {chapter_id}")
    return ApprovedChapterArtifact(
        chapter_id=chapter_id,
        analysis_path=_relative(root, analysis_path),
        analysis_sha256=_digest(analysis_path),
        review_path=_relative(root, review_path),
        review_sha256=_digest(review_path),
        review_binding_path=_relative(root, binding_path),
        review_binding_sha256=_digest(binding_path),
    )


def _inside(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError(f"approved ruler artifact is missing or outside project: {path}")
    return resolved


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expect_hash(path: Path, expected: str) -> None:
    if _digest(path) != expected:
        raise ValueError(f"artifact hash mismatch: {path}")


__all__ = [
    "ApprovedChapterArtifact",
    "ApprovedPackageReference",
    "ApprovedRulerEvidencePackage",
    "ApprovedSelectionManifest",
    "SelectedChapterReference",
    "build_approved_ruler_package",
    "load_approved_ruler_package",
]
