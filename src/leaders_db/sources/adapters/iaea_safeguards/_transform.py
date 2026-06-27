"""Transform IAEA Safeguards status-list rows into normalized observations.

This module owns the per-row :class:`NormalizedObservation` build
loop for the unified IAEA Safeguards status-list adapter. The
function takes the parsed row-level frame returned by
:func:`._raw_read.read_iaea_safeguards_pdf` and emits one
observation per cached country row + indicator.

Catalog
-------

The canonical IAEA Safeguards status-list catalog carries 4
source-native indicator codes (one per non-State column in the
cached PDF table):

- ``iaea_safeguards_safeguards_agreement_status`` -- the
  Composite status of a Comprehensive Safeguards Agreement
  (CSA) for the State (e.g. ``In Force: 153`` /
  ``Not in Force: 66`` / ``N/A``).
- ``iaea_safeguards_infcirc_number`` -- the INFCIRC document
  identifier (e.g. ``INFCIRC/153`` / ``INFCIRC/540`` / blank
  for non-States).
- ``iaea_safeguards_additional_protocol_status`` -- the
  Additional Protocol (AP) status label (e.g. ``Signed`` /
  ``Approved`` / ``In Force`` / ``Not in Force`` / ``Not Signed``
  / ``N/A``).
- ``iaea_safeguards_small_quantities_protocol_status`` -- the
  Small Quantities Protocol (SQP) status label (e.g.
  ``Modified`` / ``Original`` / ``Not applicable`` /
  ``Not in Force``).

The catalog deliberately does NOT include a separate
``iaea_safeguards_safeguards_agreement_type`` indicator: the
canonical IAEA table has a single ``Safeguards Agreement``
column carrying the composite status label (e.g. ``In Force:
153`` / ``Not in Force: 66`` / ``N/A``), NOT a separate type
column. The adapter never invents a separate type indicator
from the composite label.

The catalog is preserved on :data:`IAEA_SAFEGUARDS_INDICATOR_CODES`
so downstream query code can filter by indicator without
consulting the per-source catalog.

Source-native preservation
-------------------------

The transform preserves the source-native country display name
verbatim on every emitted observation's
``extension["iaea_safeguards_state"]`` field and the verbatim
source-native cell labels on the
``extension["iaea_safeguards_<cell_type>_raw"]`` fields. The
unified adapter does NOT invent ISO3 country codes (the IAEA
Safeguards Status List uses IAEA's own country display names,
which are NOT ISO3); ``country_code`` / ``leader_id`` /
``leader_name`` remain ``None`` until later matching /
resolution stages introduce a canonical ISO3 mapping.

Per-row page provenance
-----------------------

Every parsed row dict carries a ``page_number`` key (1-based)
set by the raw-read layer; the transform reads it and forwards
it to the :class:`NormalizedObservation`
``RawLocator.page_number`` field so audit code can recover the
exact page the row originated from. For multi-page PDFs the
per-row page provenance is preserved verbatim on every emitted
observation.

Per-indicator value typing
-------------------------

The 3 cell-label indicators (``safeguards_agreement_status``,
``additional_protocol_status``,
``small_quantities_protocol_status``) emit
``value_type="categorical"`` with the source-native cell label
preserved on ``value`` (no string normalization that loses
provenance). The ``infcirc_number`` indicator emits
``value_type="categorical"`` with the source-native INFCIRC
identifier (e.g. ``"INFCIRC/153"``) preserved on ``value``.
Empty cells (e.g. blank INFCIRC for non-States) emit
``value=None`` / ``value_type="missing"`` plus the verbatim
raw cell text on ``extension.raw_value`` so audit code can
recover the original cell.

Attribution
-----------

Every emitted observation carries the canonical attribution
text from :data:`IAEA_SAFEGUARDS_ATTRIBUTION_TEXT` on
``extension["attribution"]`` so the Stage 15 summary report
and the manual-review queue can propagate the attribution
forward (Always-On Rule #15). The descriptor's
``coverage_hint.notes`` carries the explicit caveat that this
source captures safeguards / legal / status evidence and is NOT
a direct nuclear-weapons score or proof of safeguards
compliance / non-compliance by itself.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    IAEA_SAFEGUARDS_ATTRIBUTION_TEXT,
    IAEA_SAFEGUARDS_COVERAGE_YEAR,
    IAEA_SAFEGUARDS_DEFAULT_VERSION,
    IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_CODES,
    IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER,
    IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS,
    IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS,
    IAEA_SAFEGUARDS_INFCIRC_SCALE,
    IAEA_SAFEGUARDS_INFCIRC_UNIT,
    IAEA_SAFEGUARDS_OBSERVATION_FAMILY,
    IAEA_SAFEGUARDS_REQUIRED_COLUMNS,
    IAEA_SAFEGUARDS_SOURCE_KEY,
    IAEA_SAFEGUARDS_TEXT_SCALE,
    IAEA_SAFEGUARDS_TEXT_UNIT,
    IAEA_SAFEGUARDS_TRANSFORM_NAME,
)

# The canonical column -> indicator code mapping. The transform
# iterates this dict so the catalog is data-driven and the
# 4-indicator catalog lives in one place. The mapping preserves
# the canonical PDF column names verbatim; the indicator codes
# are stable identifiers exposed on the per-observation payload.
_COLUMN_TO_INDICATOR: dict[str, str] = {
    "Safeguards Agreement": (
        IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS
    ),
    "INFCIRC": IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER,
    "Additional Protocol": (
        IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS
    ),
    "Small Quantities Protocol": (
        IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS
    ),
}


def _country_matches(
    request: SourceIngestRequest,
    state: str,
) -> bool:
    """Return True iff the row's state matches any case-folded
    substring in ``request.countries``.

    The cached IAEA Safeguards Status List uses IAEA's own
    country display names, which are NOT ISO3; the unified
    adapter never invents ISO3 codes. The filter is a
    case-folded substring match against the source-native
    display name so callers can filter for "Safeguards status
    of State A" by passing ``countries=("State A",)``.
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
    haystack = state.casefold()
    return any(needle in haystack for needle in needles)


