from pathlib import Path


def test_clean_room_package_has_no_leaders_db_dependency() -> None:
    root = Path(__file__).parents[1] / "src/simple_evidence"
    content = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    assert "leaders_db" not in content
    assert "evidence_funnel" not in content


def test_project_files_remain_below_four_hundred_lines() -> None:
    root = Path(__file__).parents[1]
    oversized = {
        str(path.relative_to(root)): len(path.read_text(encoding="utf-8").splitlines())
        for folder in ("src", "tests")
        for path in (root / folder).rglob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 400
    }

    assert oversized == {}

