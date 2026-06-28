"""Transform CTBTO Treaty Status rows into normalized observations.

This module owns the per-row :class:`NormalizedObservation`
build loop for the unified CTBTO Treaty Status adapter. The
function takes the parsed row-level frame returned by
:func:`._raw_read.read_ctbto_treaty_status_cache` and emits
one observation per cached State row + source-derived status
indicator.

Catalog
-------

The canonical CTBTO Treaty Status catalog carries 2
source-derived status indicators (one per date-bearing column
in the cached CTBTO States Signatories export):

- ``ctbto_treaty_status_signature_status`` -- the source-
  derived signature status: ``"signed"`` iff a signature
  date is present in the cached row, ``"not_signed"``
  otherwise. The adapter NEVER invents a signature status
  from empty / blank date cells -- an empty signature date
  cell is treated as ``"not_signed"`` per the canonical CTBTO
  page semantics.
- ``ctbto_treaty_status_ratification_status`` -- the source-
  derived ratification status: ``"ratified"`` iff a
  ratification date is present in the cached row,
  ``"not_ratified"`` otherwise. The adapter NEVER invents a
  ratification status from empty / blank date cells.

The catalog deliberately does NOT include a default
``ctbto_treaty_status_annex_2_status`` indicator: the
canonical CTBTO States Signatories page does NOT carry an
Annex 2 flag column (Annex 2 refers to the 44 States that the
CTBTO PrepCom identified as needing to ratify the CTBT for
the Treaty to enter into force, but the public table does NOT
surface an Annex 2 status column); the adapter never invents
an Annex 2 flag from missing source-native data. When the
cached fixture / source-native data carries an explicit Annex
2 flag column the adapter emits an OPTIONAL per-row Annex 2
observation, but the default 2-indicator catalog does NOT
include the Annex 2 indicator.

The catalog is preserved on
:data:`CTBTO_TREATY_STATUS_INDICATOR_CODES` so downstream
query code can filter by indicator without consulting the
per-source catalog.

Source-native preservation
--------------------------

The transform preserves the source-native State display name
verbatim on every emitted observation's
``extension["ctbto_treaty_status_state"]`` field and the
source-native Region display name on
``extension["ctbto_treaty_status_region"]``. The signature /
ratification date cells are preserved verbatim as strings on
``extension["ctbto_treaty_status_signature_date_raw"]`` /
``extension["ctbto_treaty_status_ratification_date_raw"]``
(the adapter does NOT coerce them to numeric years that
could mislead Stage 11 confidence calculations). The unified
adapter does NOT invent ISO3 country codes (the CTBTO States
Signatories page uses CTBTO's own State display names, which
are NOT ISO3); ``country_code`` / ``leader_id`` /
``leader_name`` remain ``None`` until later matching /
resolution stages introduce a canonical ISO3 mapping.

Per-indicator value typing
--------------------------

The 2 status-flag indicators
(``ctbto_treaty_status_signature_status``,
``ctbto_treaty_status_ratification_status``) emit
``value_type="categorical"`` with the source-derived status
sentinel preserved on ``value`` (no string normalization that
loses provenance). Empty / blank date cells emit
``value="not_signed"`` / ``value="not_ratified"`` plus the
verbatim raw date cell text on ``extension.raw_value`` so
audit code can recover the original cell.

Attribution
-----------

Every emitted observation carries the canonical attribution
text from :data:`CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT` on
``extension["attribution"]`` so the Stage 15 summary report
and the manual-review queue can propagate the attribution
forward (Always-On Rule #15). The descriptor's
``coverage_hint.notes`` carries the explicit caveat that
this source captures treaty-status evidence and is NOT
direct proof of nuclear behaviour, compliance, or
non-compliance.
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
    CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT,
    CTBTO_TREATY_STATUS_COVERAGE_YEAR,
    CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_CODES,
    CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS,
    CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS,
    CTBTO_TREATY_STATUS_OBSERVATION_FAMILY,
    CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN,
    CTBTO_TREATY_STATUS_SNAPSHOT_DATE,
    CTBTO_TREATY_STATUS_SOURCE_KEY,
    CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED,
    CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED,
    CTBTO_TREATY_STATUS_STATUS_RATIFIED,
    CTBTO_TREATY_STATUS_STATUS_SCALE,
    CTBTO_TREATY_STATUS_STATUS_SIGNED,
    CTBTO_TREATY_STATUS_STATUS_UNIT,
    CTBTO_TREATY_STATUS_TRANSFORM_NAME,
)


def _country_matches(
    request: SourceIngestRequest,
    state: str,
) -> bool:
    """Return True iff the row's state matches any case-folded
    substring in ``request.countries``.

    The cached CTBTO States Signatories page uses CTBTO's own
    State display names, which are NOT ISO3; the unified
    adapter never invents ISO3 codes. The filter is a
    case-folded substring match against the source-native
    display name so callers can filter for "CTBT signature /
    ratification status of State A" by passing
    ``countries=("State A",)``.
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
    """Return True iff ANY requested year is in-coverage for the
    CTBTO Treaty Status single-year 2024 envelope.

    The CTBTO States Signatories page is a single-point
    treaty-status snapshot (the canonical probed stamp is
    "status as of 13 March 2024"). The descriptor advertises
    ``start_year == end_year == 2024``. A request with
    ``years=None`` reads the full envelope (equivalent to
    ``years=(2024,)``); a request with explicit years where
    NO requested year falls inside the envelope emits zero
    observations (no stale-proxy fill per SRC-COV-002 /
    SRC-COV-003 -- the readiness envelope surfaces a
    structured ``YEAR_ABSENT`` warning per out-of-coverage
    year so the operator can see the gap).

    For a mixed request such as ``years=(2023, 2024)`` the
    helper returns ``True`` because the ``2024`` year is in
    coverage -- the transform emits the full observation set
    for the snapshot year and the readiness envelope
    surfaces a single ``YEAR_ABSENT`` warning for the
    out-of-coverage ``2023`` year. This is intentionally
    permissive at the row level (the source is a single-year
    snapshot so every observation is dated 2024) while
    strict at the per-year level (the readiness envelope
    flags every out-of-coverage year individually so the
    operator can see the temporal-fit gap).
    """
    if not request.years:
        return True
    return any(
        int(y) == CTBTO_TREATY_STATUS_COVERAGE_YEAR
        for y in request.years
    )