def _year_in_coverage(request: SourceIngestRequest) -> bool:
    """Return True iff the request is in-coverage for the IAEA
    Safeguards single-year 2025 envelope.

    The IAEA Safeguards Status List is a single-point legal
    / status snapshot (the canonical probed stamp is "status
    as of 31 December 2025"). The descriptor advertises
    ``start_year == end_year == 2025``. A request with
    ``years=None`` reads the full envelope (equivalent to
    ``years=(2025,)``); a request with explicit years that
    falls outside the envelope emits zero observations (no
    stale-proxy fill per SRC-COV-002 / SRC-COV-003 -- the
    readiness envelope surfaces a structured ``YEAR_ABSENT``
    warning so the operator can see the gap).
    """
    if not request.years:
        return True
    return all(
        IAEA_SAFEGUARDS_COVERAGE_YEAR in (int(y),)
        for y in request.years
    )


def _coerce_text_cell(cell: Any) -> str:
    """Return the cell text as a stripped ``str``.

    Used for the 4 cell-label columns (Safeguards Agreement /
    Additional Protocol / Small Quantities Protocol) and for the
    State column. The helper coerces ``None`` / ``str`` /
    non-string cells to a stripped ``str`` so the transform layer
    can branch on string sentinels.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip()
    return str(cell).strip()


def _json_scalar(value: Any) -> JsonScalar:
    """Convert a raw cell value to a :class:`JsonScalar`.

    Mirrors the SIPRI Milex / SIPRI Yearbook Ch.7 / CIRIGHTS
    pattern: ``None`` returns ``None``; numbers return
    ``int`` / ``float``; everything else is coerced via
    ``str(value).strip()`` for the audit-trail extension
    payload.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _build_observation(
    request: SourceIngestRequest,
    *,
    indicator_code: str,
    state: str,
    raw_value: JsonScalar,
    normalized_value: JsonScalar,
    value_type: str,
    unit: str | None,
    scale: str | None,
    raw_value_cell: str,
    raw_column_label: str,
    safeguard_status_cell: str,
    infcirc_cell: str,
    additional_protocol_cell: str,
    small_quantities_protocol_cell: str,
    source_row_reference: str,
    asset_id: str,
    cache_path: Path | None,
    row_index: int,
    page_number: int | None,
) -> NormalizedObservation:
    """Build one ``nuclear_safeguards_status_country`` observation."""
    raw_locator = RawLocator(
        asset_id=asset_id,
        path=str(cache_path) if cache_path is not None else None,
        column_name=raw_column_label,
        row_number=row_index,
        page_number=page_number,
    )
    transform_locator = TransformLocator(
        adapter_version=None,
        transform_name=IAEA_SAFEGUARDS_TRANSFORM_NAME,
        catalog_key=IAEA_SAFEGUARDS_SOURCE_KEY,
        rule_id=source_row_reference,
    )
    extension: dict[str, JsonScalar] = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "iaea_safeguards_state": state,
        "iaea_safeguards_safeguards_agreement_status_raw": (
            safeguard_status_cell
        ),
        "iaea_safeguards_infcirc_raw": infcirc_cell,
        "iaea_safeguards_additional_protocol_status_raw": (
            additional_protocol_cell
        ),
        "iaea_safeguards_small_quantities_protocol_status_raw": (
            small_quantities_protocol_cell
        ),
        "iaea_safeguards_status_date": (
            request.source_version  # canonical status-date stamp
            if request.source_version is not None
            else IAEA_SAFEGUARDS_DEFAULT_VERSION
        ),
        "iaea_safeguards_raw_column": raw_column_label,
        "iaea_safeguards_raw_value_cell": raw_value_cell,
        "page_number": page_number,
        "attribution": IAEA_SAFEGUARDS_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=source_row_reference,
        observation_family=IAEA_SAFEGUARDS_OBSERVATION_FAMILY,
        indicator_code=indicator_code,
        value=normalized_value,
        value_type=value_type,  # type: ignore[arg-type]
        year=IAEA_SAFEGUARDS_COVERAGE_YEAR,
        country_code=None,
        country_name=state,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=scale,
        source_version=IAEA_SAFEGUARDS_DEFAULT_VERSION,
        raw_locator=raw_locator,
        transform_locator=transform_locator,
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _build_infcirc_observation(
    request: SourceIngestRequest,
    *,
    state: str,
    infcirc_cell: str,
    source_row_reference: str,
    asset_id: str,
    cache_path: Path | None,
    safeguard_status_cell: str,
    additional_protocol_cell: str,
    small_quantities_protocol_cell: str,
    row_index: int,
    page_number: int | None,
) -> NormalizedObservation:
    """Build the ``iaea_safeguards_infcirc_number`` observation.

    The INFCIRC indicator emits ``value_type="categorical"``
    with the source-native identifier (e.g. ``"INFCIRC/153"``)
    preserved on ``value``. An empty INFCIRC cell (e.g. for
    non-States) emits ``value=None`` /
    ``value_type="missing"`` plus the verbatim raw cell text on
    ``extension.raw_value``.
    """
    raw_value = _json_scalar(infcirc_cell)
    normalized_value = raw_value if raw_value else None
    value_type = "categorical" if normalized_value else "missing"
    return _build_observation(
        request,
        indicator_code=IAEA_SAFEGUARDS_INDICATOR_INFCIRC_NUMBER,
        state=state,
        raw_value=raw_value,
        normalized_value=normalized_value,
        value_type=value_type,
        unit=IAEA_SAFEGUARDS_INFCIRC_UNIT,
        scale=IAEA_SAFEGUARDS_INFCIRC_SCALE,
        raw_value_cell=infcirc_cell,
        raw_column_label="INFCIRC",
        safeguard_status_cell=safeguard_status_cell,
        infcirc_cell=infcirc_cell,
        additional_protocol_cell=additional_protocol_cell,
        small_quantities_protocol_cell=small_quantities_protocol_cell,
        source_row_reference=(
            f"{source_row_reference}:infcirc"
        ),
        asset_id=asset_id,
        cache_path=cache_path,
        row_index=row_index,
        page_number=page_number,
    )


