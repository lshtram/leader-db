"""Unified-source PTS observation-emission helpers.

This module owns the per-row emission loop for the
unified-source Political Terror Scale adapter. The
function takes the wide-format country-year DataFrame
returned by the legacy reader
(:func:`leaders_db.ingest.pts_xlsx.read_pts`) -- one
row per ``(COW_Code_A, Year)`` with the canonical PTS
columns ``country``, ``cow_code``, ``year``, ``region``,
``pts_amnesty_score``, ``pts_human_rights_watch_score``,
``pts_state_dept_score`` -- and emits the canonical
observation records via :func:`build_observation` from
:mod:`._observation_builder`.

Split out of
:mod:`leaders_db.sources.adapters.pts.adapter` to keep
the adapter class module focused on the lifecycle
methods (``check_ready`` / ``read_raw`` / ``transform``)
and respect the documented 400-line module convention.

The per-row observation construction contract lives in
:mod:`._observation_builder`. The missing-value
coercion helpers (the §6 4-case sentinel matrix + the
§6.5 defensive check) live in :mod:`._missing_values`.
This module composes them into the per-row emission
loop + the positional-row-index lookup helper.

Sentinel-matrix semantics
-------------------------

The PTS xlsx carries TWO independent signals per
indicator cell. The legacy reader applies the §6
4-case precedence rule (NA_Status takes precedence
over PTS_X) at read time and produces a wide-format
DataFrame where:

- Valid cells (int 1-5 with NA_Status=0) appear as
  the int 1-5 value.
- Dropped cells (cases 2/3/4) appear as ``pd.NA`` in
  the wide-format indicator columns.
- The pre-coercion cell text is preserved in
  ``df.attrs["_pts_raw_lookup"]`` (a dict keyed by
  ``(country, year, variable_name)``) for the
  ``raw_value`` audit trail.

The unified transform layer skips rows whose
indicator cell is ``None`` / ``NaN`` -- no silent
conversion of missing raw cells (SRC-OBS-007). The
audit-trail ``raw_value`` is recovered from the
``_pts_raw_lookup`` attribute so even the dropped
cells carry an auditable raw cell string.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    SourceIngestRequest,
)

from ._catalog import (
    PTS_OBSERVATION_FAMILY as _PTS_OBSERVATION_FAMILY,
)
from ._missing_values import (
    _raw_cell_text,
)
from ._observation_builder import (
    PTS_TRANSFORM_NAME,
    _default_asset_id,
    _default_source_version,
    build_observation,
)


def _rating_category_to_family_local(rating_category: str) -> str:
    """Local rating-category -> family resolver.

    Mirrors the UCDP / V-Dem / WGI / CPI pattern: the
    PTS dataset feeds a single observation family
    (``domestic_violence_country_year``). Unknown
    rating categories fall back to that family so a
    future catalog addition does not silently drop
    observations. The resolution is local to this
    helper so the transform layer does not need to
    consult the catalog module at per-row time.
    """
    return _PTS_OBSERVATION_FAMILY


def _canonical_source_version() -> str:
    """Return the canonical PTS source version stamp.

    The unified adapter hardcodes the canonical
    version ``"PTS-2025"`` (matches the staged
    ``data/raw/political_terror_scale/metadata.json``
    ``version`` field's canonical stamp + the
    canonical attribution block in
    ``docs/sources/attributions.md``). Observations
    therefore carry this validated version, not
    arbitrary metadata / request text.
    """
    return _default_source_version()


def _canonical_asset_id() -> str:
    """Return the canonical PTS xlsx asset id.

    The legacy PTS reader does not embed the asset id
    in the wide frame; the transform layer uses this
    helper so all observations in a single run share
    the same logical asset id (matching the WGI /
    V-Dem / CPI / UCDP convention).
    """
    return _default_asset_id()


def _locate_row_index(
    wide_df: Any,
    cow_code: str,
    year: int,
) -> int | None:
    """Return the wide-frame row index for
    ``(cow_code, year)``.

    The legacy wide-format DataFrame is sorted by
    ``COW_Code_A`` ascending for deterministic
    idempotency (per
    ``pts_xlsx.read_pts_from_dataframe``); the
    ``cow_code`` and ``year`` columns form the
    canonical country-year key. The unified transform
    preserves the row index when feasible (per
    ``docs/architecture/sources.md`` §5.4) so audit
    code can recover the input row from the staged
    xlsx byte-for-byte.

    Returns ``None`` when the ``(cow_code, year)``
    key does not match any row in the frame
    (defensive guard for a malformed wide frame).
    """
    if wide_df is None:
        return None
    try:
        match = wide_df.loc[
            (wide_df["cow_code"] == cow_code)
            & (wide_df["year"].astype(int) == int(year))
        ]
    except (KeyError, TypeError, ValueError):
        return None
    if match.empty:
        return None
    # The legacy reader returns a frame sorted by
    # ``COW_Code_A`` ascending; the first matching
    # row is the canonical one. Return the positional
    # index of the matching row in the wide frame.
    idx_value = match.index[0]
    try:
        return int(idx_value)
    except (TypeError, ValueError):
        return None


def emit_pts_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    xlsx_path: Path | None,
    metadata: dict[str, Any] | None,
    *,
    specs: list[Any] | None = None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide PTS frame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by the
        legacy
        :func:`leaders_db.ingest.pts_xlsx.read_pts`
        reader -- one row per ``(COW_Code_A, Year)``
        with columns ``country``, ``cow_code``,
        ``year``, ``region``, ``pts_amnesty_score``,
        ``pts_human_rights_watch_score``,
        ``pts_state_dept_score``. ``pd.NA`` cells in
        the indicator columns are skipped (no silent
        conversion of missing raw cells;
        SRC-OBS-007).
    request:
        The request-scoped
        :class:`SourceIngestRequest` driving the run.
        Used for the source-version stamp. Year /
        country / leader filters are applied by the
        caller BEFORE this helper is invoked so the
        wide_df has already been narrowed.
    xlsx_path:
        Optional path to the staged xlsx; carried
        verbatim onto every observation's
        :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json``
        payload. Not consumed for the observation
        emission contract -- kept in the signature for
        symmetry with the WGI / V-Dem / CPI / UCDP
        transform helpers.
    specs:
        Optional list of legacy
        :class:`IndicatorSpec` records. When ``None``,
        the unified transform receives the narrowed
        frame but emits zero observations (the caller
        must load the catalog and pass ``specs``
        explicitly -- the lazy-load of the catalog is
        the caller's responsibility so the unified
        adapter never imports legacy at module level).

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty
        when ``wide_df`` is empty or ``specs`` is
        ``None`` / empty (e.g. an out-of-coverage year
        request, or the staged fixture has no rows for
        the requested filter scope, or the catalog was
        not provided).
    """
    if metadata is None:
        metadata = {}

    if wide_df is None or specs is None or len(specs) == 0:
        return iter(())

    xlsx_path_str = (
        str(xlsx_path) if isinstance(xlsx_path, Path) else None
    )
    source_version = _canonical_source_version()
    asset_id = _canonical_asset_id()

    # The pre-coercion raw cell text lookup. The legacy
    # reader attaches ``_pts_raw_lookup`` to the wide
    # frame's attrs as a dict keyed by
    # ``(country, year, variable_name) -> str``.
    raw_lookup = wide_df.attrs.get("_pts_raw_lookup") if hasattr(
        wide_df, "attrs",
    ) else None
    if not isinstance(raw_lookup, dict):
        raw_lookup = {}

    observations: list[NormalizedObservation] = []

    # Iterate via ``itertuples`` for speed: the wide
    # frame has up to 7 columns + the cow_code / year
    # identity columns, so the per-row overhead is
    # minimal.
    for row in wide_df.itertuples(index=False):
        # Identity columns. The legacy wide-format
        # frame has string ``cow_code``, int ``year``,
        # string ``country``, and string ``region``
        # columns.
        cow_code_raw = getattr(row, "cow_code", None)
        if (
            not isinstance(cow_code_raw, str)
            or not cow_code_raw.strip()
        ):
            continue
        cow_code = cow_code_raw.strip().upper()
        try:
            year = int(row.year)
        except (TypeError, ValueError):
            continue

        # The canonical per-row source row reference
        # pattern is ``"pts:<COW_Code_A>"`` (matches
        # the legacy Stage 2 DB writer).
        source_row_reference = f"pts:{cow_code}"

        # The wide frame is sorted by ``COW_Code_A``
        # ascending per the legacy reader's idempotency
        # contract; the positional row index is
        # preserved so audit code can recover the
        # input row.
        row_number = _locate_row_index(wide_df, cow_code, year)

        # Country / region audit-trail columns are
        # preserved verbatim from the xlsx so audit
        # code can recover the input row's labels.
        country_label = getattr(row, "country", None)
        region_label = getattr(row, "region", None)

        for spec in specs:
            variable_name = getattr(spec, "variable_name", None)
            if (
                not isinstance(variable_name, str)
                or not variable_name
            ):
                continue
            cell = getattr(row, variable_name, None)

            # Skip ``None`` / ``pd.NA`` cells. The
            # legacy reader applies the §6 sentinel
            # matrix at read time; valid cells appear
            # as the int 1-5 value, dropped cells
            # appear as ``pd.NA``. The unified
            # transform does NOT emit observations for
            # missing cells (no silent conversion of
            # missing raw cells; SRC-OBS-007).
            try:
                import math

                import pandas as _pd
                if cell is None or (
                    isinstance(cell, float)
                    and math.isnan(cell)
                ):
                    continue
                if _pd.isna(cell):
                    continue
            except ImportError:
                # pandas unavailable (defensive; the
                # project's runtime requires pandas).
                if cell is None:
                    continue

            # Recover the pre-coercion raw cell text
            # for the audit trail. The legacy reader
            # attaches the lookup dict to
            # ``df.attrs["_pts_raw_lookup"]`` keyed by
            # ``(country, year, variable_name)``. The
            # raw text follows the §6.3 audit-trail
            # matrix: int 1-5 -> ``str(int)``;
            # ``'NA'`` -> ``"NA"``; ``None`` ->
            # ``"None"``.
            raw_audit_key = (
                country_label if isinstance(
                    country_label, str,
                ) else None,
                year,
                variable_name,
            )
            raw_value_audit = raw_lookup.get(
                raw_audit_key,
                _raw_cell_text(cell),
            )

            # The paired ``NA_Status_X`` cell is NOT
            # carried on the wide frame's indicator
            # columns (the legacy reader collapses it
            # into the §6 precedence decision at read
            # time: valid cells appear as the int 1-5
            # value; dropped cells appear as
            # ``pd.NA``). The audit trail preserves
            # the §6 sentinel matrix verdict via
            # ``na_status_audit``: ``"0"`` for emitted
            # (valid, case-1) cells -- the only path
            # the unified transform emits. Dropped
            # cells (any of cases 2/3/4) are NOT
            # emitted as observations, so the audit
            # value is the canonical ``"0"`` stamp
            # for every emitted observation. The
            # downstream Stage 12 cross-source
            # comparison can recover the verdict from
            # ``pts_na_status``.
            na_status_audit = "0"

            observations.append(
                build_observation(
                    request,
                    cow_code=cow_code,
                    year=year,
                    variable_name=variable_name,
                    spec=spec,
                    cell=cell,
                    raw_value_audit=(
                        raw_value_audit
                        if isinstance(raw_value_audit, str)
                        else _raw_cell_text(cell)
                    ),
                    na_status_audit=na_status_audit,
                    xlsx_path_str=xlsx_path_str,
                    asset_id=asset_id,
                    row_number=row_number,
                    source_version=source_version,
                    source_row_reference=source_row_reference,
                    country_label=country_label,
                    region_label=region_label,
                ),
            )
    return iter(observations)


__all__ = [
    "PTS_TRANSFORM_NAME",
    "emit_pts_observations",
]
