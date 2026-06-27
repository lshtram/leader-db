"""Transform SIPRI Arms Transfers rows into normalized observations.

This module owns the per-row :class:`NormalizedObservation` build
loop for the unified SIPRI Arms Transfers adapter. The function
takes the parsed row-level frame returned by
:func:`._raw_read.read_sipri_arms_transfers_csv` and emits:

1. **Per-transfer row observations** -- one observation per
   cached transfer row under the
   ``arms_transfer_register_row`` family. Each row produces up
   to 3 per-row indicator observations:
   ``sipri_arms_transfers_tiv_delivered``,
   ``sipri_arms_transfers_tiv_ordered``, and
   ``sipri_arms_transfers_number_delivered``. Rows with missing
   / blank / non-numeric TIV or number cells are emitted with
   ``value=None`` / ``value_type="missing"`` plus the verbatim
   raw cell text on ``extension.raw_value`` -- the observation
   is NOT dropped; the analyst can see the upstream gap without
   losing the observation id / locator (matches the SIPRI
   Yearbook Ch.7 / FAS / RSF / PTS defensive pattern).

2. **Per-``(role, country, year)`` aggregate observations** --
   one observation per ``(role, country, year)`` triple under
   the ``arms_transfer_country_year_aggregate`` family where
   ``role`` is ``"supplier"`` or ``"recipient"``. The aggregate
   is the deterministic sum of TIV delivered over all transfers
   in the parsed frame where the country appears as supplier
   (resp. recipient) and the delivery year matches the year.
   The aggregate scope key keeps the supplier-side and
   recipient-side aggregates separate (no double-counting when
   the same country appears as both supplier and recipient in
   the same year).

Source-native preservation
--------------------------

The transform preserves the source-native supplier and
recipient display names verbatim on the per-transfer
observations (``extension["sipri_arms_transfers_supplier"]`` /
``extension["sipri_arms_transfers_recipient"]``). The unified
adapter does NOT invent ISO3 country codes (the SIPRI Trade
Register uses SIPRI's own country display names, which are not
ISO3); ``country_code`` / ``leader_id`` / ``leader_name``
remain ``None`` until later matching / resolution stages
introduce a canonical ISO3 mapping. The aggregate observations
similarly carry the source-native display name on
``country_name`` (no ISO3 invention).

Attribution
-----------

Every emitted observation carries the canonical attribution
text from :data:`SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT` on
``extension["attribution"]`` so the Stage 15 summary report
and the manual-review queue can propagate the attribution
forward (Always-On Rule #15).
"""

from __future__ import annotations

import math
import re
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
    SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT,
    SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
    SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
    SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED,
    SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED,
    SIPRI_ARMS_TRANSFERS_NUMBER_SCALE,
    SIPRI_ARMS_TRANSFERS_NUMBER_UNIT,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE,
    SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER,
    SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS,
    SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS,
    SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
    SIPRI_ARMS_TRANSFERS_TIV_SCALE,
    SIPRI_ARMS_TRANSFERS_TIV_UNIT,
    SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME,
)

_YEAR_RE = re.compile(r"\d{4}")