def _build_cell_observation(
    request: SourceIngestRequest,
    *,
    indicator_code: str,
    state: str,
    cell_text: str,
    raw_column_label: str,
    source_row_reference: str,
    asset_id: str,
    cache_path: Path | None,
    safeguard_status_cell: str,
    infcirc_cell: str,
    additional_protocol_cell: str,
    small_quantities_protocol_cell: str,
    row_index: int,
    page_number: int | None,
) -> NormalizedObservation:
    """Build a non-INFCIRC cell observation (3 cell-label
    indicators).

    The helper handles the 3 string-cell indicators
    (``safeguards_agreement_status``,
    ``additional_protocol_status``,
    ``small_quantities_protocol_status``). An empty cell
    emits ``value=None`` / ``value_type="missing"`` plus the
    verbatim raw cell text on ``extension.raw_value`` (the
    observation is NOT dropped -- audit code can recover the
    upstream gap via the raw_value field).
    """
    raw_value = _json_scalar(cell_text)
    normalized_value = raw_value if raw_value else None
    value_type = "categorical" if normalized_value else "missing"
    suffix = indicator_code.replace(
        "iaea_safeguards_", "",
    )
    return _build_observation(
        request,
        indicator_code=indicator_code,
        state=state,
        raw_value=raw_value,
        normalized_value=normalized_value,
        value_type=value_type,
        unit=IAEA_SAFEGUARDS_TEXT_UNIT,
        scale=IAEA_SAFEGUARDS_TEXT_SCALE,
        raw_value_cell=cell_text,
        raw_column_label=raw_column_label,
        safeguard_status_cell=safeguard_status_cell,
        infcirc_cell=infcirc_cell,
        additional_protocol_cell=additional_protocol_cell,
        small_quantities_protocol_cell=small_quantities_protocol_cell,
        source_row_reference=(
            f"{source_row_reference}:{suffix}"
        ),
        asset_id=asset_id,
        cache_path=cache_path,
        row_index=row_index,
        page_number=page_number,
    )


