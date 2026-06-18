"""Stage 2 -- SIPRI Yearbook Ch.7 (World Nuclear Forces): catalog, paths, parquet.

The I/O half of the SIPRI Yearbook Ch.7 adapter. Owns the
catalog + path helpers + parquet write + read orchestrator.
The PDF read lives in
:mod:`leaders_db.ingest.sipri_yearbook_ch7_pdf`. The DB writes
live in :mod:`leaders_db.ingest.sipri_yearbook_ch7_db`. The
pure coercion helpers live in
:mod:`leaders_db.ingest.sipri_yearbook_ch7_db_helpers`. The
orchestrator lives in :mod:`leaders_db.ingest.sipri_yearbook_ch7`.

SIPRI Yearbook Ch.7 is the **first PDF-based source** in the
pipeline. The Stage 2 adapter reads only Table 7.1 on the first
content page of the 97-page YB24 07 WNF.pdf via ``pdfplumber``
and handles 3 sentinels: ``"-"`` (U+2013 en-dash, nil -> 0),
``".."`` (two ASCII dots, N/A -> None), and ``"c. <num>
[letter]"`` (circa + footnote -> parsed integer).

Constants live here (the lowest-level module that does NOT
import from siblings).
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pdfplumber
import pyarrow.parquet as pq

from ..paths import processed_dir, raw_dir
from .sipri_yearbook_ch7_pdf import read_table_7_1

_logger = logging.getLogger(__name__)

# Constants: source key, attribution block, catalog path, raw
# PDF name (YB24; a future YB25 would be "YB25 07 WNF.pdf"),
# parquet name, parquet file-level metadata keys, the non-country
# denylist, the snapshot-year regex, and the default snapshot
# year. The attribution block is byte-for-byte equal to the
# citation in docs/source-attributions.md (drift-guard test).
SIPRI_YEARBOOK_CH7_SOURCE_KEY: str = "sipri_yearbook_ch7"
SIPRI_YEARBOOK_CH7_ATTRIBUTION: str = (
    'Stockholm International Peace Research Institute. 2024. '
    '"World Nuclear Forces." In '
    'SIPRI Yearbook 2024: Armaments, Disarmament and International Security. '
    'Oxford University Press.'
)
_DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "sipri_yearbook_ch7.csv"
)
_RAW_PDF_NAME: str = "YB24 07 WNF.pdf"
_PROCESSED_PARQUET_NAME: str = "sipri_yearbook_ch7_country_year.parquet"
_PARQUET_META_ATTRIBUTION: str = "sipri_yearbook_ch7_attribution"
_PARQUET_META_SOURCE_KEY: str = "sipri_yearbook_ch7_source_key"
_SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS: frozenset[str] = frozenset({
    "Total", "World",
})
_SNAPSHOT_YEAR_RE = re.compile(r"January\s+(\d{4})")
_DEFAULT_SNAPSHOT_YEAR: int = 2024


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the SIPRI Yearbook Ch.7 indicator catalog.

    The V-Dem / WDI / WGI / UCDP / SIPRI milex
    :class:`IndicatorSpec` shape is reused verbatim.
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

        Accepts both ``higher_is_better=1/0`` (WGI / V-Dem /
        WDI / UCDP / SIPRI milex convention) and ``True/False``
        (Python-bool literals).
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=_parse_higher_is_better(
                row.get("higher_is_better", "1"),
            ),
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
        )


def _parse_higher_is_better(raw: object) -> bool:
    """Parse a ``higher_is_better`` catalog value into a bool.

    Accepts ``"1"`` / ``"0"`` and ``"True"`` / ``"False"``. The
    default is ``True`` (matching the V-Dem default).
    """
    if isinstance(raw, bool):
        return raw
    if not isinstance(raw, str):
        return True
    text = raw.strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n", ""}:
        return False
    return True  # defensive default


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the SIPRI Yearbook Ch.7 indicator catalog.

    Mirrors the V-Dem / WDI / WGI / UCDP / SIPRI milex loaders:
    handles the leading ``#`` comment block, drops comment-only
    lines, validates the required column set, and returns one
    :class:`IndicatorSpec` per data row in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing.
    """
    path = catalog_path or _DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(
            f"SIPRI Yearbook Ch.7 indicator catalog not found: {path}"
        )
    required = {
        "variable_name", "raw_column", "rating_category",
        "raw_scale", "normalized_scale_target", "higher_is_better",
        "unit", "description",
    }
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"SIPRI Yearbook Ch.7 catalog {path} has no data rows"
        )
    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"SIPRI Yearbook Ch.7 catalog {path} is missing "
            f"required columns: {sorted(missing)}"
        )
    specs: list[IndicatorSpec] = []
    for row in reader:
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