def _coerce_int(value: Any) -> int | None:
    """Coerce a raw cell value to ``int`` or return ``None``.

    Handles SIPRI export quirks for both year columns AND
    count columns:

    - Plain integer (``"8"`` / ``8``) returns the int.
    - 4-digit year (``"2012"`` / ``2012``) returns the int.
    - Year range (``"2012-2014"``) returns the first 4-digit
      year (``2012``).
    - Comma-separated list (``"2012,2013,2014"``) returns the
      first 4-digit year (``2012``).
    - String sentinels (``".."`` / ``""`` / ``"?"`` / ``"n.a."``
      / ``"-"``) return ``None``.

    For year columns, callers should use
    :func:`_coerce_year` (which additionally validates the
    4-digit year envelope). For count columns (``Numbers
    delivered`` / ``Numbers ordered``), this helper returns
    the canonical int so the transform layer can emit a
    numeric observation. Non-numeric cells return ``None``
    so the transform layer emits
    ``value=None`` / ``value_type="missing"`` plus the
    verbatim raw cell text.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            return int(value)
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text in {"-", "..", "...", "?", "n.a.", "na", "nil"}:
        return None
    # Try a direct int() parse first (handles "8", "876",
    # "100"); fall back to the 4-digit-year regex (handles
    # "2012" or "2012-2014" range / "2012,2013" list).
    try:
        return int(text)
    except ValueError:
        pass
    match = _YEAR_RE.search(text)
    if match is None:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _coerce_year(value: Any) -> int | None:
    """Coerce a raw cell value to a 4-digit year int or ``None``.

    Used for year columns (``Order year`` / ``Delivery year``).
    Unlike :func:`_coerce_int`, this helper enforces the 4-digit
    year shape so a small count cell (e.g. ``"8"``) cannot be
    mistaken for a year.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 1000 <= value <= 9999:
            return value
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if value.is_integer():
            int_value = int(value)
            if 1000 <= int_value <= 9999:
                return int_value
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text in {"-", "..", "...", "?", "n.a.", "na", "nil"}:
        return None
    match = _YEAR_RE.search(text)
    if match is None:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _coerce_float(value: Any) -> float | None:
    """Coerce a raw cell value to ``float`` or return ``None``.

    SIPRI TIV cells may carry decimal points, thousands
    separators, or string sentinels. The helper handles
    ``"-"`` / ``""`` / ``".."`` / ``"?"`` / ``"n.a."`` as
    missing; parses numeric cells (integer, decimal,
    thousands-separated) into ``float``; falls back to
    ``None`` for any unparseable cell so the transform layer
    can emit ``value=None`` / ``value_type="missing"`` plus
    the verbatim raw cell text.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        as_float = float(value)
        if math.isnan(as_float):
            return None
        return as_float
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.casefold()
    if lowered in {"-", "..", "...", "?", "n.a.", "na", "nil", "neg."}:
        return None
    cleaned = text.replace(",", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_text(value: Any) -> str:
    """Return the raw cell value as a stripped ``str``.

    Used for supplier / recipient / designation / status /
    comments cells where the SIPRI Trade Register stores
    source-native strings.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _json_scalar(value: Any) -> JsonScalar:
    """Convert a raw cell value to a :class:`JsonScalar`.

    Mirrors the SIPRI Milex / SIPRI Yearbook Ch.7 / CIRIGHTS
    pattern: ``None`` / NaN cells return ``None``; numbers
    return ``int`` / ``float``; everything else is coerced via
    ``str(value).strip()`` for the audit-trail extension
    payload.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        as_float = float(value)
        if math.isnan(as_float):
            return None
        return value
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _safe_float_for_aggregation(value: Any) -> float:
    """Return a 0.0 fallback when ``_coerce_float`` returns
    ``None`` so the aggregate sum does not collapse to ``None``.

    Used only on the aggregate ``TIV (delivered)`` cells where
    the canonical SIPRI Trade Register contract is that every
    cached row carries a numeric TIV (delivered) value; a
    non-numeric cell is treated as a 0 contribution to the
    sum. This matches the SIPRI export contract: a row with
    a missing TIV is unusual but not malformed -- it just
    contributes nothing to the aggregate.
    """
    coerced = _coerce_float(value)
    return coerced if coerced is not None else 0.0


def _country_matches(
    request: SourceIngestRequest,
    supplier: str,
    recipient: str,
) -> bool:
    """Return True iff the row's supplier or recipient matches
    any case-folded substring in ``request.countries``.

    The cached SIPRI Trade Register uses SIPRI's own country
    display names, which are NOT ISO3; the unified adapter
    never invents ISO3 codes. The filter is a substring match
    against the source-native display name (case-folded) on
    EITHER side of the transfer (supplier OR recipient), so
    callers can filter for "transfers to Country A" by passing
    ``countries=("Country A",)``.
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
    haystack = (supplier + "\n" + recipient).casefold()
    return any(needle in haystack for needle in needles)


def _row_passes_year_filter(
    delivery_year: int | None,
    requested_years: set[int] | None,
) -> bool:
    """Return True iff the row's delivery year matches a
    requested year.

    The canonical "flow" year of a recorded arms transfer is
    the delivery year -- every emitted observation
    (per-transfer register row + per-``(role, country, year)``
    aggregate) is stamped with the delivery year. The
    ``request.years`` filter therefore checks ONLY the
    delivery year so a request for ``years=(2018,)`` never
    emits a ``year=2020`` row from an order-2018 /
    delivery-2020 record (the canonical test
    ``test_years_filter_emits_no_delivery_year_2020_from_order_year_2018``
    enforces this). A row whose delivery year is ``None`` is
    filtered out -- without a canonical delivery year the
    observation has no ``year`` stamp to satisfy the request
    scope.

    Note: ``TIV (ordered)`` is conceptually an order-year
    quantity, but the per-row register observation still
    carries the delivery year stamp so the request-scoping
    invariant holds: the canonical output year of EVERY
    emitted observation must be in the requested years.
    """
    if requested_years is None:
        return True
    if delivery_year is None:
        return False
    return delivery_year in requested_years


