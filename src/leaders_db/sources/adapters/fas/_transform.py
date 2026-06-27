"""Transform FAS Nuclear Notebook rows into normalized observations.

The FAS clean adapter consumes the legacy wide-format pandas
DataFrame emitted by
:func:`leaders_db.ingest.fas_html.read_fas_status_html` and pivots it
to one :class:`NormalizedObservation` per non-missing
``(country, snapshot_year, variable_name)`` triple. The transform
layer:

- Filters by the request's ``countries`` filter using the FAS
  source-native country display name (case-insensitive exact
  match -- the FAS table does NOT carry ISO3 codes; Stage 3 fills
  the ISO3 mapping later via ``country_aliases.csv``).
- Applies the request ``years`` filter against the parsed
  snapshot year; for FAS the snapshot year is the only year the
  source provides so the filter is effectively a "do you want
  snapshot year rows" gate. A request with ``years=None`` emits
  the snapshot year rows without warning; a request with an
  explicit ``years`` tuple that does NOT match the snapshot year
  still emits the snapshot year rows (no silent stale-proxy fill
  per SRC-COV-002 / SRC-COV-003) AND tags every observation with
  the requested year / snapshot year / proxy_snapshot_semantics
  audit metadata so downstream audit code can detect the
  temporal-fit gap.
- Emits missing observations for sentinel values that map to
  ``None`` (e.g. ``"n.a."``, ``"?"``) while preserving the
  sentinel literal in audit-trail ``extension.raw_value``. This
  matches the legacy DB writer semantics and lets downstream
  consumers distinguish source-reported missingness from a fully
  absent cell.
- Skips only cells where both the numeric value AND raw literal are
  absent, so the runner never fabricates evidence for missing table
  structure.
- Preserves the source-native country display name verbatim in
  ``country_name`` and leaves ``country_code`` as ``None`` until
  Stage 3 resolves it via the canonical country aliases table.
- Preserves the source-native leader fields as ``None`` (FAS is
  country-year nuclear evidence, not leader evidence).
- Attaches the canonical FAS attribution text (Rule #15) to every
  observation's ``extension.attribution`` field.
- Stamps the ``source_row_reference`` as
  ``"fas:<raw_column>:<country>"`` -- matching the legacy Stage 2
  DB writer's convention (the audit-trail audit cross-checks the
  new runner's output against the legacy DB table by
  ``source_row_reference`` equality).
"""

from __future__ import annotations

from collections.abc import Iterable
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
    FAS_ATTRIBUTION_TEXT,
    FAS_DEFAULT_VERSION,
    FAS_HTML_ASSET_ID,
    FAS_OBSERVATION_FAMILY,
    FAS_SNAPSHOT_YEAR,
    FAS_SOURCE_KEY,
    FAS_STATUS_PAGE_URL,
    FAS_TRANSFORM_NAME,
)
from ._readiness import html_path


def emit_fas_observations(
    request: SourceIngestRequest,
    raw: RawReadResult,
) -> Iterable[NormalizedObservation]:
    """Convert the raw FAS wide frame into normalized observations.

    Iterates the legacy wide-format DataFrame carried in
    ``raw.payload["frame"]`` (one row per country; columns are the
    5 catalog ``variable_name``s plus the ``_raw_value`` siblings),
    filters by the request country filter, and emits one
    :class:`NormalizedObservation` per non-null ``(country,
    snapshot_year, variable_name)`` cell.

    The transform layer NEVER invents values, country codes
    (ISO3), country names, leader IDs, or proxy years: cells with
    null numeric values are skipped; countries not present in the
    wide frame are skipped; ``leader_id`` / ``leader_name`` are
    always ``None``. The snapshot year is stamped on every
    observation's ``year`` field with the request's
    ``requested_year`` recorded in ``extension.requested_year``
    when the request explicitly asks for a year other than the
    snapshot year.
    """
    payload = raw.payload if isinstance(raw.payload, dict) else {}
    frame = payload.get("frame")
    specs = payload.get("specs") or []
    raw_value_lookup: dict[tuple[str, int, str], str] = (
        payload.get("raw_value_lookup") or {}
    )
    if frame is None:
        return iter(())

    snapshot_year = int(payload.get("snapshot_year") or FAS_SNAPSHOT_YEAR)
    requested_year_int = (
        int(request.years[0])
        if request.years and len(request.years) == 1
        else None
    )
    proxy_active = bool(
        requested_year_int is not None
        and requested_year_int != snapshot_year
    )

    country_filter = _country_filter(request)

    observations: list[NormalizedObservation] = []
    for row in frame.itertuples(index=False):
        country = _text(getattr(row, "country", None))
        if not country:
            continue
        if country_filter is not None and country.casefold() not in country_filter:
            continue
        for spec in specs:
            raw_value = raw_value_lookup.get(
                (country, snapshot_year, spec.variable_name),
            )
            value = _coerce_numeric(getattr(row, spec.variable_name, None))
            if value is None and not raw_value:
                # Both numeric value AND raw literal are missing --
                # skip the row so the runner never fabricates a
                # missing observation.
                continue
            observations.append(
                _build_observation(
                    request=request,
                    country=country,
                    snapshot_year=snapshot_year,
                    spec=spec,
                    value=value,
                    raw_value=raw_value or "",
                    requested_year=requested_year_int,
                    proxy_active=proxy_active,
                ),
            )
    return iter(observations)


