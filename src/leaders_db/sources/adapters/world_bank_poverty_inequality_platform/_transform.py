"""Transform World Bank Poverty and Inequality Platform (PIP)
rows into normalized observations.

This module owns the per-row :class:`NormalizedObservation`
build loop for the unified World Bank PIP adapter. The function
takes the parsed row-level frame returned by
:func:`._raw_read.read_world_bank_poverty_inequality_platform_cache`
and emits one observation per cached row + source-native
catalog indicator (3 per-row indicators by default:
``world_bank_poverty_inequality_platform_poverty_headcount_ratio``
/ ``world_bank_poverty_inequality_platform_poverty_gap`` /
``world_bank_poverty_inequality_platform_gini_index``).

Catalog
-------

The canonical World Bank PIP catalog carries 3 source-native
numeric indicators (one per indicator cell typically exposed by
the canonical PIP CSV / JSON export):

- ``world_bank_poverty_inequality_platform_poverty_headcount_ratio``
  -- the poverty headcount ratio at the row's poverty line.
  Preserved verbatim on
  ``extension["world_bank_poverty_inequality_platform_poverty_line_raw"]``.
- ``world_bank_poverty_inequality_platform_poverty_gap`` -- the
  poverty gap at the row's poverty line.
- ``world_bank_poverty_inequality_platform_gini_index`` -- the
  Gini index of the row's distribution.

The catalog deliberately does NOT include a default PPP factor
/ survey-year / survey-comparability indicator beyond what the
source-native CSV / JSON explicitly exposes; the transform
preserves the source-native ``ppp_version`` / ``ppp_base_year`` /
``survey_year`` / ``survey_comparability`` / ``version_id`` /
``notes`` cells on the audit-trail extension payload when the
cached header declares those columns. The transform never
invents a value from missing source-native data; a blank /
non-numeric cell is emitted with
``value=None`` / ``value_type="missing"`` plus the verbatim
raw cell text on ``extension.raw_value``.

Source-native preservation
--------------------------

The transform preserves the source-native country display name
+ source-native country code verbatim on every emitted
observation:

- ``extension["world_bank_poverty_inequality_platform_country_code_raw"]``
  carries the source-native reporting identifier (a
  3-character code that LOOKS LIKE ISO3 but is the World
  Bank's own reporting identifier -- NOT a canonical ISO3
  mapping). The transform never assumes the source identifier
  is a canonical ISO3 even when it resembles one; ``country_code``
  remains ``None`` until later matching / resolution stages
  introduce a canonical ISO3 mapping.
- ``country_name`` carries the source-native reporting country
  display name verbatim.
- The source-native ``reporting_level`` (``"national"`` /
  ``"rural"`` / ``"urban"`` / etc.) and ``welfare_type``
  (``"income"`` / ``"consumption"`` / etc.) are preserved on
  the audit-trail extension payload so downstream code can
  recover the verbatim source provenance.

Per-row emission produces 3 observations per cached row for the
default 3-indicator catalog (N rows x 3 indicators = 3N
observations).

Attribution
-----------

Every emitted observation carries the canonical attribution
text from
:data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT`
on ``extension["attribution"]`` (with the ``{version_ID}``
placeholder interpolated from the bundle's canonical PIP
version stamp) so the Stage 15 summary report and the
manual-review queue can propagate the attribution forward
(Always-On Rule #15). The descriptor's ``coverage_hint.notes``
carries the explicit caveat that PIP poverty / inequality
estimates are SURVEY- and PPP-specific and SHOULD NOT be
silently mixed across PIP version stamps or PPP bases without
explicit metadata propagation.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    JsonScalar,
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

from ._constants import (
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_SCALE,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_UNIT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_SCALE,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_UNIT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_SCALE,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_UNIT,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME,
)


def _coerce_text_cell(cell: Any) -> str:
    """Return the cell text as a stripped ``str``.

    Used for the source-native country / reporting-level /
    welfare-type / poverty-line / optional cells. The helper
    coerces ``None`` / ``str`` / non-string cells to a stripped
    ``str`` so the transform layer can branch on string
    sentinels.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip()
    return str(cell).strip()


