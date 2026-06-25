"""Unified-source World Bank WGI observation-emission helpers.

This module owns the per-row :class:`NormalizedObservation`
build loop for the unified-source WGI adapter. The function
takes the wide-format DataFrame returned by the legacy
:func:`leaders_db.ingest.wgi_xlsx.read_wgi` reader (one row per
``(iso3, year)``, one column per catalog ``variable_name``) and
emits the canonical observation records with raw locators
(xlsx path + sheet name + column name + row number when
available), transform locators (transform name + catalog key +
rule id), attribution text, and unit labels per indicator.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wgi.adapter` to
keep the adapter class module focused on the lifecycle methods
(``check_ready`` / ``read_raw`` / ``transform``) and respect
the documented 400-line module convention.

Legacy wide-frame contract
--------------------------

The legacy :func:`read_wgi` reader emits a wide-format DataFrame
with one row per ``(iso3, year)`` and one column per catalog
``variable_name`` (e.g. ``wgi_voice_and_accountability``). The
``"#N/A"`` literal is coerced to ``NaN`` in the wide frame, so
the transform skips NaN cells (no silent conversion of missing
raw cells; SRC-OBS-007).

The legacy reader DOES NOT expose per-cell row numbers for the
WGI xlsx; the wide frame carries the ``iso3`` + ``year`` per
row but the original xlsx row index (16..229 in the live xlsx)
is not preserved through the long-to-wide pivot. The unified
``RawLocator.row_number`` is therefore ``None`` and the
``transform_locator.rule_id`` carries the
``world_bank_wgi:<iso3>:<year>`` pattern that downstream audit
code can resolve via ``wgi:<iso3>`` -> Stage 3 country match ->
back to the xlsx row. This is the documented contract per the
brief: "If row numbers are not available from legacy wide frame,
use best available locator and document/test that row_number is
None rather than fabricated."

Per-observation extension payload
---------------------------------

Every observation's ``extension`` carries:

- ``wgi_raw_indicator_code`` -- the catalog ``variable_name``
  (e.g. ``wgi_voice_and_accountability``); mirrors the WDI
  convention so downstream score modules can resolve the raw
  value back to the catalog indicator without re-reading the
  legacy catalog.
- ``wgi_sheet_name`` -- the legacy xlsx sheet name for the
  indicator (e.g. ``VoiceandAccountability``); useful for audit
  code that wants to reopen the staged xlsx and look at the
  full per-year statistics (Estimate, StdErr, NumSrc, Rank,
  Lower, Upper).
- ``wgi_indicator_category`` -- the catalog
  ``rating_category`` value (``effectiveness`` for 5 indicators
  + ``integrity`` for ``Control of Corruption``). Carried so
  downstream code can filter by category without re-reading
  the legacy catalog.
- ``attribution`` -- the canonical WGI citation block (Rule
  #15; byte-identical to the legacy ``WGI_ATTRIBUTION``
  constant and the ``docs/sources/attributions.md`` entry).
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
    WORLD_BANK_WGI_ATTRIBUTION_TEXT,
    WORLD_BANK_WGI_DEFAULT_VERSION,
    WORLD_BANK_WGI_OBSERVATION_FAMILY,
    WORLD_BANK_WGI_SOURCE_KEY,
)

# Asset id used for the ``wgidataset.xlsx`` raw asset across all
# observation locators in a single run. Matches the WDI
# convention (one logical asset per raw bundle) so audit code
# can group observations by asset.
WORLD_BANK_WGI_XLSX_ASSET_ID: str = (
    f"{WORLD_BANK_WGI_SOURCE_KEY}:wgidataset.xlsx"
)

# Transform-name string carried on every NormalizedObservation's
# ``transform_locator``. Surfaces the legacy reader/transform
# pair that produced the observation so downstream scoring can
# audit the parse path.
WORLD_BANK_WGI_TRANSFORM_NAME: str = "read_wgi"


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
    """Return the canonical WGI version stamp.

    The unified adapter hardcodes the canonical version
    ``"Worldwide Governance Indicators 2023 Update (data
    through 2022)"`` (matches the staged
    ``data/raw/world_bank_wgi/metadata.json`` ``version`` field
    and the canonical attribution block in
    ``docs/sources/attributions.md``). Observations therefore
    carry this validated version, not arbitrary metadata /
    request text.
    """
    return WORLD_BANK_WGI_DEFAULT_VERSION


def _resolve_sheet_name(variable_name: str) -> str | None:
    """Map a catalog ``variable_name`` back to its legacy xlsx sheet name.

    The catalog at ``src/leaders_db/ingest/catalogs/wgi.csv``
    uses the legacy xlsx sheet name as ``raw_column``. The
    transform carries the sheet name onto every observation's
    ``extension`` so audit code can re-open the xlsx and look at
    the full per-year statistics (Estimate, StdErr, NumSrc,
    Rank, Lower, Upper) for the indicator.

    Returns ``None`` when the ``variable_name`` is not in the
    canonical mapping; the extension payload then omits the
    ``wgi_sheet_name`` field so the contract is best-effort
    (the transform never silently invents metadata).
    """
    _SHEET_BY_VARIABLE: dict[str, str] = {
        "wgi_voice_and_accountability": "VoiceandAccountability",
        "wgi_political_stability": "Political StabilityNoViolence",
        "wgi_government_effectiveness": "GovernmentEffectiveness",
        "wgi_regulatory_quality": "RegulatoryQuality",
        "wgi_rule_of_law": "RuleofLaw",
        "wgi_control_of_corruption": "ControlofCorruption",
    }
    return _SHEET_BY_VARIABLE.get(variable_name)


def _resolve_indicator_category(variable_name: str) -> str | None:
    """Map a catalog ``variable_name`` back to its ``rating_category``.

    Returns ``None`` when the ``variable_name`` is not in the
    canonical mapping so the extension payload omits the
    category rather than silently guessing.
    """
    _CATEGORY_BY_VARIABLE: dict[str, str] = {
        "wgi_voice_and_accountability": "effectiveness",
        "wgi_political_stability": "effectiveness",
        "wgi_government_effectiveness": "effectiveness",
        "wgi_regulatory_quality": "effectiveness",
        "wgi_rule_of_law": "effectiveness",
        "wgi_control_of_corruption": "integrity",
    }
    return _CATEGORY_BY_VARIABLE.get(variable_name)


def emit_world_bank_wgi_observations(
    wide_df: Any,
    request: SourceIngestRequest,
    xlsx_path: Path | None,
    metadata: dict[str, Any] | None,
) -> Iterable[NormalizedObservation]:
    """Convert the wide-format DataFrame into
    :class:`NormalizedObservation` records.

    Parameters
    ----------
    wide_df:
        The wide-format DataFrame returned by the legacy
        :func:`leaders_db.ingest.wgi_xlsx.read_wgi` reader --
        one row per ``(iso3, year)`` with one column per
        catalog ``variable_name``. ``NaN`` cells are skipped
        (no silent conversion of missing raw cells;
        SRC-OBS-007).
    request:
        The request-scoped :class:`SourceIngestRequest`
        driving the run. Used for the source-version stamp.
        Year / country / leader filters are applied by the
        caller BEFORE this helper is invoked so the wide_df
        has already been narrowed.
    xlsx_path:
        Optional path to the staged ``wgidataset.xlsx``;
        carried verbatim onto every observation's
        :class:`RawLocator`.
    metadata:
        Optional parsed bundle ``metadata.json`` payload. Not
        consumed for the observation emission contract -- kept
        in the signature for symmetry with the PWT / Maddison /
        WDI transform helpers.

    Returns
    -------
    Iterable[NormalizedObservation]
        An iterable of canonical observations. Empty when
        ``wide_df`` is empty (e.g. an out-of-coverage year
        request, or the staged fixture has no rows for the
        requested filter scope).
    """
    if metadata is None:
        metadata = {}

    if wide_df is None:
        return iter(())

    xlsx_path_str = str(xlsx_path) if isinstance(xlsx_path, Path) else None
    asset_id = WORLD_BANK_WGI_XLSX_ASSET_ID
    source_version = _canonical_version()

    observations: list[NormalizedObservation] = []
    for _, wide_row in wide_df.iterrows():
        iso3 = str(wide_row["iso3"])
        year = int(wide_row["year"])

        for column_name in wide_df.columns:
            if column_name in {"iso3", "year"}:
                continue
            cell_value = wide_row.get(column_name)
            if not _is_real_number(cell_value):
                # NaN / None -- do NOT emit an observation
                # (no silent conversion of missing cells).
                continue

            sheet_name = _resolve_sheet_name(column_name)
            indicator_category = _resolve_indicator_category(
                column_name,
            )

            # The wide frame loses the original xlsx row index
            # through the long-to-wide pivot; the legacy
            # ``source_row_reference`` is the canonical
            # ``wgi:<iso3>`` pattern (the same pattern the
            # legacy Stage 2 DB writer uses). We surface that
            # pattern on the transform locator rule_id so
            # downstream scoring / audit code can resolve the
            # per-row legacy reference without re-reading the
            # xlsx. We do NOT invent a row_number.
            source_row_reference = f"{WORLD_BANK_WGI_SOURCE_KEY}:{iso3}"
            rule_id = (
                f"{WORLD_BANK_WGI_SOURCE_KEY}:{iso3}:{year}:{column_name}"
            )

            extension: dict[str, Any] = {
                "attribution": WORLD_BANK_WGI_ATTRIBUTION_TEXT,
                "source_row_reference": source_row_reference,
            }
            if sheet_name is not None:
                extension["wgi_sheet_name"] = sheet_name
            if indicator_category is not None:
                extension["wgi_indicator_category"] = (
                    indicator_category
                )

            observations.append(
                NormalizedObservation(
                    source_id=request.source_id,
                    observation_id=(
                        f"{WORLD_BANK_WGI_SOURCE_KEY}:{iso3}:"
                        f"{year}:{column_name}"
                    ),
                    observation_family=WORLD_BANK_WGI_OBSERVATION_FAMILY,
                    indicator_code=column_name,
                    value=float(cell_value),
                    value_type="numeric",
                    year=year,
                    country_code=iso3,
                    country_name=None,
                    leader_id=None,
                    leader_name=None,
                    unit="z_score",
                    scale="z_score",
                    source_version=source_version,
                    raw_locator=RawLocator(
                        asset_id=asset_id,
                        path=xlsx_path_str,
                        sheet=sheet_name,
                        # The legacy wide frame does not carry
                        # the xlsx row index; row_number is
                        # intentionally None (we never
                        # fabricate locators; see
                        # docs/process/coding-guidelines.md
                        # "no invented historical data").
                        row_number=None,
                        column_name=column_name,
                    ),
                    transform_locator=TransformLocator(
                        adapter_version=None,
                        transform_name=WORLD_BANK_WGI_TRANSFORM_NAME,
                        catalog_key=WORLD_BANK_WGI_SOURCE_KEY,
                        rule_id=rule_id,
                    ),
                    quality_flags=(),
                    warnings=(),
                    extension=extension,
                ),
            )
    return iter(observations)


__all__ = [
    "WORLD_BANK_WGI_TRANSFORM_NAME",
    "WORLD_BANK_WGI_XLSX_ASSET_ID",
    "emit_world_bank_wgi_observations",
]
