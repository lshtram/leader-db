"""Unified-source Maddison Project observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation`
build loop for the unified-source Maddison Project adapter.
The function takes the legacy long-format DataFrame (one row
per ``(countrycode, year, variable_name)`` triple) and emits
the canonical observation records with raw locators, transform
locators, attribution text, the documented 2023 -> 2022
1-year-gap proxy quality flag, and column-specific unit labels.

Split out of :mod:`leaders_db.sources.adapters.maddison_project.adapter`
to keep the adapter class module focused on the lifecycle
methods (``check_ready`` / ``read_raw`` / ``transform``) and
respect the documented 400-line module convention.

Year semantics
--------------

The Maddison Project Database 2023 release ends at 2022; the
adaptersupports two distinct year semantics:

1. **2023 proxy (documented).** A request for ``year=2023`` is
   proxied to ``year=2022`` data per the legacy Stage 2
   orchestrator contract and the 1-year-gap mapping documented
   in ``docs/sources/attributions.md``. The proxy is surfaced
   on every affected observation via:

   - ``quality_flags=("proxy_year",)``
   - ``extension={"proxy_source_year": <int>, ...}``
   - ``extension={"requested_year": 2023, ...}``

2. **2024+ (out of coverage).** A request for any year beyond
   2022 (e.g. ``year=2024``) emits zero observations plus a
   structured ``YEAR_ABSENT`` warning on the readiness
   envelope. There is no multi-year stale-proxy fill.

Legacy row provenance
---------------------

The ``source_row_reference`` column produced by the legacy
Stage 2 reader carries the literal pattern
``maddison_project:<raw_column>:<iso3>:<year>``. We propagate
that pattern onto the canonical observation's
``transform_locator.rule_id`` so downstream scoring / audit
code can resolve the per-row legacy reference without
re-reading the xlsx.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from leaders_db.sources.contracts import (
    NormalizedObservation,
    RawLocator,
    SourceIngestRequest,
    TransformLocator,
)

from ._descriptor import (
    MADDISON_PROJECT_ATTRIBUTION_TEXT,
    MADDISON_PROJECT_COLUMN_UNITS,
    MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN,
    MADDISON_PROJECT_OBSERVATION_FAMILY,
    MADDISON_PROJECT_PROXY_REQUESTED_YEAR,
    MADDISON_PROJECT_PROXY_YEAR,
    MADDISON_PROJECT_SHEET_NAME,
    MADDISON_PROJECT_SOURCE_KEY,
    MADDISON_PROJECT_TRANSFORM_NAME,
    MADDISON_PROJECT_XLSX_ASSET_ID,
)


def _is_real_number(value: Any) -> bool:
    """Return True iff ``value`` is a non-NaN, non-None numeric."""
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isnan(value)
    return isinstance(value, (int,))


def _canonical_version() -> str:
    """Return the canonical Maddison Project version stamp.

    The unified adapter hardcodes the canonical version
    ``"2023"`` (matches the legacy Stage 2 ``sources.version``
    stamp and the canonical attribution block in
    ``docs/sources/attributions.md``). Observations therefore
    carry this validated version, not arbitrary metadata / request
    text.
    """
    # Local import so the helper is callable independently
    # of the descriptor module import order.
    from ._descriptor import MADDISON_PROJECT_DEFAULT_VERSION

    return MADDISON_PROJECT_DEFAULT_VERSION


def _build_proxy_quality_flags(
    long_row: Any,
) -> tuple[str, ...]:
    """Return the per-observation quality flags tuple.

    The legacy long-format DataFrame carries a ``year`` column
    that is the actual source-year row. When the request asked
    for ``year=2023`` and the source-year row is ``2022`` (the
    1-year-gap proxy), the row carries the ``"proxy_year"``
    quality flag. All other rows carry no flags. Derived GDP
    rows carry the additional ``"derived"`` quality flag so
    the derivation provenance is never silent.
    """
    flags: list[str] = []
    raw_column = str(long_row.get("raw_column", ""))
    if raw_column == MADDISON_PROJECT_DERIVED_GDP_RAW_COLUMN:
        flags.append("derived")
    # ``requested_year`` is set by the adapter's transform
    # helper when the request proxied 2023 -> 2022; the
    # per-row ``year`` then equals 2022. We check the year
    # against the proxy source-year constant directly so we
    # never need to thread a flag through the long-frame.
    row_year = long_row.get("year")
    if (
        row_year is not None
        and int(row_year) == MADDISON_PROJECT_PROXY_YEAR
    ):
        # Only mark as proxy when the request actually asked
        # for 2023 (the adapter sets ``request.years``;
        # detection from the row alone is impossible because
        # the legacy long-format DataFrame only carries the
        # source-year). The transform helper passes the
        # request explicitly via ``requested_year`` in the
        # emission kwargs below.
        pass
    return tuple(flags)


def emit_maddison_project_observations(
    long_df: Any,
    request: SourceIngestRequest,
    xlsx_path: Path | None,
    metadata: dict[str, Any] | None,
) -> Iterable[NormalizedObservation]:
    """Convert the long-format DataFrame into :class:`NormalizedObservation` records.

    Parameters
    ----------
    long_df:
        The long-format DataFrame returned by the legacy
        :func:`leaders_db.ingest.maddison_project_xlsx.read_maddison_project`.
        One row per ``(countrycode, year, variable_name)`` triple
        with the ``raw_value`` preserved.
    request:
        The request-scoped :class:`SourceIngestRequest` driving
        the run. Used for the proxy-detection logic (a request
        with ``years=(2023,)`` makes every row carry the
        ``proxy_year`` quality flag) and the source-version
        stamp.
    xlsx_path:
        Optional path to the staged ``mpd2023.xlsx``; carried
        verbatim onto every observation's :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json`` payload. Not
        consumed for the observation emission contract -- kept
        in the signature for symmetry with the PWT transform
        helper and for future source-version overrides.

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty when
        ``long_df`` is empty (e.g. an out-of-coverage year
        request). When the request asked for ``year=2023``
        (the documented 1-year-gap proxy) every emitted
        observation carries the ``proxy_year`` quality flag
        plus ``requested_year`` / ``proxy_source_year`` /
        ``attribution`` fields in its ``extension`` payload.
    """
    _ = metadata

    if long_df is None:
        return iter(())

    xlsx_path_str = str(xlsx_path) if isinstance(xlsx_path, Path) else None
    asset_id = MADDISON_PROJECT_XLSX_ASSET_ID
    source_version = _canonical_version()

    # Proxy detection: a request that includes the documented
    # proxy year (2023) marks every emitted observation with
    # the ``proxy_year`` quality flag plus the requested /
    # source-year pair in ``extension``. Multi-year requests
    # that include both 2023 and 2024 will see only the 2022
    # rows (legacy reader filters; 2024 emits zero rows).
    proxy_active = False
    if request.years:
        proxy_active = any(
            int(year) == MADDISON_PROJECT_PROXY_REQUESTED_YEAR
            for year in request.years
        )

    observations: list[NormalizedObservation] = []
    for _, long_row in long_df.iterrows():
        iso3 = str(long_row["countrycode"])
        year = int(long_row["year"])
        raw_column = str(long_row["raw_column"])
        variable_name = str(long_row["variable_name"])
        numeric_value = long_row.get("normalized_value")
        raw_value = long_row.get("raw_value")
        country = str(long_row.get("country") or "") or None
        region = str(long_row.get("region") or "") or None

        # Build the per-row quality flag tuple. The
        # ``proxy_year`` flag is appended only when the
        # request proxied 2023 -> 2022 (proxy_active).
        quality_flags = list(_build_proxy_quality_flags(long_row))
        if proxy_active:
            quality_flags.append("proxy_year")

        # Build the per-row extension payload. The legacy
        # ``raw_value`` (verbatim xlsx cell text) is always
        # preserved. The proxy-year metadata is only attached
        # when the request proxied 2023 -> 2022.
        extension: dict[str, Any] = {
            "raw_value": raw_value,
            "country": country,
            "region": region,
            "attribution": MADDISON_PROJECT_ATTRIBUTION_TEXT,
        }
        if proxy_active:
            extension["requested_year"] = (
                MADDISON_PROJECT_PROXY_REQUESTED_YEAR
            )
            extension["proxy_source_year"] = MADDISON_PROJECT_PROXY_YEAR

        # Legacy source_row_reference is the literal
        # ``maddison_project:<raw_column>:<iso3>:<year>``
        # pattern the legacy Stage 2 DB writer uses. Surface
        # it on the transform locator rule_id so downstream
        # scoring / audit code can resolve the per-row legacy
        # reference without re-reading the xlsx.
        source_row_reference = (
            f"{MADDISON_PROJECT_SOURCE_KEY}:{raw_column}:{iso3}:{year}"
        )

        observations.append(
            NormalizedObservation(
                source_id=request.source_id,
                observation_id=(
                    f"{MADDISON_PROJECT_SOURCE_KEY}:{iso3}:"
                    f"{year}:{raw_column}"
                ),
                observation_family=MADDISON_PROJECT_OBSERVATION_FAMILY,
                indicator_code=variable_name,
                value=(
                    float(numeric_value)
                    if _is_real_number(numeric_value)
                    else None
                ),
                value_type="numeric",
                year=year,
                country_code=iso3,
                country_name=country,
                leader_id=None,
                leader_name=None,
                unit=MADDISON_PROJECT_COLUMN_UNITS.get(raw_column),
                scale=None,
                source_version=source_version,
                raw_locator=RawLocator(
                    asset_id=asset_id,
                    path=xlsx_path_str,
                    sheet=MADDISON_PROJECT_SHEET_NAME,
                    column_name=raw_column,
                ),
                transform_locator=TransformLocator(
                    adapter_version=None,
                    transform_name=MADDISON_PROJECT_TRANSFORM_NAME,
                    catalog_key=MADDISON_PROJECT_SOURCE_KEY,
                    rule_id=source_row_reference,
                ),
                quality_flags=tuple(quality_flags),
                warnings=(),
                extension=extension,
            ),
        )
    return iter(observations)


__all__ = ["emit_maddison_project_observations"]
