"""Render a dependency-free static website from a public study projection."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import html
import json
import shutil
from collections import defaultdict
from pathlib import Path

from .study_site_models import PublicEvidence, PublicRuler, StudySiteProjection
from .study_site_projection import CHAPTER_TITLES, safe_public_url

BASE = "/leaders-study"


def build_study_site(  # noqa: PLR0912
    *,
    project_root: Path,
    run_dir: Path,
    output_dir: Path,
    audit_path: Path | None = None,
    approved_audit_sha256: str | None = None,
) -> Path:
    """Build the complete static site and return its manifest path."""

    from .study_site_projection import build_study_site_projection

    resolved_output = output_dir.resolve()
    forbidden = {Path("/").resolve(), project_root.resolve(), run_dir.resolve()}
    if (
        resolved_output in forbidden
        or resolved_output.is_relative_to(run_dir.resolve())
        or any(path.is_relative_to(resolved_output) for path in forbidden)
    ):
        raise ValueError("study-site output directory is too broad or contains trusted inputs")
    if output_dir.exists() and any(output_dir.iterdir()):
        marker = output_dir / "study-site-manifest.json"
        if not marker.is_file():
            raise ValueError("refusing to replace a non-empty directory not owned by study-site")
        try:
            ownership = json.loads(marker.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("study-site ownership manifest is invalid") from exc
        if (
            ownership.get("schema_version") != "study_site_manifest_v1"
            or ownership.get("base_path") != f"{BASE}/"
            or not isinstance(ownership.get("files"), list)
        ):
            raise ValueError("study-site ownership manifest is invalid")
        expected_files: set[str] = set()
        for item in ownership["files"]:
            if not isinstance(item, dict) or not {
                "path",
                "bytes",
                "sha256",
            }.issubset(item):
                raise ValueError("study-site ownership manifest is invalid")
            path = (resolved_output / str(item["path"])).resolve()
            if not path.is_relative_to(resolved_output) or not path.is_file():
                raise ValueError("study-site ownership inventory is invalid")
            if path.stat().st_size != item["bytes"]:
                raise ValueError("study-site ownership inventory is invalid")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("study-site ownership inventory is invalid")
            expected_files.add(str(path.relative_to(resolved_output)))
        actual_files = {
            str(path.relative_to(resolved_output))
            for path in resolved_output.rglob("*")
            if path.is_file() and path != marker
        }
        if expected_files != actual_files:
            raise ValueError("study-site ownership inventory is invalid")
    projection = build_study_site_projection(
        project_root=project_root,
        run_dir=run_dir,
        audit_path=audit_path,
        approved_audit_sha256=approved_audit_sha256,
    )
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    _write(output_dir / "assets/site.css", _css())
    _write(output_dir / "assets/site.js", _js())
    _write(output_dir / "index.html", _home(projection))
    _write(output_dir / "methodology/index.html", _methodology(projection))
    _write(output_dir / "questions/index.html", _questions(projection))
    _write(output_dir / "pipeline/index.html", _pipeline(projection))
    _write(output_dir / "sources/index.html", _sources(project_root, projection))
    _write(output_dir / "run-details/index.html", _run_details(projection))
    for ruler in projection.rulers:
        _write(output_dir / f"rulers/{ruler.iso3.lower()}-2023/index.html", _ruler(ruler))
        for source_id, records in _by_source(ruler).items():
            _write(
                output_dir / f"evidence/{ruler.iso3.lower()}/{source_id}/index.html",
                _source(ruler, records),
            )
    manifest_path = output_dir / "study-site-manifest.json"
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path != manifest_path:
            files.append({
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest = {
        "schema_version": "study_site_manifest_v1",
        "run_id": projection.run_id,
        "audit_path": projection.audit_path,
        "audit_sha256": projection.audit_sha256,
        "base_path": f"{BASE}/",
        "files": files,
    }
    _write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def _home(site: StudySiteProjection) -> str:
    rows = []
    for ruler in site.rulers:
        cells = "".join(
            f'<td><a href="{BASE}/rulers/{ruler.iso3.lower()}-2023/#{chapter.chapter_id}">'
            f'<b>{chapter.score:g}</b><small>{chapter.confidence:g}% confidence</small></a></td>'
            for chapter in ruler.chapters
        )
        rows.append(
            f'<tr><td>{ruler.shared_rank}</td><th><a href="{BASE}/rulers/{ruler.iso3.lower()}-2023/">'
            f'{_e(ruler.ruler_name)}</a><small>{ruler.iso3}</small></th>{cells}'
            f'<td><b>{ruler.overall_mean:.3f}</b></td></tr>'
        )
    heads = "".join(f'<th title="{_e(title)}">{chapter}</th>' for chapter, title in CHAPTER_TITLES.items())
    content = f"""<header class="hero"><p class="eyebrow">Leaders Database · 2023 study</p>
