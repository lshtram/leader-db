"""Public study-site projection and rendering tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leaders_db.research.study_site_models import PublicEvidence
from leaders_db.research.study_site_projection import safe_public_url


def test_safe_public_url_accepts_only_http_and_https() -> None:
    assert safe_public_url("https://example.org/report") == "https://example.org/report"
    with pytest.raises(ValueError, match="unsafe public URL"):
        safe_public_url("file:///private/report.html")
    with pytest.raises(ValueError, match="unsafe public URL"):
        safe_public_url("javascript:alert(1)")


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
