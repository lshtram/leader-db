"""Public study-site projection and rendering tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.study_site_models import PublicEvidence
from leaders_db.research.study_site_projection import (
    _confined_path,
    _reader_sections,
    safe_public_url,
)


def test_reader_sections_split_short_answer_from_full_account() -> None:
    assert _reader_sections(
        "[[reader_summary_and_exposition_v1]]\n"
        "Short answer.\n\nFirst event.\n\nSecond event."
    ) == (
        "Short answer.",
        "First event.\n\nSecond event.",
    )
    assert _reader_sections("Historical single rationale.") == (
        "Historical single rationale.",
        None,
    )
    assert _reader_sections("Historical first paragraph.\n\nHistorical second paragraph.") == (
        "Historical first paragraph.\n\nHistorical second paragraph.",
        None,
    )


def test_safe_public_url_accepts_only_http_and_https() -> None:
    assert safe_public_url("https://example.org/report") == "https://example.org/report"
    with pytest.raises(ValueError, match="unsafe public URL"):
        safe_public_url("file:///private/report.html")
    with pytest.raises(ValueError, match="unsafe public URL"):
        safe_public_url("javascript:alert(1)")


def test_public_artifact_paths_are_confined_to_project(tmp_path: Path) -> None:
    inside = tmp_path / "artifact.json"
    inside.write_text("{}", encoding="utf-8")
    assert _confined_path(tmp_path, "artifact.json") == inside
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="outside the project root"):
            _confined_path(tmp_path, outside.as_posix())
    finally:
        outside.unlink()


def test_public_evidence_rejects_path_traversal_ids() -> None:
    payload = {
        "evidence_id": "E001",
        "source_id": "../../index.html",
        "url": "https://example.org",
        "title": "Example",
        "publisher": "Example",
        "fact_summary": "Fact",
        "question_ids": ["1B.1"],
        "polarity": "supporting",
        "exact_excerpt": "Excerpt",
        "excerpt_sha256": "a" * 64,
        "locator": "unit 1",
        "start_unit": 1,
        "end_unit": 1,
        "period_fit": "2023",
        "ruler_attribution": "direct",
        "limitations": [],
        "verification_status": "verified",
        "verification_notes": [],
        "raw_sha256": "b" * 64,
    }
    with pytest.raises(ValueError):
        PublicEvidence.model_validate(payload)


def test_builder_refuses_unowned_nonempty_output(tmp_path: Path) -> None:
    from leaders_db.research.study_site_render import build_study_site

    output = tmp_path / "existing"
    output.mkdir()
    (output / "user-file.txt").write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="not owned"):
        build_study_site(project_root=tmp_path, run_dir=tmp_path / "run", output_dir=output)
    assert (output / "user-file.txt").read_text(encoding="utf-8") == "preserve"


def test_builder_refuses_fake_ownership_manifest(tmp_path: Path) -> None:
    from leaders_db.research.study_site_render import build_study_site

    output = tmp_path / "existing"
    output.mkdir()
    (output / "study-site-manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="ownership manifest is invalid"):
        build_study_site(project_root=tmp_path, run_dir=tmp_path / "run", output_dir=output)


def test_builder_refuses_forged_empty_ownership_inventory(tmp_path: Path) -> None:
    from leaders_db.research.study_site_render import build_study_site

    output = tmp_path / "existing"
    output.mkdir()
    (output / "user-file.txt").write_text("preserve", encoding="utf-8")
    (output / "study-site-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "study_site_manifest_v1",
                "base_path": "/leaders-study/",
                "files": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ownership inventory is invalid"):
        build_study_site(project_root=tmp_path, run_dir=tmp_path / "run", output_dir=output)
    assert (output / "user-file.txt").read_text(encoding="utf-8") == "preserve"


def test_builder_refuses_output_beneath_run_directory(tmp_path: Path) -> None:
    from leaders_db.research.study_site_render import build_study_site

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(ValueError, match="too broad"):
        build_study_site(
            project_root=tmp_path,
            run_dir=run_dir,
            output_dir=run_dir / "publication/site",
        )


def test_builder_refuses_audit_outside_selected_run(tmp_path: Path) -> None:
    from leaders_db.research.study_site_render import build_study_site

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    outside = tmp_path / "outside-audit.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="audit must be a file beneath"):
        build_study_site(
            project_root=tmp_path,
            run_dir=run_dir,
            output_dir=tmp_path / "site",
            audit_path=outside,
            approved_audit_sha256="0" * 64,
        )


def test_builder_requires_hash_for_audit_override(tmp_path: Path) -> None:
    from leaders_db.research.study_site_render import build_study_site

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    audit = run_dir / "alternate-audit.json"
    audit.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="requires an approved SHA-256"):
        build_study_site(
            project_root=tmp_path,
            run_dir=run_dir,
            output_dir=tmp_path / "site",
            audit_path=audit,
        )


def test_historical_projection_without_audit_binding_still_loads() -> None:
    from leaders_db.research.study_site_models import StudySiteProjection

    projection = StudySiteProjection.model_validate(
        {
            "schema_version": "study_site_projection_v1",
            "run_id": "historical-run",
            "target_year": 2023,
            "audit_decision": "pass",
            "pipeline_version_id": "pipeline-v1",
            "methodology_version_id": "methodology-v1",
            "rulers": [],
        }
    )

    assert projection.audit_path is None
    assert projection.audit_sha256 is None


def test_live_five_ruler_site_builds_when_artifacts_are_available(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    run_dir = project_root / "research/runs/2023-five-ruler-flow-test-v2"
    if not run_dir.exists():
        pytest.skip("local production artifacts are not present")

    from leaders_db.research.study_site_render import build_study_site

    manifest_path = build_study_site(
        project_root=project_root,
        run_dir=run_dir,
        output_dir=tmp_path / "site",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated = {item["path"] for item in manifest["files"]}
    assert "index.html" in generated
    assert "rulers/usa-2023/index.html" in generated
    assert "methodology/index.html" in generated
    index = (tmp_path / "site/index.html").read_text(encoding="utf-8")
    assert "Client" not in index
    assert "Xi Jinping" in index
    assert "Benjamin Netanyahu" in index
    assert index.count("<tr><td>2</td>") == 2
    assert "file://" not in index
    ruler_page = (tmp_path / "site/rulers/usa-2023/index.html").read_text(
        encoding="utf-8"
    )
    assert ruler_page.count('class="chapter"') == 8
    assert ruler_page.count('class="question"') == 80
    assert "client_score" not in ruler_page