def _coerce_text_cell(cell: Any) -> str:
    """Return the cell text as a stripped ``str``.

    Used for the Region / State columns and the signature /
    ratification date cells. The helper coerces ``None`` /
    ``str`` / non-string cells to a stripped ``str`` so the
    transform layer can branch on string sentinels.
    """
    if cell is None:
        return ""
    if isinstance(cell, str):
        return cell.strip()
    return str(cell).strip()


def _signature_status_from_cell(date_cell: str) -> str:
    """Return the source-derived signature status sentinel.

    ``"signed"`` iff ``date_cell`` is a non-empty string;
    ``"not_signed"`` otherwise. The helper never inverts this
    rule -- an empty / blank signature date cell is ALWAYS
    treated as ``"not_signed"`` per the canonical CTBTO page
    semantics, and the transform layer does NOT invent a
    signature status from empty / blank date cells.
    """
    if date_cell.strip():
        return CTBTO_TREATY_STATUS_STATUS_SIGNED
    return CTBTO_TREATY_STATUS_STATUS_NOT_SIGNED


def _ratification_status_from_cell(date_cell: str) -> str:
    """Return the source-derived ratification status sentinel.

    ``"ratified"`` iff ``date_cell`` is a non-empty string;
    ``"not_ratified"`` otherwise. The helper never inverts
    this rule -- an empty / blank ratification date cell is
    ALWAYS treated as ``"not_ratified"`` per the canonical
    CTBTO page semantics, and the transform layer does NOT
    invent a ratification status from empty / blank date
    cells.
    """
    if date_cell.strip():
        return CTBTO_TREATY_STATUS_STATUS_RATIFIED
    return CTBTO_TREATY_STATUS_STATUS_NOT_RATIFIED


