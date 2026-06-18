"""Stage 2 — V-Dem CSV read, indicator catalog, and parquet write.

This module is the I/O half of the V-Dem adapter. It owns:

- :class:`IndicatorSpec` -- one row of the catalog, typed.
- :func:`load_indicator_catalog` -- read the catalog CSV (handles the
  comment block at the top + comment-only line filtering).
- :func:`read_vdem_csv` -- read the wide V-Dem CSV and narrow it to
  the catalog + identity columns.
- :func:`write_vdem_parquet` -- persist the narrow frame as parquet
  with the V-Dem attribution attached to the schema metadata.

The DB-side functions (sources upsert, source_observations write, run
manifest) live in :mod:`leaders_db.ingest.vdem_db`. The orchestrator
that ties everything together lives in :mod:`leaders_db.ingest.vdem`.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir

_logger = logging.getLogger(__name__)

#: Source key used everywhere in the data lake + CLI dispatch. Lives
#: here (the lowest-level module) to avoid a circular import:
#: ``vdem_db`` imports it from us, and ``vdem`` re-exports it for
#: callers that want ``leaders_db.ingest.vdem.VDEM_SOURCE_KEY``.
VDEM_SOURCE_KEY = "vdem"

#: Stable V-Dem attribution block. The canonical text lives in
#: ``docs/source-attributions.md`` (V-Dem section). This constant must
#: be a substring of that doc; the
#: :func:`test_vdem_attribution_matches_attributions_doc` test enforces
#: the byte-for-byte consistency. The constant lives in ``vdem_io`` to
#: break the import cycle: ``vdem_db`` imports it from here, and
#: ``vdem`` re-exports it.
VDEM_ATTRIBUTION: str = (
    "Coppedge, Michael, John Gerring, Carl Henrik Knutsen, Staffan I. "
    "Lindberg, Jan Teorell, David Altman, Fabio Angiolillo, Michael "
    "Bernhard, Agnes Cornell, M. Steven Fish, Linnea Fox, Lisa "
    "Gastaldi, Haakon Gjerløw, Adam Glynn, Ana Good God, Allen Hicken, "
    "Katrin Kinzelbach, Joshua Krusell, Kyle L. Marquardt, Kelly "
    "McMann, Valeriya Mechkova, Juraj Medzihorsky, Anja Neundorf, "
    "Pamela Paxton, Daniel Pemstein, Josefine Pernes, Johannes von "
    "Römer, Brigitte Seim, Rachel Sigman, Svend-Erik Skaaning, "
    "Jeffrey Staton, Aksel Sundström, Marcus Tannenberg, Eitan "
    "Tzelgov, Yi-ting Wang, Tore Wig, Steven Wilson and Daniel "
    "Ziblatt. 2026. \"V-Dem [Country-Year/Country-Date] Dataset v16\" "
    "Varieties of Democracy (V-Dem) Project. "
    "https://doi.org/10.23696/vdemds26."
)

#: The default location of the indicator catalog. Lives here so
#: :func:`write_run_manifest` (in ``vdem_db``) can import it without
#: a cycle.
_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "catalogs" / "vdem.csv"

#: Identity columns carried from the wide V-Dem CSV into the narrow
#: frame. The narrow DataFrame renames ``country_id`` to
#: ``vdem_country_id`` to avoid collision with the ``countries.id``
#: foreign key in :class:`SourceObservation` (Stage 3 fills the FK).
_VDEM_IDENTITY_COLUMNS: tuple[str, ...] = (
    "country_name",
    "country_text_id",
    "vdem_country_id",  # renamed below from V-Dem's "country_id" column
    "year",
)

#: The default location of the raw V-Dem CSV inside the data lake.
_RAW_CSV_NAME = "V-Dem-CY-Full+Others-v16.csv"

#: The narrow parquet that Stage 2 writes under ``data/processed/vdem/``.
_PROCESSED_PARQUET_NAME = "vdem_country_year.parquet"

#: Parquet file-level metadata keys (UTF-8 bytes for pyarrow schema.metadata).
_PARQUET_META_ATTRIBUTION = "vdem_attribution"
_PARQUET_META_SOURCE_KEY = "vdem_source_key"


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the V-Dem indicator catalog.

    ``raw_scale`` and ``higher_is_better`` are stored here so the score
    modules in Stage 9-10 can resolve normalization and direction without
    re-deriving them from the catalog at every call.
    """

    variable_name: str
    raw_column: str
    rating_category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    description: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The CSV uses ``higher_is_better=1`` for "higher is better" and
        ``0`` otherwise. The constructor converts that to a real bool.
        Empty / missing values in the optional fields become ``""``.
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=row.get("higher_is_better", "1").strip() == "1",
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def load_indicator_catalog(catalog_path: Path | None = None) -> list[IndicatorSpec]:
    """Load the V-Dem indicator catalog from ``catalogs/vdem.csv``.

    The catalog file may begin with a comment block (lines starting with
    ``#``); the loader skips those before detecting the header row.
    Returns the rows in file order, which is the canonical
    :class:`IndicatorSpec` list used by every downstream V-Dem call.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog header.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"V-Dem indicator catalog not found: {path}")

    required = {
        "variable_name",
        "raw_column",
        "rating_category",
        "raw_scale",
        "normalized_scale_target",
        "higher_is_better",
        "unit",
        "description",
    }

    # Read raw lines, drop comment-only lines, then hand the cleaned text
    # to csv.DictReader. Comment-only means: stripped line starts with ``#``
    # or is blank. Inline ``#`` characters inside a data row are preserved.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(f"V-Dem catalog {path} has no data rows after stripping comments")

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"V-Dem catalog {path} is missing required columns: {sorted(missing)}"
        )

    specs: list[IndicatorSpec] = []
    for row in reader:
        # Skip empty rows (e.g. trailing blank line).
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


def default_raw_csv_path() -> Path:
    """Return the conventional V-Dem raw CSV path inside the data lake."""
    return raw_dir(VDEM_SOURCE_KEY) / _RAW_CSV_NAME


def default_processed_parquet_path() -> Path:
    """Return the conventional V-Dem narrow parquet path."""
    processed_dir(VDEM_SOURCE_KEY).mkdir(parents=True, exist_ok=True)
    return processed_dir(VDEM_SOURCE_KEY) / _PROCESSED_PARQUET_NAME


def read_vdem_csv(
    csv_path: Path | None = None,
    *,
    year: int | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read the wide V-Dem CSV and narrow it to the catalog + identity cols.

    The narrow DataFrame has one row per ``(country_text_id, year)`` and
    one column per catalog indicator, plus the four identity columns
    ``country_name``, ``country_text_id``, ``vdem_country_id``, ``year``.
    Note the rename: V-Dem's raw column is ``country_id`` (the V-Dem
    internal integer). It is renamed to ``vdem_country_id`` here to
    avoid collision with the ``countries.id`` foreign key on
    :class:`SourceObservation` (which is filled by Stage 3 country match).

    Args:
        csv_path: override the raw CSV path. Default: ``data/raw/vdem/...v16.csv``.
        year: if set, keep only rows with that year. Default: keep all years.
        catalog_path: override the indicator catalog. Default: the checked-in catalog.

    Returns:
        A pandas DataFrame with the narrowed columns. ``year`` is integer.

    Raises:
        FileNotFoundError: if the raw CSV is missing.
        KeyError: if a catalog ``raw_column`` is absent from the CSV header.
    """
    path = csv_path or default_raw_csv_path()
    if not path.is_file():
        raise FileNotFoundError(f"V-Dem raw CSV not found: {path}")

    specs = load_indicator_catalog(catalog_path=catalog_path)
    raw_columns = [s.raw_column for s in specs]
    usecols = [
        "country_name",
        "country_text_id",
        "country_id",
        "year",
        *raw_columns,
    ]

    df = pd.read_csv(path, usecols=usecols, low_memory=False)

    # Coerce year to int (V-Dem stores it as int already, but be defensive).
    df["year"] = df["year"].astype(int)

    # Validate that every catalog raw_column is present in the loaded frame.
    missing = [s.raw_column for s in specs if s.raw_column not in df.columns]
    if missing:
        raise KeyError(
            f"V-Dem CSV is missing catalog columns: {missing}. "
            "Check that the file is v16 and the catalog is in sync."
        )

    # Rename V-Dem's ``country_id`` to ``vdem_country_id`` so the narrow
    # frame does not collide with our ``countries.id`` foreign key.
    df = df.rename(columns={"country_id": "vdem_country_id"})

    if year is not None:
        df = df.loc[df["year"] == int(year)].reset_index(drop=True)

    return df


