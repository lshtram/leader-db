"""Render an approved ruler evidence package and its measured profile as HTML."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from .chapter_analysis_models import (
    ChapterAnalysisQuality,
    ChapterQualityReviewBinding,
    ResolvedChapterAnalysis,
)
from .ruler_html_style import REPORT_CSS
from .ruler_report_profile import profile_html, usage_profile


def build_ruler_html_report(
    *,
    project_root: Path,
    run_dir: Path,
    selection_manifest_path: Path,
    dossier_usage_path: Path,
    production_run_manifest_path: Path,
    output_path: Path,
) -> Path:
    """Write one self-contained, linked HTML report from approved artifacts."""

    selection = _load(selection_manifest_path)
    from .production_run import load_production_run_manifest

    production_run = load_production_run_manifest(
        production_run_manifest_path, project_root=project_root
    )
    if not selection["complete_ruler_safe_for_judge_use"]:
        raise ValueError("selection manifest is not approved for complete ruler use")
    package_path = run_dir / "corpus-judge-package.json"
    package = _load(package_path)
    evidence = {item["evidence_id"]: item for item in package["evidence"]}
    chapters = _chapters(run_dir, selection, set(evidence), package_path)
    questions = _question_text(project_root)
    phases = usage_profile(run_dir, dossier_usage_path)
    documents = _documents(run_dir)
    content = _render(
        project_root,
        selection,
        chapters,
        evidence,
        questions,
        phases,
        documents,
        production_run.model_dump(mode="json"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _chapters(run_dir, selection, package_ids, package_path=None):
    rows = []
    expected_chapters = {f"{index}B" for index in range(1, 9)}
    received_chapters = {item["chapter_id"] for item in selection["chapters"]}
    if received_chapters != expected_chapters or len(selection["chapters"]) != 8:
        raise ValueError("selection manifest must contain chapters 1B through 8B once")
    if selection.get("quality_review_contract") != "independent-full-index-v1":
        raise ValueError("selection manifest lacks the independent full-index review contract")
    for item in selection["chapters"]:
        analysis_path = run_dir / item["analysis_path"]
        review_path = run_dir / item["review_path"]
        _check_hash(analysis_path, item["analysis_sha256"])
        _check_hash(review_path, item["review_sha256"])
        if package_path is None:
            package_path = run_dir / "corpus-judge-package.json"
        _validate_review_binding(item, run_dir, analysis_path, review_path, package_path)
        analysis = ResolvedChapterAnalysis.model_validate_json(
            analysis_path.read_text(encoding="utf-8")
        )
        review = ChapterAnalysisQuality.model_validate_json(
            review_path.read_text(encoding="utf-8")
        )
        if not (
            item["chapter_id"] == analysis.chapter_id == review.chapter_id
            and review.safe_for_judge_use
        ):
            raise ValueError("selected chapter identities or approval do not reconcile")
        expected_questions = {
            f'{item["chapter_id"]}.{index}' for index in range(1, 11)
        }
        received_questions = {answer.question_id for answer in analysis.answers}
        if received_questions != expected_questions or len(analysis.answers) != 10:
            raise ValueError("selected chapter does not contain ten unique answers")
        cited = {
            evidence_id
            for answer in analysis.answers
            for evidence_id in (
                answer.supporting_evidence_ids
                + answer.contrary_or_qualifying_evidence_ids
            )
        }
        if not cited.issubset(package_ids):
            raise ValueError("selected chapter cites evidence outside the judge package")
        rows.append((item, analysis, review))
    return tuple(rows)


def _check_hash(path, expected):
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"artifact hash mismatch: {path}")


def _validate_review_binding(
    item: dict,
    run_dir: Path,
    analysis_path: Path,
    review_path: Path,
    package_path: Path,
) -> None:
    binding_path = run_dir / item["review_binding_path"]
    _check_hash(binding_path, item["review_binding_sha256"])
    binding = ChapterQualityReviewBinding.model_validate_json(
        binding_path.read_text(encoding="utf-8")
    )
    if (
        binding.contract != "independent-full-index-v1"
        or binding.chapter_id != item["chapter_id"]
        or binding.analysis_sha256 != _file_hash(analysis_path)
        or binding.review_sha256 != _file_hash(review_path)
        or binding.judge_package_sha256 != _file_hash(package_path)
    ):
        raise ValueError("quality review is not bound to the selected analysis and package")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _question_text(project_root):
    payload = _load(
        project_root / "src/leaders_db/conversational_evidence/data/questions.json"
    )
    return {
        question["id"]: question["text"]
        for chapter in payload["chapters"]
        for question in chapter["questions"]
    }


def _documents(run_dir):
    acquisition = _load(run_dir / "acquisition/acquisition-manifest.json")
    catalog = _load(Path(acquisition["catalogue_path"]))
    metadata = {item["url"]: item for item in catalog["candidates"]}
    batches = defaultdict(list)
    batch_inputs = _batch_input_tokens(run_dir / "reading")
    for name in ("reading-plan.json", "reading-plan-repaired.json"):
        for batch in _load(run_dir / name)["batches"]:
            for source_id in batch["source_ids"]:
                batches[source_id].append(batch["batch_id"])
    rows = []
    for item in acquisition["records"]:
        source = metadata.get(item["requested_url"], {})
        rows.append(
            {
                **item,
                "title": source.get("title", ""),
                "publisher": source.get("publisher", ""),
                "batches": tuple(sorted(set(batches[item["source_id"]]))),
                "shared_batch_input_tokens": sum(
                    batch_inputs[batch_id]
                    for batch_id in set(batches[item["source_id"]])
                ),
            }
        )
    return tuple(rows)


def _batch_input_tokens(reading_dir):
    totals = defaultdict(int)
    for batch_dir in (path for path in reading_dir.iterdir() if path.is_dir()):
        for events_path in batch_dir.rglob("events.jsonl"):
            for line in events_path.read_text(errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "turn.completed":
                    totals[batch_dir.name] += int(
                        event.get("usage", {}).get("input_tokens", 0) or 0
                    )
    return totals


def _render(
    project_root,
    selection,
    chapters,
    evidence,
    questions,
    phases,
    documents,
    production_run,
):
    totals = {
        key: sum(item[key] for item in phases)
        for key in ("calls", "input", "cached", "output", "reasoning")
    }
    acquired = [item for item in documents if item["status"] == "acquired"]
    acquired_tokens = sum(int(x.get("estimated_tokens") or 0) for x in acquired)
    chapter_links = "".join(
        f'<a href="#{x[0]["chapter_id"]}">{x[0]["chapter_id"]}</a>'
        for x in chapters
    )
    answer_html = "".join(
        _chapter_html(item, analysis, review, evidence, questions)
        for item, analysis, review in chapters
    )
    attribution = html.escape(
        (project_root / "docs/sources/attributions.md").read_text(encoding="utf-8")
    )
    provenance = production_run["pipeline_provenance"]
    stage_rows = "".join(
        "<tr><td>" + _e(item["stage_id"]) + "</td><td>"
        + _e(item["implementation_id"]) + "</td><td>"
        + _e(item["contract_id"]) + "</td></tr>"
        for item in provenance["stages"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(selection['ruler_name'])} {selection['target_year']} evidence report</title>
<style>{REPORT_CSS}</style></head><body><main>
<header><p class="eyebrow">Leaders Database · approved evidence report</p>
<h1>{_e(selection['ruler_name'])} — {selection['target_year']}</h1>
<p>All eight chapters passed independent evidence-quality review. This report answers
all 80 evidence questions without assigning ruler scores.</p></header>
<nav><a href="#profile">Profile</a><a href="#documents">Documents</a>
{chapter_links}</nav>
<section class="summary">
<div><b>{len(documents)}</b><span>candidate URLs dispositioned</span></div>
<div><b>{len(acquired)}</b><span>sources acquired</span></div>
<div><b>{acquired_tokens:,}</b><span>estimated acquired-source tokens</span></div>
<div><b>{len(evidence)}</b><span>verified evidence records</span></div>
<div><b>{totals['input']:,}</b><span>measured model input tokens</span></div>
<div><b>{totals['output']:,}</b><span>measured model output tokens</span></div>
</section>
<section id="pipeline"><h2>Pipeline identity</h2>
<p>Run: {_e(production_run['run_id'])} · Pipeline: {_e(provenance['pipeline_version_id'])}
· Methodology: {_e(provenance['methodology_version_id'])} · Release:
{_e(provenance['release_id'])} ({_e(provenance['release_sha256'])})</p>
<table><thead><tr><th>Stage</th><th>Implementation</th><th>Contract</th></tr></thead>
<tbody>{stage_rows}</tbody></table></section>
{answer_html}
{profile_html(phases, totals, selection)}
{_documents_html(documents)}
<section id="attributions"><h2>Source attribution</h2><pre>{attribution}</pre></section>
</main></body></html>"""