<h1>Five rulers, examined through evidence</h1><p class="lede">This demonstration compares five 2023 ruler-periods across eight chapters. Each chapter score is supported by ten research questions, reviewed answers, and cited passages.</p></header>
<section><h2>Comparative results</h2><p>Higher scores represent better performance under the chapter rubric. Overall is the unweighted mean of the eight reviewed chapter scores; equal means share rank.</p>
<div class="table-wrap"><table><thead><tr><th>Rank</th><th>Ruler</th>{heads}<th>Overall</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class="cards"><a href="{BASE}/methodology/"><b>How the study works</b><span>Scoring, confidence, attribution, bias, and missing evidence.</span></a><a href="{BASE}/questions/"><b>Research framework</b><span>Eight chapters and all 80 evidence questions.</span></a><a href="{BASE}/pipeline/"><b>Research pipeline</b><span>From ruler identity to independently reviewed publication.</span></a></section>"""
    return _page("2023 five-ruler study", content)


def _ruler(ruler: PublicRuler) -> str:
    chapters = []
    evidence = {item.evidence_id: item for item in ruler.evidence}
    for chapter in ruler.chapters:
        questions = []
        for question in chapter.questions:
            citations = []
            for label, ids in (("Supporting evidence", question.supporting_evidence_ids), ("Qualifying evidence", question.qualifying_evidence_ids)):
                if ids:
                    citations.append(f"<h5>{label}</h5>" + "".join(_citation(ruler, evidence[item]) for item in ids))
            gaps = "" if not question.limitations_and_gaps else "<h5>Limitations and gaps</h5><ul>" + "".join(f"<li>{_e(item)}</li>" for item in question.limitations_and_gaps) + "</ul>"
            questions.append(f'<details class="question" id="{question.question_id}"><summary><span>{question.question_id}</span>{_e(question.question)}</summary><div class="question-body"><div class="answer">{_paras(question.answer)}</div>{gaps}{"".join(citations)}</div></details>')
        flag = "" if not chapter.manual_review_required else f'<aside class="notice"><b>Manual review flag</b><p>{_e(chapter.manual_review_reason)}</p></aside>'
        weak = ", ".join(chapter.missing_or_weak_lenses) or "None recorded"
        reader_judgment = f'<h3>Short answer</h3>{_paras(chapter.summary or chapter.rationale)}'
        if chapter.exposition:
            reader_judgment += (
                f'<h3>What happened during the year</h3>{_paras(chapter.exposition)}'
            )
        attribution = ""
        if not chapter.exposition:
            attribution = f'<div><h4>Ruler attribution</h4>{_paras(chapter.ruler_attribution)}</div><div><h4>Inherited baseline and constraints</h4>{_paras(chapter.inherited_baseline_and_constraints)}</div>'
        chapters.append(f'''<details class="chapter" id="{chapter.chapter_id}"><summary><span class="chapter-code">{chapter.chapter_id}</span><span><b>{_e(chapter.title)}</b><small>Score {chapter.score:g} · confidence {chapter.confidence:g}% · plausible range {chapter.plausible_lower:g}–{chapter.plausible_upper:g}</small></span></summary><div class="chapter-body">{flag}{reader_judgment}<div class="judgment-grid">{attribution}<div><h4>Calibration</h4>{_paras(chapter.lower_anchor_rejected)}{_paras(chapter.higher_anchor_rejected)}</div><div><h4>Coverage</h4><p>Missing or weak lenses: {_e(weak)}. Missing evidence affects confidence rather than automatically lowering the score.</p></div></div><h3>Ten evidence questions</h3>{''.join(questions)}</div></details>''')
    content = f'''<header class="hero"><p class="eyebrow"><a href="{BASE}/">2023 results</a> · {ruler.iso3}</p><h1>{_e(ruler.ruler_name)}</h1><p class="lede">Overall mean {ruler.overall_mean:.3f} · shared rank {ruler.shared_rank}. Scores are assigned to chapters; questions are evidence lenses.</p><div class="actions"><button data-expand="all">Expand all</button><button data-expand="none">Collapse all</button></div></header>{''.join(chapters)}'''
    return _page(f"{ruler.ruler_name} — 2023", content)


def _citation(ruler: PublicRuler, item: PublicEvidence) -> str:
    href = f"{BASE}/evidence/{ruler.iso3.lower()}/{item.source_id}/#evidence-{item.evidence_id}"
    return f'<article class="citation"><a href="{href}"><b>{_e(item.publisher)}</b> · {_e(item.title or item.evidence_id)}</a><p>{_e(item.fact_summary)}</p></article>'


def _source(ruler: PublicRuler, records: list[PublicEvidence]) -> str:
    first = records[0]
    original = safe_public_url(first.url)
    blocks = []
    for item in records:
        uses = _uses(ruler, item.evidence_id)
        back = " · ".join(f'<a href="{BASE}/rulers/{ruler.iso3.lower()}-2023/#{qid}">{qid}</a>' for qid in uses)
        notes = "" if not item.verification_notes else "<h3>Verification notes</h3><ul>" + "".join(f"<li>{_e(note)}</li>" for note in item.verification_notes) + "</ul>"
        blocks.append(f'''<article class="source-evidence" id="evidence-{item.evidence_id}"><p class="eyebrow">{item.evidence_id} · {_e(item.locator)}</p><h2>{_e(item.fact_summary)}</h2><p>Used by: {back}</p><blockquote>{_e(item.exact_excerpt)}</blockquote><dl><dt>Period fit</dt><dd>{_e(item.period_fit)}</dd><dt>Ruler attribution</dt><dd>{_e(item.ruler_attribution)}</dd><dt>Verification</dt><dd>{_e(item.verification_status)}</dd><dt>Stored source hash</dt><dd><code>{item.raw_sha256}</code></dd></dl>{notes}</article>''')
    content = f'''<header class="hero"><p class="eyebrow"><a href="{BASE}/rulers/{ruler.iso3.lower()}-2023/">{_e(ruler.ruler_name)}</a> · stored evidence</p><h1>{_e(first.title or first.publisher)}</h1><p>{_e(first.publisher)} · {first.source_id}</p><p><a class="button" href="{_e(original)}" target="_blank" rel="noopener noreferrer">Open original source</a></p><p class="notice">The verified excerpt retained by the study remains available here if the publisher link changes. This public view shows cited text, not the complete acquired document.</p></header>{''.join(blocks)}'''
    return _page(first.title or first.source_id, content)


def _methodology(site: StudySiteProjection) -> str:
    content = f'''<header class="hero"><p class="eyebrow">Methodology · {_e(site.methodology_version_id)}</p><h1>How the study reaches a score</h1></header><section><h2>Unit of judgment</h2><p>Each record concerns the publicly recognized holder of the formal governing office for one country and year. The study assigns one score to each chapter. Ten questions organize the evidence considered for that chapter; they are not separately scored.</p><h2>Evidence and attribution</h2><p>Research records factual claims, exact cited passages, period fit, and the basis for attributing conduct or outcomes to the ruler. Inherited conditions and institutional constraints are stated separately from target-year choices.</p><h2>Scoring and comparison</h2><p>Scores use a 1–10 scale in half-point increments and are calibrated across the five-ruler cohort. The judgment explains why adjacent lower and higher anchors were rejected. Overall is an unweighted descriptive mean, not a ninth judgment.</p><h2>Confidence and missing evidence</h2><p>Confidence records how firmly the evidence supports the judgment. Missing lenses, secrecy, temporal proxies, disagreement, and uneven reporting widen uncertainty or lower confidence. Missing evidence does not automatically count against a ruler.</p><h2>Bias controls and review</h2><p>The process distinguishes source volume from severity, assesses information-environment bias, and preserves contrary evidence. Independent review checks evidence answers before judging; a separate review checks chapter scores and ordering before publication.</p></section>'''
    return _page("Methodology", content)


def _questions(site: StudySiteProjection) -> str:
    exemplar = site.rulers[0]
    sections = []
    for chapter in exemplar.chapters:
        rows = "".join(f'<li><b>{item.question_id}</b> {_e(item.question)}</li>' for item in chapter.questions)
        sections.append(f'<section><h2>{chapter.chapter_id} · {_e(chapter.title)}</h2><ol class="question-list">{rows}</ol></section>')
    return _page("Research framework", '<header class="hero"><p class="eyebrow">Research framework</p><h1>Eight chapters, 80 evidence questions</h1><p class="lede">Each set of ten questions is used to assemble one chapter judgment.</p></header>' + "".join(sections))


def _pipeline(site: StudySiteProjection) -> str:
    stages = [
        ("Identity", "Resolve and lock the formal ruler and target period."),
        ("Discovery", "Search chapter by chapter and preserve the complete candidate catalogue."),
        ("Acquisition", "Disposition every candidate and retain every lawful readable document."),
        ("Corpus reading", "Read every queued document and verify code-bound passages."),
        ("Question answers", "Answer all 80 lenses from the verified evidence ledger."),
        ("Independent review", "Review factual support, balance, period fit, and completeness; repair material gaps."),
        ("Ruler approval", "Bind approved answers, evidence, reading coverage, and hashes."),
        ("Comparative judging", "Assign one calibrated score, confidence, and range per chapter."),
        ("Audit and publication", "Review scores and ordering, preserve flags, and publish only an allowed package."),
    ]
    flow = "".join(f'<li><span>{index}</span><div><h2>{title}</h2><p>{text}</p></div></li>' for index, (title, text) in enumerate(stages, 1))
    return _page("Research pipeline", f'<header class="hero"><p class="eyebrow">Pipeline · {_e(site.pipeline_version_id)}</p><h1>From ruler identity to cited publication</h1></header><ol class="pipeline">{flow}</ol>')


def _sources(project_root: Path, site: StudySiteProjection) -> str:
    attribution = (project_root / "docs/sources/attributions.md").read_text(encoding="utf-8")
    content = f'''<header class="hero"><p class="eyebrow">Sources and limitations</p><h1>What the evidence can establish</h1></header><section><h2>Scope</h2><p>This is a five-ruler 2023 demonstration, not a global ranking. Information environments differ, and source availability does not measure conduct.</p><h2>Stored evidence and publisher links</h2><p>Evidence pages reproduce verified excerpts needed to inspect a claim and link to the publisher. Complete acquired documents remain outside the public site. External pages can move; the stored, hash-bound excerpt preserves what was reviewed.</p><h2>Review flags</h2><p>The audit permitted publication with explicit nonblocking flags for Russia chapter 3B and Israel chapter 7B. Those flags appear beside the affected judgments.</p><h2>Attribution record</h2><pre>{_e(attribution)}</pre></section>'''
    return _page("Sources and limitations", content)


def _run_details(site: StudySiteProjection) -> str:
    totals = sum(len(ruler.evidence) for ruler in site.rulers)
    rows = "".join(f'<tr><th>{_e(ruler.ruler_name)}</th><td>{len(ruler.evidence):,}</td><td>{len(_by_source(ruler)):,}</td></tr>' for ruler in site.rulers)
    content = f'''<header class="hero"><p class="eyebrow">Run details</p><h1>{_e(site.run_id)}</h1><p class="lede">Audit: {_e(site.audit_decision)}</p></header><section><dl><dt>Pipeline</dt><dd>{_e(site.pipeline_version_id)}</dd><dt>Methodology</dt><dd>{_e(site.methodology_version_id)}</dd><dt>Publicly cited evidence records</dt><dd>{totals:,}</dd></dl><table><thead><tr><th>Ruler</th><th>Cited records</th><th>Cited sources</th></tr></thead><tbody>{rows}</tbody></table><p>Operational prompts, event logs, full acquired documents, and internal filesystem paths are excluded from this public projection.</p></section>'''
    return _page("Run details", content)


def _page(title: str, content: str) -> str:
    nav = f'''<nav><a class="brand" href="{BASE}/">Leaders Database</a><div><a href="{BASE}/">Results</a><a href="{BASE}/methodology/">Methodology</a><a href="{BASE}/questions/">Questions</a><a href="{BASE}/pipeline/">Pipeline</a><a href="{BASE}/sources/">Sources</a></div></nav>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(title)} · Leaders Database</title><link rel="stylesheet" href="{BASE}/assets/site.css"><script src="{BASE}/assets/site.js" defer></script></head><body>{nav}<main>{content}</main><footer><a href="{BASE}/run-details/">Run details</a><span>2023 five-ruler demonstration</span></footer></body></html>'''


def _by_source(ruler: PublicRuler) -> dict[str, list[PublicEvidence]]:
    result: defaultdict[str, list[PublicEvidence]] = defaultdict(list)
    for item in ruler.evidence:
        result[item.source_id].append(item)
    for source_id, records in result.items():
        metadata = {(item.url, item.title, item.publisher, item.raw_sha256) for item in records}
        if len(metadata) != 1:
            raise ValueError(f"conflicting source metadata for {source_id}")
    return dict(sorted(result.items()))


def _uses(ruler: PublicRuler, evidence_id: str) -> list[str]:
    return [question.question_id for chapter in ruler.chapters for question in chapter.questions if evidence_id in question.supporting_evidence_ids + question.qualifying_evidence_ids]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _e(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def _paras(value: str) -> str:
    return "".join(f"<p>{_e(item)}</p>" for item in value.split("\n") if item.strip())


def _css() -> str:
    return """@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=Source+Serif+4:opsz,wght@8..60,500;8..60,650&display=swap');
