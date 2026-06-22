"""Country scope derivation for the Country-Year Chronicle slice.

This module owns the per-ISO3 country-scope metadata used by the
Increment 5 all-country condensed export. A country scope entry
encodes:

- the canonical display name (from V-Dem ``country_name``);
- the source-backed existence window ``[start_year, end_year]``
  (from V-Dem's min / max year per ``country_text_id``);
- a ``source`` tag (``"vdem"`` or ``"metadata"``) so a downstream
  reader can audit which source supplied the window.

The scope is merged with the pilot :data:`COUNTRY_METADATA` so
historical identities that V-Dem does not code separately (SUN)
remain in scope, and so the pilot's curated status overrides
(e.g. IND's ``colonial_status_until=1946``) are preserved.

The module is deliberately small: the scope is a dict of
:class:`CountryScopeEntry`, the existence-window mapper is a
single function, and the merge with the pilot metadata is one
straightforward loop. No I/O outside the V-Dem raw CSV; no LLM;
no client-matrix use.

Source strategy (chosen for the Increment 5 pass):

- **V-Dem ``country_text_id`` / ``country_name`` / ``year``** is the
  authoritative source-backed scope. Every V-Dem country has a
  defensible min / max year that the per-country ``groupby`` returns;
  the per-country ``country_name`` is V-Dem's own label, which is
  the most stable reference for the prototype. V-Dem has 202
  countries in v16; all 202 are valid 3-letter uppercase ISO3
  codes, so no IDs were dropped at the format filter.
- **The pilot :data:`COUNTRY_METADATA`** is overlaid so historical
  identities that V-Dem merges (SUN) and curated overrides
  (IND's colonial cutoff) keep their pilot semantics. The pilot
  metadata wins on conflicts (V-Dem's RUS record covers
  1789-2025; the pilot metadata pins RUS to start_year=1991).
- **CShapes / GW mappings** are NOT used to broaden scope in this
  pass. CShapes carries 252 GW codes (181 active in 2019); many
  are not modern ISO3 codes. Hand-mapping GW codes to ISO3 would
  risk inventing a colonial-period scope that V-Dem does not
  back; the safer path is to keep V-Dem as the scope source and
  rely on the per-country pilot metadata for the historical
  identities that V-Dem merges.

The existence-window helper
:func:`get_existence_status` is the only producer of the four
canonical ``existence_status`` labels
(:data:`EXISTS_STATUS_EXISTS`,
:data:`EXISTS_STATUS_NOT_FORMED`,
:data:`EXISTS_STATUS_SPLIT`,
:data:`EXISTS_STATUS_OUT_OF_SCOPE`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

from .constants import (
    COUNTRY_METADATA,
    EXISTS_STATUS_EXISTS,
    EXISTS_STATUS_NOT_FORMED,
    EXISTS_STATUS_OUT_OF_SCOPE,
    EXISTS_STATUS_SPLIT,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types and constants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CountryScopeEntry:
    """Per-country scope metadata used by the condensed writer.

    Attributes:
        iso3: Three-letter ISO3 code (the canonical identity key).
        country_name: Human-readable country name (from V-Dem's
            ``country_name`` column, with the pilot metadata
            override applied where applicable).
        start_year: First year of the source-backed existence
            window, inclusive. ``None`` when the source did not
            supply a defensible start year.
        end_year: Last year of the source-backed existence
            window, inclusive. ``None`` when the source did not
            supply a defensible end year (e.g. a country that is
            still in existence).
        source: Short source tag describing where the window
            came from. ``"vdem"`` for V-Dem-derived entries,
            ``"metadata"`` for pilot-metadata-only entries
            (today only SUN), and ``"merged"`` for entries where
            the pilot metadata overrode V-Dem (the
            ``country_name`` came from the pilot, the window
            from V-Dem).
    """

    iso3: str
    country_name: str
    start_year: int | None
    end_year: int | None
    source: str


#: Pattern that matches a valid three-letter uppercase ISO3 code.
#: V-Dem v16's country_text_id column always matches this pattern
#: (verified during Increment 0 reconnaissance). The condensed
#: writer uses it as a defensive filter even though today the
#: upstream read is already filtered.
_ISO3_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{3}$")


# ---------------------------------------------------------------------------
# Default V-Dem raw CSV path
# ---------------------------------------------------------------------------


def default_vdem_csv_path() -> Path:
    """Return the canonical raw V-Dem CSV path inside the data lake."""
    from ..paths import raw_dir

    return raw_dir("vdem") / "V-Dem-CY-Full+Others-v16.csv"


# ---------------------------------------------------------------------------
# V-Dem coverage reader
# ---------------------------------------------------------------------------


def _read_vdem_coverage(raw_csv_path: Path) -> pd.DataFrame:
    """Return ``(country_text_id, country_name, min_year, max_year)``.

    Reads the V-Dem raw CSV with a narrow column selection so the
    in-memory footprint is small. Drops rows with a missing
    country_text_id or year. Returns an empty ``DataFrame`` with
    the expected columns when the file is missing.
    """
    if not raw_csv_path.is_file():
        _logger.warning(
            "V-Dem raw CSV not found at %s; country scope will fall "
            "back to COUNTRY_METADATA only.",
            raw_csv_path,
        )
        return pd.DataFrame(
            columns=["country_text_id", "country_name", "min_year", "max_year"],
        )
    df = pd.read_csv(
        raw_csv_path,
        usecols=["country_text_id", "country_name", "year"],
        low_memory=False,
    )
    df = df.dropna(subset=["country_text_id", "year"])
    df["year"] = df["year"].astype("Int64")
    coverage = (
        df.groupby("country_text_id", as_index=False)
        .agg(
            country_name=("country_name", "first"),
            min_year=("year", "min"),
            max_year=("year", "max"),
        )
    )
    coverage["min_year"] = coverage["min_year"].astype("Int64")
    coverage["max_year"] = coverage["max_year"].astype("Int64")
    return coverage


# ---------------------------------------------------------------------------
# Scope derivation
# ---------------------------------------------------------------------------


def _safe_int(value: object) -> int | None:
    """Coerce a string / int / ``Int64`` to ``int`` or ``None``.

    Used for the pilot ``start_year`` / ``end_year`` / ``colonial_status_until``
    metadata fields where empty strings are common. A non-numeric
    value returns ``None`` rather than raising so the scope build
    degrades gracefully.
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _build_entry_from_vdem(row: pd.Series) -> CountryScopeEntry:
    """Build a :class:`CountryScopeEntry` from one V-Dem coverage row."""
    iso3 = str(row["country_text_id"]).strip().upper()
    country_name = (
        str(row["country_name"]).strip()
        if pd.notna(row["country_name"])
        else iso3
    )
    min_year = (
        int(row["min_year"])
        if pd.notna(row["min_year"])
        else None
    )
    max_year = (
        int(row["max_year"])
        if pd.notna(row["max_year"])
        else None
    )
    return CountryScopeEntry(
        iso3=iso3,
        country_name=country_name,
        start_year=min_year,
        end_year=max_year,
        source="vdem",
    )