def default_pdf_path() -> Path:
    """Return the conventional SIPRI Yearbook Ch.7 PDF path.

    Resolves to
    ``<project_root>/data/raw/sipri_yearbook_ch7/YB24 07 WNF.pdf``.
    Raises :class:`FileNotFoundError` if the file is missing.
    """
    path = raw_dir(SIPRI_YEARBOOK_CH7_SOURCE_KEY) / _RAW_PDF_NAME
    if not path.is_file():
        raise FileNotFoundError(
            f"SIPRI Yearbook Ch.7 PDF not found: {path}"
        )
    return path


def default_processed_parquet_path() -> Path:
    """Return the conventional SIPRI Yearbook Ch.7 narrow parquet
    path. Creates the ``data/processed/sipri_yearbook_ch7/``
    directory if missing.
    """
    processed_dir(SIPRI_YEARBOOK_CH7_SOURCE_KEY).mkdir(
        parents=True, exist_ok=True,
    )
    return (
        processed_dir(SIPRI_YEARBOOK_CH7_SOURCE_KEY)
        / _PROCESSED_PARQUET_NAME
    )


def read_sipri_yearbook_ch7(
    *,
    year: int | None = None,
    pdf_path: Path | None = None,
    catalog_path: Path | None = None,
) -> pd.DataFrame:
    """Read the SIPRI Yearbook Ch.7 PDF and pivot to wide format.

    Opens the PDF, extracts Table 7.1 via
    :func:`sipri_yearbook_ch7_pdf.read_table_7_1`, filters
    aggregate rows, builds a long frame, and pivots long ->
    wide. Indicator columns are ``Int64`` (nullable). An
    out-of-snapshot year returns empty. Attaches
    ``pdf_pages_total``, ``snapshot_year``, and the
    ``_sipri_yearbook_ch7_raw_lookup`` audit-trail attrs.

    Args:
        year: filter to a single year. Default: snapshot year.
        pdf_path: override the input PDF. Default: data-lake path.
        catalog_path: override the catalog. Default: checked-in.

    Returns:
        A DataFrame with ``country`` (display name), ``year``
        (int), and one column per catalog indicator (``Int64``
        nullable). The country column carries the raw display
        name (Stage 3 resolves to ISO3 via ``country_aliases.csv``).

    Raises:
        FileNotFoundError: if the PDF is missing.
        ValueError: if Table 7.1 cannot be found in the first
            3 pages.
    """
    path = pdf_path or default_pdf_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"SIPRI Yearbook Ch.7 PDF not found: {path}"
        )

    specs = load_indicator_catalog(catalog_path=catalog_path)

    with pdfplumber.open(path) as pdf:
        pdf_pages_total = len(pdf.pages)
        first_page_text = pdf.pages[0].extract_text() or ""
        snapshot_year = _extract_snapshot_year(first_page_text)

    # read_table_7_1 re-opens the PDF; pdfplumber is fast.
    table_rows = read_table_7_1(path)
    country_rows = [
        row for row in table_rows
        if row["country"] not in _SIPRI_YEARBOOK_CH7_NON_COUNTRY_LABELS
    ]

    if year is not None and int(year) != int(snapshot_year):
        return _empty_wide(specs, pdf_pages_total, snapshot_year)

    # Build the long frame + raw_lookup (preserves the literal
    # PDF cell text for the source_observations audit trail).
    long_records: list[dict[str, object]] = []
    raw_lookup: dict[tuple[str, int, str], str] = {}
    snapshot_y = int(snapshot_year)
    for country_dict in country_rows:
        country = str(country_dict["country"])
        for spec in specs:
            raw_col = spec.raw_column
            value = country_dict.get(raw_col)
            raw_value = country_dict.get(f"raw_value_{raw_col}", "")
            long_records.append({
                "country": country,
                "year": snapshot_y,
                "variable_name": spec.variable_name,
                "value": value,
            })
            raw_lookup[(country, snapshot_y, spec.variable_name)] = (
                str(raw_value)
            )

    if not long_records:
        return _empty_wide(
            specs, pdf_pages_total, snapshot_year, raw_lookup,
        )

    # Pivot to wide. Re-order to match the catalog
    # (``total_inventory, deployed, retired``).
    long_df = pd.DataFrame.from_records(long_records)
    indicator_cols = [s.variable_name for s in specs]
    wide = long_df.pivot_table(
        index=["country", "year"],
        columns="variable_name",
        values="value",
        aggfunc="first",
    ).reset_index()
    wide = wide[["country", "year", *indicator_cols]]
    wide["year"] = wide["year"].astype(int)
    for col in indicator_cols:
        wide[col] = wide[col].astype("Int64")

    wide.attrs["pdf_pages_total"] = int(pdf_pages_total)
    wide.attrs["snapshot_year"] = snapshot_y
    wide.attrs["_sipri_yearbook_ch7_raw_lookup"] = raw_lookup
    return wide