def _chapter_html(item, analysis, review, evidence, questions):
    quality = {row.question_id: row for row in review.lens_quality}
    parts = [
        f'<section class="chapter" id="{item["chapter_id"]}"><h2>Chapter {item["chapter_id"]}</h2>',
        (
            f'<p class="gate">Approved: {_e(review.overall_verdict)} · '
            f"{len(review.concrete_corrections_required)} nonblocking corrections "
            "retained</p>"
        ),
    ]
    for answer in analysis.answers:
        cited_ids = tuple(
            dict.fromkeys(
                answer.supporting_evidence_ids
                + answer.contrary_or_qualifying_evidence_ids
            )
        )
        lens = quality[answer.question_id]
        parts.append(
            f'<article id="{answer.question_id}"><h3>{answer.question_id}: '
            f'{_e(questions[answer.question_id])}</h3>'
            f'<p class="quality">Quality — factual {lens.factual_support_1_to_5}/5 · '
            f"completeness {lens.completeness_1_to_5}/5 · "
            f"balance {lens.balance_1_to_5}/5 · attribution/period "
            f"{lens.attribution_and_period_1_to_5}/5 · judge usefulness "
            f"{lens.judge_usefulness_1_to_5}/5</p>"
            f'<div class="answer">'
            f'{_linked_answer(answer.answer, cited_ids, answer.question_id)}</div>'
            f'{_limitations(answer.limitations_and_gaps)}'
            f'<details><summary>Evidence base ({len(cited_ids)} records)</summary>'
            f"{_evidence_table(cited_ids, evidence, answer.question_id)}"
            "</details></article>"
        )
    parts.append("</section>")
    return "".join(parts)