:root{--ink:#192421;--muted:#5d6965;--paper:#f4f1e9;--card:#fff;--line:#d9ded9;--green:#184f44;--soft:#e7efeb;--warn:#fff3d8}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'DM Sans',sans-serif}a{color:#075e70}nav{display:flex;justify-content:space-between;gap:24px;align-items:center;padding:18px max(24px,calc((100% - 1240px)/2));background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}nav div{display:flex;gap:18px;flex-wrap:wrap}.brand{font:650 22px 'Source Serif 4',serif;color:var(--ink);text-decoration:none}main{max-width:1240px;margin:auto;padding:42px 24px 80px}.hero{max-width:900px;margin-bottom:42px}h1,h2,h3{font-family:'Source Serif 4',serif;line-height:1.15}h1{font-size:clamp(40px,7vw,72px);margin:.15em 0}h2{font-size:32px}.eyebrow{text-transform:uppercase;letter-spacing:.1em;font-size:12px;color:var(--muted)}.lede{font:500 20px/1.5 'Source Serif 4',serif;color:#3b4844}.table-wrap{overflow:auto;background:#fff;border:1px solid var(--line)}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}td a,th a{text-decoration:none}small{display:block;color:var(--muted);font-weight:400}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:28px}.cards a{display:grid;gap:8px;padding:24px;background:var(--card);border:1px solid var(--line);text-decoration:none}.cards b{font:650 24px 'Source Serif 4',serif}.cards span{color:var(--muted)}.chapter,.question{background:#fff;border:1px solid var(--line);margin:14px 0}.chapter>summary,.question>summary{cursor:pointer;display:flex;gap:18px;align-items:start;padding:20px}.chapter>summary b{font:650 23px 'Source Serif 4',serif}.chapter-code{background:var(--green);color:#fff;padding:5px 8px}.chapter-body,.question-body{padding:0 24px 28px}.question>summary span{font-weight:700;color:var(--green)}.answer{font:500 17px/1.6 'Source Serif 4',serif}.judgment-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.judgment-grid>div{background:var(--soft);padding:18px}.citation{border-left:4px solid var(--green);padding:10px 14px;background:#f5f7f5;margin:10px 0}.citation p{margin:.4em 0;color:var(--muted)}.notice{background:var(--warn);padding:14px;border:1px solid #e9cf92}.source-evidence{background:#fff;border:1px solid var(--line);padding:28px;margin:24px 0;scroll-margin-top:90px}.source-evidence blockquote{font:500 17px/1.6 'Source Serif 4',serif;border-left:4px solid var(--green);margin:20px 0;padding:12px 20px;background:#f6f6f2;white-space:pre-wrap}.source-evidence dl,section dl{display:grid;grid-template-columns:180px 1fr;gap:8px 16px}.source-evidence dt,section dt{font-weight:700}.source-evidence dd,section dd{margin:0}.button,button{display:inline-block;padding:9px 14px;border:1px solid var(--green);background:white;color:var(--green);cursor:pointer;text-decoration:none}.actions{display:flex;gap:10px}.question-list li{margin:12px 0}.pipeline{list-style:none;padding:0}.pipeline li{display:grid;grid-template-columns:48px 1fr;gap:18px;margin:14px 0;background:#fff;padding:20px;border:1px solid var(--line)}.pipeline li>span{background:var(--green);color:#fff;width:38px;height:38px;display:grid;place-items:center;border-radius:50%}.pipeline h2{margin:0;font-size:24px}pre{white-space:pre-wrap;background:#fff;padding:20px;border:1px solid var(--line);max-height:700px;overflow:auto}footer{padding:28px max(24px,calc((100% - 1240px)/2));background:var(--green);color:#fff;display:flex;justify-content:space-between}footer a{color:#fff}@media(max-width:800px){nav{align-items:flex-start;position:static}nav div{display:none}.cards,.judgment-grid{grid-template-columns:1fr}.source-evidence dl,section dl{grid-template-columns:1fr}.hero{margin-bottom:24px}main{padding-top:24px}}@media print{nav,.actions,footer{display:none}body{background:#fff}.chapter,.question{break-inside:avoid}}"""


def _js() -> str:
    return """document.addEventListener('DOMContentLoaded',()=>{const hash=location.hash.slice(1);if(hash){let node=document.getElementById(hash);while(node){if(node.tagName==='DETAILS')node.open=true;node=node.parentElement}}document.querySelectorAll('[data-expand]').forEach(button=>button.addEventListener('click',()=>{const open=button.dataset.expand==='all';document.querySelectorAll('details').forEach(item=>{item.open=open})}))});"""


__all__ = ["build_study_site"]
