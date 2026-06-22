"""Archigos + REIGN raw-file loaders for the ruler resolver.

This module owns the data-lake file readers that build the in-memory
frames the :class:`RulerResolver` consumes:

- :func:`load_archigos_frame` reads the Archigos v4.1 Stata
  ``.dta`` file once and narrows to the pilot ISO3 set (via the
  COW->ISO3 mapping).
- :func:`load_reign_frame` reads the REIGN 2021-8 csv once and
  narrows to the same ISO3 set.

Both loaders are best-effort: when the raw file is missing the
loader logs a warning and returns an empty ``DataFrame`` with the
right columns so the resolver degrades gracefully (missing ruler).

The module is split out of ``ruler_resolver.py`` to keep that file
focused on the lookup logic and under the 400-line convention.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import pandas as pd

from ..paths import raw_dir
from .source_constants import ARCHIGOS_COW_TO_ISO3, REIGN_COW_TO_ISO3

_logger = logging.getLogger(__name__)


def default_archigos_dta_path() -> Path:
    """Return the canonical Archigos raw dta path inside the data lake."""
    return raw_dir("archigos") / "Archigos_4.1_stata14.dta"


def default_reign_csv_path() -> Path:
    """Return the canonical REIGN raw csv path inside the data lake."""
    return raw_dir("reign") / "REIGN_2021_8.csv"


def load_archigos_frame(
    *,
    archigos_dta_path: Path | None = None,
    iso3_scope: set[str] | None = None,
) -> pd.DataFrame:
    """Read the Archigos raw dta and narrow to ``iso3_scope``.

    Returns an empty ``DataFrame`` (with the right columns) when
    the file is missing. Logs a warning so the runner can surface
    the gap in the CLI summary.
    """
    path = archigos_dta_path or default_archigos_dta_path()
    if not path.is_file():
        _logger.warning(
            "Archigos raw dta not found at %s; Archigos-backed "
            "ruler lookups will be empty (REIGN is still attempted "
            "where its coverage applies).",
            path,
        )
        return pd.DataFrame(
            columns=["iso3", "ccode", "leader", "startdate", "enddate"]
        )
    with warnings.catch_warnings():
        # The .dta uses cp1252-encoded leader names; pandas emits
        # a UnicodeWarning on the fallback decode. The strings are
        # still valid for our purpose (ruler_name display), so we
        # silence the warning here and keep the leader names
        # verbatim.
        warnings.simplefilter("ignore", category=UnicodeWarning)
        df = pd.read_stata(path)
    cow_for_iso3 = {iso3: c for c, iso3 in ARCHIGOS_COW_TO_ISO3.items()}
    if iso3_scope:
        cow_set = {cow_for_iso3[i] for i in iso3_scope if i in cow_for_iso3}
        # Pilot runs are fully covered by the hand-maintained COW->ISO3 map.
        # All-country runs are not: they rely on V-Dem's per-row COWcode bridge.
        # If the hand map covers only a small fraction of the requested scope,
        # keep all Archigos COW rows so resolver.resolve(..., cowcode=...) can hit.
        if len(cow_set) >= max(1, len(iso3_scope) // 2):
            df = df[df["ccode"].isin(cow_set)].copy()
        else:
            df = df.copy()
    else:
        df = df.copy()
    df["iso3"] = df["ccode"].map(ARCHIGOS_COW_TO_ISO3)
    return df[["iso3", "ccode", "leader", "startdate", "enddate"]].reset_index(drop=True)


def load_reign_frame(
    *,
    reign_csv_path: Path | None = None,
    iso3_scope: set[str] | None = None,
) -> pd.DataFrame:
    """Read the REIGN raw csv and narrow to ``iso3_scope``.

    Returns an empty ``DataFrame`` (with the right columns) when
    the file is missing.
    """
    path = reign_csv_path or default_reign_csv_path()
    if not path.is_file():
        _logger.warning(
            "REIGN raw csv not found at %s; REIGN-backed ruler "
            "lookups will be empty (Archigos is still attempted "
            "where its coverage applies).",
            path,
        )
        return pd.DataFrame(
            columns=["iso3", "ccode", "year", "month", "leader", "government"]
        )
    df = pd.read_csv(path, low_memory=False)
    cow_for_iso3 = {iso3: c for c, iso3 in REIGN_COW_TO_ISO3.items()}
    if iso3_scope:
        cow_set = {cow_for_iso3[i] for i in iso3_scope if i in cow_for_iso3}
        if len(cow_set) >= max(1, len(iso3_scope) // 2):
            df = df[df["ccode"].isin(cow_set)].copy()
        else:
            df = df.copy()
    else:
        df = df.copy()
    df["iso3"] = df["ccode"].map(REIGN_COW_TO_ISO3)
    df["year"] = df["year"].astype("Int64").fillna(0).astype(int)
    df["month"] = df["month"].astype("Int64").fillna(0).astype(int)
    return df[["iso3", "ccode", "year", "month", "leader", "government"]].reset_index(drop=True)


__all__ = [
    "default_archigos_dta_path",
    "default_reign_csv_path",
    "load_archigos_frame",
    "load_reign_frame",
]