def _linked_answer(text, evidence_ids, anchor_prefix=""):
    escaped = _e(text)
    prefix = f"{anchor_prefix}-" if anchor_prefix else ""
    for evidence_id in sorted(evidence_ids, key=len, reverse=True):
        escaped = re.sub(
            rf"(?<![\w-]){re.escape(evidence_id)}(?![\w-])",
            f'<a class="cite" href="#ev-{prefix}{evidence_id}">'
            f"{evidence_id}</a>",
            escaped,
        )
    return "".join(f"<p>{part}</p>" for part in escaped.split("\n") if part.strip())


def _limitations(items):
    if not items:
        return ""
    return "<h4>Limitations and gaps</h4><ul>" + "".join(
        f"<li>{_e(item)}</li>" for item in items
    ) + "</ul>"


def _evidence_table(ids, evidence, anchor_prefix):
    rows = []
    for evidence_id in ids:
        item = evidence[evidence_id]
        rows.append(
            f'<div class="evidence" id="ev-{anchor_prefix}-{evidence_id}">'
            f"<h4>{evidence_id} · "
            f'{_e(item["publisher"])}</h4>'
            f'<p><a href="{_safe_href(item["url"])}" target="_blank" rel="noopener">'
            f'{_e(item["title"] or item["url"])}</a> · locator: '
            f'{_e(item["locator"])}</p>'
            f'<p><b>Finding:</b> {_e(item["fact_summary"])}</p>'
            f'<blockquote>{_e(item["exact_excerpt"])}</blockquote>'
            f'<p class="meta">Period: {_e(item["period_fit"])} · attribution: '
            f'{_e(item["ruler_attribution"])} · verification: '
            f'{_e(item["verification_status"])} · limitations: '
            f'{_e(item["limitations"])}</p></div>'
        )
    return "".join(rows)


def _documents_html(documents):
    rows = []
    ordered = sorted(
        documents,
        key=lambda item: int(item.get("estimated_tokens") or 0),
        reverse=True,
    )
    for item in ordered:
        batch_text = ", ".join(item["batches"]) or "not queued / duplicate or unavailable"
        rows.append(
            f'<tr><td>{_e(item["source_id"])}</td><td>'
            f'<a href="{_safe_href(item["requested_url"])}" target="_blank" '
            'rel="noopener">'
            f'{_e(item["title"] or item["requested_url"])}</a><br>'
            f'<small>{_e(item["publisher"])}</small></td>'
            f'<td>{_e(item["status"])}</td>'
            f'<td>{int(item.get("estimated_tokens") or 0):,}</td>'
            f'<td>{int(item.get("extracted_characters") or 0):,}</td>'
            f'<td>{int(item["shared_batch_input_tokens"]):,}</td>'
            f'<td>{_e(batch_text)}</td></tr>'
        )
    return (
        '<section id="documents"><h2>Source-by-source processing profile</h2>'
        "<p>Estimated source tokens measure extracted document text. They are distinct "
        "from model input tokens, which also include instructions, evidence schemas, "
        "repeated verification passages, and review context. Shared reading-batch input "
        "is the measured model input for every batch containing the source; it is shown "
        "as shared context and is not allocated as if one document incurred the whole "
        "batch cost.</p><table><thead><tr>"
        "<th>Source ID</th><th>Document</th><th>Acquisition</th>"
        "<th>Estimated source tokens</th><th>Extracted characters</th>"
        "<th>Shared reading-batch model input</th>"
        f'<th>Reading batches</th></tr></thead><tbody>{"".join(rows)}</tbody>'
        "</table></section>"
    )


def _e(value):
    return html.escape(str(value or ""), quote=True)


def _safe_href(value):
    text = str(value or "")
    return _e(text) if urlparse(text).scheme.lower() in {"http", "https"} else "#"


__all__ = ["build_ruler_html_report"]
