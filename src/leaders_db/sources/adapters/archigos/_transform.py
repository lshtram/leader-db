"""Transform Archigos long rows into normalized observations."""

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
    ARCHIGOS_ATTRIBUTION_TEXT,
    ARCHIGOS_DEFAULT_VERSION,
    ARCHIGOS_DTA_ASSET_ID,
    ARCHIGOS_DTA_NAME,
    ARCHIGOS_OBSERVATION_FAMILY,
    ARCHIGOS_SOURCE_KEY,
    ARCHIGOS_TRANSFORM_NAME,
)


def emit_archigos_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frame = payload.get("frame")
    specs = payload.get("specs")
    if frame is None or specs is None:
        return iter(())
    spec_by_variable = {spec.variable_name: spec for spec in specs}
    leader_by_obsid = _leader_lookup(frame)
    requested_years = set(request.years) if request.years else None
    observations: list[NormalizedObservation] = []
    for row in frame.itertuples(index=False):
        year = _coerce_int(getattr(row, "year", None))
        if year is None or (requested_years is not None and year not in requested_years):
            continue
        idacr = _text(getattr(row, "idacr", None))
        ccode = _coerce_int(getattr(row, "ccode", None))
        if not _country_matches(request, idacr, ccode):
            continue
        variable_name = _text(getattr(row, "variable_name", None))
        spec = spec_by_variable.get(variable_name)
        if spec is None:
            continue
        obsid = _text(getattr(row, "obsid", None))
        raw_column = spec.raw_column
        source_row_reference = _text(getattr(row, "source_row_reference", None))
        observations.append(
            _build_observation(
                request,
                row=row,
                obsid=obsid,
                idacr=idacr,
                ccode=ccode,
                year=year,
                variable_name=variable_name,
                raw_column=raw_column,
                source_row_reference=source_row_reference,
                spec=spec,
                leader_name=leader_by_obsid.get(obsid),
            ),
        )
    return iter(observations)


def _build_observation(
    request: SourceIngestRequest,
    *,
    row: Any,
    obsid: str,
    idacr: str,
    ccode: int | None,
    year: int,
    variable_name: str,
    raw_column: str,
    source_row_reference: str,
    spec: Any,
    leader_name: str | None,
) -> NormalizedObservation:
    raw_value = _text(getattr(row, "raw_value", None))
    normalized_value = _json_scalar(getattr(row, "normalized_value", None))
    extension = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "archigos_obsid": obsid,
        "archigos_idacr": idacr,
        "archigos_ccode": ccode,
        "archigos_end_year": _coerce_int(getattr(row, "end_year", None)),
        "archigos_raw_column": raw_column,
        "higher_is_better": bool(getattr(spec, "higher_is_better", False)),
        "raw_scale": getattr(spec, "raw_scale", None),
        "normalized_scale_target": getattr(spec, "normalized_scale_target", None),
        "attribution": ARCHIGOS_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=f"{ARCHIGOS_SOURCE_KEY}:{obsid}:{year}:{variable_name}",
        observation_family=ARCHIGOS_OBSERVATION_FAMILY,
        indicator_code=variable_name,
        value=raw_value,
        value_type=_value_type(variable_name),
        year=year,
        country_code=None,
        country_name=None,
        leader_id=None,
        leader_name=leader_name,
        unit=getattr(spec, "unit", None),
        scale=getattr(spec, "raw_scale", None),
        source_version=ARCHIGOS_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=ARCHIGOS_DTA_ASSET_ID,
            path=str(request.raw_root / ARCHIGOS_SOURCE_KEY / ARCHIGOS_DTA_NAME),
            row_number=None,
            column_name=raw_column,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=ARCHIGOS_TRANSFORM_NAME,
            catalog_key=ARCHIGOS_SOURCE_KEY,
            rule_id=source_row_reference,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _leader_lookup(frame: Any) -> dict[str, str]:
    leaders: dict[str, str] = {}
    for row in frame.itertuples(index=False):
        if _text(getattr(row, "variable_name", None)) != "archigos_leader_name":
            continue
        obsid = _text(getattr(row, "obsid", None))
        leader = _text(getattr(row, "raw_value", None))
        if obsid and leader:
            leaders[obsid] = leader
    return leaders


def _country_matches(request: SourceIngestRequest, idacr: str, ccode: int | None) -> bool:
    if not request.countries:
        return True
    needles = {item.strip().casefold() for item in request.countries if item.strip()}
    tokens = {idacr.casefold()}
    if ccode is not None:
        tokens.add(str(ccode).casefold())
    return bool(tokens & needles)


def _value_type(variable_name: str) -> str:
    if variable_name == "archigos_leader_name":
        return "text"
    if variable_name in {"archigos_entry_type", "archigos_exit_type", "archigos_gender"}:
        return "categorical"
    return "text"


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


__all__ = ["emit_archigos_observations"]