def _build_register_observation(
    request: SourceIngestRequest,
    *,
    indicator_code: str,
    supplier: str,
    recipient: str,
    designation: str,
    status: str,
    order_year: int | None,
    delivery_year: int | None,
    delivery_year_raw: str,
    order_date: str,
    delivery_date: str,
    description: str,
    weapon_category: str,
    numbers_ordered: str,
    numbers_delivered_raw: str,
    tiv_ordered_raw: str,
    tiv_delivered_raw: str,
    comments: str,
    raw_value: JsonScalar,
    normalized_value: JsonScalar,
    value_type: str,
    unit: str | None,
    scale: str | None,
    source_row_reference: str,
    asset_id: str,
    cache_path: Path | None,
    source_year: int | None,
    preamble_lines: list[str],
    row_index: int,
) -> NormalizedObservation:
    """Build one ``arms_transfer_register_row`` observation."""
    raw_locator = RawLocator(
        asset_id=asset_id,
        path=str(cache_path) if cache_path is not None else None,
        column_name=indicator_code.replace(
            "sipri_arms_transfers_", "",
        ),
        row_number=row_index,
    )
    transform_locator = TransformLocator(
        adapter_version=None,
        transform_name=SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME,
        catalog_key=SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
        rule_id=source_row_reference,
    )
    extension: dict[str, JsonScalar] = {
        "source_row_reference": source_row_reference,
        "raw_value": raw_value,
        "normalized_value": normalized_value,
        "sipri_arms_transfers_supplier": supplier,
        "sipri_arms_transfers_recipient": recipient,
        "sipri_arms_transfers_designation": designation,
        "sipri_arms_transfers_status": status,
        "sipri_arms_transfers_order_year": order_year,
        "sipri_arms_transfers_delivery_year": delivery_year,
        "sipri_arms_transfers_delivery_year_raw": (
            delivery_year_raw or None
        ),
        "sipri_arms_transfers_order_date": order_date or None,
        "sipri_arms_transfers_delivery_date": (
            delivery_date or None
        ),
        "sipri_arms_transfers_description": description or None,
        "sipri_arms_transfers_weapon_category": (
            weapon_category or None
        ),
        "sipri_arms_transfers_numbers_ordered_raw": (
            numbers_ordered or None
        ),
        "sipri_arms_transfers_numbers_delivered_raw": (
            numbers_delivered_raw or None
        ),
        "sipri_arms_transfers_tiv_ordered_raw": (
            tiv_ordered_raw or None
        ),
        "sipri_arms_transfers_tiv_delivered_raw": (
            tiv_delivered_raw or None
        ),
        "sipri_arms_transfers_comments": comments or None,
        "sipri_arms_transfers_preamble": (
            "\n".join(preamble_lines) if preamble_lines else None
        ),
        "attribution": SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT,
    }
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=source_row_reference,
        observation_family=SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_REGISTER,
        indicator_code=indicator_code,
        value=normalized_value,
        value_type=value_type,  # type: ignore[arg-type]
        year=source_year,
        country_code=None,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit=unit,
        scale=scale,
        source_version=SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        raw_locator=raw_locator,
        transform_locator=transform_locator,
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _build_aggregate_observation(
    request: SourceIngestRequest,
    *,
    role: str,
    country: str,
    year: int,
    tiv_total: float,
    asset_id: str,
    cache_path: Path | None,
    preamble_lines: list[str],
) -> NormalizedObservation:
    """Build one ``arms_transfer_country_year_aggregate`` observation.

    The aggregate observation carries the deterministic sum
    of TIV delivered over all transfers in the parsed frame
    where the country appears as ``role`` (supplier OR
    recipient) and the delivery year matches ``year``. The
    scope key is ``(role, country, year)`` so supplier-side and
    recipient-side aggregates are kept separate (no double-
    counting when the same country appears as both supplier
    and recipient in the same year).
    """
    if role == "supplier":
        indicator_code = (
            SIPRI_ARMS_TRANSFERS_INDICATOR_SUPPLIER_YEAR_TIV_DELIVERED
        )
    else:
        indicator_code = (
            SIPRI_ARMS_TRANSFERS_INDICATOR_RECIPIENT_YEAR_TIV_DELIVERED
        )
    source_row_reference = (
        f"{SIPRI_ARMS_TRANSFERS_SOURCE_KEY}:{role}:"
        f"{country}:{year}"
    )
    extension: dict[str, JsonScalar] = {
        "source_row_reference": source_row_reference,
        "raw_value": tiv_total,
        "normalized_value": tiv_total,
        "sipri_arms_transfers_aggregate_role": role,
        "sipri_arms_transfers_aggregate_country": country,
        "sipri_arms_transfers_aggregate_year": year,
        "sipri_arms_transfers_preamble": (
            "\n".join(preamble_lines) if preamble_lines else None
        ),
        "attribution": SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT,
    }
    raw_locator = RawLocator(
        asset_id=asset_id,
        path=str(cache_path) if cache_path is not None else None,
        column_name="TIV (delivered)",
    )
    transform_locator = TransformLocator(
        adapter_version=None,
        transform_name=SIPRI_ARMS_TRANSFERS_TRANSFORM_NAME,
        catalog_key=SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
        rule_id=source_row_reference,
    )
    return NormalizedObservation(
        source_id=request.source_id,
        observation_id=source_row_reference,
        observation_family=(
            SIPRI_ARMS_TRANSFERS_OBSERVATION_FAMILY_AGGREGATE
        ),
        indicator_code=indicator_code,
        value=tiv_total,
        value_type="numeric",
        year=year,
        country_code=None,
        country_name=country,
        leader_id=None,
        leader_name=None,
        unit=SIPRI_ARMS_TRANSFERS_TIV_UNIT,
        scale=SIPRI_ARMS_TRANSFERS_TIV_SCALE,
        source_version=SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        raw_locator=raw_locator,
        transform_locator=transform_locator,
        quality_flags=(),
        warnings=(),
        extension=extension,
    )


