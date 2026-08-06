"""Resumable lawful acquisition of every source-catalogue candidate."""

from __future__ import annotations

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

import requests
from pydantic import BaseModel, ConfigDict, Field

from .catalog_robots import RobotsPolicyCache
from .source_candidate_catalog import SourceCandidate, read_source_candidate_catalog

_USER_AGENT = "leaders-db-evidence-research/1.0 (+research prototype)"


class CatalogAcquisitionConfig(BaseModel):
    """Operational controls; none of these values cap corpus coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workers: int = Field(default=8, ge=1, le=32)
    timeout_seconds: float = Field(default=25, ge=2, le=120)
    max_source_bytes: int = Field(default=30_000_000, ge=100_000)
    max_transient_attempts: int = Field(default=3, ge=1, le=5)
    respect_robots_txt: bool = True


class AcquisitionRecord(BaseModel):
    """Terminal acquisition disposition for one canonical candidate URL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    requested_url: str
    final_url: str | None = None
    status: Literal[
        "acquired",
        "robots_disallowed",
        "access_blocked",
        "not_found",
        "transient_failure",
        "unsupported_content",
        "too_large",
        "extraction_failed",
    ]
    http_status: int | None = None
    content_type: str | None = None
    elapsed_seconds: float = Field(ge=0)
    raw_bytes: int = Field(default=0, ge=0)
    raw_sha256: str | None = None
    extracted_characters: int = Field(default=0, ge=0)
    estimated_tokens: int = Field(default=0, ge=0)
    unit_count: int = Field(default=0, ge=0)
    raw_path: str | None = None
    extracted_path: str | None = None
    error: str | None = None
    acquisition_attempts: int = Field(default=1, ge=1)


