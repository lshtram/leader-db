"""Offline adapter for the staged UNSD SNAAMA current-USD export."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from leaders_db.sources.contracts import (
    CoverageHint,
    NormalizedObservation,
    RawAsset,
    RawLocator,
    RawReadResult,
    ReadinessResult,
    SourceAdapter,
    SourceDescriptor,
    SourceId,
    SourceIngestRequest,
    SourceWarning,
    TransformLocator,
)

SOURCE_KEY = "un_snaama"
VERSION = "UNdata export 2026-06-19"
ZIP_NAME = "snaama_gdp_expenditure_current_usd.zip"
ATTRIBUTION = "UNSD National Accounts Main Aggregates Database (United Nations 2026)."
HOMEPAGE = "https://unstats.un.org/unsd/snaama/"
EXPECTED_COLUMNS = ("Country or Area", "Year", "Item", "Value")
ITEM_INDICATORS = {
    "Gross Domestic Product (GDP)": "un_snaama_gdp_current_usd",
    "Final consumption expenditure": "un_snaama_final_consumption_current_usd",
    "Household consumption expenditure (including Non-profit institutions serving households)": (
        "un_snaama_household_consumption_current_usd"
    ),
    "General government final consumption expenditure": (
        "un_snaama_government_consumption_current_usd"
    ),
    "Gross capital formation": "un_snaama_gross_capital_formation_current_usd",
    "Gross fixed capital formation (including Acquisitions less disposals of valuables)": (
        "un_snaama_gross_fixed_capital_formation_current_usd"
    ),
}


def build_un_snaama_descriptor() -> SourceDescriptor:
    return SourceDescriptor(
        source_id=SourceId(slug=SOURCE_KEY),
        display_name="UNSD National Accounts Main Aggregates Database",
        source_type="dataset",
        supported_observation_families=("economic_country_year",),
        default_version=VERSION,
        homepage_url=HOMEPAGE,
        attribution_key=SOURCE_KEY,
        coverage_hint=CoverageHint(
            start_year=1970,
            end_year=2024,
            notes="Current-price US-dollar GDP and expenditure components; revisions apply.",
        ),
        requires_network=False,
    )


class UnSnaamaAdapter:
    """Read and normalize the immutable local UNdata CSV archive."""

    descriptor = build_un_snaama_descriptor()

    def check_ready(self, request: SourceIngestRequest) -> ReadinessResult:
        path = _bundle(request) / ZIP_NAME
        metadata_path = _bundle(request) / "metadata.json"
        errors: list[SourceWarning] = []
        metadata = _metadata(metadata_path)
        if not path.is_file():
            errors.append(_error(request, "missing_raw", f"Missing staged archive: {path}"))
        if not metadata:
            errors.append(
                _error(request, "invalid_metadata", f"Missing or invalid {metadata_path}")
            )
        elif metadata.get("source_version") != VERSION:
            errors.append(
                _error(request, "metadata_version_mismatch", "SNAAMA metadata version mismatch")
            )
        elif path.is_file() and _expected_checksum(metadata) != _sha256(path):
            errors.append(_error(request, "checksum_mismatch", "SNAAMA archive checksum mismatch"))
        if request.source_version not in (None, VERSION):
            errors.append(
                _error(request, "unsupported_version", "Unsupported SNAAMA source version")
            )
        warnings: list[SourceWarning] = []
        for year in request.years or ():
            if year < 1970 or year > 2024:
                warnings.append(
                    SourceWarning(
                        code="year_absent",
                        message=f"SNAAMA has no observation year {year}; no proxy is emitted.",
                        source_id=request.source_id,
                        context={"year": year},
                    )
                )
        if request.leaders:
            warnings.append(
                SourceWarning(
                    code="unsupported_filter",
                    message="SNAAMA is country-year data; leader filters are ignored.",
                    source_id=request.source_id,
                )
            )
        return ReadinessResult(ready=not errors, warnings=tuple(warnings), errors=tuple(errors))

    def read_raw(self, request: SourceIngestRequest) -> RawReadResult:
        path = _bundle(request) / ZIP_NAME
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(members) != 1:
                raise ValueError(f"Expected one CSV in {path}; found {len(members)}")
            with archive.open(members[0]) as handle:
                frame = pd.read_csv(handle)
        missing = sorted(set(EXPECTED_COLUMNS).difference(frame.columns))
        if missing:
            raise ValueError(f"SNAAMA CSV is missing columns: {missing}")
        return RawReadResult(
            source_id=request.source_id,
            assets=(
                RawAsset(
                    asset_id=f"{SOURCE_KEY}:{ZIP_NAME}",
                    source_id=request.source_id,
                    version=VERSION,
                    media_type="application/zip",
                    path=path,
                    url="https://data.un.org/Data.aspx?d=SNAAMA",
                    checksum_sha256=_sha256(path),
                ),
            ),
            payload={"frame": frame, "path": path, "member": members[0]},
        )

    def transform(
        self, request: SourceIngestRequest, raw: RawReadResult
    ) -> Iterable[NormalizedObservation]:
        if not isinstance(raw.payload, dict) or not isinstance(
            raw.payload.get("frame"), pd.DataFrame
        ):
            raise TypeError("UnSnaamaAdapter requires a DataFrame raw payload")
        frame = raw.payload["frame"]
        frame = frame.loc[frame["Item"].isin(ITEM_INDICATORS)]
        if request.years:
            frame = frame.loc[frame["Year"].astype(int).isin(request.years)]
        if request.countries:
            wanted = {value.casefold().strip() for value in request.countries}
            frame = frame.loc[frame["Country or Area"].str.casefold().isin(wanted)]
        return iter(_emit_rows(frame, request, raw.payload["path"], raw.payload["member"]))


def _emit_rows(
    frame: pd.DataFrame, request: SourceIngestRequest, path: Path, member: str
) -> list[NormalizedObservation]:
    observations: list[NormalizedObservation] = []
    for index, row in frame.iterrows():
        country = str(row["Country or Area"])
        year = int(row["Year"])
        item = str(row["Item"])
        indicator = ITEM_INDICATORS[item]
        observations.append(
            NormalizedObservation(
                source_id=request.source_id,
                observation_id=f"{SOURCE_KEY}:{country}:{year}:{indicator}",
                observation_family="economic_country_year",
                indicator_code=indicator,
                value=float(row["Value"]),
                value_type="numeric",
                year=year,
                country_code=None,
                country_name=country,
                leader_id=None,
                leader_name=None,
                unit="current_usd",
                scale="total",
                source_version=VERSION,
                raw_locator=RawLocator(
                    asset_id=f"{SOURCE_KEY}:{ZIP_NAME}",
                    path=str(path),
                    sheet=member,
                    row_number=int(index) + 2,
                    column_name="Value",
                ),
                transform_locator=TransformLocator(
                    transform_name="un_snaama_current_usd_v1",
                    catalog_key=SOURCE_KEY,
                    rule_id=item,
                ),
                quality_flags=("current_prices", "market_exchange_rate_usd"),
                extension={
                    "attribution": ATTRIBUTION,
                    "source_item": item,
                    "interpretation_warning": (
                        "Current-price US dollars mix real change, inflation, and exchange-rate "
                        "change; they are not a real-growth measure. Revisions and UNSD "
                        "estimates may apply."
                    ),
                    "higher_is_better": None,
                },
            )
        )
    return observations


def _bundle(request: SourceIngestRequest) -> Path:
    return Path(request.raw_root) / SOURCE_KEY


def _metadata(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _expected_checksum(metadata: dict[str, Any]) -> str | None:
    checksums = metadata.get("checksum_sha256")
    return checksums.get(ZIP_NAME) if isinstance(checksums, dict) else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _error(request: SourceIngestRequest, code: str, message: str) -> SourceWarning:
    return SourceWarning(code=code, message=message, severity="error", source_id=request.source_id)


def create_un_snaama_adapter() -> UnSnaamaAdapter:
    return UnSnaamaAdapter()


def register_un_snaama(registry: Any) -> UnSnaamaAdapter:
    adapter = create_un_snaama_adapter()
    registry.register(adapter)
    return adapter


if not isinstance(UnSnaamaAdapter(), SourceAdapter):
    raise TypeError("UnSnaamaAdapter does not satisfy SourceAdapter")


__all__ = [
    "ATTRIBUTION",
    "ITEM_INDICATORS",
    "SOURCE_KEY",
    "VERSION",
    "UnSnaamaAdapter",
    "build_un_snaama_descriptor",
    "create_un_snaama_adapter",
    "register_un_snaama",
]