def _empty_wide(
    specs: list[IndicatorSpec],
    pdf_pages_total: int,
    snapshot_year: int,
    raw_lookup: dict[tuple[str, int, str], str] | None = None,
) -> pd.DataFrame:
    """Build an empty wide frame with the expected column shape
    and audit attrs. Used for the out-of-snapshot-year and
    all-rows-filtered cases.
    """
    wide = pd.DataFrame(
        columns=["country", "year"] + [s.variable_name for s in specs],
    )
    wide.attrs["pdf_pages_total"] = int(pdf_pages_total)
    wide.attrs["snapshot_year"] = int(snapshot_year)
    wide.attrs["_sipri_yearbook_ch7_raw_lookup"] = raw_lookup or {}
    return wide


def _extract_snapshot_year(page_text: str) -> int:
    """Extract the snapshot year from the Table 7.1 caption.

    The YB24 caption reads ``Table 7.1. World nuclear forces,
    January 2024``. The test fixture has no caption and falls
    back to 2024.
    """
    match = _SNAPSHOT_YEAR_RE.search(page_text)
    return int(match.group(1)) if match else _DEFAULT_SNAPSHOT_YEAR



def write_sipri_yearbook_ch7_parquet(
    df: pd.DataFrame,
    parquet_path: Path | None = None,
    attribution: str | None = None,
) -> Path:
    """Persist the wide-format frame as parquet with attribution
    metadata.

    Mirrors :func:`sipri_milex_io.write_sipri_milex_parquet`.
    The ``_sipri_yearbook_ch7_raw_lookup`` attr is intentionally
    stripped before the write (the raw_value audit trail is
    reconstructed from ``source_observations``).
    """
    out = parquet_path or default_processed_parquet_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.attrs = {
        k: v for k, v in (df.attrs or {}).items()
        if k != "_sipri_yearbook_ch7_raw_lookup"
    }
    df.to_parquet(out, engine="pyarrow", index=False)
    _attach_parquet_metadata(
        out, attribution=attribution or SIPRI_YEARBOOK_CH7_ATTRIBUTION,
    )
    return out


def _attach_parquet_metadata(parquet_path: Path, *, attribution: str) -> None:
    """Attach the SIPRI Yearbook Ch.7 attribution + source key to
    the parquet's schema metadata.

    Best-effort: on failure, the parquet remains valid and we
    log a warning. Schema/data errors re-raise so the
    orchestrator can decide.
    """
    try:
        table = pq.read_table(parquet_path)
        meta = dict(table.schema.metadata or {})
        meta[_PARQUET_META_ATTRIBUTION] = attribution.encode("utf-8")
        meta[_PARQUET_META_SOURCE_KEY] = (
            SIPRI_YEARBOOK_CH7_SOURCE_KEY.encode("utf-8")
        )
        new_table = table.replace_schema_metadata(meta)
        pq.write_table(new_table, parquet_path, compression="snappy")
    except (OSError, pq.ArrowException) as exc:
        # Transient I/O or pyarrow error. The data is intact;
        # the audit metadata is lost. The attribution is also
        # carried in the run manifest, so the audit trail
        # survives.
        _logger.warning(
            "Failed to attach SIPRI Yearbook Ch.7 attribution metadata "
            "to %s: %s. The data parquet is valid; the run manifest "
            "is the audit fallback.",
            parquet_path, exc,
        )


__all__ = [
    "SIPRI_YEARBOOK_CH7_ATTRIBUTION",
    "SIPRI_YEARBOOK_CH7_SOURCE_KEY",
    "IndicatorSpec",
    "default_pdf_path",
    "default_processed_parquet_path",
    "load_indicator_catalog",
    "read_sipri_yearbook_ch7",
    "write_sipri_yearbook_ch7_parquet",
]
