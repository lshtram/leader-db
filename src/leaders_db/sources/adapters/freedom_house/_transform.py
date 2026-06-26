"""Transform FIW ratings/statuses sheets into normalized observations."""

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
    FREEDOM_HOUSE_ATTRIBUTION_TEXT,
    FREEDOM_HOUSE_DEFAULT_VERSION,
    FREEDOM_HOUSE_INDICATOR_CIVIL_LIBERTIES,
    FREEDOM_HOUSE_INDICATOR_POLITICAL_RIGHTS,
    FREEDOM_HOUSE_INDICATOR_STATUS,
    FREEDOM_HOUSE_OBSERVATION_FAMILY,
    FREEDOM_HOUSE_RATINGS_ASSET_ID,
    FREEDOM_HOUSE_RATINGS_XLSX_NAME,
    FREEDOM_HOUSE_SOURCE_KEY,
    FREEDOM_HOUSE_TRANSFORM_NAME,
)

_RAW_TO_INDICATOR = {
    "PR": FREEDOM_HOUSE_INDICATOR_POLITICAL_RIGHTS,
    "CL": FREEDOM_HOUSE_INDICATOR_CIVIL_LIBERTIES,
    "Status": FREEDOM_HOUSE_INDICATOR_STATUS,
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        import pandas as pd

        if pd.isna(value):
            return True
    except (ImportError, TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() in {"", "-"}


def _edition_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
        if text.startswith("Jan.-Feb. ") and text[-4:].isdigit():
            return int(text[-4:])
    return None


def _coerce_rating(value: Any) -> int | None:
    if _is_missing(value):
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError):
        return None
    return rating if 1 <= rating <= 7 else None


def _normalise_rating(value: int) -> float:
    return round((7 - value) / 6, 6)


def _country_filter_matches(country: str, request: SourceIngestRequest) -> bool:
    if not request.countries:
        return True
    needles = {item.strip().casefold() for item in request.countries if item.strip()}
    return country.casefold() in needles


def emit_fiw_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frames = payload.get("frames")
    if not isinstance(frames, dict):
        return iter(())
    requested_years = set(request.years) if request.years else None
    observations: list[NormalizedObservation] = []
    for sheet_name, frame in frames.items():
        observations.extend(_emit_sheet(request, frame, sheet_name, requested_years))
    return iter(observations)


def _emit_sheet(
    request: SourceIngestRequest,
    frame: Any,
    sheet_name: str,
    requested_years: set[int] | None,
) -> list[NormalizedObservation]:
    if frame is None or len(frame.index) < 4:
        return []
    observations: list[NormalizedObservation] = []
    entity_type = "territory" if "Territory" in sheet_name else "country"
    for col in range(1, len(frame.columns), 3):
        year = _edition_year(frame.iat[0, col])
        if year is None or (requested_years is not None and year not in requested_years):
            continue
        under_review = frame.iat[1, col] if col < len(frame.columns) else None
        raw_columns = {offset: str(frame.iat[2, col + offset]).strip() for offset in range(3)}
        for row_index in range(3, len(frame.index)):
            country_raw = frame.iat[row_index, 0]
            if _is_missing(country_raw):
                continue
            country = str(country_raw).strip()
            if not _country_filter_matches(country, request):
                continue
            for offset, raw_column in raw_columns.items():
                indicator = _RAW_TO_INDICATOR.get(raw_column)
                if indicator is None:
                    continue
                cell = frame.iat[row_index, col + offset]
                if _is_missing(cell):
                    continue
                obs = _build_observation(
                    request,
                    country=country,
                    entity_type=entity_type,
                    year=year,
                    under_review=under_review,
                    indicator=indicator,
                    raw_column=raw_column,
                    raw_value=cell,
                    row_number=row_index + 1,
                    sheet_name=sheet_name,
                )
                if obs is not None:
                    observations.append(obs)
    return observations


def _build_observation(
    request: SourceIngestRequest,
    *,
    country: str,
    entity_type: str,
    year: int,
    under_review: Any,
    indicator: str,
    raw_column: str,
    raw_value: Any,
    row_number: int,
    sheet_name: str,
) -> NormalizedObservation | None:
    if indicator == FREEDOM_HOUSE_INDICATOR_STATUS:
        value: Any = str(raw_value).strip()
        value_type = "categorical"
        unit = "status"
        scale = "F/PF/NF"
        normalized_value = None
        higher_is_better = None
    else:
        value = _coerce_rating(raw_value)
        if value is None:
            return None
        value_type = "numeric"
        unit = "rating"
        scale = "1-7"
        normalized_value = _normalise_rating(value)
        higher_is_better = False
    row_ref = f"{FREEDOM_HOUSE_SOURCE_KEY}:{entity_type}:{country}:{year}:{raw_column}"
    extension = {
        "freedom_house_entity_type": entity_type,
        "freedom_house_raw_column": raw_column,
        "freedom_house_years_under_review": (
            None if _is_missing(under_review) else str(under_review)
        ),
        "source_row_reference": row_ref,
        "raw_value": str(raw_value).strip(),
        "normalized_value": normalized_value,
        "higher_is_better": higher_is_better,
        "raw_scale": scale,
        "normalized_scale_target": "0-1" if normalized_value is not None else None,
        "attribution": FREEDOM_HOUSE_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=f"{FREEDOM_HOUSE_SOURCE_KEY}:{entity_type}:{country}:{year}:{indicator}",
        observation_family=FREEDOM_HOUSE_OBSERVATION_FAMILY,
        indicator_code=indicator,
        value=value,
        value_type=value_type,
        year=year,
        country_code=None,
        country_name=country,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=scale,
        source_version=FREEDOM_HOUSE_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=FREEDOM_HOUSE_RATINGS_ASSET_ID,
            path=str(
                request.raw_root
                / FREEDOM_HOUSE_SOURCE_KEY
                / FREEDOM_HOUSE_RATINGS_XLSX_NAME,
            ),
            sheet=sheet_name,
            row_number=row_number,
            column_name=f"{year}:{raw_column}",
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=FREEDOM_HOUSE_TRANSFORM_NAME,
            catalog_key=FREEDOM_HOUSE_SOURCE_KEY,
            rule_id=row_ref,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


__all__ = ["emit_fiw_observations"]
