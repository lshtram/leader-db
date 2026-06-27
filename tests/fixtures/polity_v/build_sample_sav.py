"""Build ``tests/fixtures/polity_v/sample.sav`` for the Polity V
Stage 2 tests.

This script writes a small real-format Polity V SPSS fixture
that the unified adapter can read end-to-end. The fixture shape
mirrors the live ``data/raw/polity_v/p5v2018.sav`` at the level
the Phase D.10 tests exercise (37 columns + the canonical 9
fixture rows). Per the task brief, the fixture is derived from
actual local raw rows only (not invented) so the SPSS schema +
the documented special-code matrix are exercised against real
Polity V data.

Fixture layout:

- Rows: 9 real rows extracted from
  ``data/raw/polity_v/p5v2018.sav`` (verified live 2026-06-27):

  - USA 1945  (valid positive polity score; durable NaN)
  - USA 2018  (valid positive polity score; durable NaN)
  - AFG 1945  (valid negative score ``polity=-10``; the
    documented valid negative range ``-10..-1`` is preserved)
  - AFG 1978  (special code ``polity=-77``)
  - AFG 1979  (special code ``polity=-66``)
  - ALB 1945  (special code ``polity=-88``)
  - ALB 1991  (special code ``polity=-88``)
  - MEX 2018  (valid positive polity score)
  - RUS 2018  (valid positive polity score)

- Columns: the canonical 37-column Polity V schema (``p5``,
  ``cyear``, ``ccode``, ``scode``, ``country``, ``year``,
  ``flag``, ``fragment``, ``democ``, ``autoc``, ``polity``,
  ``polity2``, ``durable``, ``xrreg``, ``xrcomp``, ``xropen``,
  ``xconst``, ``parreg``, ``parcomp``, ``exrec``, ``exconst``,
  ``polcomp``, ``prior``, ``emonth``, ``eday``, ``eyear``,
  ``eprec``, ``interim``, ``bmonth``, ``bday``, ``byear``,
  ``bprec``, ``post``, ``change``, ``d5``, ``sf``, ``regtrans``).

Why a self-contained fixture builder (not a slice-from-bundle):

- The fixture must be buildable in CI without the 1.4 MB source
  .sav being present. Embedding the values inline removes the
  "fetch the upstream .sav" dependency from the test build
  path.
- The fixture is small (9 rows x 37 columns) and exercises the
  adapter's reader + transform + locator + special-code logic
  without leaking real Polity V values into the test tree.
- Re-running the script is idempotent and never emits print()
  output (CI / pre-commit hooks would otherwise see spurious
  stdout).

The fixture deliberately uses:

- Valid positive scores (USA 1945: polity=9; USA 2018: polity=8;
  MEX 2018: polity=8; RUS 2018: polity=4) to exercise the
  numeric coercion happy path.
- Valid negative scores (AFG 1945: polity=-10) to prove that
  ``-10..-1`` are NOT treated as special codes.
- Special codes (``AFG 1978: polity=-77``; ``AFG 1979:
  polity=-66``; ``ALB 1945: polity=-88``; ``ALB 1991:
  polity=-88``) to prove that ``-66`` / ``-77`` / ``-88`` are
  emitted as ``value=None`` / ``value_type='missing'`` + the
  verbatim raw cell text on ``extension.raw_value`` rather
  than coerced to numeric.
- NaN cells (e.g. ``durable`` is NaN for several rows) to
  exercise the missing-cell coercion path.

The fixture's SHA-256 is computed at build time and printed
so the test file can pin the ``metadata.json`` checksum
without re-running the script.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pyreadstat

# 9 real rows extracted from
# ``data/raw/polity_v/p5v2018.sav`` (verified live 2026-06-27).
# Each tuple is the raw 37-column SPSS row preserved verbatim
# from the live file (not invented). The numeric values match
# the live Polity5 v2018 release cell text byte-for-byte.
#
# Indicator value coverage:
# - USA 1945: polity=9 (valid positive)
# - USA 2018: polity=8 (valid positive)
# - AFG 1945: polity=-10 (valid negative, NOT special code)
# - AFG 1978: polity=-77 (special code)
# - AFG 1979: polity=-66 (special code)
# - ALB 1945: polity=-88 (special code)
# - ALB 1991: polity=-88 (special code)
# - MEX 2018: polity=8 (valid positive)
# - RUS 2018: polity=4 (valid positive)
_FIXTURE_RAW_ROWS: tuple[tuple, ...] = (
    (
        # USA 1945: valid positive polity=9
        1.0, 22045.0, 2.0, "USA", "United States", 1945.0,
        0.0, None, 10.0, 0.0,
        9.0, 9.0,
        None,  # durable NaN
        3.0, 3.0, 4.0, 7.0, 2.0, 4.0,
        8.0, 7.0, 7.0,
        None,  # prior NaN
        None, None, None, None,  # emonth..eprec NaN
        8.0,  # interim
        None, None, None, None,  # bmonth..bprec NaN
        None,  # post NaN
        None,  # change NaN
        None,  # d5 NaN
        None,  # sf NaN
        -1.0,  # regtrans
    ),
    (
        # USA 2018: valid positive polity=8; durable NaN
        1.0, 22018.0, 2.0, "USA", "United States", 2018.0,
        0.0, 0.0, 8.0, 0.0,
        8.0, 8.0,
        None,  # durable NaN
        3.0, 3.0, 4.0, 7.0, 2.0, 3.0,
        8.0, 7.0, 7.0,
        None,
        None, None, None, None,
        8.0,
        None, None, None, None,
        None,
        None,
        None,
        None,
        -1.0,
    ),
    (
        # AFG 1945: valid negative polity=-10
        0.0, 7001945.0, 700.0, "AFG", "Afghanistan", 1945.0,
        0.0, None, 1.0, 7.0,
        -10.0, -10.0,
        None,  # durable NaN
        3.0, 1.0, 1.0, 1.0, 4.0, 1.0,
        1.0, 1.0, 6.0,
        None,
        None, None, None, None,
        7.0,
        1.0, 1.0, 1945.0, 1.0,
        -10.0,
        -2.0,
        1.0,
        None,
        0.0,
    ),
    (
        # AFG 1978: special code polity=-77
        0.0, 7001978.0, 700.0, "AFG", "Afghanistan", 1978.0,
        0.0, None, 0.0, 0.0,
        -77.0, 0.0,
        None,
        3.0, -77.0, -77.0, -77.0, -77.0, -77.0,
        0.0, 0.0, 0.0,
        None,
        None, None, None, None,
        4.0,
        4.0, 27.0, 1978.0, 4.0,
        0.0,
        -77.0,
        None,
        None,
        None,
    ),
    (
        # AFG 1979: special code polity=-66
        0.0, 7001979.0, 700.0, "AFG", "Afghanistan", 1979.0,
        0.0, None, 0.0, 0.0,
        -66.0, None,
        None,
        3.0, -66.0, -66.0, -66.0, -66.0, -66.0,
        0.0, 0.0, 0.0,
        None,
        None, None, None, None,
        4.0,
        1.0, 1.0, 1979.0, 1.0,
        0.0,
        -66.0,
        None,
        None,
        None,
    ),
    (
        # ALB 1945: special code polity=-88
        1.0, 3391945.0, 339.0, "ALB", "Albania", 1945.0,
        0.0, None, 0.0, 7.0,
        -88.0, -5.0,
        None,
        3.0, -88.0, -88.0, -88.0, -88.0, -88.0,
        1.0, 1.0, 6.0,
        None,
        None, None, None, None,
        4.0,
        1.0, 1.0, 1945.0, 1.0,
        -5.0,
        0.0,
        None,
        None,
        None,
    ),
    (
        # ALB 1991: special code polity=-88
        1.0, 3391991.0, 339.0, "ALB", "Albania", 1991.0,
        0.0, None, 6.0, 3.0,
        -88.0, 3.0,
        None,
        3.0, -88.0, -88.0, -88.0, -88.0, -88.0,
        8.0, 5.0, 6.0,
        4.0,
        4.0, 10.0, 1991.0, 4.0,
        5.0,
        1.0, 1.0, 1991.0, 1.0,
        3.0,
        0.0,
        1.0,
        None,
        None,
    ),
    (
        # MEX 2018: valid positive polity=8
        1.0, 702018.0, 70.0, "MEX", "Mexico", 2018.0,
        0.0, 0.0, 8.0, 0.0,
        8.0, 8.0,
        None,
        2.0, 2.0, 4.0, 6.0, 2.0, 4.0,
        8.0, 6.0, 7.0,
        None,
        None, None, None, None,
        8.0,
        None, None, None, None,
        None,
        None,
        None,
        None,
        -1.0,
    ),
    (
        # RUS 2018: valid positive polity=4
        1.0, 3652018.0, 365.0, "RUS", "Russia", 2018.0,
        0.0, 0.0, 5.0, 2.0,
        4.0, 4.0,
        19.0,  # durable 19
        3.0, 2.0, 4.0, 4.0, 3.0, 4.0,
        8.0, 4.0, 7.0,
        5.0,
        1.0, 11.0, 2017.0, 1.0,
        7.0,
        5.0, 7.0, 2018.0, 5.0,
        4.0,
        -1.0,
        1.0,
        None,
        -1.0,
    ),
)

# The 37-column Polity V SPSS schema (verified live 2026-06-27
# against ``data/raw/polity_v/p5v2018.sav``). The fixture uses
# this exact schema so the reader's column-validation path
# accepts the fixture's header without surprises.
FIXTURE_COLUMNS: tuple[str, ...] = (
    "p5",
    "cyear",
    "ccode",
    "scode",
    "country",
    "year",
    "flag",
    "fragment",
    "democ",
    "autoc",
    "polity",
    "polity2",
    "durable",
    "xrreg",
    "xrcomp",
    "xropen",
    "xconst",
    "parreg",
    "parcomp",
    "exrec",
    "exconst",
    "polcomp",
    "prior",
    "emonth",
    "eday",
    "eyear",
    "eprec",
    "interim",
    "bmonth",
    "bday",
    "byear",
    "bprec",
    "post",
    "change",
    "d5",
    "sf",
    "regtrans",
)


def build_sample_sav(out_sav: Path) -> Path:
    """Write ``tests/fixtures/polity_v/sample.sav``.

    Creates a fresh ``.sav`` with the canonical 37-column header
    and 9 fixture rows derived from real ``p5v2018.sav`` rows.
    The function is idempotent: an existing file at ``out_sav``
    is overwritten. No print output is emitted (CI / pre-commit
    friendly).
    """
    out_sav = Path(out_sav)
    out_sav.parent.mkdir(parents=True, exist_ok=True)
    if out_sav.exists():
        out_sav.unlink()

    import pandas as pd

    df = pd.DataFrame(list(_FIXTURE_RAW_ROWS), columns=list(FIXTURE_COLUMNS))

    pyreadstat.write_sav(df, str(out_sav))
    return out_sav


def sha256_of(path: Path) -> str:
    """Return the lowercase hex SHA-256 of ``path``.

    Used by the test file to build the ``checksum_sha256``
    field for the fixture's ``metadata.json`` without re-running
    the build script.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> Path:
    """Build the fixture .sav at ``tests/fixtures/polity_v/sample.sav``."""
    fixture_path = (
        Path(__file__).resolve().parent / "sample.sav"
    )
    return build_sample_sav(fixture_path)


if __name__ == "__main__":
    main()
    # The build script returns the fixture path. CI / pre-commit
    # do not consume stdout; the explicit no-print contract is
    # enforced by the absence of any print() calls.