def _is_in_coverage(year: int | None) -> bool:
    """Return True iff ``year`` falls within the canonical
    1950-2025 SIPRI Arms Transfers coverage envelope.

    Used to filter out rows with out-of-coverage delivery
    years before they enter the aggregate -- the row-level
    register observations still carry the original ``year``
    field on the ``extension`` payload so audit code can
    recover the original cell, but the row is excluded from
    the per-``(role, country, year)`` aggregate scope. The
    readiness envelope surfaces a structured ``YEAR_ABSENT``
    warning on the request so the operator can see the gap.
    """
    if year is None:
        return False
    return (
        SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR
        <= year
        <= SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR
    )


def emit_sipri_arms_transfers_observations(
    request: SourceIngestRequest,
    rows: list[dict[str, str]],
    *,
    cache_path: Path | None,
    asset_id: str,
    preamble_lines: list[str] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the parsed row-level frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    request:
        The request-scoped :class:`SourceIngestRequest` driving
        the run.
    rows:
        The parsed row-level frame returned by
        :func:`._raw_read.read_sipri_arms_transfers_csv`. One
        row per transfer, keyed by the documented CSV header
        column names.
    cache_path:
        Optional path to the staged cached export; carried
        verbatim onto every observation's :class:`RawLocator`.
    asset_id:
        The asset id string (``sipri_arms_transfers:trade_register.csv``
        or ``sipri_arms_transfers:trade_register.json``) carried
        on every observation's :class:`RawLocator`.
    preamble_lines:
        Optional list of SIPRI preamble / citation lines
        preserved from the cached CSV; propagated onto every
        emitted observation's
        ``extension["sipri_arms_transfers_preamble"]`` audit-trail
        field.

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. The order is:
        per-transfer register observations (interleaved per
        indicator, per row in the parsed frame), followed by
        per-``(role, country, year)`` aggregate observations
        in deterministic scope order.

    Notes
    -----
    The transform layer never invents ISO3 country codes,
    leader identifiers, missing values, or proxy years. A
    non-numeric TIV / number cell is emitted with
    ``value=None`` / ``value_type='missing'`` plus the verbatim
    raw cell text on ``extension["raw_value"]`` -- the
    observation is NOT dropped (matches the SIPRI Yearbook
    Ch.7 / FAS / RSF / PTS defensive pattern).
    """
    if preamble_lines is None:
        preamble_lines = []

    requested_years = (
        {int(y) for y in request.years} if request.years else None
    )

    # First pass: emit per-transfer register observations and
    # collect per-``(role, country, year)`` TIV (delivered) sums
    # for the aggregate pass.
    aggregate_sums: dict[tuple[str, str, int], float] = {}
    observations: list[NormalizedObservation] = []

    for row_index, row in enumerate(rows, start=2):
        # The CSV reader routes each parsed row into a dict
        # keyed by the documented column names; missing optional
        # columns default to ``""`` so the per-cell coercion
        # below always sees a string.
        supplier = _coerce_text(row.get("Supplier"))
        recipient = _coerce_text(row.get("Recipient"))
        designation = _coerce_text(row.get("Designation"))
        status = _coerce_text(row.get("Status"))
        order_year = _coerce_year(row.get("Order year"))
        delivery_year_raw = _coerce_text(row.get("Delivery year"))
        delivery_year = _coerce_year(delivery_year_raw)
        order_date = _coerce_text(row.get("Order date"))
        delivery_date = _coerce_text(row.get("Delivery date"))
        description = _coerce_text(row.get("Description"))
        weapon_category = _coerce_text(row.get("Weapon category"))
        numbers_ordered_raw = _coerce_text(
            row.get("Numbers ordered"),
        )
        numbers_delivered_raw = _coerce_text(
            row.get("Numbers delivered"),
        )
        tiv_ordered_raw = _coerce_text(row.get("TIV (ordered)"))
        tiv_delivered_raw = _coerce_text(
            row.get("TIV (delivered)"),
        )
        comments = _coerce_text(row.get("Comments"))

        if not _country_matches(request, supplier, recipient):
            continue
        if not _row_passes_year_filter(
            delivery_year, requested_years,
        ):
            continue

        # The canonical "flow" year of a recorded arms transfer
        # is the delivery year -- every emitted observation
        # (per-transfer register row + per-``(role, country,
        # year)`` aggregate) is stamped with the delivery year.
        # There is no order-year fallback: a row whose delivery
        # year is missing is filtered out by
        # :func:`_row_passes_year_filter` so the canonical
        # output year is always defined when an observation is
        # emitted. Out-of-coverage delivery years still flow
        # through here (the row's delivery year was in
        # ``requested_years`` so it survived the filter); the
        # transform emits the observation with the literal
        # delivery year stamp and excludes it from the
        # aggregate (the aggregate only counts in-coverage
        # delivery years via :func:`_is_in_coverage`).
        source_year = delivery_year

        source_row_reference = (
            f"{SIPRI_ARMS_TRANSFERS_SOURCE_KEY}:row_{row_index}:"
            f"{supplier or 'unknown'}_to_{recipient or 'unknown'}"
        )

        # Per-row indicator emission. Each cell becomes one
        # observation under the ``arms_transfer_register_row``
        # family; missing / non-numeric cells become
        # ``value=None`` / ``value_type='missing'`` with the
        # verbatim raw cell text on ``extension.raw_value``.
        # Indicator 1: TIV (delivered)
        tiv_delivered_value = _coerce_float(tiv_delivered_raw)
        if tiv_delivered_value is None:
            observations.append(
                _build_register_observation(
                    request,
                    indicator_code=(
                        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED
                    ),
                    supplier=supplier,
                    recipient=recipient,
                    designation=designation,
                    status=status,
                    order_year=order_year,
                    delivery_year=delivery_year,
                    delivery_year_raw=delivery_year_raw,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    description=description,
                    weapon_category=weapon_category,
                    numbers_ordered=numbers_ordered_raw,
                    numbers_delivered_raw=numbers_delivered_raw,
                    tiv_ordered_raw=tiv_ordered_raw,
                    tiv_delivered_raw=tiv_delivered_raw,
                    comments=comments,
                    raw_value=_json_scalar(tiv_delivered_raw),
                    normalized_value=None,
                    value_type="missing",
                    unit=SIPRI_ARMS_TRANSFERS_TIV_UNIT,
                    scale=SIPRI_ARMS_TRANSFERS_TIV_SCALE,
                    source_row_reference=(
                        f"{source_row_reference}:tiv_delivered"
                    ),
                    asset_id=asset_id,
                    cache_path=cache_path,
                    source_year=source_year,
                    preamble_lines=preamble_lines,
                    row_index=row_index,
                ),
            )
        else:
            observations.append(
                _build_register_observation(
                    request,
                    indicator_code=(
                        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_DELIVERED
                    ),
                    supplier=supplier,
                    recipient=recipient,
                    designation=designation,
                    status=status,
                    order_year=order_year,
                    delivery_year=delivery_year,
                    delivery_year_raw=delivery_year_raw,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    description=description,
                    weapon_category=weapon_category,
                    numbers_ordered=numbers_ordered_raw,
                    numbers_delivered_raw=numbers_delivered_raw,
                    tiv_ordered_raw=tiv_ordered_raw,
                    tiv_delivered_raw=tiv_delivered_raw,
                    comments=comments,
                    raw_value=_json_scalar(tiv_delivered_raw),
                    normalized_value=tiv_delivered_value,
                    value_type="numeric",
                    unit=SIPRI_ARMS_TRANSFERS_TIV_UNIT,
                    scale=SIPRI_ARMS_TRANSFERS_TIV_SCALE,
                    source_row_reference=(
                        f"{source_row_reference}:tiv_delivered"
                    ),
                    asset_id=asset_id,
                    cache_path=cache_path,
                    source_year=source_year,
                    preamble_lines=preamble_lines,
                    row_index=row_index,
                ),
            )
            # Aggregate accumulation: only rows with a numeric
            # TIV (delivered) contribute to the aggregate.
            if _is_in_coverage(delivery_year):
                aggregate_key = ("supplier", supplier, delivery_year)
                aggregate_sums[aggregate_key] = (
                    aggregate_sums.get(aggregate_key, 0.0)
                    + tiv_delivered_value
                )
                aggregate_key = (
                    "recipient",
                    recipient,
                    delivery_year,
                )
                aggregate_sums[aggregate_key] = (
                    aggregate_sums.get(aggregate_key, 0.0)
                    + tiv_delivered_value
                )

        # Indicator 2: TIV (ordered)
        tiv_ordered_value = _coerce_float(tiv_ordered_raw)
        if tiv_ordered_value is None:
            observations.append(
                _build_register_observation(
                    request,
                    indicator_code=(
                        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED
                    ),
                    supplier=supplier,
                    recipient=recipient,
                    designation=designation,
                    status=status,
                    order_year=order_year,
                    delivery_year=delivery_year,
                    delivery_year_raw=delivery_year_raw,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    description=description,
                    weapon_category=weapon_category,
                    numbers_ordered=numbers_ordered_raw,
                    numbers_delivered_raw=numbers_delivered_raw,
                    tiv_ordered_raw=tiv_ordered_raw,
                    tiv_delivered_raw=tiv_delivered_raw,
                    comments=comments,
                    raw_value=_json_scalar(tiv_ordered_raw),
                    normalized_value=None,
                    value_type="missing",
                    unit=SIPRI_ARMS_TRANSFERS_TIV_UNIT,
                    scale=SIPRI_ARMS_TRANSFERS_TIV_SCALE,
                    source_row_reference=(
                        f"{source_row_reference}:tiv_ordered"
                    ),
                    asset_id=asset_id,
                    cache_path=cache_path,
                    source_year=source_year,
                    preamble_lines=preamble_lines,
                    row_index=row_index,
                ),
            )
        else:
            observations.append(
                _build_register_observation(
                    request,
                    indicator_code=(
                        SIPRI_ARMS_TRANSFERS_INDICATOR_TIV_ORDERED
                    ),
                    supplier=supplier,
                    recipient=recipient,
                    designation=designation,
                    status=status,
                    order_year=order_year,
                    delivery_year=delivery_year,
                    delivery_year_raw=delivery_year_raw,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    description=description,
                    weapon_category=weapon_category,
                    numbers_ordered=numbers_ordered_raw,
                    numbers_delivered_raw=numbers_delivered_raw,
                    tiv_ordered_raw=tiv_ordered_raw,
                    tiv_delivered_raw=tiv_delivered_raw,
                    comments=comments,
                    raw_value=_json_scalar(tiv_ordered_raw),
                    normalized_value=tiv_ordered_value,
                    value_type="numeric",
                    unit=SIPRI_ARMS_TRANSFERS_TIV_UNIT,
                    scale=SIPRI_ARMS_TRANSFERS_TIV_SCALE,
                    source_row_reference=(
                        f"{source_row_reference}:tiv_ordered"
                    ),
                    asset_id=asset_id,
                    cache_path=cache_path,
                    source_year=source_year,
                    preamble_lines=preamble_lines,
                    row_index=row_index,
                ),
            )

        # Indicator 3: Numbers delivered (count)
        numbers_delivered_value = _coerce_int(numbers_delivered_raw)
        if numbers_delivered_value is None:
            observations.append(
                _build_register_observation(
                    request,
                    indicator_code=(
                        SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED
                    ),
                    supplier=supplier,
                    recipient=recipient,
                    designation=designation,
                    status=status,
                    order_year=order_year,
                    delivery_year=delivery_year,
                    delivery_year_raw=delivery_year_raw,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    description=description,
                    weapon_category=weapon_category,
                    numbers_ordered=numbers_ordered_raw,
                    numbers_delivered_raw=numbers_delivered_raw,
                    tiv_ordered_raw=tiv_ordered_raw,
                    tiv_delivered_raw=tiv_delivered_raw,
                    comments=comments,
                    raw_value=_json_scalar(numbers_delivered_raw),
                    normalized_value=None,
                    value_type="missing",
                    unit=SIPRI_ARMS_TRANSFERS_NUMBER_UNIT,
                    scale=SIPRI_ARMS_TRANSFERS_NUMBER_SCALE,
                    source_row_reference=(
                        f"{source_row_reference}:number_delivered"
                    ),
                    asset_id=asset_id,
                    cache_path=cache_path,
                    source_year=source_year,
                    preamble_lines=preamble_lines,
                    row_index=row_index,
                ),
            )
        else:
            observations.append(
                _build_register_observation(
                    request,
                    indicator_code=(
                        SIPRI_ARMS_TRANSFERS_INDICATOR_NUMBER_DELIVERED
                    ),
                    supplier=supplier,
                    recipient=recipient,
                    designation=designation,
                    status=status,
                    order_year=order_year,
                    delivery_year=delivery_year,
                    delivery_year_raw=delivery_year_raw,
                    order_date=order_date,
                    delivery_date=delivery_date,
                    description=description,
                    weapon_category=weapon_category,
                    numbers_ordered=numbers_ordered_raw,
                    numbers_delivered_raw=numbers_delivered_raw,
                    tiv_ordered_raw=tiv_ordered_raw,
                    tiv_delivered_raw=tiv_delivered_raw,
                    comments=comments,
                    raw_value=_json_scalar(numbers_delivered_raw),
                    normalized_value=numbers_delivered_value,
                    value_type="numeric",
                    unit=SIPRI_ARMS_TRANSFERS_NUMBER_UNIT,
                    scale=SIPRI_ARMS_TRANSFERS_NUMBER_SCALE,
                    source_row_reference=(
                        f"{source_row_reference}:number_delivered"
                    ),
                    asset_id=asset_id,
                    cache_path=cache_path,
                    source_year=source_year,
                    preamble_lines=preamble_lines,
                    row_index=row_index,
                ),
            )

    # Aggregate pass: emit per-``(role, country, year)``
    # observations in deterministic scope order. The aggregate
    # sums are rounded to 3 decimal places for stable output
    # (SIPRI TIV values are reported to 1 decimal place in the
    # canonical export, so the sum is stable to 3 decimal
    # places).
    for (role, country, year), tiv_total in sorted(
        aggregate_sums.items(),
        key=lambda item: (item[0][0], item[0][1], item[0][2]),
    ):
        if not country:
            # Defensive: skip empty country labels (the
            # canonical SIPRI export never carries an empty
            # supplier / recipient, but a user-edited cache
            # might).
            continue
        observations.append(
            _build_aggregate_observation(
                request,
                role=role,
                country=country,
                year=year,
                tiv_total=round(tiv_total, 3),
                asset_id=asset_id,
                cache_path=cache_path,
                preamble_lines=preamble_lines,
            ),
        )

    return iter(observations)


def required_columns() -> tuple[str, ...]:
    """Return the canonical required CSV columns.

    Re-exported here so the transform layer can validate the
    parsed header against the same set the readiness gate
    enforces.
    """
    return SIPRI_ARMS_TRANSFERS_REQUIRED_COLUMNS


def optional_columns() -> tuple[str, ...]:
    """Return the canonical optional CSV columns."""
    return SIPRI_ARMS_TRANSFERS_OPTIONAL_COLUMNS


__all__ = [
    "emit_sipri_arms_transfers_observations",
    "optional_columns",
    "required_columns",
]