def _build_status_observation(
    request: SourceIngestRequest,
    *,
    indicator_code: str,
    state: str,
    region: str,
    status_value: str,
    raw_date_cell: str,
    raw_column_label: str,
    annex_2_cell: str | None,
    source_row_reference: str,
    asset_id: str,
    cache_path: Path | None,
    row_index: int,
) -> NormalizedObservation:
    """Build one ``nuclear_treaty_status_country`` observation.

    The helper emits the canonical signature / ratification
    status observations (and the optional Annex 2 status
    observation when ``annex_2_cell`` is not ``None`` -- i.e.
    the cached fixture / source-native data carries an
    explicit Annex 2 flag column).
    """
    raw_locator = RawLocator(
        asset_id=asset_id,
        path=str(cache_path) if cache_path is not None else None,
        column_name=raw_column_label,
        row_number=row_index,
    )
    transform_locator = TransformLocator(
        adapter_version=None,
        transform_name=CTBTO_TREATY_STATUS_TRANSFORM_NAME,
        catalog_key=CTBTO_TREATY_STATUS_SOURCE_KEY,
        rule_id=source_row_reference,
    )
    extension: dict[str, JsonScalar] = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_date_cell,
        "normalized_value": status_value,
        "ctbto_treaty_status_state": state,
        "ctbto_treaty_status_region": region,
        "ctbto_treaty_status_signature_date_raw": "",
        "ctbto_treaty_status_ratification_date_raw": "",
        "ctbto_treaty_status_snapshot_date": (
            CTBTO_TREATY_STATUS_SNAPSHOT_DATE
        ),
        "ctbto_treaty_status_raw_column": raw_column_label,
        "ctbto_treaty_status_raw_value_cell": raw_date_cell,
        "attribution": CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT,
    }
    if indicator_code == CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS:
        extension["ctbto_treaty_status_signature_date_raw"] = (
            raw_date_cell
        )
    elif (
        indicator_code == CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS
    ):
        extension["ctbto_treaty_status_ratification_date_raw"] = (
            raw_date_cell
        )
    elif indicator_code == CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS:
        # The Annex 2 observation carries the Annex 2 flag value
        # verbatim on the audit-trail extension payload; the
        # transformed status sentinel is preserved on the
        # normalised value field. The transform layer never
        # invents an Annex 2 flag from missing source-native
        # data; this branch is only reached when the cached
        # fixture / source-native data carries an explicit
        # ``Annex 2`` column.
        extension["ctbto_treaty_status_annex_2_raw"] = annex_2_cell or ""
        extension["ctbto_treaty_status_signature_date_raw"] = ""
        extension["ctbto_treaty_status_ratification_date_raw"] = ""
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=source_row_reference,
        observation_family=CTBTO_TREATY_STATUS_OBSERVATION_FAMILY,
        indicator_code=indicator_code,
        value=status_value,
        value_type="categorical",
        year=CTBTO_TREATY_STATUS_COVERAGE_YEAR,
        country_code=None,
        country_name=state,
        leader_id=None,
        leader_name=None,
        unit=CTBTO_TREATY_STATUS_STATUS_UNIT,
        scale=CTBTO_TREATY_STATUS_STATUS_SCALE,
        source_version=CTBTO_TREATY_STATUS_DEFAULT_VERSION,
        raw_locator=raw_locator,
        transform_locator=transform_locator,
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def emit_ctbto_treaty_status_observations(
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
    (``2024``); a request where NO requested year falls
    inside the envelope (e.g. ``years=(2023,)`` -- the
    prototype's target year) emits zero observations AND a
    structured ``YEAR_ABSENT`` warning on the readiness
    envelope (no stale-proxy fill per SRC-COV-002 /
    SRC-COV-003). A mixed request such as
    ``years=(2023, 2024)`` still emits the full observation
    set because the source is a single-year 2024 snapshot
    (every observation is dated 2024) and the readiness
    envelope surfaces a single ``YEAR_ABSENT`` warning for
    the out-of-coverage ``2023`` year so the operator can
    see the temporal-fit gap. ``request.leaders`` is
    unsupported for a country-level treaty-status source and
    surfaces a structured ``UNSUPPORTED_FILTER`` warning
    (SRC-REQ-005).

    Per-row emission: each parsed row produces up to 2
    observations (one per source-derived catalog indicator --
    signature status + ratification status). When the cached
    fixture / source-native data carries an explicit Annex 2
    flag column, the transform emits an OPTIONAL 3rd Annex 2
    observation per row, but the default 2-indicator catalog
    does NOT include the Annex 2 indicator. Empty signature /
    ratification date cells emit
    ``value="not_signed"`` / ``value="not_ratified"`` plus
    the verbatim raw date cell text on ``extension.raw_value``
    -- the transform layer does NOT invent a signature /
    ratification status from empty / blank date cells.

    The transform layer never invents ISO3 country codes,
    leader identifiers, missing values, or proxy years. The
    source-native state display name is preserved verbatim on
    every emitted observation's
    ``extension["ctbto_treaty_status_state"]`` field. Raw
    signature / ratification dates are preserved verbatim as
    strings on the audit-trail extension payload (no numeric
    coercion that could mislead Stage 11 confidence
    calculations).
    """
    observations: list[NormalizedObservation] = []

    # When NO requested year is in-coverage, emit zero
    # observations (no stale-proxy fill per SRC-COV-002 /
    # SRC-COV-003). The readiness envelope surfaces a
    # structured ``YEAR_ABSENT`` warning per out-of-coverage
    # year so the operator can see the gap. A mixed request
    # such as ``years=(2023, 2024)`` still proceeds because
    # the source is a single-year 2024 snapshot and the
    # ``2024`` year is in-coverage -- the warning is emitted
    # on the readiness envelope for the ``2023`` year only.
    if not _year_in_coverage(request):
        return iter(())

    for row_index, row in enumerate(rows, start=2):
        # The cached CTBTO States Signatories CSV / HTML
        # routes each parsed row into a dict keyed by the
        # documented column names; missing optional columns
        # default to ``""`` so the per-cell coercion below
        # always sees a string.
        region = _coerce_text_cell(row.get("Region"))
        state = _coerce_text_cell(row.get("State"))
        signature_date_cell = _coerce_text_cell(
            row.get("Signature Date"),
        )
        ratification_date_cell = _coerce_text_cell(
            row.get("Ratification Date"),
        )
        annex_2_cell = row.get(CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN)
        if annex_2_cell is not None:
            annex_2_cell = _coerce_text_cell(annex_2_cell)

        if not _country_matches(request, state):
            continue
        if not state:
            # Defensive: skip empty state labels (the canonical
            # CTBTO export never carries an empty State row,
            # but a user-edited cache might).
            continue

        # Build a stable, per-indicator source_row_reference
        # for each (row, indicator) pair. The reference is
        # ``ctbto_treaty_status:row_<row_index>:<indicator_code>:<state>``
        # so:
        #
        # 1. every emitted observation has a UNIQUE
        #    ``observation_id`` (signature, ratification, and
        #    the optional Annex 2 observation for the same
        #    row no longer collide on a shared
        #    ``source_row_reference``);
        # 2. audit code can group the per-indicator
        #    observations per row via the stable
        #    ``ctbto_treaty_status:row_<row_index>:`` prefix;
        # 3. the per-indicator suffix
        #    ``:<indicator_code>:<state>`` is enough to
        #    reconstruct the raw column label from the
        #    indicator code on the audit trail.
        #
        # The raw column label is also propagated on
        # ``extension["ctbto_treaty_status_raw_column"]`` and
        # ``raw_locator.column_name`` so audit code can
        # recover the exact source-native column without
        # parsing the indicator code suffix.
        signature_source_row_reference = (
            f"{CTBTO_TREATY_STATUS_SOURCE_KEY}:row_{row_index}:"
            f"{CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS}:"
            f"{state}"
        )
        ratification_source_row_reference = (
            f"{CTBTO_TREATY_STATUS_SOURCE_KEY}:row_{row_index}:"
            f"{CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS}:"
            f"{state}"
        )
        annex_2_source_row_reference = (
            f"{CTBTO_TREATY_STATUS_SOURCE_KEY}:row_{row_index}:"
            f"{CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS}:"
            f"{state}"
        )

        # Indicator 1: signature status. The signature status
        # is ``"signed"`` iff the signature date cell is
        # non-empty, ``"not_signed"`` otherwise. The transform
        # never inverts this rule -- an empty / blank signature
        # date cell is ALWAYS treated as ``"not_signed"``.
        signature_status = _signature_status_from_cell(
            signature_date_cell,
        )
        observations.append(
            _build_status_observation(
                request,
                indicator_code=(
                    CTBTO_TREATY_STATUS_INDICATOR_SIGNATURE_STATUS
                ),
                state=state,
                region=region,
                status_value=signature_status,
                raw_date_cell=signature_date_cell,
                raw_column_label="Signature Date",
                annex_2_cell=None,
                source_row_reference=signature_source_row_reference,
                asset_id=asset_id,
                cache_path=cache_path,
                row_index=row_index,
            ),
        )

        # Indicator 2: ratification status. The ratification
        # status is ``"ratified"`` iff the ratification date
        # cell is non-empty, ``"not_ratified"`` otherwise. The
        # transform never inverts this rule -- an empty /
        # blank ratification date cell is ALWAYS treated as
        # ``"not_ratified"``.
        ratification_status = _ratification_status_from_cell(
            ratification_date_cell,
        )
        observations.append(
            _build_status_observation(
                request,
                indicator_code=(
                    CTBTO_TREATY_STATUS_INDICATOR_RATIFICATION_STATUS
                ),
                state=state,
                region=region,
                status_value=ratification_status,
                raw_date_cell=ratification_date_cell,
                raw_column_label="Ratification Date",
                annex_2_cell=None,
                source_row_reference=ratification_source_row_reference,
                asset_id=asset_id,
                cache_path=cache_path,
                row_index=row_index,
            ),
        )

        # Optional Indicator 3: Annex 2 status. The canonical
        # CTBTO page does NOT carry an Annex 2 flag column;
        # the adapter only emits the Annex 2 observation when
        # the cached fixture / source-native data carries an
        # explicit ``Annex 2`` column. The transform layer
        # never invents an Annex 2 flag from missing
        # source-native data -- this branch is only reached
        # when the parsed row has the ``Annex 2`` key.
        if annex_2_cell is not None:
            # When the Annex 2 cell is non-empty the Annex 2
            # status is ``"in_annex_2"``; when empty the
            # status is ``"not_in_annex_2"``. The transform
            # never inverts this rule -- an empty / blank
            # Annex 2 cell is ALWAYS treated as
            # ``"not_in_annex_2"``.
            annex_2_status = (
                "in_annex_2"
                if annex_2_cell.strip()
                else "not_in_annex_2"
            )
            observations.append(
                _build_status_observation(
                    request,
                    indicator_code=(
                        CTBTO_TREATY_STATUS_INDICATOR_ANNEX_2_STATUS
                    ),
                    state=state,
                    region=region,
                    status_value=annex_2_status,
                    raw_date_cell=annex_2_cell,
                    raw_column_label=(
                        CTBTO_TREATY_STATUS_OPTIONAL_ANNEX_2_COLUMN
                    ),
                    annex_2_cell=annex_2_cell,
                    source_row_reference=annex_2_source_row_reference,
                    asset_id=asset_id,
                    cache_path=cache_path,
                    row_index=row_index,
                ),
            )

    return iter(observations)


def required_columns() -> tuple[str, ...]:
    """Return the canonical required CSV / HTML table columns.

    Re-exported here so the transform layer can validate the
    parsed header against the same set the readiness gate
    enforces.
    """
    from ._constants import CTBTO_TREATY_STATUS_REQUIRED_COLUMNS
    return CTBTO_TREATY_STATUS_REQUIRED_COLUMNS


def indicator_codes() -> tuple[str, ...]:
    """Return the canonical 2-indicator catalog."""
    return CTBTO_TREATY_STATUS_INDICATOR_CODES


__all__ = [
    "emit_ctbto_treaty_status_observations",
    "indicator_codes",
    "required_columns",
]
