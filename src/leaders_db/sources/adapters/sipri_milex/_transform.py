"""Transform SIPRI Milex rows into normalized observations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from leaders_db.sources.contracts import (
    JsonScalar,
    NormalizedObservation,
    RawLocator,
    RawReadResult,
    SourceIngestRequest,
    TransformLocator,
)

from ._constants import (
    SIPRI_MILEX_ATTRIBUTION_TEXT,
    SIPRI_MILEX_DEFAULT_VERSION,
    SIPRI_MILEX_OBSERVATION_FAMILY,
    SIPRI_MILEX_SOURCE_KEY,
    SIPRI_MILEX_TRANSFORM_NAME,
    SIPRI_MILEX_XLSX_ASSET_ID,
    SIPRI_MILEX_XLSX_NAME,
)


def emit_sipri_milex_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frame = payload.get("frame")
    specs = payload.get("specs")
    if frame is None or specs is None:
        return iter(())
    spec_by_variable = {spec.variable_name: spec for spec in specs}
    raw_values = _raw_value_lookup(frame)
    requested_years = set(request.years) if request.years else None
    observations: list[NormalizedObservation] = []
    for row in frame.itertuples(index=False):
        year = _coerce_int(getattr(row, "year", None))
        if year is None or (requested_years is not None and year not in requested_years):
            continue
        country = _text(getattr(row, "country", None))
        if not _country_matches(request, country):
            continue
        source_row_reference = f"{SIPRI_MILEX_SOURCE_KEY}:{country}"
        for variable_name, spec in spec_by_variable.items():
            normalized_value = _json_scalar(getattr(row, variable_name, None))
            if normalized_value is None:
                continue
            raw_value = raw_values.get((country, year, variable_name), normalized_value)
            observations.append(
                _build_observation(
                    request,
                    country=country,
                    year=year,
                    variable_name=variable_name,
                    raw_value=raw_value,
                    normalized_value=normalized_value,
                    source_row_reference=source_row_reference,
                    spec=spec,
                    regions_covered=tuple(frame.attrs.get("regions_covered") or ()),
                    country_count=_coerce_int(frame.attrs.get("country_count")),
                ),
            )
    return iter(observations)


def _build_observation(
    request: SourceIngestRequest,
    *,
    country: str,
    year: int,
    variable_name: str,
    raw_value: Any,
    normalized_value: JsonScalar,
    source_row_reference: str,
    spec: Any,
    regions_covered: tuple[str, ...],
    country_count: int | None,
) -> NormalizedObservation:
    raw_scalar = _json_scalar(raw_value)
    extension = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_scalar,
        "normalized_value": normalized_value,
        "sipri_milex_country": country,
        "sipri_milex_year": year,
        "sipri_milex_raw_sheet": getattr(spec, "raw_column", None),
        "higher_is_better": bool(getattr(spec, "higher_is_better", False)),
        "raw_scale": getattr(spec, "raw_scale", None),
        "normalized_scale_target": getattr(spec, "normalized_scale_target", None),
        "regions_covered": list(regions_covered),
        "country_count": country_count,
        "attribution": SIPRI_MILEX_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=f"{source_row_reference}:{year}:{variable_name}",
        observation_family=SIPRI_MILEX_OBSERVATION_FAMILY,
        indicator_code=variable_name,
        value=normalized_value,
        value_type="numeric",
        year=year,
        country_code=None,
        country_name=country,
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", None),
        scale=getattr(spec, "raw_scale", None),
        source_version=SIPRI_MILEX_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=SIPRI_MILEX_XLSX_ASSET_ID,
            path=str(request.raw_root / SIPRI_MILEX_SOURCE_KEY / SIPRI_MILEX_XLSX_NAME),
            sheet=getattr(spec, "raw_column", None),
            column_name=str(year),
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=SIPRI_MILEX_TRANSFORM_NAME,
            catalog_key=SIPRI_MILEX_SOURCE_KEY,
            rule_id=f"{source_row_reference}:{year}:{variable_name}",
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _raw_value_lookup(frame: Any) -> Mapping[tuple[str, int, str], Any]:
    raw_long = getattr(frame, "attrs", {}).get("_sipri_milex_raw_long")
    if raw_long is None:
        return {}
    values: dict[tuple[str, int, str], Any] = {}
    for row in raw_long.itertuples(index=False):
        country = _text(getattr(row, "country", None))
        year = _coerce_int(getattr(row, "year", None))
        variable_name = _text(getattr(row, "variable_name", None))
        if country and year is not None and variable_name:
            values[(country, year, variable_name)] = getattr(row, "value", None)
    return values


def _country_matches(request: SourceIngestRequest, country: str) -> bool:
    if not request.countries:
        return True
    needles = {item.strip().casefold() for item in request.countries if item.strip()}
    return country.casefold() in needles


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
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _json_scalar(value: Any) -> JsonScalar:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)


__all__ = ["emit_sipri_milex_observations"]
