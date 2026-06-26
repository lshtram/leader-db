"""Transform CIRIGHTS country-year rows into normalized observations."""

from __future__ import annotations

import re
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
    CIRIGHTS_ATTRIBUTION_TEXT,
    CIRIGHTS_DEFAULT_VERSION,
    CIRIGHTS_OBSERVATION_FAMILY,
    CIRIGHTS_PROXY_REQUESTED_YEAR,
    CIRIGHTS_PROXY_YEAR,
    CIRIGHTS_SOURCE_KEY,
    CIRIGHTS_TRANSFORM_NAME,
    CIRIGHTS_XLSX_ASSET_ID,
    CIRIGHTS_XLSX_NAME,
)

_UNSAFE_COUNTRY_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)


def emit_cirights_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frame = payload.get("frame")
    specs = payload.get("specs")
    if frame is None or specs is None:
        return iter(())
    requested_data_years = _requested_data_years(request.years)
    raw_lookup: dict[tuple[str, int, str], str] = (
        frame.attrs.get("_cirights_raw_lookup", {}) or {}
    )
    observations: list[NormalizedObservation] = []
    for row in frame.itertuples(index=False):
        country = _text(getattr(row, "country", None))
        year = _coerce_int(getattr(row, "year", None))
        if not country or year is None:
            continue
        if requested_data_years is not None and year not in requested_data_years:
            continue
        if not _country_matches(country, request):
            continue
        for spec in specs:
            value = _coerce_int(getattr(row, spec.variable_name, None))
            if value is None:
                continue
            observations.append(
                _build_observation(
                    request,
                    country=country,
                    year=year,
                    spec=spec,
                    value=value,
                    raw_value=raw_lookup.get((country, year, spec.variable_name), str(value)),
                ),
            )
    return iter(observations)


def _build_observation(
    request: SourceIngestRequest,
    *,
    country: str,
    year: int,
    spec: Any,
    value: int,
    raw_value: str,
) -> NormalizedObservation:
    country_token = _safe_country_token(country) or "unknown"
    row_ref = f"{CIRIGHTS_SOURCE_KEY}:{country_token}:{year}:{spec.raw_column}"
    extension = {
        "source_row_reference": row_ref,
        "raw_value": str(raw_value),
        "normalized_value": float(value),
        "higher_is_better": bool(spec.higher_is_better),
        "raw_scale": spec.raw_scale,
        "normalized_scale_target": spec.normalized_scale_target,
        "cirights_raw_column": spec.raw_column,
        "year_window": [year, year],
        "attribution": CIRIGHTS_ATTRIBUTION_TEXT,
    }
    if (
        request.years
        and CIRIGHTS_PROXY_REQUESTED_YEAR in request.years
        and year == CIRIGHTS_PROXY_YEAR
    ):
        extension.update(
            {
                "requested_year": CIRIGHTS_PROXY_REQUESTED_YEAR,
                "proxy_year": CIRIGHTS_PROXY_YEAR,
                "proxy_year_semantics": "proxy: requested 2023 uses actual CIRIGHTS 2022 data",
            },
        )
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=f"{CIRIGHTS_SOURCE_KEY}:{country_token}:{year}:{spec.variable_name}",
        observation_family=CIRIGHTS_OBSERVATION_FAMILY,
        indicator_code=spec.variable_name,
        value=value,
        value_type="numeric",
        year=year,
        country_code=None,
        country_name=country,
        leader_id=None,
        leader_name=None,
        unit=spec.unit,
        scale=spec.raw_scale,
        source_version=CIRIGHTS_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=CIRIGHTS_XLSX_ASSET_ID,
            path=str(request.raw_root / CIRIGHTS_SOURCE_KEY / CIRIGHTS_XLSX_NAME),
            sheet="Sheet1",
            # The legacy parser does not preserve true worksheet row numbers after
            # year/country filtering. Do not synthesize one from dataframe order.
            row_number=None,
            column_name=spec.raw_column,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=CIRIGHTS_TRANSFORM_NAME,
            catalog_key=CIRIGHTS_SOURCE_KEY,
            rule_id=row_ref,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _requested_data_years(years: tuple[int, ...] | None) -> set[int] | None:
    from ._constants import CIRIGHTS_COVERAGE_END_YEAR, CIRIGHTS_COVERAGE_START_YEAR

    if years is None:
        return None
    data_years = set()
    for year in years:
        year_int = CIRIGHTS_PROXY_YEAR if year == CIRIGHTS_PROXY_REQUESTED_YEAR else int(year)
        if CIRIGHTS_COVERAGE_START_YEAR <= year_int <= CIRIGHTS_COVERAGE_END_YEAR:
            data_years.add(year_int)
    return data_years


def _country_matches(country: str, request: SourceIngestRequest) -> bool:
    if not request.countries:
        return True
    needles = {item.strip().casefold() for item in request.countries if item.strip()}
    return country.casefold() in needles


def _safe_country_token(country: str) -> str:
    if not country:
        return ""
    return _UNSAFE_COUNTRY_TOKEN_RE.sub("_", str(country)).strip("_")


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
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["emit_cirights_observations"]
