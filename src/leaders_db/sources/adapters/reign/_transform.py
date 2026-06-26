"""Transform REIGN long rows into normalized observations."""

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
    REIGN_ATTRIBUTION_TEXT,
    REIGN_CSV_ASSET_ID,
    REIGN_CSV_NAME,
    REIGN_DEFAULT_VERSION,
    REIGN_OBSERVATION_FAMILY,
    REIGN_SOURCE_KEY,
    REIGN_TRANSFORM_NAME,
)


def emit_reign_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frame = payload.get("frame")
    specs = payload.get("specs")
    if frame is None or specs is None:
        return iter(())
    spec_by_variable = {spec.variable_name: spec for spec in specs}
    requested_years = set(request.years) if request.years else None
    observations: list[NormalizedObservation] = []
    for row in frame.itertuples(index=False):
        year = _coerce_int(getattr(row, "year", None))
        if year is None or (requested_years is not None and year not in requested_years):
            continue
        country = _text(getattr(row, "country", None))
        ccode = _coerce_int(getattr(row, "ccode", None))
        if not _country_matches(request, country, ccode):
            continue
        variable_name = _text(getattr(row, "variable_name", None))
        spec = spec_by_variable.get(variable_name)
        if spec is None:
            continue
        observations.append(
            _build_observation(
                request,
                row=row,
                country=country,
                ccode=ccode,
                year=year,
                month=_coerce_int(getattr(row, "month", None)),
                leader_name=_text(getattr(row, "leader", None)),
                variable_name=variable_name,
                spec=spec,
                source_row_reference=_text(getattr(row, "source_row_reference", None)),
            ),
        )
    return iter(observations)


def _build_observation(
    request: SourceIngestRequest,
    *,
    row: Any,
    country: str,
    ccode: int | None,
    year: int,
    month: int | None,
    leader_name: str,
    variable_name: str,
    spec: Any,
    source_row_reference: str,
) -> NormalizedObservation:
    raw_value = _json_scalar(getattr(row, "raw_value", None))
    normalized_value = _json_scalar(getattr(row, "normalized_value", None))
    extension = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "reign_country": country,
        "reign_ccode": ccode,
        "reign_year": year,
        "reign_month": month,
        "reign_leader": leader_name,
        "reign_raw_column": spec.raw_column,
        "higher_is_better": bool(getattr(spec, "higher_is_better", False)),
        "raw_scale": getattr(spec, "raw_scale", None),
        "normalized_scale_target": getattr(spec, "normalized_scale_target", None),
        "attribution": REIGN_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=f"{source_row_reference}:{variable_name}",
        observation_family=REIGN_OBSERVATION_FAMILY,
        indicator_code=variable_name,
        value=raw_value,
        value_type=_value_type(variable_name, normalized_value),
        year=year,
        country_code=None,
        country_name=country,
        leader_id=None,
        leader_name=leader_name,
        unit=getattr(spec, "unit", None),
        scale=getattr(spec, "raw_scale", None),
        source_version=REIGN_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=REIGN_CSV_ASSET_ID,
            path=str(request.raw_root / REIGN_SOURCE_KEY / REIGN_CSV_NAME),
            row_number=None,
            column_name=spec.raw_column,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=REIGN_TRANSFORM_NAME,
            catalog_key=REIGN_SOURCE_KEY,
            rule_id=source_row_reference,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _country_matches(request: SourceIngestRequest, country: str, ccode: int | None) -> bool:
    if not request.countries:
        return True
    needles = {item.strip().casefold() for item in request.countries if item.strip()}
    tokens = {country.casefold()}
    if ccode is not None:
        tokens.add(str(ccode).casefold())
    return bool(tokens & needles)


def _value_type(variable_name: str, normalized_value: Any) -> str:
    if variable_name in {"reign_leader"}:
        return "text"
    if variable_name in {"reign_government"}:
        return "categorical"
    if normalized_value is None:
        return "text"
    return "numeric"


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


def _json_scalar(value: Any) -> str | int | float | bool | None:
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


__all__ = ["emit_reign_observations"]
