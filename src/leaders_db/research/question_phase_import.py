"""Trusted reuse of complete question-phase chapters in a fresh release."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .question_evidence_packet_models import ChapterQuestionEvidencePackage
from .question_packet_phase_validation import (
    payload_hash,
    sha256_file,
    validate_chapter_question_review,
    validate_chapter_question_writing,
)

_WRITING_AUTHORIZATION_CAPABILITY = object()


@dataclass(frozen=True)
class ImportedWritingAuthorization:
    preflight_path: Path
    preflight_sha256: str
    target_run: Path
    execute_chapters: frozenset[tuple[str, str]]
    request_sha256s: frozenset[str]
    limits: dict[str, int]
    profile_name: str
    profiles_path: Path
    profiles_sha256: str
    provider: str
    model: str
    surface: str
    reasoning_effort: str
    _capability: object


class PhaseImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ruler_id: str
    chapter_id: str
    writing_action: str
    writing_source_tree_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    review_action: str
    review_source_tree_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


class QuestionPhaseImportPreflight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str
    status: str
    source_run: str
    source_preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_run: str
    target_preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_name: str
    writing_profile_name: str
    profiles_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    experiment_policy_path: str
    experiment_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: tuple[PhaseImportRow, ...] = Field(min_length=40, max_length=40)
    imported_writing_chapters: int
    writing_chapters_to_execute: int
    imported_review_chapters: int
    review_chapters_to_execute: int
    imported_writing_calls: int
    writing_calls_to_execute: int
    imported_review_calls: int
    review_calls_to_execute: int
    model_calls_executed: int
    reservations_created: int


def build_question_phase_import_preflight(
    *,
    project_root: Path,
    source_run: Path,
    target_run: Path,
    packages: dict[tuple[str, str], ChapterQuestionEvidencePackage],
    approved_analysis_paths: dict[tuple[str, str], Path],
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    experiment_policy_path: Path,
    output_path: Path,
) -> Path:
    """Inventory only complete, trusted chapters that can be reused byte-for-byte."""

    if output_path.exists():
        raise FileExistsError(f"question phase import preflight exists: {output_path}")
    manifest = _construct_preflight(
        project_root=project_root,
        source_run=source_run,
        target_run=target_run,
        packages=packages,
        approved_analysis_paths=approved_analysis_paths,
        profile_name=profile_name,
        writing_profile_name=writing_profile_name,
        profiles_path=profiles_path,
        experiment_policy_path=experiment_policy_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return output_path


def apply_trusted_question_phase_imports(
    *,
    project_root: Path,
    source_run: Path,
    target_run: Path,
    packages: dict[tuple[str, str], ChapterQuestionEvidencePackage],
    approved_analysis_paths: dict[tuple[str, str], Path],
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    experiment_policy_path: Path,
    preflight_path: Path,
) -> None:
    """Reconstruct an eligible preflight, then copy only its trusted complete trees."""

    saved = QuestionPhaseImportPreflight.model_validate_json(preflight_path.read_bytes())
    expected = _construct_preflight(
        project_root=project_root,
        source_run=source_run,
        target_run=target_run,
        packages=packages,
        approved_analysis_paths=approved_analysis_paths,
        profile_name=profile_name,
        writing_profile_name=writing_profile_name,
        profiles_path=profiles_path,
        experiment_policy_path=experiment_policy_path,
    )
    if saved != expected or saved.status != "eligible":
        raise ValueError("question phase import preflight differs from trusted reconstruction")
    for row in saved.rows:
        source_root = source_run / "model-output" / row.ruler_id
        target_root = target_run / "model-output" / row.ruler_id
        if row.writing_action == "import":
            _copy_tree(
                source_root / "question-writing" / row.chapter_id,
                target_root / "question-writing" / row.chapter_id,
                row.writing_source_tree_sha256,
            )
        if row.review_action == "import":
            _copy_tree(
                source_root / "question-review" / row.chapter_id,
                target_root / "question-review" / row.chapter_id,
                row.review_source_tree_sha256,
            )


def build_imported_writing_preflight(
    *,
    project_root: Path,
    import_preflight_path: Path,
    cohort_preflight_path: Path,
    source_run: Path,
    target_run: Path,
    packages: dict[tuple[str, str], ChapterQuestionEvidencePackage],
    approved_analysis_paths: dict[tuple[str, str], Path],
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    experiment_policy_path: Path,
    maximum_input_tokens: int,
    output_path: Path,
) -> Path:
    """Measure only writing chapters not satisfied by trusted imports."""

    if output_path.exists():
        raise FileExistsError(f"imported writing preflight exists: {output_path}")
    saved_import = QuestionPhaseImportPreflight.model_validate_json(
        import_preflight_path.read_bytes()
    )
    imported = _construct_preflight(
        project_root=project_root,
        source_run=source_run,
        target_run=target_run,
        packages=packages,
        approved_analysis_paths=approved_analysis_paths,
        profile_name=profile_name,
        writing_profile_name=writing_profile_name,
        profiles_path=profiles_path,
        experiment_policy_path=experiment_policy_path,
    )
    if saved_import != imported:
        raise ValueError("writing preflight import differs from trusted reconstruction")
    cohort = json.loads(cohort_preflight_path.read_text(encoding="utf-8"))
    if (
        imported.status != "eligible"
        or cohort.get("status") != "eligible"
        or imported.target_preflight_sha256 != sha256_file(cohort_preflight_path)
    ):
        raise ValueError("imported writing preflight lacks an eligible cohort binding")
    target_run = project_root / imported.target_run
    execute = {
        (row.ruler_id, row.chapter_id)
        for row in imported.rows
        if row.writing_action == "execute"
    }
    for row in imported.rows:
        target = target_run / "model-output" / row.ruler_id / "question-writing" / row.chapter_id
        if row.writing_action == "import":
            if _tree_digest(target) != row.writing_source_tree_sha256:
                raise ValueError("applied writing import differs from its authorized tree")
        elif target.exists():
            raise ValueError("writing execution target is already in use")
    requests = [
        item
        for item in cohort["requests"]
        if (item["iso3"], item["chapter_id"]) in execute
    ]
    expected_calls = 10 * len(execute)
    if (
        len(requests) != expected_calls
        or len({(item["iso3"], item["question_id"]) for item in requests})
        != expected_calls
        or any(item["stop_reasons"] for item in requests)
    ):
        raise ValueError("imported writing request inventory is incomplete or ineligible")
    planned_input = sum(int(item["estimated_input_tokens"]) for item in requests)
    output_per_call = int(cohort["output_token_allowance_per_call"])
    maximum_calls = expected_calls
    maximum_output_tokens = maximum_calls * output_per_call
    eligible = planned_input <= maximum_input_tokens
    payload = {
        "schema_version": "imported_question_writing_preflight_v2",
        "status": "eligible" if eligible else "rejected",
        "model_calls_executed": 0,
        "reservations_created": 0,
        "api_key_used": False,
        "provider": cohort["provider"],
        "model": cohort["model"],
        "profile": cohort["profile"],
        "surface": cohort["surface"],
        "reasoning_effort": cohort["reasoning_effort"],
        "cohort_preflight_sha256": sha256_file(cohort_preflight_path),
        "import_preflight_sha256": sha256_file(import_preflight_path),
        "imported_writing_chapters": imported.imported_writing_chapters,
        "writing_chapters_to_execute": imported.writing_chapters_to_execute,
        "planned_calls": maximum_calls,
        "planned_input_tokens": planned_input,
        "planned_request_characters": sum(
            int(item["request_characters"]) for item in requests
        ),
        "output_token_allowance_per_call": output_per_call,
        "limits": {
            "maximum_calls": maximum_calls,
            "maximum_input_tokens": maximum_input_tokens,
            "maximum_output_tokens": maximum_output_tokens,
        },
        "requests": requests,
        "stop_reasons": [] if eligible else ["writing_input_limit"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return output_path


def load_imported_writing_authorization(
    *,
    project_root: Path,
    import_preflight_path: Path,
    cohort_preflight_path: Path,
    writing_preflight_path: Path,
    source_run: Path,
    target_run: Path,
    packages: dict[tuple[str, str], ChapterQuestionEvidencePackage],
    approved_analysis_paths: dict[tuple[str, str], Path],
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    experiment_policy_path: Path,
) -> ImportedWritingAuthorization:
    """Issue a launch capability only after exact preflight reconstruction."""

    saved = json.loads(writing_preflight_path.read_text(encoding="utf-8"))
    scratch = writing_preflight_path.with_name(
        f".{writing_preflight_path.name}.trusted-reconstruction"
    )
    if scratch.exists():
        raise FileExistsError(f"writing preflight reconstruction path exists: {scratch}")
    try:
        build_imported_writing_preflight(
            project_root=project_root,
            import_preflight_path=import_preflight_path,
            cohort_preflight_path=cohort_preflight_path,
            source_run=source_run,
            target_run=target_run,
            packages=packages,
            approved_analysis_paths=approved_analysis_paths,
            profile_name=profile_name,
            writing_profile_name=writing_profile_name,
            profiles_path=profiles_path,
            experiment_policy_path=experiment_policy_path,
            maximum_input_tokens=int(saved["limits"]["maximum_input_tokens"]),
            output_path=scratch,
        )
        expected = json.loads(scratch.read_text(encoding="utf-8"))
    finally:
        scratch.unlink(missing_ok=True)
    if saved != expected or saved.get("status") != "eligible":
        raise ValueError("imported writing preflight differs from trusted reconstruction")
    return ImportedWritingAuthorization(
        preflight_path=writing_preflight_path,
        preflight_sha256=sha256_file(writing_preflight_path),
        target_run=target_run,
        execute_chapters=frozenset(
            (item["iso3"], item["chapter_id"]) for item in saved["requests"]
        ),
        request_sha256s=frozenset(item["request_sha256"] for item in saved["requests"]),
        limits={key: int(value) for key, value in saved["limits"].items()},
        profile_name=str(saved["profile"]),
        profiles_path=profiles_path,
        profiles_sha256=sha256_file(profiles_path),
        provider=str(saved["provider"]),
        model=str(saved["model"]),
        surface=str(saved["surface"]),
        reasoning_effort=str(saved["reasoning_effort"]),
        _capability=_WRITING_AUTHORIZATION_CAPABILITY,
    )


def run_authorized_imported_chapter_writing(
    *,
    authorization: ImportedWritingAuthorization,
    project_root: Path,
    ruler_id: str,
    package: ChapterQuestionEvidencePackage,
    approved_analysis_path: Path,
    output_root: Path,
) -> Path:
    """Execute one preflight-authorized changed chapter under its exact request allowlist."""

    if authorization._capability is not _WRITING_AUTHORIZATION_CAPABILITY:
        raise ValueError("imported writing execution lacks trusted authorization")
    if (
        sha256_file(authorization.preflight_path) != authorization.preflight_sha256
        or sha256_file(authorization.profiles_path) != authorization.profiles_sha256
    ):
        raise ValueError("imported writing authorization input changed before execution")
    identity = (ruler_id, package.chapter_id)
    if identity not in authorization.execute_chapters:
        raise ValueError("chapter is absent from the imported writing execution inventory")
    expected_root = authorization.target_run / "model-output" / ruler_id / "question-writing"
    if output_root.resolve() != expected_root.resolve():
        raise ValueError("imported writing output root differs from its authorized release")
    from .question_packet_chapter import run_chapter_question_writing
    from .run_usage_budget import RunUsageBudgetTracker, RunUsageLimits

    limits = RunUsageLimits(
        max_calls=authorization.limits["maximum_calls"],
        max_input_tokens=authorization.limits["maximum_input_tokens"],
        max_output_tokens=authorization.limits["maximum_output_tokens"],
    )
    tracker = RunUsageBudgetTracker(
        ledger_path=authorization.target_run
        / "stage-budgets/imported-writing-usage-reservations.json",
        limits=limits,
        config_sha256=authorization.preflight_sha256,
        allowed_request_sha256s=authorization.request_sha256s,
    )
    return run_chapter_question_writing(
        project_root=project_root,
        package=package,
        output_dir=output_root / package.chapter_id,
        approved_analysis_path=approved_analysis_path,
        profile_name=authorization.profile_name,
        profiles_path=authorization.profiles_path,
        reasoning_effort=authorization.reasoning_effort,
        run_budget_tracker=tracker,
    )
def _construct_preflight(
    *,
    project_root: Path,
    source_run: Path,
    target_run: Path,
    packages: dict[tuple[str, str], ChapterQuestionEvidencePackage],
    approved_analysis_paths: dict[tuple[str, str], Path],
    profile_name: str,
    writing_profile_name: str,
    profiles_path: Path,
    experiment_policy_path: Path,
) -> QuestionPhaseImportPreflight:
    expected_keys = {
        (ruler_id, f"{number}B")
        for ruler_id in ("CHN", "ISR", "PRK", "RUS", "USA")
        for number in range(1, 9)
    }
    if set(packages) != expected_keys or set(approved_analysis_paths) != expected_keys:
        raise ValueError("question phase import requires the exact five-ruler chapter inventory")
    source_preflight = source_run / "cohort-preflight.json"
    target_preflight = target_run / "cohort-preflight.json"
    rows = []
    for ruler_id, chapter_id in sorted(expected_keys):
        package = packages[(ruler_id, chapter_id)]
        analysis_path = approved_analysis_paths[(ruler_id, chapter_id)]
        source_root = source_run / "model-output" / ruler_id
        writing_dir = source_root / "question-writing" / chapter_id
        writing_manifest = writing_dir / "writing-manifest.json"
        writing_action = "execute"
        writing_tree_hash = None
        if writing_manifest.is_file():
            manifest_payload = json.loads(writing_manifest.read_text(encoding="utf-8"))
            same_package = manifest_payload.get("package_sha256") == payload_hash(
                package.model_dump(mode="json")
            )
            if same_package:
                validate_chapter_question_writing(
                    project_root=project_root,
                    package=package,
                    output_dir=writing_dir,
                    approved_analysis_path=analysis_path,
                    profile_name=writing_profile_name,
                    profiles_path=profiles_path,
                )
                writing_action = "import"
                writing_tree_hash = _tree_digest(writing_dir)
        review_action = "execute"
        review_tree_hash = None
        review_dir = source_root / "question-review" / chapter_id
        review_manifest = review_dir / "review-manifest.json"
        if writing_action == "import" and review_manifest.is_file():
            validate_chapter_question_review(
                project_root=project_root,
                package=package,
                approved_analysis_path=analysis_path,
                writing_dir=writing_dir,
                output_dir=review_dir,
                profile_name=profile_name,
                writing_profile_name=writing_profile_name,
                profiles_path=profiles_path,
                reasoning_effort="high",
                experiment_policy_path=experiment_policy_path,
            )
            review_action = "import"
            review_tree_hash = _tree_digest(review_dir)
        rows.append(
            PhaseImportRow(
                ruler_id=ruler_id,
                chapter_id=chapter_id,
                writing_action=writing_action,
                writing_source_tree_sha256=writing_tree_hash,
                review_action=review_action,
                review_source_tree_sha256=review_tree_hash,
            )
        )
    imported_writing = sum(row.writing_action == "import" for row in rows)
    imported_review = sum(row.review_action == "import" for row in rows)
    return QuestionPhaseImportPreflight(
        schema_version="question_phase_import_preflight_v1",
        status="eligible",
        source_run=str(source_run.resolve().relative_to(project_root.resolve())),
        source_preflight_sha256=sha256_file(source_preflight),
        target_run=str(target_run.resolve().relative_to(project_root.resolve())),
        target_preflight_sha256=sha256_file(target_preflight),
        profile_name=profile_name,
        writing_profile_name=writing_profile_name,
        profiles_sha256=sha256_file(profiles_path),
        experiment_policy_path=str(
            experiment_policy_path.resolve().relative_to(project_root.resolve())
        ),
        experiment_policy_sha256=sha256_file(experiment_policy_path),
        rows=tuple(rows),
        imported_writing_chapters=imported_writing,
        writing_chapters_to_execute=40 - imported_writing,
        imported_review_chapters=imported_review,
        review_chapters_to_execute=40 - imported_review,
        imported_writing_calls=10 * imported_writing,
        writing_calls_to_execute=10 * (40 - imported_writing),
        imported_review_calls=10 * imported_review,
        review_calls_to_execute=10 * (40 - imported_review),
        model_calls_executed=0,
        reservations_created=0,
    )


def _copy_tree(source: Path, target: Path, expected_sha256: str | None) -> None:
    if expected_sha256 is None or _tree_digest(source) != expected_sha256:
        raise ValueError("question phase source tree changed after import preflight")
    if target.exists():
        raise FileExistsError(f"question phase import target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    if _tree_digest(target) != expected_sha256:
        raise ValueError("copied question phase tree differs from its trusted source")


def _tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise ValueError(f"question phase source tree is absent: {root}")
    digest = sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError("question phase source tree is empty")
    for path in files:
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


__all__ = [
    "ImportedWritingAuthorization",
    "QuestionPhaseImportPreflight",
    "apply_trusted_question_phase_imports",
    "build_imported_writing_preflight",
    "build_question_phase_import_preflight",
    "load_imported_writing_authorization",
    "run_authorized_imported_chapter_writing",
]