class CatalogAcquisitionManifest(BaseModel):
    """Hash-bound corpus-wide acquisition result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["catalog_acquisition_manifest_v1"] = (
        "catalog_acquisition_manifest_v1"
    )
    catalogue_path: str
    catalogue_sha256: str
    config: CatalogAcquisitionConfig
    started_at_epoch: float
    completed_at_epoch: float
    records: tuple[AcquisitionRecord, ...]


def acquire_catalogue(
    catalogue_path: Path,
    output_dir: Path,
    *,
    config: CatalogAcquisitionConfig,
) -> Path:
    """Acquire or explicitly disposition every canonical catalogue candidate."""

    catalogue = read_source_candidate_catalog(catalogue_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw").mkdir(exist_ok=True)
    (output_dir / "extracted").mkdir(exist_ok=True)
    records_dir = output_dir / "records"
    records_dir.mkdir(exist_ok=True)
    catalogue_hash = sha256(catalogue_path.read_bytes()).hexdigest()
    started = time.time()
    records: dict[str, AcquisitionRecord] = {}
    pending: list[tuple[SourceCandidate, int]] = []
    robots = RobotsPolicyCache(
        user_agent=_USER_AGENT, timeout_seconds=config.timeout_seconds
    )
    for candidate in catalogue.candidates:
        source_id = _source_id(candidate.url)
        recovered = _recover_record(records_dir / f"{source_id}.json", candidate.url)
        if recovered is None:
            pending.append((candidate, 0))
        elif (
            recovered.status == "transient_failure"
            and recovered.acquisition_attempts < config.max_transient_attempts
        ):
            pending.append((candidate, recovered.acquisition_attempts))
        else:
            records[candidate.url] = recovered
    with ThreadPoolExecutor(max_workers=config.workers) as executor:
        futures = {
            executor.submit(
                _acquire_with_retries,
                candidate,
                output_dir,
                config,
                robots,
                prior_attempts,
            ): candidate
            for candidate, prior_attempts in pending
        }
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                record = future.result()
            except Exception as exc:  # isolation boundary: preserve a terminal record
                record = AcquisitionRecord(
                    source_id=_source_id(candidate.url),
                    requested_url=candidate.url,
                    status="extraction_failed",
                    elapsed_seconds=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            _write_json(records_dir / f"{record.source_id}.json", record.model_dump(mode="json"))
            records[candidate.url] = record
    ordered = tuple(records[item.url] for item in catalogue.candidates)
    if len(ordered) != len(catalogue.candidates):
        raise RuntimeError("acquisition did not disposition every catalogue candidate")
    manifest = CatalogAcquisitionManifest(
        catalogue_path=str(catalogue_path.resolve()),
        catalogue_sha256=catalogue_hash,
        config=config,
        started_at_epoch=started,
        completed_at_epoch=time.time(),
        records=ordered,
    )
    path = output_dir / "acquisition-manifest.json"
    _write_json(path, manifest.model_dump(mode="json"))
    return path


def _acquire_with_retries(
    candidate: SourceCandidate,
    output_dir: Path,
    config: CatalogAcquisitionConfig,
    robots: RobotsPolicyCache,
    prior_attempts: int,
) -> AcquisitionRecord:
    attempts = prior_attempts
    while attempts < config.max_transient_attempts:
        attempts += 1
        record = _acquire_one(candidate, output_dir, config, robots).model_copy(
            update={"acquisition_attempts": attempts}
        )
        if record.status != "transient_failure":
            return record
    return record


def _acquire_one(
    candidate: SourceCandidate,
    output_dir: Path,
    config: CatalogAcquisitionConfig,
    robots: RobotsPolicyCache,
) -> AcquisitionRecord:
    started = time.monotonic()
    source_id = _source_id(candidate.url)
    if config.respect_robots_txt and not robots.allowed(candidate.url):
        return _failure(source_id, candidate.url, "robots_disallowed", started)
    downloaded = _download(candidate.url, source_id, started, config)
    if isinstance(downloaded, AcquisitionRecord):
        return downloaded
    response, content = downloaded
    content_type = response.headers.get("Content-Type", "").casefold()
    is_pdf = "application/pdf" in content_type or content.startswith(b"%PDF")
    is_html = "html" in content_type or content.lstrip().startswith((b"<!DOCTYPE", b"<html"))
    if not is_pdf and not is_html:
        return _failure(source_id, candidate.url, "unsupported_content", started, response)
    return _extract_acquired(
        candidate, source_id, response, content, content_type, is_pdf, output_dir, started
    )


def _download(
    url: str,
    source_id: str,
    started: float,
    config: CatalogAcquisitionConfig,
) -> tuple[requests.Response, bytes] | AcquisitionRecord:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=config.timeout_seconds,
            allow_redirects=True,
            stream=True,
        )
        status = response.status_code
        if status in {401, 403, 407, 429, 451}:
            return _failure(source_id, url, "access_blocked", started, response)
        if status in {404, 410}:
            return _failure(source_id, url, "not_found", started, response)
        if status >= 500:
            return _failure(source_id, url, "transient_failure", started, response)
        response.raise_for_status()
        content = _bounded_content(response, config.max_source_bytes)
    except _TooLarge:
        return _failure(source_id, url, "too_large", started)
    except requests.RequestException as exc:
        return _failure(source_id, url, "transient_failure", started, error=str(exc))
    return response, content


def _extract_acquired(
    candidate: SourceCandidate,
    source_id: str,
    response: requests.Response,
    content: bytes,
    content_type: str,
    is_pdf: bool,
    output_dir: Path,
    started: float,
) -> AcquisitionRecord:
    suffix = ".pdf" if is_pdf else ".html"
    raw_path = output_dir / "raw" / f"{source_id}{suffix}"
    raw_path.write_bytes(content)
    try:
        units = _pdf_units(raw_path) if is_pdf else _html_units(content)
    except Exception as exc:
        return _failure(
            source_id, candidate.url, "extraction_failed", started, response, str(exc)
        )
    extracted = {
        "schema_version": "catalog_document_extraction_v1",
        "source_id": source_id,
        "requested_url": candidate.url,
        "final_url": response.url,
        "raw_sha256": sha256(content).hexdigest(),
        "units": units,
    }
    extracted_path = output_dir / "extracted" / f"{source_id}.json"
    _write_json(extracted_path, extracted)
    characters = sum(len(str(unit["text"])) for unit in units)
    return AcquisitionRecord(
        source_id=source_id,
        requested_url=candidate.url,
        final_url=response.url,
        status="acquired",
        http_status=response.status_code,
        content_type=content_type or "unknown",
        elapsed_seconds=time.monotonic() - started,
        raw_bytes=len(content),
        raw_sha256=sha256(content).hexdigest(),
        extracted_characters=characters,
        estimated_tokens=(characters + 3) // 4,
        unit_count=len(units),
        raw_path=str(raw_path.relative_to(output_dir)),
        extracted_path=str(extracted_path.relative_to(output_dir)),
    )


class _TooLarge(Exception):
    pass


def _bounded_content(response: requests.Response, maximum: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=65_536):
        size += len(chunk)
        if size > maximum:
            raise _TooLarge
        chunks.append(chunk)
    return b"".join(chunks)


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hidden = 0
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not self.hidden and text:
            self.blocks.append(text)


def _html_units(content: bytes) -> list[dict[str, object]]:
    parser = _VisibleTextParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    units = []
    for index in range(0, len(parser.blocks), 25):
        number = len(units) + 1
        units.append(
            {
                "unit": number,
                "locator": f"extracted HTML block {number}",
                "text": "\n".join(parser.blocks[index : index + 25]),
            }
        )
    return units


def _pdf_units(path: Path) -> list[dict[str, object]]:
    result = subprocess.run(
        ("pdftotext", "-layout", str(path), "-"),
        capture_output=True,
        check=True,
        timeout=180,
    )
    pages = result.stdout.decode("utf-8", errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return [
        {"unit": number, "locator": f"page {number}", "text": text.strip()}
        for number, text in enumerate(pages, start=1)
    ]


def _failure(
    source_id: str,
    url: str,
    status: str,
    started: float,
    response: requests.Response | None = None,
    error: str | None = None,
) -> AcquisitionRecord:
    return AcquisitionRecord(
        source_id=source_id,
        requested_url=url,
        final_url=response.url if response is not None else None,
        status=status,
        http_status=response.status_code if response is not None else None,
        content_type=response.headers.get("Content-Type") if response is not None else None,
        elapsed_seconds=time.monotonic() - started,
        error=error,
    )


def _source_id(url: str) -> str:
    return f"SRC-{sha256(url.encode()).hexdigest()[:16]}"


def _recover_record(path: Path, expected_url: str) -> AcquisitionRecord | None:
    if not path.is_file():
        return None
    record = AcquisitionRecord.model_validate_json(path.read_text(encoding="utf-8"))
    return record if record.requested_url == expected_url else None


def _write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    with temporary.open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


__all__ = [
    "AcquisitionRecord",
    "CatalogAcquisitionConfig",
    "CatalogAcquisitionManifest",
    "acquire_catalogue",
]
