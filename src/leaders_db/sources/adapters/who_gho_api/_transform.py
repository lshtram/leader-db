"""Transform WHO GHO API country-year rows into normalized observations.

Mirrors the legacy Stage 2 reader's long-to-wide pivot semantics:
one :class:`NormalizedObservation` per ``(iso3, year, variable)``
triple, preserving the verbatim ``Value`` field (e.g.
``"76.4 [76.3-76.5]"`` with bounds) on the audit-trail
``extension.raw_value`` and the numeric ``NumericValue`` on
``value``. ISO3 is the country_code; the source-native display
name is not preserved by the WHO GHO API response (it carries
only ``SpatialDim`` / ``ParentLocationCode``), so
``country_name`` is left as ``None`` per the canonical contract
that the unified adapter never invents fields.

Stage 2 inventory of preserved fields (per requirement §13 / §14):

- ``value`` (float from ``NumericValue``) - the normalized numeric.
- ``extension.raw_value`` (verbatim ``Value`` string).
- ``extension.source_row_reference`` (``who_gho_api:<raw_column>:<iso3>``).
- ``extension.higher_is_better`` / ``raw_scale`` /
  ``normalized_scale_target`` from the catalog spec.
- ``extension.who_gho_api_raw_column`` (the WHO GHO API IndicatorCode).
- ``extension.dim1_filter`` (the per-spec Dim1 filter used).
- ``extension.spatial_dim_type`` (``COUNTRY`` -- the parser
  filters non-country records at the parser level).
- ``extension.year_window`` (single year tuple).
- ``extension.attribution`` (the canonical WHO GHO API
  attribution block).

Stage 2 emits NO observations for missing values / missing
years / missing countries / missing leader IDs / proxy years
(SRC-REQ-003 / §13 -- no invented data).
"""

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
    WHO_GHO_API_ATTRIBUTION_TEXT,
    WHO_GHO_API_DEFAULT_VERSION,
    WHO_GHO_API_OBSERVATION_FAMILY,
    WHO_GHO_API_SOURCE_KEY,
    WHO_GHO_API_TRANSFORM_NAME,
)
from ._readiness import cache_file


def emit_who_gho_api_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    """Convert raw WHO GHO API long frames into :class:`NormalizedObservation`.

    Iterates the legacy long-format DataFrames carried in
    ``raw.payload["long_frames"]`` (one frame per
    ``(IndicatorCode, year)`` cache file), filters by the
    request year / country filters, and emits one
    :class:`NormalizedObservation` per non-null ``NumericValue``
    cell.

    The WHO GHO API may return multiple ``COUNTRY`` records per
    ``(iso3, year, indicator_code)`` (e.g. WEALTHQUINTILE_WQ5 +
    WEALTHQUINTILE_TOTL disaggregations on
    ``MDG_0000000007``). The legacy Stage 2 reader uses
    ``pd.pivot_table(..., aggfunc="first")`` to pick the first
    value per ``(iso3, year, indicator)`` -- this helper
    preserves that "first-match wins" semantics via the
    :data:`_emitted_keys` set so the unified adapter never
    emits duplicate observations for the same
    ``(iso3, year, indicator)`` triple.

    The transform layer never invents values / ISO3 / country
    names / leader IDs / proxy years: cells with null
    ``NumericValue`` are skipped; countries / years not present
    in the cache are skipped; ``leader_id`` / ``leader_name`` are
    always ``None``.
    """
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    long_frames = payload.get("long_frames") or []
    specs = payload.get("specs") or []
    raw_value_lookup: dict[tuple[str, int, str], str] = (
        payload.get("raw_value_lookup") or {}
    )
    spec_by_code = _build_spec_by_code(specs)

    requested_years: set[int] | None = (
        {int(year) for year in request.years}
        if request.years else None
    )
    country_filter = _country_filter(request)

    observations: list[NormalizedObservation] = []
    emitted_keys: set[tuple[str, int, str]] = set()
    for frame in long_frames:
        if frame is None or getattr(frame, "empty", True):
            continue
        for row in frame.itertuples(index=False):
            observation = _row_to_observation(
                request=request,
                row=row,
                spec_by_code=spec_by_code,
                raw_value_lookup=raw_value_lookup,
                requested_years=requested_years,
                country_filter=country_filter,
                emitted_keys=emitted_keys,
            )
            if observation is not None:
                observations.append(observation)
    return iter(observations)