def emit_iaea_safeguards_observations(
    request: SourceIngestRequest,
    rows: list[dict[str, str]],
    *,
    cache_path: Path | None,
    asset_id: str,
) -> Iterable[NormalizedObservation]:
    """Convert the parsed row-level frame into
    :class:`NormalizedObservation` records.

    Honors ``request.years`` and ``request.countries`` by
    filtering the parsed row-level frame on the transform
    side. The descriptor advertises a single-year envelope
    (``2025``); an out-of-coverage year request (e.g.
    ``years=(2023,)`` -- the prototype's target year) emits
    zero observations AND a structured ``YEAR_ABSENT`` warning
    on the readiness envelope (no stale-proxy fill per
    SRC-COV-002 / SRC-COV-003). ``request.leaders`` is
    unsupported for a country-level safeguards status source
    and surfaces a structured ``UNSUPPORTED_FILTER`` warning
    (SRC-REQ-005).

    Per-row emission: each parsed row produces up to 4
    observations (one per source-native catalog indicator --
    the 3 cell-label indicators + the INFCIRC indicator).
    Empty cells emit ``value=None`` /
    ``value_type='missing'`` plus the verbatim raw cell text on
    ``extension.raw_value``.

    The transform layer never invents ISO3 country codes,
    leader identifiers, missing values, or proxy years. The
    source-native state display name is preserved verbatim on
    every emitted observation's
    ``extension["iaea_safeguards_state"]`` field.

    Per-row page provenance
    ------------------------

    The raw-read layer stamps each parsed row dict with a
    ``page_number`` key (1-based). The transform reads the key
    and forwards it to the :class:`NormalizedObservation`
    ``RawLocator.page_number`` field so audit code can recover
    the exact page the row originated from. Multi-page PDFs
    paginate country rows across pages; the per-row page
    provenance is preserved verbatim on every emitted
    observation.
    """
    observations: list[NormalizedObservation] = []

    # Out-of-coverage year requests emit zero observations
    # (no stale-proxy fill per SRC-COV-002 / SRC-COV-003).
    # The readiness envelope surfaces a structured
    # ``YEAR_ABSENT`` warning so the operator can see the gap.
    if not _year_in_coverage(request):
        return iter(())

    for row_index, row in enumerate(rows, start=2):
        # The pdfplumber reader routes each parsed row into a
        # dict keyed by the documented column names; missing
        # optional columns default to ``""`` so the per-cell
        # coercion below always sees a string.
        state = _coerce_text_cell(row.get("State"))
        safeguard_status_cell = _coerce_text_cell(
            row.get("Safeguards Agreement"),
        )
        infcirc_cell = _coerce_text_cell(row.get("INFCIRC"))
        additional_protocol_cell = _coerce_text_cell(
            row.get("Additional Protocol"),
        )
        small_quantities_protocol_cell = _coerce_text_cell(
            row.get("Small Quantities Protocol"),
        )

        # The raw-read layer stamps each parsed row with a
        # ``page_number`` key (1-based, matching pdfplumber
        # ``page_number`` semantics). The transform forwards
        # the per-row page provenance to the
        # :class:`NormalizedObservation`
        # ``RawLocator.page_number`` field so audit code can
        # recover the exact page the row originated from.
        # The raw-read layer guarantees every parsed row
        # carries a non-empty ``page_number`` string.
        row_page_raw = row.get("page_number", "")
        try:
            row_page = int(row_page_raw)
        except (TypeError, ValueError):
            row_page = 1

        if not _country_matches(request, state):
            continue
        if not state:
            # Defensive: skip empty state labels (the canonical
            # IAEA export never carries an empty State row, but
            # a user-edited cache might).
            continue

        # Build a stable source_row_reference for the row. The
        # reference is ``iaea_safeguards:row_<row_index>:<state>``
        # so audit code can group the 4 per-indicator
        # observations per row via a stable prefix.
        source_row_reference = (
            f"{IAEA_SAFEGUARDS_SOURCE_KEY}:row_{row_index}:"
            f"{state}"
        )

        # Indicator 1: Safeguards Agreement status.
        observations.append(
            _build_cell_observation(
                request,
                indicator_code=(
                    IAEA_SAFEGUARDS_INDICATOR_SAFEGUARDS_AGREEMENT_STATUS
                ),
                state=state,
                cell_text=safeguard_status_cell,
                raw_column_label="Safeguards Agreement",
                source_row_reference=source_row_reference,
                asset_id=asset_id,
                cache_path=cache_path,
                safeguard_status_cell=safeguard_status_cell,
                infcirc_cell=infcirc_cell,
                additional_protocol_cell=additional_protocol_cell,
                small_quantities_protocol_cell=(
                    small_quantities_protocol_cell
                ),
                row_index=row_index,
                page_number=row_page,
            ),
        )

        # Indicator 2: Additional Protocol status.
        observations.append(
            _build_cell_observation(
                request,
                indicator_code=(
                    IAEA_SAFEGUARDS_INDICATOR_ADDITIONAL_PROTOCOL_STATUS
                ),
                state=state,
                cell_text=additional_protocol_cell,
                raw_column_label="Additional Protocol",
                source_row_reference=source_row_reference,
                asset_id=asset_id,
                cache_path=cache_path,
                safeguard_status_cell=safeguard_status_cell,
                infcirc_cell=infcirc_cell,
                additional_protocol_cell=additional_protocol_cell,
                small_quantities_protocol_cell=(
                    small_quantities_protocol_cell
                ),
                row_index=row_index,
                page_number=row_page,
            ),
        )

        # Indicator 3: Small Quantities Protocol status.
        observations.append(
            _build_cell_observation(
                request,
                indicator_code=(
                    IAEA_SAFEGUARDS_INDICATOR_SMALL_QUANTITIES_PROTOCOL_STATUS
                ),
                state=state,
                cell_text=small_quantities_protocol_cell,
                raw_column_label="Small Quantities Protocol",
                source_row_reference=source_row_reference,
                asset_id=asset_id,
                cache_path=cache_path,
                safeguard_status_cell=safeguard_status_cell,
                infcirc_cell=infcirc_cell,
                additional_protocol_cell=additional_protocol_cell,
                small_quantities_protocol_cell=(
                    small_quantities_protocol_cell
                ),
                row_index=row_index,
                page_number=row_page,
            ),
        )

        # Indicator 4: INFCIRC number.
        observations.append(
            _build_infcirc_observation(
                request,
                state=state,
                infcirc_cell=infcirc_cell,
                source_row_reference=source_row_reference,
                asset_id=asset_id,
                cache_path=cache_path,
                safeguard_status_cell=safeguard_status_cell,
                additional_protocol_cell=additional_protocol_cell,
                small_quantities_protocol_cell=(
                    small_quantities_protocol_cell
                ),
                row_index=row_index,
                page_number=row_page,
            ),
        )

    return iter(observations)


def required_columns() -> tuple[str, ...]:
    """Return the canonical required PDF table columns.

    Re-exported here so the transform layer can validate the
    parsed header against the same set the readiness gate
    enforces.
    """
    return IAEA_SAFEGUARDS_REQUIRED_COLUMNS


def indicator_codes() -> tuple[str, ...]:
    """Return the canonical 4-indicator catalog."""
    return IAEA_SAFEGUARDS_INDICATOR_CODES


__all__ = [
    "emit_iaea_safeguards_observations",
    "indicator_codes",
    "required_columns",
]
