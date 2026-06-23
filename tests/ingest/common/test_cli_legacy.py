"""Phase B Increment A -- legacy STAGE2_ADAPTERS + CLI boundary tests.

This file covers the legacy ``STAGE2_ADAPTERS`` dispatch
table (every existing source key must remain callable) and
the CLI boundary regression guards
(``wikipedia_search_extract --query``).

Per the ``docs/source-ingestion-plan.md`` mirrored layout
(see the Increment A design), the tests for the legacy
dispatch + CLI boundary live in
``tests/ingest/common/test_cli_legacy.py``.

PASS-ELIGIBLE / DOMAIN-RED conventions
--------------------------------------

Every test in this file is ``PASS-ELIGIBLE``: the tests are
regression guards for the legacy dispatch table and the
existing CLI behavior. They must keep passing once the
production code lands.

Coverage
--------

- Every legacy implemented source key remains in
  ``STAGE2_ADAPTERS`` and is callable (not ``None``).
- ``STAGE2_ADAPTERS['pwt']`` is documented as pending; the
  Increment B tests flip it to a real callable.
- The CLI ``ingest-source --source wikipedia_search_extract``
  branch still requires ``--query`` (without ``--query`` the
  CLI fails fast with a Typer error mentioning ``--query``).
- The CLI ``ingest-source --source wikipedia_search_extract
  --query 'Joe Biden'`` reaches the adapter via the
  queries-only CLI branch (not the ``year=`` branch).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.ingest import STAGE2_ADAPTERS

# ---------------------------------------------------------------------------
# Legacy STAGE2_ADAPTERS compatibility
# ---------------------------------------------------------------------------


_LEGACY_IMPLEMENTED_KEYS = (
    "vdem",
    "world_bank_wdi",
    "world_bank_wgi",
    "ucdp",
    "sipri_milex",
    "sipri_yearbook_ch7",
    "pts",
    "undp_hdi",
    "who_gho_api",
    "archigos",
    "reign",
    "cirights",
    "transparency_cpi",
    "fas",
    "bti",
    "rsf_press_freedom",
    "wikidata_heads_of_state_government",
    "wikipedia_search_extract",
    "maddison_project",
)


@pytest.mark.parametrize("source_key", _LEGACY_IMPLEMENTED_KEYS)
def test_stage2_adapters_legacy_keys_still_present(source_key: str) -> None:
    """Every legacy implemented source key remains in
    ``STAGE2_ADAPTERS`` and is callable (not ``None``).

    Contract: building the new registry must NOT delete the legacy
    dispatch table entries. ``pwt`` is allowed to remain ``None``
    here -- Increment B flips it to a real adapter. The other 19
    implemented keys must remain callable.

    PASS-ELIGIBLE: regression guard for the legacy ``STAGE2_ADAPTERS``
    table; the Phase B stub does NOT mutate the table.
    """
    assert source_key in STAGE2_ADAPTERS, (
        f"STAGE2_ADAPTERS missing legacy key {source_key!r}"
    )
    assert STAGE2_ADAPTERS[source_key] is not None, (
        f"STAGE2_ADAPTERS[{source_key!r}] was reset to None"
    )
    assert callable(STAGE2_ADAPTERS[source_key])


def test_stage2_adapters_pwt_placeholder_is_explicit() -> None:
    """``STAGE2_ADAPTERS['pwt']`` is documented as pending; the
    Increment B tests flip it to a real callable.

    Contract: as of this Phase B slice, ``STAGE2_ADAPTERS['pwt']``
    is either still ``None`` (legacy state) OR a non-None
    compatibility shim that delegates to the new registry. Either
    is acceptable -- the assertion here is that the entry exists,
    is named ``"pwt"``, and is not silently dropped.

    PASS-ELIGIBLE: regression guard for the PWT entry in the
    legacy dispatch table; the Phase B stub leaves it as
    ``None``.
    """
    assert "pwt" in STAGE2_ADAPTERS
    pwt_entry = STAGE2_ADAPTERS["pwt"]
    assert pwt_entry is None or callable(pwt_entry), (
        f"STAGE2_ADAPTERS['pwt'] must be None or callable; "
        f"got {type(pwt_entry).__name__}"
    )


# ---------------------------------------------------------------------------
# CLI boundary regression: wikipedia_search_extract --query
# ---------------------------------------------------------------------------


def test_cli_ingest_source_wikipedia_without_query_fails(
    isolated_data_lake: Path,
) -> None:
    """``leaders-db ingest-source --source wikipedia_search_extract``
    without ``--query`` still fails fast with a Typer error.

    Regression guard: building the new registry / shared interface
    must not delete the ``wikipedia_search_extract`` branch in
    ``commands_stage2.py`` that turns missing ``--query`` into a
    clear ``typer.BadParameter`` (instead of a TypeError from
    passing ``year=`` to a queries-only adapter).

    PASS-ELIGIBLE: regression guard for the CLI's
    ``wikipedia_search_extract`` --query branch.
    """
    runner = CliRunner()
    result = runner.invoke(
        app, ["ingest-source", "--source", "wikipedia_search_extract"],
    )
    assert result.exit_code != 0, (
        "wikipedia_search_extract without --query must fail; "
        f"stdout={result.stdout!r}"
    )
    combined = (result.stdout or "") + (getattr(result, "stderr", None) or "")
    assert "--query" in combined, (
        "Error must mention --query so the user knows how to fix it; "
        f"got {combined!r}"
    )


def test_cli_ingest_source_wikipedia_with_query_dispatches_branch(
    isolated_data_lake: Path,
) -> None:
    """``leaders-db ingest-source --source wikipedia_search_extract
    --query 'Joe Biden'`` reaches the adapter via the queries-only
    CLI branch (not the ``year=`` branch).

    Regression guard: the CLI's wikipedia branch is the one place
    where ``year=`` would TypeError; we send a ``--query`` and
    assert the CLI echoes the query list (proving it took the
    queries branch) and exits with an error (no fixture cache ->
    no HTTP -> the adapter would fail at the network step, but
    that is fine -- the CLI branch dispatch is what we are
    asserting here).

    PASS-ELIGIBLE: regression guard for the CLI's
    ``wikipedia_search_extract`` --query branch (positive path).
    """
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "ingest-source",
            "--source",
            "wikipedia_search_extract",
            "--query",
            "Joe Biden",
        ],
    )
    combined = (result.stdout or "") + (getattr(result, "stderr", None) or "")
    # The CLI prints "(queries=...)" on the queries branch.
    assert "queries=" in combined, (
        "CLI did not echo the queries list -- the wikipedia branch "
        f"may have been removed. stdout={result.stdout!r}"
    )
    assert "Joe Biden" in combined


__all__ = []
