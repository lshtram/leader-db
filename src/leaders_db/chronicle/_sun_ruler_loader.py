"""Soviet-leaders curated raw-file loader for the SUN ruler resolver.

This module owns the data-lake file reader for the curated, hand-coded
SUN leader spells that back the Soviet Union identity gap:

- :func:`load_sun_frame` reads the local CSV at
  ``data/raw/soviet_leaders_curated/soviet_leaders.csv`` and returns a
  ``pandas.DataFrame`` with the columns the ruler resolver expects
  (``iso3``, ``leader``, ``startdate``, ``enddate`` plus the optional
  documentation columns ``office``, ``ruler_title``, ``ruler_type``).

The loader is best-effort: when the raw file is missing the loader
logs a warning and returns an empty ``DataFrame`` with the right
columns so the resolver degrades gracefully (SUN rows fall back to
missing-ruler per the Increment 2 baseline).

The module is split out of ``ruler_resolver.py`` to keep that file
focused on the lookup logic and under the 400-line convention.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..paths import raw_dir

_logger = logging.getLogger(__name__)


def default_sun_csv_path() -> Path:
    """Return the canonical curated SUN-leaders CSV path inside the data lake."""
    return raw_dir("soviet_leaders_curated") / "soviet_leaders.csv"


def load_sun_frame(
    *,
    sun_csv_path: Path | None = None,
) -> pd.DataFrame:
    """Read the curated SUN-leaders CSV.

    Returns an empty ``DataFrame`` (with the right columns) when the
    file is missing. Logs a warning so the runner can surface the gap
    in the CLI summary.

    The CSV is expected to carry the columns ``iso3``, ``leader``,
    ``startdate``, ``enddate``, ``office``, ``ruler_title``,
    ``ruler_type``. Only ``iso3``, ``leader``, ``startdate``,
    ``enddate`` are required by the resolver; the rest are
    documentation-only and are returned to the caller so the row
    builder can lift ``ruler_title`` / ``ruler_type`` if useful.

    Unlike Archigos (cp1252), this file is plain UTF-8.
    """
    path = sun_csv_path or default_sun_csv_path()
    if not path.is_file():
        _logger.warning(
            "SUN curated leaders CSV not found at %s; "
            "Soviet Union ruler lookups will be empty.",
            path,
        )
        return pd.DataFrame(
            columns=[
                "iso3",
                "leader",
                "startdate",
                "enddate",
                "office",
                "ruler_title",
                "ruler_type",
            ]
        )
    df = pd.read_csv(path)
    required = {"iso3", "leader", "startdate", "enddate"}
    missing = required - set(df.columns)
    if missing:
        _logger.warning(
            "SUN curated leaders CSV at %s is missing required "
            "columns %s; treating the file as empty.",
            path,
            sorted(missing),
        )
        return pd.DataFrame(columns=list(required))
    df = df[df["iso3"] == "SUN"].copy()
    return df.reset_index(drop=True)


__all__ = ["default_sun_csv_path", "load_sun_frame"]
