"""Phase B Increment B -- PWT ``transform_pwt_long_frame`` boundary.

This file covers the Stage 2 ``transform_pwt_long_frame``
module's boundary contract: the transform pivots the wide
frame into the canonical long schema (``iso3``, ``year``,
``variable_name``, ``raw_value``, ``numeric_value``,
``raw_column``, ``source_row_reference``, ``temporal_kind``,
``attribution``). It also covers the source-owned indicator
catalog (``src/leaders_db/ingest/sources/pwt/catalog.csv``)
contract and the missing-cell DROP semantics.

PASS-ELIGIBLE / DOMAIN-RED conventions
--------------------------------------

- ``PASS-ELIGIBLE`` -- the catalog-exists / catalog-fields
  test passes against the committed artifact (file-shape
  contract).
- ``DOMAIN-RED`` -- the long-row schema, locator format,
  temporal_kind, attribution, duplicate-rejection,
  catalog-driven emission, and missing-cell tests are
  intentionally RED until the production transform lands.
  Failure mode is an assertion failure on the wrong-shaped
  stub output (1 placeholder long row) -- NOT
  ``ModuleNotFoundError``.

Coverage
--------

- The source-owned ``catalog.csv`` exists with 11 indicator
  rows and the required fields.
- The transform is catalog-driven: variable emission is
  limited to catalog rows and not a hard-coded extra.
- The transform emits the canonical long-row schema with no
  derived rows.
- ``source_row_reference`` is exactly
  ``pwt:Data:<countrycode>:<year>:<raw_column>``.
- ``temporal_kind`` is ``observed`` for every emitted row.
- The ``attribution`` column is the canonical PWT citation
  text on every row.
- Duplicate ``(countrycode, year)`` rows raise
  ``ValueError``.
- Blank / sentinel / non-numeric cells are DROPPED (no
  observation row emitted); numeric and numeric-like strings
  emit rows with the coerced ``numeric_value`` and
  preserved ``raw_value``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .conftest import (
    PWT_CATALOG_RAW_COLUMNS,
    PWT_XLSX_NAME,
)

# ---------------------------------------------------------------------------
# 1. Source-owned indicator catalog
# ---------------------------------------------------------------------------


def test_pwt_source_owned_catalog_exists_with_11_indicators() -> None:
    """``src/leaders_db/ingest/sources/pwt/catalog.csv`` exists
    and has 11 indicator rows with the required fields.

    PASS-ELIGIBLE: the catalog file is committed (Phase B slice
    adds it as a source-owned artifact) and satisfies the
    file-shape contract. The catalog-DRIVEN transform behavior
    is asserted separately in
    :func:`test_pwt_transform_is_catalog_driven`.
    """
    import csv

    from leaders_db.ingest.sources.pwt import PWT_CATALOG_RAW_COLUMNS

    catalog_path = (
        Path(__file__).resolve().parents[4]
        / "src"
        / "leaders_db"
        / "ingest"
        / "sources"
        / "pwt"
        / "catalog.csv"
    )
    catalog_path = catalog_path.resolve()
    assert catalog_path.is_file(), (
        f"PWT source-owned catalog missing at {catalog_path}"
    )

    # Read the catalog (skip leading comment lines that start
    # with ``#``).
    cleaned_lines: list[str] = []
    for raw_line in catalog_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        cleaned_lines.append(raw_line)

    reader = csv.DictReader(cleaned_lines)
    rows = [row for row in reader if row.get("variable_name")]
    assert len(rows) == 11, (
        f"expected 11 indicator rows in the PWT catalog; got "
        f"{len(rows)}"
    )

    # Every catalog row has the required fields.
    required_fields = {
        "variable_name",
        "raw_column",
        "rating_category",
        "raw_scale",
        "higher_is_better",
        "unit",
        "description",
    }
    for row in rows:
        missing = required_fields - set(row.keys())
        assert not missing, (
            f"catalog row {row.get('variable_name')!r} missing fields: "
            f"{sorted(missing)}"
        )

    # The 11 ``raw_column`` values in the catalog match the
    # per-source package's canonical constant
    # ``PWT_CATALOG_RAW_COLUMNS``.
    catalog_raw_columns = {row["raw_column"] for row in rows}
    assert catalog_raw_columns == set(PWT_CATALOG_RAW_COLUMNS), (
        f"catalog raw_columns {sorted(catalog_raw_columns)} do not "
        f"match PWT_CATALOG_RAW_COLUMNS "
        f"{sorted(PWT_CATALOG_RAW_COLUMNS)}"
    )


def test_pwt_transform_is_catalog_driven() -> None:
    """The transform is catalog-driven: variable emission is
    limited to catalog rows and not a hard-coded extra.

    The test builds a wide DataFrame with one extra column
    (``extra_not_in_catalog``) that is NOT in the
    ``PWT_CATALOG_RAW_COLUMNS`` list. The transform must NOT
    emit long rows for the extra column -- it must only emit
    rows for catalog raw_columns.

    DOMAIN-RED: the Phase B stub ``transform_pwt_long_frame``
    returns a wrong-shaped long DataFrame (1 row with
    placeholder content) regardless of the input. The test
    fails at the assertion that the long frame has rows for
    ``rgdpe`` and NOT for ``extra_not_in_catalog`` -- the
    production transform must be catalog-driven.
    """
    from leaders_db.ingest.sources.pwt import PWT_CATALOG_RAW_COLUMNS
    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    # Wide frame with one extra column NOT in the catalog.
    wide_df = pd.DataFrame(
        {
            "countrycode": ["USA"],
            "country": ["United States"],
            "currency_unit": ["US Dollar"],
            "year": [2019],
            "rgdpe": [1.0e12],  # in catalog
            "extra_not_in_catalog": ["ignored"],  # NOT in catalog
        }
    )

    long_df = transform_pwt_long_frame(wide_df)

    # The long frame's ``raw_column`` values must be a subset
    # of the catalog raw_columns. The extra column must NOT
    # produce a long row.
    long_raw_columns = set(long_df["raw_column"].tolist())
    catalog_set = set(PWT_CATALOG_RAW_COLUMNS)
    extras = long_raw_columns - catalog_set
    assert not extras, (
        f"transform emitted rows for non-catalog raw_columns: "
        f"{sorted(extras)}"
    )

    # The catalog column ``rgdpe`` MUST produce a long row.
    assert "rgdpe" in long_raw_columns, (
        "transform did not emit a row for the catalog column "
        "rgdpe; production must be catalog-driven"
    )


# ---------------------------------------------------------------------------
# 2. Transform: long-row schema + locator + temporal_kind + attribution
# ---------------------------------------------------------------------------


def test_pwt_transform_emits_canonical_long_row_columns(
    pwt_xlsx_dir: Path,
) -> None:
    """The transform emits the canonical long-row schema.

    DOMAIN-RED: ``transform_pwt_long_frame()`` returns a
    wrong-shaped long DataFrame (1 row with
    ``variable_name = "__derived_pwt_stub"``) in the Phase B
    stub. The test fails at the
    ``not any(v.startswith("__derived") ...)`` assertion --
    the production transform must emit the canonical long
    schema without derived rows.
    """
    from leaders_db.ingest.sources.pwt.reader import read_pwt
    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    raw_df = read_pwt(xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME)
    long_df = transform_pwt_long_frame(raw_df)
    expected_columns = {
        "iso3",
        "year",
        "variable_name",
        "raw_value",
        "numeric_value",
        "raw_column",
        "source_row_reference",
        "temporal_kind",
        "attribution",
    }
    assert expected_columns.issubset(set(long_df.columns)), (
        f"transform frame missing required columns: "
        f"{set(expected_columns) - set(long_df.columns)}"
    )
    assert not any(
        v.startswith("__derived") for v in long_df["variable_name"].tolist()
    ), "transform must not emit derived rows for PWT"


def test_pwt_transform_locator_format(pwt_xlsx_dir: Path) -> None:
    """``source_row_reference`` is exactly
    ``pwt:Data:<countrycode>:<year>:<raw_column>``.

    DOMAIN-RED: ``transform_pwt_long_frame()`` returns a
    wrong-shaped long DataFrame (1 row with
    ``source_row_reference = "stub:USA:2019:stub"``) in the
    Phase B stub. The test fails at the prefix assertion --
    the production transform must stamp the canonical
    locator.
    """
    from leaders_db.ingest.sources.pwt.reader import read_pwt
    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    raw_df = read_pwt(xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME)
    long_df = transform_pwt_long_frame(raw_df)

    locators = long_df["source_row_reference"].tolist()
    assert locators, "transform emitted zero rows"
    prefix = "pwt:Data:"
    for ref in locators:
        assert ref.startswith(prefix), (
            f"locator must start with {prefix!r}; got {ref!r}"
        )
        tail = ref[len(prefix):]
        parts = tail.split(":")
        assert len(parts) == 3, (
            f"locator must have exactly 3 colon-separated fields "
            f"after the prefix; got {ref!r}"
        )
        iso3, year_str, raw_column = parts
        assert iso3 in {"USA", "MEX", "SWE"}
        assert year_str.isdigit() and 1900 <= int(year_str) <= 2100
        assert raw_column in PWT_CATALOG_RAW_COLUMNS


def test_pwt_transform_temporal_kind_is_observed(pwt_xlsx_dir: Path) -> None:
    """Every emitted row has ``temporal_kind == "observed"``.

    DOMAIN-RED: ``transform_pwt_long_frame()`` returns a
    wrong-shaped long DataFrame (1 row with
    ``temporal_kind = "proxy"``) in the Phase B stub. The test
    fails at the ``kinds == {"observed"}`` assertion -- the
    production transform must stamp the canonical
    temporal_kind.
    """
    from leaders_db.ingest.sources.pwt.reader import read_pwt
    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    raw_df = read_pwt(xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME)
    long_df = transform_pwt_long_frame(raw_df)
    kinds = set(long_df["temporal_kind"].tolist())
    assert kinds == {"observed"}, (
        f"all PWT rows must be temporal_kind='observed'; got {kinds}"
    )


def test_pwt_transform_attribution_constant(pwt_xlsx_dir: Path) -> None:
    """The ``attribution`` column on every emitted row is the
    canonical PWT citation text.

    DOMAIN-RED: ``transform_pwt_long_frame()`` returns a
    wrong-shaped long DataFrame (1 row with
    ``attribution = "stub attribution"``) in the Phase B
    stub. The test fails at the
    ``all(long_df["attribution"] == PWT_ATTRIBUTION)``
    assertion -- the production transform must stamp the
    canonical PWT citation.
    """
    from leaders_db.ingest.sources.pwt import PWT_ATTRIBUTION
    from leaders_db.ingest.sources.pwt.reader import read_pwt
    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    raw_df = read_pwt(xlsx_path=pwt_xlsx_dir / PWT_XLSX_NAME)
    long_df = transform_pwt_long_frame(raw_df)
    assert all(
        long_df["attribution"] == PWT_ATTRIBUTION
    ), "every row must carry the canonical PWT attribution"


def test_pwt_transform_rejects_duplicate_country_year(
    pwt_xlsx_dir: Path,
) -> None:
    """Duplicate ``(countrycode, year)`` rows in the wide input
    raise ``ValueError`` from the transform.

    Per the Phase B review (test text was ambiguous: ``dedupe
    or reject``): canonical source rows must be unique. The
    transform rejects duplicate ``(countrycode, year)`` source
    rows with a clear ``ValueError`` rather than silently
    deduping (the latter hides source-data bugs and creates
    non-deterministic output across runs).

    The test bypasses the reader (which would return 0 rows in
    the Phase B stub) by constructing a wide DataFrame
    directly with the duplicate rows. The transform must
    raise ``ValueError`` at the first duplicate it sees.

    DOMAIN-RED: ``transform_pwt_long_frame()`` does not raise
    ``ValueError`` in the Phase B stub (it returns a
    wrong-shaped long DataFrame). The test fails at the
    ``pytest.raises(ValueError)`` block -- the production
    transform must detect duplicates and raise.
    """
    import pytest

    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    # Build a wide DataFrame with two duplicate (USA, 2019) rows.
    # Bypasses the reader stub (which returns 0 rows) so the
    # transform sees the duplicates regardless of the reader
    # state.
    wide_df = pd.DataFrame(
        {
            "countrycode": ["USA", "USA"],
            "country": ["United States", "United States"],
            "currency_unit": ["US Dollar", "US Dollar"],
            "year": [2019, 2019],
            "rgdpe": [1.0e12, 2.0e12],
            "rgdpo": [None, None],
            "pop": [None, None],
            "emp": [None, None],
            "avh": [None, None],
            "hc": [None, None],
            "ccon": [None, None],
            "cda": [None, None],
            "ctfp": [None, None],
            "rkna": [None, None],
            "rtfpna": [None, None],
        }
    )

    with pytest.raises(ValueError) as exc_info:
        transform_pwt_long_frame(wide_df)
    msg = str(exc_info.value).lower()
    assert "duplicate" in msg or "country" in msg, (
        f"ValueError must name the duplicate key; got {msg!r}"
    )


def test_pwt_transform_coerces_blank_and_non_numeric_cells(
    pwt_xlsx_dir: Path,
) -> None:
    """Blank / whitespace / sentinel / non-numeric cells are
    DROPPED (no observation row emitted); numeric and
    numeric-like strings emit rows with the coerced
    ``numeric_value`` and preserved ``raw_value``.

    The test bypasses the reader (which returns 0 rows in the
    Phase B stub) by constructing a wide DataFrame directly
    with the mixed-coercion cell pattern. The transform must
    DROP the cell entirely (no long row) for invalid/missing
    cells, and emit a long row for numeric / numeric-like
    cells.

    Per the canonical missing-cell emission rule (see the
    Year Behavior section above), the following cells produce
    NO observation row (the cell is dropped -- not even an
    audit-trail row is emitted):

    - ``None`` (openpyxl empty cell)
    - ``""`` (empty string)
    - ``"  "`` (whitespace)
    - ``"NA"`` / ``"N/A"`` / ``"NaN"`` / ``"null"`` (sentinels)
    - Any non-numeric, non-empty string (e.g. ``"not-a-number"``)

    The following cells DO produce an observation row:

    - Numeric ``int`` / ``float`` (e.g. ``1234.5``)
    - Numeric-like strings (e.g. ``"1234.5"``)

    DOMAIN-RED: ``transform_pwt_long_frame()`` returns a
    wrong-shaped long DataFrame (1 row with placeholder
    content) in the Phase B stub. The test fails at the
    ``len(match) == 0`` assertion for the dropped cells
    (the stub emits a row) and at the ``len(match) == 1``
    assertion for the numeric cells -- the production
    transform must drop invalid cells and emit rows for
    numeric / numeric-like cells.
    """
    from leaders_db.ingest.sources.pwt.transform import (
        transform_pwt_long_frame,
    )

    # Build a wide DataFrame with a comprehensive mixed-coercion
    # cell pattern. Each catalog column gets a different cell
    # type to exercise the documented rule.
    wide_df = pd.DataFrame(
        {
            "countrycode": ["USA"],
            "country": ["United States"],
            "currency_unit": ["US Dollar"],
            "year": [2019],
            # rgdpe: non-numeric string ("N/A") -> DROPPED.
            "rgdpe": ["N/A"],
            # rgdpo: empty string -> DROPPED.
            "rgdpo": [""],
            # pop: whitespace -> DROPPED.
            "pop": ["  "],
            # emp: sentinel "NaN" -> DROPPED.
            "emp": ["NaN"],
            # avh: numeric float -> round-trip to 1234.5.
            "avh": [1234.5],
            # hc: None (openpyxl empty cell) -> DROPPED.
            "hc": [None],
            # ccon: numeric-like string "1234.5" -> float(1234.5).
            "ccon": ["1234.5"],
            # cda: "NA" sentinel -> DROPPED.
            "cda": ["NA"],
            # ctfp: "null" sentinel -> DROPPED.
            "ctfp": ["null"],
            # rkna: arbitrary non-numeric string -> DROPPED.
            "rkna": ["not-a-number"],
            # rtfpna: numeric int -> round-trip to 42.
            "rtfpna": [42],
        }
    )

    long_df = transform_pwt_long_frame(wide_df)

    # Filter to USA 2019 rows.
    usa_2019 = long_df[
        (long_df["iso3"] == "USA") & (long_df["year"] == 2019)
    ]

    # Helper: look up a single (raw_column) row.
    def row_for(raw_column: str) -> pd.DataFrame:
        return usa_2019[usa_2019["raw_column"] == raw_column]

    # --- Invalid / missing cells: NO observation row emitted. ---

    for raw_column in ("rgdpe", "rgdpo", "pop", "emp", "hc",
                       "cda", "ctfp", "rkna"):
        match = row_for(raw_column)
        assert len(match) == 0, (
            f"expected NO USA-2019 row for invalid/missing "
            f"raw_column={raw_column!r}; got {len(match)} "
            f"(missing-cell rule violated)"
        )

    # --- Numeric / numeric-like cells: row emitted, numeric
    # value round-trips, raw_value preserved. ---

    def cell(raw_column: str) -> dict:
        match = row_for(raw_column)
        assert len(match) == 1, (
            f"expected exactly one USA-2019 row for numeric "
            f"raw_column={raw_column!r}; got {len(match)}"
        )
        return match.iloc[0].to_dict()

    avh = cell("avh")
    assert avh["raw_value"] in (1234.5, "1234.5"), (
        f"raw_value for numeric cell must be preserved; got "
        f"{avh['raw_value']!r}"
    )
    assert avh["numeric_value"] == 1234.5, (
        f"numeric_value for numeric cell must round-trip; got "
        f"{avh['numeric_value']!r}"
    )

    ccon = cell("ccon")
    assert ccon["raw_value"] == "1234.5", (
        f"raw_value for numeric-like string must be preserved; got "
        f"{ccon['raw_value']!r}"
    )
    assert ccon["numeric_value"] == 1234.5, (
        f"numeric_value for numeric-like string must coerce to "
        f"float; got {ccon['numeric_value']!r}"
    )

    rtfpna = cell("rtfpna")
    assert rtfpna["numeric_value"] == 42, (
        f"numeric_value for int cell must round-trip; got "
        f"{rtfpna['numeric_value']!r}"
    )


__all__ = []
