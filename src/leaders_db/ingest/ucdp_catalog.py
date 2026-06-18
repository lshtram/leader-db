"""Stage 2 -- UCDP indicator catalog: dataclass + CSV loader.

This module holds the UCDP indicator catalog dataclass and CSV
loader. It is split out of :mod:`ucdp_io` to keep the IO module
under the 400-line convention from
:file:`docs/coding-guidelines.md`. The catalog is the single source
of truth for which UCDP indicators are read in Stage 2; every Stage 2
UCDP call resolves its indicator list from this file.

The catalog has the standard 8 columns plus a 9th ``filter_logic``
column that holds the pandas query string for the type +
cross-border filter (e.g., ``type_of_violence == 1``,
``type_of_violence == 1 and gwnob.notna()``). The 9th column is
specific to UCDP; V-Dem / WDI / WGI catalogs do not need it because
those sources do not have a 3-way type + cross-border filter.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

#: Default location of the UCDP indicator catalog. Lives here so
#: :func:`write_ucdp_run_manifest` in :mod:`ucdp_db` can import it
#: without a cycle.
DEFAULT_CATALOG_PATH: Path = (
    Path(__file__).resolve().parent / "catalogs" / "ucdp.csv"
)


@dataclass(frozen=True)
class IndicatorSpec:
    """One row of the UCDP indicator catalog.

    The V-Dem / WDI / WGI :class:`IndicatorSpec` shape is reused,
    with the addition of ``filter_logic`` -- the 9th column in the
    UCDP catalog that holds the pandas query string for the type +
    cross-border filter (``type_of_violence == 1``,
    ``type_of_violence == 3``, ``type_of_violence == 1 and gwnob.notna()``).
    """

    variable_name: str
    raw_column: str
    rating_category: str
    raw_scale: str
    normalized_scale_target: str
    higher_is_better: bool
    unit: str
    description: str
    filter_logic: str = ""

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> IndicatorSpec:
        """Build a spec from one CSV row.

        The CSV uses ``higher_is_better=0`` for "lower is better" and
        ``1`` otherwise (the WGI / V-Dem / WDI convention). The
        constructor converts that to a real bool. ``filter_logic`` is
        an optional 9th column; missing values become ``""``.
        """
        return cls(
            variable_name=row["variable_name"],
            raw_column=row["raw_column"],
            rating_category=row["rating_category"],
            raw_scale=row["raw_scale"],
            normalized_scale_target=row["normalized_scale_target"],
            higher_is_better=row.get("higher_is_better", "0").strip() == "1",
            unit=row.get("unit", "").strip(),
            description=row.get("description", "").strip(),
            filter_logic=row.get("filter_logic", "").strip(),
        )


def load_indicator_catalog(
    catalog_path: Path | None = None,
) -> list[IndicatorSpec]:
    """Load the UCDP indicator catalog from ``catalogs/ucdp.csv``.

    Mirrors the V-Dem / WDI / WGI loaders: handles the leading ``#``
    comment block, drops comment-only lines, validates the required
    column set, and returns one :class:`IndicatorSpec` per data row
    in file order.

    Raises:
        FileNotFoundError: if the catalog file is missing.
        ValueError: if a required column is missing in the catalog
            header.
    """
    path = catalog_path or DEFAULT_CATALOG_PATH
    if not path.is_file():
        raise FileNotFoundError(f"UCDP indicator catalog not found: {path}")

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

    # Read raw lines, drop comment-only lines, then hand the cleaned
    # text to csv.DictReader. ``filter_logic`` is an optional 9th
    # column.
    cleaned_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)
    if not cleaned_lines:
        raise ValueError(
            f"UCDP catalog {path} has no data rows after stripping comments"
        )

    reader = csv.DictReader(cleaned_lines)
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(
            f"UCDP catalog {path} is missing required columns: "
            f"{sorted(missing)}"
        )

    specs: list[IndicatorSpec] = []
    for row in reader:
        # Skip empty rows (e.g. trailing blank line).
        if not row.get("variable_name"):
            continue
        specs.append(IndicatorSpec.from_csv_row(row))
    return specs


__all__ = [
    "DEFAULT_CATALOG_PATH",
    "IndicatorSpec",
    "load_indicator_catalog",
]
