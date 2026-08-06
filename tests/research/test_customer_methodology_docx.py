from __future__ import annotations

import hashlib
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import yaml

from leaders_db.conversational_evidence.data import questions
from leaders_db.research.question_lens_presentation import (
    load_question_lens_presentation,
)

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAMESPACES = {"w": WORD_NAMESPACE}


def test_methodology_v2_freeze_matches_every_declared_file(project_root: Path) -> None:
    manifest_path = (
        project_root
        / "configs/evidence-funnel/methodology-2026-08-v2.freeze.yaml"
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    recorded = manifest["file_hashes"]
    hash_lines: list[str] = []

    for relative_path, expected_digest in recorded.items():
        digest = hashlib.sha256((project_root / relative_path).read_bytes()).hexdigest()
        assert digest == expected_digest
        hash_lines.append(f"{digest}  {relative_path}\n")

    aggregate = hashlib.sha256("".join(sorted(hash_lines)).encode()).hexdigest()
    assert aggregate == manifest["aggregate_sha256"]


def test_customer_word_methodology_matches_all_eighty_runtime_lenses(
    project_root: Path,
) -> None:
    path = (
        project_root
        / "docs/customer-facing/leaders-database-research-and-evaluation-pipeline.docx"
    )
    rows = _accepted_question_rows(path)
    detailed_by_id = {item["id"]: item["text"] for item in questions()}
    presentation = load_question_lens_presentation()

    assert len(rows) == 80
    category_names = {
        key: category.name for key, category in presentation.evidence_categories.items()
    }
    for lens in presentation.lenses:
        title, simple_question, detailed_question, evidence_categories = rows[lens.id]
        assert title == f"{lens.id} — {lens.title}"
        assert simple_question == f"Core question\n{lens.simple_question}"
        assert detailed_question == f"What researchers examine\n{detailed_by_id[lens.id]}"
        expected_categories = " • ".join(
            category_names[key] for key in lens.priority_categories
        )
        assert evidence_categories == f"Most relevant evidence: {expected_categories}"


def _accepted_question_rows(path: Path) -> dict[str, tuple[str, str, str, str]]:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    rows: dict[str, tuple[str, str, str, str]] = {}
    for table_row in root.findall(".//w:tr", NAMESPACES):
        cells = table_row.findall("./w:tc", NAMESPACES)
        if len(cells) != 1:
            continue
        paragraphs = _accepted_paragraphs(cells[0])
        if len(paragraphs) != 4 or " — " not in paragraphs[0]:
            continue
        methodology_id = paragraphs[0].split(" — ", maxsplit=1)[0]
        if methodology_id in {item["id"] for item in questions()}:
            rows[methodology_id] = paragraphs
    return rows


def _accepted_paragraphs(element: ElementTree.Element) -> tuple[str, ...]:
    paragraphs: list[str] = []
    for paragraph in element.findall(".//w:p", NAMESPACES):
        parent_by_child = {child: parent for parent in paragraph.iter() for child in parent}
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{{{WORD_NAMESPACE}}}t" and not _inside_deleted(
                node, parent_by_child
            ):
                parts.append(node.text or "")
            elif node.tag == f"{{{WORD_NAMESPACE}}}br" and not _inside_deleted(
                node, parent_by_child
            ):
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return tuple(paragraphs)


def _inside_deleted(
    node: ElementTree.Element,
    parent_by_child: dict[ElementTree.Element, ElementTree.Element],
) -> bool:
    parent = parent_by_child.get(node)
    while parent is not None:
        if parent.tag == f"{{{WORD_NAMESPACE}}}del":
            return True
        parent = parent_by_child.get(parent)
    return False
