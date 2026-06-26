"""Transform UNDP HDI country-year rows into normalized observations."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    RawReadResult,
    SourceIngestRequest,
    TransformLocator,
)

from ._constants import (
    UNDP_HDI_ATTRIBUTION_TEXT,
    UNDP_HDI_COVERAGE_END_YEAR,
    UNDP_HDI_COVERAGE_START_YEAR,
    UNDP_HDI_CSV_ASSET_ID,
    UNDP_HDI_CSV_NAME,
    UNDP_HDI_DEFAULT_VERSION,
    UNDP_HDI_OBSERVATION_FAMILY,
    UNDP_HDI_PROXY_REQUESTED_YEAR,
    UNDP_HDI_PROXY_YEAR,
    UNDP_HDI_SOURCE_KEY,
    UNDP_HDI_TRANSFORM_NAME,
)


def emit_undp_hdi_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frame = payload.get("frame")
    specs = payload.get("specs")
    if frame is None or specs is None:
        return iter(())
    spec_by_variable = {spec.variable_name: spec for spec in specs}
    requested_data_years = _requested_data_years(request.years)
    observations: list[NormalizedObservation] = []
    for row in frame.itertuples(index=False):
        iso3 = _text(getattr(row, "iso3", None)).upper()
        country = _text(getattr(row, "country", None))
        year = _coerce_int(getattr(row, "year", None))
        variable_name = _text(getattr(row, "variable_name", None))
        spec = spec_by_variable.get(variable_name)
        if not iso3 or year is None or spec is None:
            continue
        if requested_data_years is not None and year not in requested_data_years:
            continue
        if not _country_matches(iso3, country, request):
            continue
        value = _coerce_float(getattr(row, "raw_value", None))
        if value is None:
            continue
        observations.append(_build_observation(request, row=row, spec=spec, value=value))
    return iter(observations)


def _build_observation(
    request: SourceIngestRequest,
    *,
    row: Any,
    spec: Any,
    value: float,
) -> NormalizedObservation:
    iso3 = _text(getattr(row, "iso3", None)).upper()
    country = _text(getattr(row, "country", None))
    year = int(row.year)
    row_ref = _text(getattr(row, "source_row_reference", None)) or f"{UNDP_HDI_SOURCE_KEY}:{iso3}"
    column_name = f"{spec.raw_column}_{year}"
    rule_id = f"{row_ref}:{year}:{spec.variable_name}"
    extension = {
        "source_row_reference": row_ref,
        "raw_value": _text(getattr(row, "raw_value", None)),
        "normalized_value": value,
        "higher_is_better": bool(spec.higher_is_better),
        "raw_scale": spec.raw_scale,
        "normalized_scale_target": spec.normalized_scale_target,
        "undp_hdi_raw_column": spec.raw_column,
        "region": _text(getattr(row, "region", None)),
        "hdicode": _text(getattr(row, "hdicode", None)),
        "category": spec.category,
        "year_window": [year, year],
        "attribution": UNDP_HDI_ATTRIBUTION_TEXT,
    }
    if (
        request.years
        and UNDP_HDI_PROXY_REQUESTED_YEAR in request.years
        and year == UNDP_HDI_PROXY_YEAR
    ):
        extension.update({
            "requested_year": UNDP_HDI_PROXY_REQUESTED_YEAR,
            "proxy_year": UNDP_HDI_PROXY_YEAR,
            "proxy_year_semantics": "proxy: requested 2023 uses actual UNDP HDI 2022 data",
        })
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=f"{UNDP_HDI_SOURCE_KEY}:{iso3}:{year}:{spec.variable_name}",
        observation_family=UNDP_HDI_OBSERVATION_FAMILY,
        indicator_code=spec.variable_name,
        value=value,
        value_type="numeric",
        year=year,
        country_code=iso3,
        country_name=country,
        leader_id=None,
        leader_name=None,
        unit=spec.unit,
        scale=spec.raw_scale,
        source_version=UNDP_HDI_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=UNDP_HDI_CSV_ASSET_ID,
            path=str(request.raw_root / UNDP_HDI_SOURCE_KEY / UNDP_HDI_CSV_NAME),
            row_number=None,
            column_name=column_name,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=UNDP_HDI_TRANSFORM_NAME,
            catalog_key=UNDP_HDI_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _requested_data_years(years: tuple[int, ...] | None) -> set[int] | None:
    if years is None:
        return None
    data_years = set()
    for year in years:
        year_int = UNDP_HDI_PROXY_YEAR if year == UNDP_HDI_PROXY_REQUESTED_YEAR else int(year)
        if UNDP_HDI_COVERAGE_START_YEAR <= year_int <= UNDP_HDI_COVERAGE_END_YEAR:
            data_years.add(year_int)
    return data_years


def _country_matches(iso3: str, country: str, request: SourceIngestRequest) -> bool:
    if not request.countries:
        return True
    needles = {item.strip().casefold() for item in request.countries if item.strip()}
    return iso3.casefold() in needles or country.casefold() in needles


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except (ImportError, TypeError, ValueError):
        pass
    return str(value).strip()


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


__all__ = ["emit_undp_hdi_observations"]