def _coerce_year_cell(cell: Any) -> int | None:
    """Coerce a raw cell value to a 4-digit year ``int`` or
    ``None``.

    Used for the PIP ``year`` cell. The PIP year cell carries
    the source-native year as a string / numeric value (e.g.
    ``"2018"`` / ``2018``). Returns ``None`` when the cell is
    blank / non-numeric so the transform layer emits zero
    observations for the row (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003).
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, int):
        if 1000 <= cell <= 9999:
            return cell
        return None
    if isinstance(cell, float):
        if math.isnan(cell):
            return None
        if cell.is_integer():
            int_value = int(cell)
            if 1000 <= int_value <= 9999:
                return int_value
        return None
    if not isinstance(cell, str):
        return None
    text = cell.strip()
    if not text:
        return None
    if text in {"-", "..", "...", "?", "n.a.", "na", "nil"}:
        return None
    try:
        int_value = int(text)
    except ValueError:
        return None
    if 1000 <= int_value <= 9999:
        return int_value
    return None


def _coerce_float_cell(cell: Any) -> float | None:
    """Coerce a raw cell value to ``float`` or return ``None``.

    PIP ``headcount`` / ``poverty_gap`` / ``gini`` cells carry
    numeric values that may include decimal points. The helper
    handles string sentinels (``"-"`` / ``""`` / ``".."`` /
    ``"?"`` / ``"n.a."``) as missing; parses numeric cells
    (integer, decimal) into ``float``; falls back to ``None``
    for any unparseable cell so the transform layer can emit
    ``value=None`` / ``value_type="missing"`` plus the verbatim
    raw cell text on ``extension.raw_value``.
    """
    if cell is None:
        return None
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        as_float = float(cell)
        if math.isnan(as_float):
            return None
        return as_float
    if not isinstance(cell, str):
        return None
    text = cell.strip()
    if not text:
        return None
    lowered = text.casefold()
    if lowered in {"-", "..", "...", "?", "n.a.", "na", "nil"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _country_matches(
    request: SourceIngestRequest,
    country_name: str,
) -> bool:
    """Return True iff the row's source-native country display
    name matches any case-folded substring in
    ``request.countries``.

    The cached World Bank PIP dataset uses the World Bank's
    own country display names, which are NOT ISO3; the unified
    adapter never invents ISO3 codes. The filter is a
    case-folded substring match against the source-native
    display name so callers can filter for "PIP observations
    for Country A" by passing ``countries=("Country A",)``.
    """
    if not request.countries:
        return True
    needles = {
        item.strip().casefold()
        for item in request.countries
        if item and item.strip()
    }
    if not needles:
        return True
    haystack = country_name.casefold()
    return any(needle in haystack for needle in needles)


def _year_in_coverage(year: int | None) -> bool:
    """Return True iff ``year`` falls within the canonical
    1960-2024 World Bank PIP coverage envelope.

    Used to filter out rows with out-of-coverage years BEFORE
    they enter the observation set -- the row-level
    observations still carry the original ``year`` field on
    the ``extension`` payload so audit code can recover the
    original cell, but the row is excluded from the canonical
    output. The readiness envelope surfaces a structured
    ``YEAR_ABSENT`` warning on the request so the operator
    can see the gap.
    """
    if year is None:
        return False
    return (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_START_YEAR
        <= year
        <= WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_COVERAGE_END_YEAR
    )


def _row_passes_year_filter(
    row_year: int | None,
    requested_years: set[int] | None,
) -> bool:
    """Return True iff the row's ``year`` matches a requested
    year.

    The canonical "observation year" of a PIP row is the
    ``year`` column itself; the canonical output year of
    EVERY emitted observation is the row's ``year`` stamp. The
    ``request.years`` filter therefore checks ONLY the row's
    ``year`` so a request for ``years=(2018,)`` never emits a
    ``year=2020`` row. A row whose ``year`` is ``None`` is
    filtered out -- without a canonical year the observation
    has no ``year`` stamp to satisfy the request scope.
    """
    if requested_years is None:
        return True
    if row_year is None:
        return False
    return row_year in requested_years


def _attribution_with_version(version_id: str) -> str:
    """Return the canonical attribution text with the
    ``{version_ID}`` placeholder interpolated.

    The unified
    :data:`WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT`
    constant carries a ``{version_ID}`` placeholder so the
    downstream reports can carry the exact PIP version stamp
    the cached bundle carries without consulting the
    bundle's ``metadata.json``. The helper interpolates the
    placeholder with the supplied ``version_id`` (defaulting
    to the canonical default version-id when no
    bundle-specific version is supplied).
    """
    text = (
        WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_ATTRIBUTION_TEXT
    )
    if "{version_ID}" not in text:
        return text
    if not version_id:
        version_id = (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID
        )
    return text.replace("{version_ID}", version_id)


def _build_indicator_observation(
    request: SourceIngestRequest,
    *,
    indicator_code: str,
    country_code_raw: str,
    country_name: str,
    row_year: int,
    reporting_level: str,
    welfare_type: str,
    poverty_line_raw: str,
    raw_value_cell: str,
    normalized_value: float | None,
    value_type: str,
    unit: str,
    scale: str,
    raw_column_label: str,
    attribution_text: str,
    source_row_reference: str,
    asset_id: str,
    cache_path: Path | None,
    row_index: int,
    optional_extension: Mapping[str, JsonScalar],
) -> NormalizedObservation:
    """Build one ``poverty_inequality_country_year`` observation
    for a single catalog indicator."""
    raw_locator = RawLocator(
        asset_id=asset_id,
        path=str(cache_path) if cache_path is not None else None,
        column_name=raw_column_label,
        row_number=row_index,
    )
    transform_locator = TransformLocator(
        adapter_version=None,
        transform_name=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_TRANSFORM_NAME,
        catalog_key=WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY,
        rule_id=source_row_reference,
    )
    extension: dict[str, JsonScalar] = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_value_cell,
        "normalized_value": normalized_value,
        "world_bank_poverty_inequality_platform_country_code_raw": (
            country_code_raw
        ),
        "world_bank_poverty_inequality_platform_country_name_raw": (
            country_name
        ),
        "world_bank_poverty_inequality_platform_reporting_level": (
            reporting_level
        ),
        "world_bank_poverty_inequality_platform_welfare_type": (
            welfare_type
        ),
        "world_bank_poverty_inequality_platform_poverty_line_raw": (
            poverty_line_raw
        ),
        "world_bank_poverty_inequality_platform_raw_column": (
            raw_column_label
        ),
        "world_bank_poverty_inequality_platform_raw_value_cell": (
            raw_value_cell
        ),
        "world_bank_poverty_inequality_platform_indicator": (
            indicator_code
        ),
        "attribution": attribution_text,
    }
    # Preserve required audit cells and optional source-native
    # extras on the audit-trail extension payload when present in
    # the cached header.
    for key, value in optional_extension.items():
        if key in extension:
            continue
        extension[key] = value
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=source_row_reference,
        observation_family=(
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OBSERVATION_FAMILY
        ),
        indicator_code=indicator_code,
        value=normalized_value,
        value_type=value_type,  # type: ignore[arg-type]
        year=row_year,
        country_code=None,
        country_name=country_name,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=scale,
        source_version=(
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION
        ),
        raw_locator=raw_locator,
        transform_locator=transform_locator,
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _build_optional_extension(
    row: dict[str, str],
) -> dict[str, JsonScalar]:
    """Return required audit + optional source-native extension
    fields.

    ``version_id`` and ``ppp_version`` are required audit fields
    in the canonical 11-column PIP schema. The PIP CSV / JSON
    export may also carry optional source-native extras
    (``ppp_base_year`` / ``survey_year`` / ``survey_comparability`` /
    ``notes``). When present in the cached header, these cells
    are preserved on the audit-trail extension payload so
    downstream code can recover the verbatim source-native
    provenance without inventing values.
    """
    out: dict[str, JsonScalar] = {}
    extension_columns = (
        "version_id",
        "ppp_version",
        *WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_OPTIONAL_COLUMNS,
    )
    for col in extension_columns:
        if col not in row:
            continue
        cell = _coerce_text_cell(row.get(col))
        if not cell:
            continue
        out[f"world_bank_poverty_inequality_platform_{col}_raw"] = cell
    return out


def _emit_indicator_observation(
    request: SourceIngestRequest,
    *,
    indicator_code: str,
    unit: str,
    scale: str,
    raw_column_label: str,
    country_code_raw: str,
    country_name: str,
    row_year: int,
    reporting_level: str,
    welfare_type: str,
    poverty_line_raw: str,
    raw_cell: str,
    asset_id: str,
    cache_path: Path | None,
    row_index: int,
    attribution_text: str,
    optional_extension: Mapping[str, JsonScalar],
) -> NormalizedObservation:
    """Build the canonical observation for one indicator cell.

    Emits ``value_type="missing"`` when the cell is blank /
    non-numeric with the verbatim raw cell text on
    ``extension.raw_value``; emits ``value_type="numeric"``
    with the parsed ``float`` otherwise.
    """
    parsed = _coerce_float_cell(raw_cell)
    source_row_reference = (
        f"{WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_SOURCE_KEY}:"
        f"row_{row_index}:{indicator_code}:"
        f"{country_code_raw or country_name or 'unknown'}:"
        f"{row_year}"
    )
    if parsed is None:
        return _build_indicator_observation(
            request,
            indicator_code=indicator_code,
            country_code_raw=country_code_raw,
            country_name=country_name,
            row_year=row_year,
            reporting_level=reporting_level,
            welfare_type=welfare_type,
            poverty_line_raw=poverty_line_raw,
            raw_value_cell=_coerce_text_cell(raw_cell),
            normalized_value=None,
            value_type="missing",
            unit=unit,
            scale=scale,
            raw_column_label=raw_column_label,
            attribution_text=attribution_text,
            source_row_reference=source_row_reference,
            asset_id=asset_id,
            cache_path=cache_path,
            row_index=row_index,
            optional_extension=optional_extension,
        )
    return _build_indicator_observation(
        request,
        indicator_code=indicator_code,
        country_code_raw=country_code_raw,
        country_name=country_name,
        row_year=row_year,
        reporting_level=reporting_level,
        welfare_type=welfare_type,
        poverty_line_raw=poverty_line_raw,
        raw_value_cell=_coerce_text_cell(raw_cell),
        normalized_value=parsed,
        value_type="numeric",
        unit=unit,
        scale=scale,
        raw_column_label=raw_column_label,
        attribution_text=attribution_text,
        source_row_reference=source_row_reference,
        asset_id=asset_id,
        cache_path=cache_path,
        row_index=row_index,
        optional_extension=optional_extension,
    )


def emit_world_bank_poverty_inequality_platform_observations(
    request: SourceIngestRequest,
    rows: list[dict[str, str]],
    *,
    cache_path: Path | None,
    asset_id: str,
    version_id: str | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the parsed row-level frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries`` by
    filtering the parsed row-level frame on the transform
    side. The descriptor advertises a broad 1960-2024
    envelope; a request where NO requested year falls inside
    the envelope emits zero observations AND a structured
    ``YEAR_ABSENT`` warning on the readiness envelope (no
    stale-proxy fill per SRC-COV-002 / SRC-COV-003). The
    prototype's target year 2023 falls WITHIN the envelope.
    ``request.leaders`` is unsupported for a country-year
    poverty / inequality source and surfaces a structured
    ``UNSUPPORTED_FILTER`` warning (SRC-REQ-005).

    Per-row emission: each parsed row produces up to 3
    observations (one per source-native catalog indicator:
    headcount + poverty gap + Gini). Blank / non-numeric cells
    emit ``value=None`` / ``value_type="missing"`` plus the
    verbatim raw cell text on ``extension.raw_value`` -- the
    transform layer does NOT invent a value from missing
    source-native data.

    The transform layer never invents ISO3 country codes,
    leader identifiers, missing values, or proxy years. The
    source-native country code + display name + reporting
    level + welfare type + poverty line are preserved verbatim
    on every emitted observation's audit-trail extension
    payload (no numeric coercion that could mislead Stage 11
    confidence calculations).
    """
    observations: list[NormalizedObservation] = []

    requested_years: set[int] | None
    if request.years:
        requested_years = {int(y) for y in request.years}
    else:
        requested_years = None

    effective_version_id = (
        version_id
        if version_id
        else (
            WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_DEFAULT_VERSION_ID
        )
    )
    attribution_text = _attribution_with_version(effective_version_id)

    for row_index, row in enumerate(rows, start=2):
        # The cached World Bank PIP CSV / JSON routes each
        # parsed row into a dict keyed by the documented column
        # names; missing optional columns default to ``""`` so
        # the per-cell coercion below always sees a string.
        country_code_raw = _coerce_text_cell(row.get("country_code"))
        country_name = _coerce_text_cell(row.get("country_name"))
        year_cell = row.get("year")
        row_year = _coerce_year_cell(year_cell)
        reporting_level = _coerce_text_cell(row.get("reporting_level"))
        welfare_type = _coerce_text_cell(row.get("welfare_type"))
        poverty_line_raw = _coerce_text_cell(row.get("poverty_line"))
        headcount_cell = row.get("headcount")
        poverty_gap_cell = row.get("poverty_gap")
        gini_cell = row.get("gini")

        if not _country_matches(request, country_name):
            continue
        if not _year_in_coverage(row_year):
            continue
        if not _row_passes_year_filter(row_year, requested_years):
            continue
        if not country_name and not country_code_raw:
            # Defensive: skip rows with no identifying
            # information (the canonical PIP export never
            # carries such a row, but a user-edited cache
            # might).
            continue

        # The canonical output year of every emitted observation
        # is the row's ``year`` stamp. The transform does NOT
        # apply any year-proxy / 1-year-gap substitution -- a
        # request for ``years=(2023,)`` filters out rows with a
        # different ``year`` and the readiness envelope surfaces
        # a structured ``YEAR_ABSENT`` warning on the out-of-
        # coverage year request.
        canonical_year = row_year if row_year is not None else 0

        optional_extension = _build_optional_extension(row)

        # Indicator 1: poverty headcount ratio (the proportion
        # of the population living below the row's poverty
        # line). Blank / non-numeric cells emit
        # ``value_type="missing"`` plus the verbatim raw cell
        # text on ``extension.raw_value``.
        observations.append(
            _emit_indicator_observation(
                request,
                indicator_code=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_HEADCOUNT
                ),
                unit=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_UNIT
                ),
                scale=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_RATIO_SCALE
                ),
                raw_column_label="headcount",
                country_code_raw=country_code_raw,
                country_name=country_name,
                row_year=canonical_year,
                reporting_level=reporting_level,
                welfare_type=welfare_type,
                poverty_line_raw=poverty_line_raw,
                raw_cell=_coerce_text_cell(headcount_cell),
                asset_id=asset_id,
                cache_path=cache_path,
                row_index=row_index,
                attribution_text=attribution_text,
                optional_extension=optional_extension,
            ),
        )

        # Indicator 2: poverty gap (the depth of poverty below
        # the row's poverty line). Blank / non-numeric cells
        # emit ``value_type="missing"`` plus the verbatim raw
        # cell text.
        observations.append(
            _emit_indicator_observation(
                request,
                indicator_code=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GAP
                ),
                unit=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_UNIT
                ),
                scale=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GAP_SCALE
                ),
                raw_column_label="poverty_gap",
                country_code_raw=country_code_raw,
                country_name=country_name,
                row_year=canonical_year,
                reporting_level=reporting_level,
                welfare_type=welfare_type,
                poverty_line_raw=poverty_line_raw,
                raw_cell=_coerce_text_cell(poverty_gap_cell),
                asset_id=asset_id,
                cache_path=cache_path,
                row_index=row_index,
                attribution_text=attribution_text,
                optional_extension=optional_extension,
            ),
        )

        # Indicator 3: Gini index of the row's distribution.
        # Blank / non-numeric cells emit
        # ``value_type="missing"`` plus the verbatim raw cell
        # text.
        observations.append(
            _emit_indicator_observation(
                request,
                indicator_code=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_GINI
                ),
                unit=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_UNIT
                ),
                scale=(
                    WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_GINI_SCALE
                ),
                raw_column_label="gini",
                country_code_raw=country_code_raw,
                country_name=country_name,
                row_year=canonical_year,
                reporting_level=reporting_level,
                welfare_type=welfare_type,
                poverty_line_raw=poverty_line_raw,
                raw_cell=_coerce_text_cell(gini_cell),
                asset_id=asset_id,
                cache_path=cache_path,
                row_index=row_index,
                attribution_text=attribution_text,
                optional_extension=optional_extension,
            ),
        )

    return iter(observations)


def required_columns() -> tuple[str, ...]:
    """Return the canonical required CSV / JSON columns.

    Re-exported here so the transform layer can validate the
    parsed header against the same set the readiness gate
    enforces.
    """
    return WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_REQUIRED_COLUMNS


def indicator_codes() -> tuple[str, ...]:
    """Return the canonical 3-indicator catalog."""
    return WORLD_BANK_POVERTY_INEQUALITY_PLATFORM_INDICATOR_CODES


__all__ = [
    "emit_world_bank_poverty_inequality_platform_observations",
    "indicator_codes",
    "required_columns",
]