def derive_country_scope(
    *,
    vdem_csv_path: Path | None = None,
    existing_metadata: dict[str, dict[str, str]] | None = None,
    include_non_iso3_ids: bool = False,
) -> dict[str, CountryScopeEntry]:
    """Derive the country scope by merging V-Dem coverage with pilot metadata.

    Parameters
    ----------
    vdem_csv_path:
        Path to the raw V-Dem CSV. Defaults to
        :func:`default_vdem_csv_path`. When the file is missing the
        function still returns a scope derived from the pilot
        metadata only.
    existing_metadata:
        Optional override for :data:`COUNTRY_METADATA`. When
        ``None`` the canonical :data:`COUNTRY_METADATA` constant is
        used.
    include_non_iso3_ids:
        When ``False`` (default) the function drops any V-Dem
        ``country_text_id`` that does not match the canonical
        3-letter uppercase pattern. Today every V-Dem country is a
        match, so the flag is a defensive guard for future V-Dem
        releases.

    Returns
    -------
    dict[str, CountryScopeEntry]
        Mapping of ISO3 -> :class:`CountryScopeEntry`. Pilot
        metadata wins on conflicts (the ``country_name`` and
        ``start_year`` / ``end_year`` come from the pilot when
        present; the underlying V-Dem values are kept only when
        the pilot has no entry).
    """
    path = vdem_csv_path or default_vdem_csv_path()
    coverage = _read_vdem_coverage(path)

    scope: dict[str, CountryScopeEntry] = {}

    # 1. Seed scope from V-Dem coverage (filtered to ISO3-shaped IDs).
    for _, row in coverage.iterrows():
        iso3 = str(row["country_text_id"]).strip().upper()
        if not iso3:
            continue
        if not include_non_iso3_ids and not _ISO3_PATTERN.match(iso3):
            continue
        scope[iso3] = _build_entry_from_vdem(row)

    # 2. Overlay the pilot metadata. The pilot wins on conflicts
    #    (historical identities like SUN are not in V-Dem, and
    #    curated overrides like IND's colonial cutoff and RUS's
    #    start_year=1991 must override the V-Dem defaults).
    pilot = existing_metadata if existing_metadata is not None else COUNTRY_METADATA
    for raw_iso3, meta in pilot.items():
        iso3 = raw_iso3.strip().upper()
        if not iso3:
            continue
        if not _ISO3_PATTERN.match(iso3):
            continue
        country_name = (meta.get("country_name") or iso3).strip()
        start_year = _safe_int(meta.get("start_year"))
        end_year = _safe_int(meta.get("end_year"))
        existing = scope.get(iso3)
        if existing is None:
            scope[iso3] = CountryScopeEntry(
                iso3=iso3,
                country_name=country_name,
                start_year=start_year,
                end_year=end_year,
                source="metadata",
            )
            continue
        # The pilot metadata wins on conflicts. The source tag
        # becomes "merged" when the pilot supplied values that
        # differ from the V-Dem defaults.
        merged_name = country_name or existing.country_name
        merged_start = start_year if start_year is not None else existing.start_year
        merged_end = end_year if end_year is not None else existing.end_year
        # If the pilot and V-Dem agree on every value, keep the
        # V-Dem source tag. Otherwise mark "merged".
        if (
            merged_name == existing.country_name
            and merged_start == existing.start_year
            and merged_end == existing.end_year
        ):
            merged_source = existing.source
        else:
            merged_source = "merged"
        scope[iso3] = CountryScopeEntry(
            iso3=iso3,
            country_name=merged_name,
            start_year=merged_start,
            end_year=merged_end,
            source=merged_source,
        )
    return scope


