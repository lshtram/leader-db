"""Clean source adapter for staged EIU Democracy Index PDF reports."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawAsset,
    RawLocator,
    RawReadResult,
    ReadinessResult,
    SourceDescriptor,
    SourceIngestRequest,
    SourceWarning,
    TransformLocator,
)
from leaders_db.sources.registry import SourceRegistry
from leaders_db.sources.warnings import MISSING_METADATA, MISSING_RAW, UNSUPPORTED_FILTER

from ._constants import (
    EIU_DEMOCRACY_INDEX_ADAPTER_VERSION,
    EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT,
    EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH,
    EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
    EIU_DEMOCRACY_INDEX_INDICATORS,
    EIU_DEMOCRACY_INDEX_LOCAL_FILES_INVALID,
    EIU_DEMOCRACY_INDEX_METADATA_NAME,
    EIU_DEMOCRACY_INDEX_METADATA_VERSION_MISMATCH,
    EIU_DEMOCRACY_INDEX_MISSING_REQUESTED_PDF,
    EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,
    EIU_DEMOCRACY_INDEX_PDF_PATTERN,
    EIU_DEMOCRACY_INDEX_PDF_TEXT_UNAVAILABLE,
    EIU_DEMOCRACY_INDEX_SOURCE_KEY,
    EIU_DEMOCRACY_INDEX_UNSUPPORTED_VERSION,
)
from ._descriptor import build_eiu_democracy_index_descriptor
from ._parser import EiuDemocracyIndexRow, parse_eiu_democracy_index_rows


@dataclass(frozen=True)
class EiuDemocracyIndexTextPage:
    """Extracted text for one PDF page."""

    year: int
    path: Path
    page_number: int
    text: str
    source_url: str | None = None


class EiuDemocracyIndexAdapter:
    """Unified-source adapter for local EIU Democracy Index PDFs."""

    descriptor: SourceDescriptor = build_eiu_democracy_index_descriptor()

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult:
        bundle_dir = _bundle_dir(request)
        metadata_path = bundle_dir / EIU_DEMOCRACY_INDEX_METADATA_NAME
        if not metadata_path.is_file():
            return _not_ready(
                request,
                MISSING_METADATA,
                f"EIU Democracy Index metadata.json is missing at {metadata_path}",
            )
        payload = _read_metadata(metadata_path)
        version_error = _version_error(request, payload)
        if version_error is not None:
            return _not_ready(request, version_error[0], version_error[1])
        local_files = payload.get("local_files")
        if not isinstance(local_files, list) or not all(
            isinstance(item, str) for item in local_files
        ):
            return _not_ready(
                request,
                EIU_DEMOCRACY_INDEX_LOCAL_FILES_INVALID,
                "EIU Democracy Index metadata local_files must be a list of PDF names",
            )
        missing_listed = [name for name in local_files if not (bundle_dir / name).is_file()]
        if missing_listed:
            return _not_ready(
                request,
                MISSING_RAW,
                "EIU Democracy Index metadata lists missing local PDFs",
                context={"missing_files": tuple(missing_listed)},
            )
        requested_missing = [
            year
            for year in _requested_years(request, local_files)
            if year not in _years_from_files(local_files)
        ]
        blocking_error: tuple[str, str, Mapping[str, Any]] | None = None
        if requested_missing:
            blocking_error = (
                EIU_DEMOCRACY_INDEX_MISSING_REQUESTED_PDF,
                "EIU Democracy Index requested year has no staged local PDF",
                {"missing_years": tuple(requested_missing)},
            )
        else:
            blocking_error = _checksum_error(request, bundle_dir, payload, local_files)
        if blocking_error is not None:
            return _not_ready(
                request,
                blocking_error[0],
                blocking_error[1],
                context=blocking_error[2],
            )
        warnings: list[SourceWarning] = []
        if request.leaders:
            warnings.append(
                SourceWarning(
                    code=UNSUPPORTED_FILTER,
                    message=(
                        "EIU Democracy Index is country-year evidence and does not "
                        "support leaders= filters"
                    ),
                    source_id=request.source_id,
                    context={"leaders": request.leaders},
                ),
            )
        return ReadinessResult(ready=True, warnings=tuple(warnings))

    def read_raw(self, request: SourceIngestRequest) -> RawReadResult:
        bundle_dir = _bundle_dir(request)
        payload = _read_metadata(bundle_dir / EIU_DEMOCRACY_INDEX_METADATA_NAME)
        local_files = tuple(str(name) for name in payload.get("local_files", ()))
        years = _requested_years(request, local_files)
        pages: list[EiuDemocracyIndexTextPage] = []
        assets: list[RawAsset] = []
        warnings: list[SourceWarning] = []
        for year in years:
            pdf_path = bundle_dir / EIU_DEMOCRACY_INDEX_PDF_PATTERN.format(year=year)
            checksum = _sha256(pdf_path)
            source_url = _source_url(payload, year)
            assets.append(
                RawAsset(
                    asset_id=_asset_id(year),
                    source_id=request.source_id,
                    version=str(
                        payload.get("source_version") or EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
                    ),
                    media_type="application/pdf",
                    path=pdf_path,
                    url=source_url,
                    checksum_sha256=checksum,
                ),
            )
            extracted_pages = _extract_pdf_text(pdf_path, year=year, source_url=source_url)
            if not extracted_pages:
                warnings.append(
                    SourceWarning(
                        code=EIU_DEMOCRACY_INDEX_PDF_TEXT_UNAVAILABLE,
                        message="No extractable text found in EIU Democracy Index PDF",
                        source_id=request.source_id,
                        context={"year": year, "path": str(pdf_path)},
                    ),
                )
            pages.extend(extracted_pages)
        return RawReadResult(
            source_id=request.source_id,
            assets=tuple(assets),
            payload={"metadata": payload, "pages": tuple(pages)},
            warnings=tuple(warnings),
        )

    def transform(
        self,
        request: SourceIngestRequest,
        raw: RawReadResult,
    ) -> Iterable[NormalizedObservation]:
        payload = raw.payload if isinstance(raw.payload, Mapping) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        pages = payload.get("pages", ())
        source_version = str(metadata.get("source_version") or EIU_DEMOCRACY_INDEX_DEFAULT_VERSION)
        seen: set[tuple[int, str, str]] = set()
        for page in pages:
            if not isinstance(page, EiuDemocracyIndexTextPage):
                continue
            for row in parse_eiu_democracy_index_rows(page.text, page_number=page.page_number):
                if request.countries and row.country_name.casefold() not in {
                    country.casefold() for country in request.countries
                }:
                    continue
                for indicator_code, value, value_type, raw_value in _row_values(row):
                    if value is None:
                        continue
                    key = (page.year, row.country_name.casefold(), indicator_code)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield NormalizedObservation(
                        source_id=request.source_id,
                        observation_id=_observation_id(page.year, row.country_name, indicator_code),
                        observation_family=EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,
                        indicator_code=indicator_code,
                        value=value,
                        value_type=value_type,
                        year=page.year,
                        country_code=None,
                        country_name=row.country_name,
                        leader_id=None,
                        leader_name=None,
                        unit=_unit_for_indicator(indicator_code, value_type),
                        scale="0-10" if _is_score_indicator(indicator_code) else None,
                        source_version=source_version,
                        raw_locator=RawLocator(
                            asset_id=_asset_id(page.year),
                            path=str(page.path),
                            url=page.source_url,
                            page_number=page.page_number,
                            column_name=indicator_code,
                        ),
                        transform_locator=TransformLocator(
                            adapter_version=EIU_DEMOCRACY_INDEX_ADAPTER_VERSION,
                            transform_name="parse_eiu_democracy_index_rows",
                            catalog_key=indicator_code,
                        ),
                        extension={
                            "source_key": EIU_DEMOCRACY_INDEX_SOURCE_KEY,
                            "source_native_country_name": row.country_name,
                            "source_year": page.year,
                            "source_url": page.source_url,
                            "raw_value": raw_value,
                            "raw_row_text": row.raw_row_text,
                            "source_row_reference": (
                                f"{EIU_DEMOCRACY_INDEX_SOURCE_KEY}:{page.year}:{row.country_name}"
                            ),
                            "attribution": EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT,
                        },
                    )


def create_eiu_democracy_index_adapter() -> EiuDemocracyIndexAdapter:
    """Create an EIU Democracy Index adapter instance."""
    return EiuDemocracyIndexAdapter()


def register_eiu_democracy_index(registry: SourceRegistry) -> EiuDemocracyIndexAdapter:
    """Register EIU Democracy Index in a source registry."""
    adapter = create_eiu_democracy_index_adapter()
    registry.register(adapter)
    return adapter


def _bundle_dir(request: SourceIngestRequest) -> Path:
    return request.raw_root / EIU_DEMOCRACY_INDEX_SOURCE_KEY


def _not_ready(
    request: SourceIngestRequest,
    code: str,
    message: str,
    *,
    context: Mapping[str, Any] | None = None,
) -> ReadinessResult:
    return ReadinessResult(
        ready=False,
        errors=(
            SourceWarning(
                code=code,
                message=message,
                severity="error",
                source_id=request.source_id,
                context=dict(context or {}),
            ),
        ),
    )


def _read_metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _version_error(
    request: SourceIngestRequest,
    metadata: Mapping[str, Any],
) -> tuple[str, str] | None:
    metadata_version = metadata.get("source_version")
    if metadata_version != EIU_DEMOCRACY_INDEX_DEFAULT_VERSION:
        return (
            EIU_DEMOCRACY_INDEX_METADATA_VERSION_MISMATCH,
            "EIU Democracy Index metadata source_version does not match the adapter default",
        )
    if request.source_version not in (None, EIU_DEMOCRACY_INDEX_DEFAULT_VERSION):
        return (
            EIU_DEMOCRACY_INDEX_UNSUPPORTED_VERSION,
            "EIU Democracy Index requested source_version is unsupported",
        )
    return None


def _years_from_files(local_files: Iterable[str]) -> tuple[int, ...]:
    years: list[int] = []
    prefix = "democracy-index-"
    suffix = ".pdf"
    for name in local_files:
        if name.startswith(prefix) and name.endswith(suffix):
            year_text = name.removeprefix(prefix).removesuffix(suffix)
            if year_text.isdigit():
                years.append(int(year_text))
    return tuple(sorted(set(years)))


def _requested_years(request: SourceIngestRequest, local_files: Iterable[str]) -> tuple[int, ...]:
    if request.years is None:
        return _years_from_files(local_files)
    return tuple(request.years)


def _checksum_error(
    request: SourceIngestRequest,
    bundle_dir: Path,
    metadata: Mapping[str, Any],
    local_files: Iterable[str],
) -> tuple[str, str, Mapping[str, Any]] | None:
    checksums = metadata.get("checksum_sha256")
    if not isinstance(checksums, Mapping):
        return None
    requested_names = tuple(
        EIU_DEMOCRACY_INDEX_PDF_PATTERN.format(year=year)
        for year in _requested_years(request, local_files)
    )
    missing_checksums = [name for name in requested_names if not _checksum_entry(checksums, name)]
    if missing_checksums:
        return (
            EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH,
            "EIU Democracy Index metadata checksum_sha256 map is missing entries for PDFs",
            {"missing_checksum_files": tuple(missing_checksums)},
        )
    for name in requested_names:
        expected_sha = _checksum_entry(checksums, name)
        if expected_sha is None:
            continue
        actual_sha = _sha256(bundle_dir / name)
        if actual_sha.lower() != expected_sha.strip().lower():
            return (
                EIU_DEMOCRACY_INDEX_CHECKSUM_MISMATCH,
                f"EIU Democracy Index PDF checksum mismatch for {name!r}",
                {
                    "file": name,
                    "expected_sha256": expected_sha.strip().lower(),
                    "actual_sha256": actual_sha.lower(),
                },
            )
    return None


def _checksum_entry(checksums: Mapping[str, Any], file_name: str) -> str | None:
    value = checksums.get(file_name)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _extract_pdf_text(
    path: Path,
    *,
    year: int,
    source_url: str | None,
) -> tuple[EiuDemocracyIndexTextPage, ...]:
    pdftotext_pages = _extract_pdf_text_with_pdftotext(
        path,
        year=year,
        source_url=source_url,
    )
    if pdftotext_pages:
        return pdftotext_pages
    return _extract_pdf_text_with_pdfplumber(path, year=year, source_url=source_url)


def _extract_pdf_text_with_pdftotext(
    path: Path,
    *,
    year: int,
    source_url: str | None,
) -> tuple[EiuDemocracyIndexTextPage, ...]:
    if shutil.which("pdftotext") is None:
        return ()
    try:
        completed = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode != 0 or not completed.stdout:
        return ()
    pages: list[EiuDemocracyIndexTextPage] = []
    for index, text in enumerate(completed.stdout.split("\f"), start=1):
        if "Overall" not in text or "Rank" not in text:
            continue
        pages.append(
            EiuDemocracyIndexTextPage(
                year=year,
                path=path,
                page_number=index,
                text=text,
                source_url=source_url,
            ),
        )
    return tuple(pages)


def _extract_pdf_text_with_pdfplumber(
    path: Path,
    *,
    year: int,
    source_url: str | None,
) -> tuple[EiuDemocracyIndexTextPage, ...]:
    import pdfplumber

    pages: list[EiuDemocracyIndexTextPage] = []
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            if "Overall" not in text or "Rank" not in text:
                continue
            pages.append(
                EiuDemocracyIndexTextPage(
                    year=year,
                    path=path,
                    page_number=index,
                    text=text,
                    source_url=source_url,
                ),
            )
    return tuple(pages)


def _row_values(row: EiuDemocracyIndexRow) -> tuple[tuple[str, Any, str, str], ...]:
    return (
        (EIU_DEMOCRACY_INDEX_INDICATORS[0], row.overall_score, "numeric", str(row.overall_score)),
        (EIU_DEMOCRACY_INDEX_INDICATORS[1], row.rank, "numeric", str(row.rank)),
        (EIU_DEMOCRACY_INDEX_INDICATORS[2], row.rank_change, "numeric", str(row.rank_change)),
        (
            EIU_DEMOCRACY_INDEX_INDICATORS[3],
            row.electoral_process_pluralism,
            "numeric",
            str(row.electoral_process_pluralism),
        ),
        (
            EIU_DEMOCRACY_INDEX_INDICATORS[4],
            row.functioning_government,
            "numeric",
            str(row.functioning_government),
        ),
        (
            EIU_DEMOCRACY_INDEX_INDICATORS[5],
            row.political_participation,
            "numeric",
            str(row.political_participation),
        ),
        (
            EIU_DEMOCRACY_INDEX_INDICATORS[6],
            row.political_culture,
            "numeric",
            str(row.political_culture),
        ),
        (
            EIU_DEMOCRACY_INDEX_INDICATORS[7],
            row.civil_liberties,
            "numeric",
            str(row.civil_liberties),
        ),
        (EIU_DEMOCRACY_INDEX_INDICATORS[8], row.regime_type, "categorical", str(row.regime_type)),
    )


def _is_score_indicator(indicator_code: str) -> bool:
    return indicator_code not in {
        "eiu_democracy_index_rank",
        "eiu_democracy_index_rank_change",
        "eiu_democracy_index_regime_type",
    }


def _unit_for_indicator(indicator_code: str, value_type: str) -> str | None:
    if value_type != "numeric":
        return None
    if indicator_code == "eiu_democracy_index_rank":
        return "rank"
    if indicator_code == "eiu_democracy_index_rank_change":
        return "rank_change"
    return "index_score"


def _asset_id(year: int) -> str:
    return f"{EIU_DEMOCRACY_INDEX_SOURCE_KEY}:{EIU_DEMOCRACY_INDEX_PDF_PATTERN.format(year=year)}"


def _observation_id(year: int, country: str, indicator_code: str) -> str:
    normalised_country = "_".join(country.casefold().split())
    return f"{EIU_DEMOCRACY_INDEX_SOURCE_KEY}:{year}:{normalised_country}:{indicator_code}"


def _source_url(metadata: Mapping[str, Any], year: int) -> str | None:
    urls = metadata.get("source_urls")
    if isinstance(urls, Mapping):
        value = urls.get(str(year))
        return str(value) if value is not None else None
    value = metadata.get("source_url")
    return str(value) if value is not None else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "EiuDemocracyIndexAdapter",
    "EiuDemocracyIndexTextPage",
    "create_eiu_democracy_index_adapter",
    "register_eiu_democracy_index",
]