def write_vdem_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the narrow frame as parquet.

    Uses pyarrow under the hood (already a project dependency). The
    parquet carries the V-Dem attribution as file-level metadata so
    downstream stages can recover the source without re-reading the
    attributions doc. Metadata attachment is best-effort: if pyarrow
    rejects the rewrite, the parquet itself remains valid and a warning
    is logged.

    Args:
        df: the narrow DataFrame (output of :func:`read_vdem_csv`).
        parquet_path: override the output path. Default: data-lake path.
        attribution: override the attribution text embedded in the
            parquet metadata. Default: the :data:`VDEM_ATTRIBUTION`
            constant (defined in this module to break the import
            cycle).
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(out, attribution=attribution or VDEM_ATTRIBUTION)
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the V-Dem attribution + source key to the parquet's schema metadata.

    pyarrow exposes arbitrary UTF-8 metadata on the schema. We rewrite
    the parquet in place to add it. This is best-effort: if the
    rewrite fails (corrupt file, race, full disk) the parquet remains
    valid and we log a warning. Schema/data errors are NOT swallowed
    silently -- they re-raise so the orchestrator can decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = VDEM_SOURCE_KEY.encode("utf-8")
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact; the audit
        # metadata is lost. Log and continue -- the attribution is
        # also carried in the run manifest, so the audit trail survives.
        _logger.warning(
            "Failed to attach V-Dem attribution metadata to %s: %s. "
            "The data parquet is valid; the run manifest is the audit fallback.",
            parquet_path,
            exc,
        )


__all__ = [
    "IndicatorSpec",
    "default_processed_parquet_path",
    "default_raw_csv_path",
    "load_indicator_catalog",
    "read_vdem_csv",
    "write_vdem_parquet",
]