def derive_all_country_scope(
    *,
    vdem_csv_path: Path | None = None,
) -> dict[str, CountryScopeEntry]:
    """Derive the full all-country scope used by ``--countries all``.

    This is a thin alias over :func:`derive_country_scope` that
    documents the intent: the all-country scope is the V-Dem
    coverage merged with the pilot historical identities, with
    all entries valid 3-letter uppercase ISO3 codes.

    The function is deliberately a separate symbol so callers
    (tests, CLI) can ask for the all-country scope by intent
    rather than re-deriving it.
    """
    return derive_country_scope(vdem_csv_path=vdem_csv_path)


# ---------------------------------------------------------------------------
# Existence-window mapper
# ---------------------------------------------------------------------------


def get_existence_status(entry: CountryScopeEntry, year: int) -> str:
    """Map ``(entry, year)`` to one of the four canonical labels.

    The mapping:

    - ``entry.start_year is None`` or ``entry.end_year is None`` ->
      :data:`EXISTS_STATUS_OUT_OF_SCOPE`. Today this never fires
      (V-Dem supplies a min / max year for every ID it carries),
      but the channel is reserved for future sources that may add
      countries without a defensible window.
    - ``year < entry.start_year`` -> :data:`EXISTS_STATUS_NOT_FORMED`.
    - ``year > entry.end_year`` -> :data:`EXISTS_STATUS_SPLIT`.
    - otherwise -> :data:`EXISTS_STATUS_EXISTS`.
    """
    if entry.start_year is None or entry.end_year is None:
        return EXISTS_STATUS_OUT_OF_SCOPE
    if year < entry.start_year:
        return EXISTS_STATUS_NOT_FORMED
    if year > entry.end_year:
        return EXISTS_STATUS_SPLIT
    return EXISTS_STATUS_EXISTS


__all__ = [
    "CountryScopeEntry",
    "default_vdem_csv_path",
    "derive_all_country_scope",
    "derive_country_scope",
    "get_existence_status",
]