def _build_observation(
    *,
    request: SourceIngestRequest,
    country: str,
    snapshot_year: int,
    spec: Any,
    value: JsonScalar,
    raw_value: str,
    requested_year: int | None,
    proxy_active: bool,
) -> NormalizedObservation:
    """Assemble one :class:`NormalizedObservation` for a valid row."""
    source_row_reference = (
        f"{FAS_SOURCE_KEY}:{spec.raw_column}:{country}"
    )
    raw_scalar = _json_scalar(raw_value)
    if value is None:
        value_type = "missing"
    else:
        value_type = "numeric"

    extension: dict[str, JsonScalar] = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_scalar,
        "normalized_value": value,
        "higher_is_better": bool(getattr(spec, "higher_is_better", False)),
        "raw_scale": getattr(spec, "raw_scale", "") or None,
        "normalized_scale_target": (
            getattr(spec, "normalized_scale_target", "") or None
        ),
        "fas_raw_column": spec.raw_column,
        "snapshot_year": snapshot_year,
        "year_window": [snapshot_year, snapshot_year],
        "source_row_url": FAS_STATUS_PAGE_URL,
        "attribution": FAS_ATTRIBUTION_TEXT,
    }
    if proxy_active and requested_year is not None:
        extension["requested_year"] = requested_year
        extension["proxy_snapshot_semantics"] = (
            f"requested {requested_year} uses actual FAS "
            f"{snapshot_year} snapshot data (no silent stale-proxy fill "
            "per SRC-COV-002 / SRC-COV-003; Stage 11 confidence "
            "penalises the temporal-fit gap)."
        )

    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=(
            f"{FAS_SOURCE_KEY}:{country}:{snapshot_year}:"
            f"{spec.variable_name}"
        ),
        observation_family=FAS_OBSERVATION_FAMILY,
        indicator_code=spec.variable_name,
        value=value,
        value_type=value_type,  # type: ignore[arg-type]
        year=snapshot_year,
        country_code=None,
        country_name=country,
        leader_id=None,
        leader_name=None,
        unit=getattr(spec, "unit", "") or None,
        scale=getattr(spec, "raw_scale", "") or None,
        source_version=FAS_DEFAULT_VERSION,
        raw_locator=RawLocator(
            asset_id=FAS_HTML_ASSET_ID,
            path=str(html_path(request)),
            url=FAS_STATUS_PAGE_URL,
            row_number=None,
            column_name=spec.raw_column,
        ),
        transform_locator=TransformLocator(
            adapter_version=None,
            transform_name=FAS_TRANSFORM_NAME,
            catalog_key=FAS_SOURCE_KEY,
            rule_id=source_row_reference,
        ),
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _country_filter(request: SourceIngestRequest) -> set[str] | None:
    """Return the FAS source-native country filter, or ``None`` for no filter.

    FAS uses source-native display names (e.g. ``"Russia"``,
    ``"United States"``, ``"North Korea"``) -- NOT ISO3 codes. The
    transform applies a case-insensitive exact match against the
    displayed country cell; ISO3 filtering happens in Stage 3 via
    the canonical ``country_aliases.csv`` mapping. Unknown ISO3
    filters silently emit zero rows (the caller should filter on
    the source-native display name to opt in to FAS evidence).
    """
    if not request.countries:
        return None
    return {
        str(country).strip().casefold()
        for country in request.countries
        if str(country).strip()
    }


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


def _coerce_numeric(value: Any) -> float | None:
    if value is None:
        return None
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except (ImportError, TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_scalar(value: Any) -> JsonScalar:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


__all__ = ["emit_fas_observations"]
