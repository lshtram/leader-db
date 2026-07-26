"""Freeze and acquire the matched AMLO 5B long-document reader experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pdfplumber
import requests

from leaders_db.conversational_evidence.document_reader_experiment import (
    DocumentPackItem,
    estimate_tokens,
    load_document_reader_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = (
    PROJECT_ROOT
    / "research/conversational-evidence/amlo-2022-5b-manual-deep-research-v1"
    / "accessible-source-universe.md"
)
USER_AGENT = "leaders-db-research-document-acquisition/0.1"
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
ROW_PATTERN = re.compile(r"^\| ([A-Z]+-[0-9]{3}) \|")


class _BlockParser(HTMLParser):
    """Extract visible text blocks without executing page scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "blockquote"}:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "h4", "tr", "blockquote"}:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        value = " ".join(" ".join(self._parts).split())
        if value:
            self.blocks.append(value)
        self._parts = []


def main() -> None:
    """Acquire the accessible matched pack and freeze all scientific inputs."""

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("access_audit", type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-bytes", type=int, default=100_000_000)
    parser.add_argument("--reuse-frozen-from", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_document_reader_config()
    catalog = parse_catalog(args.catalog)
    access = load_access_audit(args.access_audit)
    resolved = resolve_pack(config.document_pack, config.fallbacks, catalog, access)

    frozen_dir = output_dir / "frozen"
    raw_dir = frozen_dir / "raw"
    extracted_dir = frozen_dir / "extracted"
    raw_dir.mkdir(parents=True)
    extracted_dir.mkdir()
    acquired: list[dict[str, Any]] = []
    reuse_manifest = (
        _read_json(args.reuse_frozen_from / "manifest.json")
        if args.reuse_frozen_from is not None
        else None
    )
    for requested_item, selected_id in resolved:
        source = catalog[selected_id]
        record = (
            reuse_source(
                args.reuse_frozen_from,
                reuse_manifest,
                requested_item.source_id,
                selected_id,
                raw_dir=raw_dir,
                extracted_dir=extracted_dir,
            )
            if args.reuse_frozen_from is not None and reuse_manifest is not None
            else acquire_source(
                selected_id,
                source,
                raw_dir=raw_dir,
                extracted_dir=extracted_dir,
                timeout=args.timeout,
                max_bytes=args.max_bytes,
            )
        )
        record.update(
            {
                "requested_source_id": requested_item.source_id,
                "document_type": requested_item.document_type,
                "source_role": requested_item.source_role,
            }
        )
        acquired.append(record)

    files_to_freeze = (
        args.catalog,
        args.access_audit,
        PROJECT_ROOT
        / "src/leaders_db/conversational_evidence/data/document_reader_experiment.json",
        PROJECT_ROOT / "src/leaders_db/conversational_evidence/data/questions.json",
        PROJECT_ROOT / "docs/methodology/chapter-guides/5b-economic-wellbeing.md",
        PROJECT_ROOT / "configs/research-models.yaml",
        PROJECT_ROOT / "configs/research-pricing.yaml",
        PROJECT_ROOT / ".agents/skills/ruler-evidence-researcher/SKILL.md",
    )
    frozen_inputs: dict[str, str] = {}
    for source_path in files_to_freeze:
        target = frozen_dir / source_path.name
        target.write_bytes(source_path.read_bytes())
        frozen_inputs[target.name] = _sha256_bytes(target.read_bytes())

    manifest = {
        "schema_version": "document_reader_ab_manifest_v1",
        "status": "frozen_acquired_execution_pending",
        "case": {
            "ruler": "Andrés Manuel López Obrador",
            "country": "Mexico",
            "iso3": "MEX",
            "period": [2022, 2022],
            "chapter_id": config.chapter_id,
        },
        "experiment_version": config.version,
        "reader_arms": {
            "A": config.baseline_reader,
            "B_primary": config.reader_ladder[0],
            "B_fallback": list(config.reader_ladder[1:]),
            "normalizer": config.normalizer,
            "compiler": config.compiler,
            "format_errors_are_quality_failures": False,
        },
        "acquired_documents": acquired,
        "frozen_inputs": frozen_inputs,
        "repository": {
            "commit": _git(["rev-parse", "HEAD"]).strip(),
            "dirty_status_sha256": _sha256_text(_git(["status", "--porcelain=v1"])),
        },
    }
    _write_json(output_dir / "manifest.json", manifest)
    for arm in ("arm-a-sol", "arm-b-minimax", "arm-b-luna-fallback"):
        (output_dir / arm / "maps").mkdir(parents=True)
    for order in ("forward", "reverse"):
        (output_dir / "evaluation" / order).mkdir(parents=True)
    write_checksums(output_dir)


def parse_catalog(path: Path) -> dict[str, dict[str, str]]:
    """Read stable source IDs and URLs from the discovery catalog."""

    records: dict[str, dict[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = ROW_PATTERN.match(line)
        link = LINK_PATTERN.search(line)
        if row and link:
            records[row.group(1)] = {"title": link.group(1), "url": link.group(2)}
    return records


def load_access_audit(path: Path) -> dict[str, dict[str, object]]:
    """Load the latest observation for each stable source ID."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(item["source_id"]): item for item in payload["records"]}


def resolve_pack(
    pack: tuple[DocumentPackItem, ...],
    fallbacks: dict[str, tuple[str, ...]],
    catalog: dict[str, dict[str, str]],
    access: dict[str, dict[str, object]],
) -> tuple[tuple[DocumentPackItem, str], ...]:
    """Resolve inaccessible items only through the frozen same-role fallback list."""

    resolved: list[tuple[DocumentPackItem, str]] = []
    used: set[str] = set()
    for item in pack:
        choices = (item.source_id, *fallbacks.get(item.source_id, ()))
        selected = next(
            (
                source_id
                for source_id in choices
                if source_id in catalog
                and access.get(source_id, {}).get("state") == "open_machine_readable"
                and source_id not in used
            ),
            None,
        )
        if selected is None:
            states = {source_id: access.get(source_id, {}).get("state") for source_id in choices}
            raise ValueError(f"no machine-readable source for {item.source_id}: {states}")
        used.add(selected)
        resolved.append((item, selected))
    return tuple(resolved)


def acquire_source(
    source_id: str,
    source: dict[str, str],
    *,
    raw_dir: Path,
    extracted_dir: Path,
    timeout: float,
    max_bytes: int,
) -> dict[str, Any]:
    """Download one allowed source and preserve raw and extracted forms."""

    response = requests.get(
        source["url"],
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    content = response.content
    if len(content) > max_bytes:
        raise ValueError(f"{source_id} exceeds configured acquisition size")
    content_type = response.headers.get("Content-Type", "").casefold()
    is_pdf = "application/pdf" in content_type or content.startswith(b"%PDF")
    suffix = ".pdf" if is_pdf else ".html"
    raw_path = raw_dir / f"{source_id}{suffix}"
    raw_path.write_bytes(content)
    if is_pdf:
        units = extract_pdf_units(raw_path)
        extraction = "pdfplumber_page_text"
    else:
        units = extract_html_units(content)
        extraction = "stdlib_html_block_text"
    extracted_path = extracted_dir / f"{source_id}.json"
    extracted_payload = {
        "schema_version": "document_extraction_v1",
        "source_id": source_id,
        "title": source["title"],
        "requested_url": source["url"],
        "final_url": response.url,
        "content_type": content_type or "unknown",
        "raw_sha256": _sha256_bytes(content),
        "extraction_method": extraction,
        "units": units,
        "characters_extracted": sum(len(item["text"]) for item in units),
        "estimated_source_tokens": sum(estimate_tokens(item["text"]) for item in units),
    }
    _write_json(extracted_path, extracted_payload)
    return {
        "source_id": source_id,
        "title": source["title"],
        "requested_url": source["url"],
        "final_url": response.url,
        "content_type": content_type or "unknown",
        "raw_path": str(raw_path.relative_to(raw_dir.parent.parent)),
        "raw_sha256": _sha256_bytes(content),
        "raw_bytes": len(content),
        "extracted_path": str(extracted_path.relative_to(raw_dir.parent.parent)),
        "extracted_sha256": _sha256_bytes(extracted_path.read_bytes()),
        "unit_count": len(units),
        "characters_extracted": extracted_payload["characters_extracted"],
        "estimated_source_tokens": extracted_payload["estimated_source_tokens"],
    }


def reuse_source(
    prior_dir: Path,
    prior_manifest: dict[str, Any],
    requested_source_id: str,
    selected_source_id: str,
    *,
    raw_dir: Path,
    extracted_dir: Path,
) -> dict[str, Any]:
    """Reuse an identical hash-verified acquisition from a prior frozen run."""

    prior = next(
        (
            item
            for item in prior_manifest["acquired_documents"]
            if item["requested_source_id"] == requested_source_id
            and item["source_id"] == selected_source_id
        ),
        None,
    )
    if prior is None:
        raise ValueError(f"prior run lacks reusable source {requested_source_id}")
    prior_raw = prior_dir / str(prior["raw_path"])
    prior_extracted = prior_dir / str(prior["extracted_path"])
    if _sha256_bytes(prior_raw.read_bytes()) != prior["raw_sha256"]:
        raise ValueError(f"prior raw checksum failed for {requested_source_id}")
    if _sha256_bytes(prior_extracted.read_bytes()) != prior["extracted_sha256"]:
        raise ValueError(f"prior extraction checksum failed for {requested_source_id}")
    raw_target = raw_dir / prior_raw.name
    extracted_target = extracted_dir / prior_extracted.name
    shutil.copy2(prior_raw, raw_target)
    shutil.copy2(prior_extracted, extracted_target)
    reused = dict(prior)
    reused.update(
        {
            "raw_path": str(raw_target.relative_to(raw_dir.parent.parent)),
            "extracted_path": str(extracted_target.relative_to(raw_dir.parent.parent)),
            "reused_from": str(prior_dir.resolve()),
        }
    )
    return reused


def extract_pdf_units(path: Path) -> list[dict[str, object]]:
    """Extract one locator-preserving unit per PDF page."""

    units: list[dict[str, object]] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            units.append({"unit": page_number, "locator": f"page {page_number}", "text": text})
    return units


def extract_html_units(content: bytes) -> list[dict[str, object]]:
    """Extract and coalesce visible HTML blocks with stable ordinal locators."""

    parser = _BlockParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    parser.close()
    units: list[dict[str, object]] = []
    pending: list[str] = []
    for block in parser.blocks:
        pending.append(block)
        if sum(len(value) for value in pending) >= 1_500:
            units.append(_html_unit(len(units) + 1, pending))
            pending = []
    if pending:
        units.append(_html_unit(len(units) + 1, pending))
    return units


def _html_unit(number: int, blocks: list[str]) -> dict[str, object]:
    return {
        "unit": number,
        "locator": f"extracted HTML block {number}",
        "text": "\n".join(blocks),
    }


def write_checksums(output_dir: Path) -> None:
    """Write deterministic checksums for every frozen or generated input."""

    paths = sorted(
        path for path in output_dir.rglob("*") if path.is_file() and path.name != "checksums.sha256"
    )
    text = "".join(
        f"{_sha256_bytes(path.read_bytes())}  {path.relative_to(output_dir)}\n" for path in paths
    )
    (output_dir / "checksums.sha256").write_text(text, encoding="utf-8")


def _git(arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode())


if __name__ == "__main__":
    main()