def _row_to_observation(
    *,
    request: SourceIngestRequest,
    row: Any,
    spec_by_code: dict[str, Any],
    raw_value_lookup: dict[tuple[str, int, str], str],
    requested_years: set[int] | None,
    country_filter: set[str] | None,
    emitted_keys: set[tuple[str, int, str]],
) -> NormalizedObservation | None:
    """Convert one legacy long-format row to a normalized observation.

    Returns ``None`` when the row's data is incomplete (null
    ``NumericValue`` / missing ISO3 / missing year / out of
    request year filter / out of request country filter / no
    catalog spec for the indicator code / already-emitted
    ``(iso3, year, indicator_code)`` triple from an earlier
    disaggregation row).
    """
    iso3 = _str(getattr(row, "iso3", None)).upper()
    year = _coerce_int(getattr(row, "year", None))
    raw_column = _str(getattr(row, "indicator_code", None))
    value = _coerce_float(getattr(row, "value", None))
    if not iso3 or year is None or not raw_column or value is None:
        return None
    if requested_years is not None and year not in requested_years:
        return None
    if country_filter is not None and iso3 not in country_filter:
        return None

    spec = spec_by_code.get(raw_column)
    if spec is None:
        # Indicator code not in the in-scope catalog -- silently
        # skip (the cache may carry indicators the catalog does
        # not track).
        return None

    key = (iso3, year, raw_column)
    if key in emitted_keys:
        return None
    emitted_keys.add(key)

    raw_value = raw_value_lookup.get(key, "")
    return _build_observation(
        request=request,
        iso3=iso3,
        year=year,
        raw_column=raw_column,
        value=value,
        raw_value=raw_value,
        spec=spec,
    )


def _build_observation(
    *,
    request: SourceIngestRequest,
    iso3: str,
    year: int,
    raw_column: str,
    value: float,
    raw_value: str,
    spec: Any,
) -> NormalizedObservation:
    """Assemble one :class:`NormalizedObservation` for a valid row."""
    row_ref = f"{WHO_GHO_API_SOURCE_KEY}:{raw_column}:{iso3}"
    cache_path = cache_file(request, year, raw_column)
    rule_id = f"{row_ref}:{year}"
    dim1_filter = _str(getattr(spec, "dim1_filter", ""))
    extension = {
        "source_row_reference": row_ref,
        "raw_value": raw_value,
        "normalized_value": value,
        "higher_is_better": bool(getattr(spec, "higher_is_better", False)),
        "raw_scale": getattr(spec, "raw_scale", ""),
        "normalized_scale_target": getattr(
            spec, "normalized_scale_target", "",
        ),
        "who_gho_api_raw_column": raw_column,
        "dim1_filter": dim1_filter or None,
        "spatial_dim_type": "COUNTRY",
        "year_window": [year, year],
        "attribution": WHO_GHO_API_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=(
            f"{WHO_GHO_API_SOURCE_KEY}:{iso3}:{year}:"
            f"{spec.variable_name}"
        ),
        observation_family=WHO_GHO_API_OBSERVATION_FAMILY,
        indicator_code=spec.variable_name,
        value=value,
        value_type="numeric",
        year=year,
        country_code=iso3,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", "") or None,
        scale=getattr(spec, "raw_scale", "") or None,
        source_version=WHO_GHO_API_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=(
                f"{WHO_GHO_API_SOURCE_KEY}:cache:{year}:{raw_column}"
            ),
            path=str(cache_path),
            url=None,
            row_number=None,
            column_name=raw_column,
            api_endpoint=None,
            json_pointer="/value",
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=WHO_GHO_API_TRANSFORM_NAME,
            catalog_key=WHO_GHO_API_SOURCE_KEY,
            rule_id=rule_id,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _build_spec_by_code(specs: Iterable[Any]) -> dict[str, Any]:
    """Map WHO GHO API ``IndicatorCode`` -> catalog spec."""
    return {spec.raw_column: spec for spec in specs}


def _country_filter(request: SourceIngestRequest) -> set[str] | None:
    """Return the ISO3 country filter (upper-cased) or ``None`` for no filter."""
    if not request.countries:
        return None
    return {
        str(country).strip().upper()
        for country in request.countries
        if str(country).strip()
    }


def _str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if _pd_isna(value):
            return ""
    except (ImportError, TypeError, ValueError):
        pass
    return str(value).strip()


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if _pd_isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if _pd_isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pd_isna(value: Any) -> bool:
    """Return ``True`` if ``value`` is NaN/NaT/None."""
    try:
        import pandas as pd
    except ImportError:
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


__all__ = ["emit_who_gho_api_observations"]
