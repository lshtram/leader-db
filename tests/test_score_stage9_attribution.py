"""Tests for the Stage 9 CSV attribution block — helper unit tests.

The all-countries CSV is an exported artifact under
``data/outputs/``; per AGENTS.md rule #15 ("carry source
attribution forward in every public output") and
``docs/source-attributions.md`` §3.2 / §3.6, the writer must
carry the source attribution block for the contributing
sources as a ``# Attribution: <text>`` comment block at the
top of the file. The block is the small but contractually
important glue between the score module and the docs — without
it a downstream consumer cannot answer "where did these numbers
come from?" without re-reading ``docs/source-attributions.md``.

Scope
-----

The tests live in a sibling test file so the canonical
``test_score_stage9_batch.py``,
``test_score_stage9_csv.py`` (the direct writer path), and
``test_score_stage9_csv_categories.py`` (the per-category CLI
explicit ``category_key=`` path) stay under the 400-line
convention while still being one test module per production
seam family. The split mirrors the
``stage9_batch`` / ``stage9_batch_csv`` /
``stage9_csv`` / ``stage9_csv_categories`` /
``stage9_attribution`` pattern:

- :mod:`tests.test_score_stage9_batch` — the all-countries
  batch seam and the CSV row format / atomic-rename contract
  (no attribution assertions);
- :mod:`tests.test_score_stage9_batch_csv` — the CSV writer's
  data-shape contract (NA sentinel, missingness columns,
  review-flags encoding, parent-directory creation,
  atomic-rename);
- :mod:`tests.test_score_stage9_csv` — the writer path
  through the all-countries batch seam (attribution block
  emission for the derived ``social_wellbeing`` category,
  comment prefix, header stability, pandas round-trip);
- :mod:`tests.test_score_stage9_csv_categories` — the CSV
  writer's per-category CLI explicit ``category_key=`` contract
  (one test per registered category, the explicit-override
  semantics, the unknown-category defensive path);
- :mod:`tests.test_score_stage9_attribution` — this file, the
  :func:`build_attribution_comment_lines` helper unit tests
  (helper does the right thing in isolation from the writer).

The tests cover:

- the :func:`build_attribution_comment_lines` helper emits one
  line per expected source and the text is byte-for-byte equal
  to the ``docs/source-attributions.md`` strings;
- the helper returns ``()`` for unknown / empty categories and
  never emits the ``client_existing`` attribution (AGENTS.md
  rule #6).
"""

from __future__ import annotations

from leaders_db.score._attributions import (
    ATTRIBUTION_COMMENT_PREFIX,
    CATEGORY_SOURCE_ATTRIBUTIONS,
    build_attribution_comment_lines,
)

# ---------------------------------------------------------------------------
# Attribution helper (unit tests)
# ---------------------------------------------------------------------------


def test_attribution_helper_emits_one_line_per_social_wellbeing_source() -> None:
    """The helper emits one ``# Attribution: ...`` line per expected source.

    The ``social_wellbeing`` category has 4 expected sources per
    :data:`SOCIAL_WELLBEING_PLAN.expected_sources`
    (``undp_hdi``, ``who_gho_api``, ``world_bank_wdi``,
    ``vdem``); the helper must emit exactly one line per source
    so a reviewer can grep for any one of them in the CSV.
    """
    lines = build_attribution_comment_lines("social_wellbeing")
    assert len(lines) == 4
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_attribution_text_matches_doc() -> None:
    """The attribution text is byte-for-byte equal to the doc strings.

    The helper is the glue between the score module and
    ``docs/source-attributions.md``; if the helper's text drifts
    from the doc a downstream consumer cannot rely on grep. This
    test pins the exact substring of every line so a future
    edit in either place is caught at the next ``pytest`` run.
    """
    expected_substrings = {
        "undp_hdi": "UNDP HDR 2023-24 (United Nations Development Programme 2024).",
        "who_gho_api": "WHO Global Health Observatory (World Health Organization).",
        "world_bank_wdi": "World Bank WDI (World Bank 2024).",
        "vdem": "V-Dem v16 (Coppedge et al. 2026).",
        "wgi": "World Bank WGI (World Bank 2023).",
        "pts": "Political Terror Scale (Wood, Gibney, et al.).",
        "cirights": (
            "CIRI Human Rights Data Project v3.12.10.24 "
            "(Cingranelli, Richards, and Crepaz 2024)."
        ),
        "ucdp": "UCDP GED 23.1 (Davies et al. 2023).",
        "ti_cpi": "Transparency International CPI 2023.",
        "bti": "BTI 2026 (Bertelsmann Stiftung 2026).",
        "sipri_milex": "SIPRI milex (Stockholm International Peace Research Institute 2026).",
        "fas": "FAS Nuclear Notebook (Federation of American Scientists).",
        "sipri_yearbook_ch7": (
            "SIPRI Yearbook 2024 Ch.7 "
            "(Stockholm International Peace Research Institute 2024)."
        ),
    }
    # Cover all registered categories; each carries the
    # substring for its own sources.
    for category_key, expected_source_keys in (
        ("social_wellbeing", ("undp_hdi", "who_gho_api",
                              "world_bank_wdi", "vdem")),
        ("integrity", ("wgi", "vdem", "ti_cpi")),
        ("effectiveness", ("wgi", "vdem", "bti")),
        ("economic_wellbeing", ("world_bank_wdi", "bti")),
        ("domestic_violence", ("pts", "cirights", "ucdp", "vdem")),
        ("international_peace", ("ucdp", "sipri_milex")),
        ("nuclear", ("fas", "sipri_yearbook_ch7")),
    ):
        lines = build_attribution_comment_lines(category_key)
        for source_key in expected_source_keys:
            expected = expected_substrings[source_key]
            matching = [line for line in lines if expected in line]
            assert matching, (
                f"no attribution line contains the canonical text for "
                f"{source_key!r} in {category_key} "
                f"(expected substring {expected!r})"
            )


def test_attribution_helper_integrity_emits_three_lines() -> None:
    """The integrity category emits exactly one line per expected source.

    Per ``INTEGRITY_PLAN.expected_sources`` the integrity
    category has 3 expected sources (``wgi``, ``vdem``,
    ``ti_cpi``); the helper must emit exactly one line per
    source so a reviewer can grep for any one of them in the
    CSV.
    """
    lines = build_attribution_comment_lines("integrity")
    assert len(lines) == 3
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_effectiveness_emits_three_lines() -> None:
    """The effectiveness category emits exactly one line per expected source.

    Per ``EFFECTIVENESS_PLAN.expected_sources`` the effectiveness
    category has 3 expected sources (``wgi``, ``vdem``, ``bti``);
    the helper must emit exactly one line per source so a
    reviewer can grep for any one of them in the CSV.
    """
    lines = build_attribution_comment_lines("effectiveness")
    assert len(lines) == 3
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_economic_wellbeing_emits_two_lines() -> None:
    """The economic_wellbeing category emits exactly one line per
    expected source.

    Per ``ECONOMIC_WELLBEING_PLAN.expected_sources`` the
    economic_wellbeing category has 2 expected sources
    (``world_bank_wdi``, ``bti``); the helper must emit exactly
    one line per source so a reviewer can grep for any one of
    them in the CSV.
    """
    lines = build_attribution_comment_lines("economic_wellbeing")
    assert len(lines) == 2
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_domestic_violence_emits_four_lines() -> None:
    """The domestic_violence category emits exactly one line per
    expected source.

    Per ``DOMESTIC_VIOLENCE_PLAN.expected_sources`` the
    domestic_violence category has 4 expected sources
    (``pts``, ``cirights``, ``ucdp``, ``vdem``); the helper must
    emit exactly one line per source so a reviewer can grep for
    any one of them in the CSV.
    """
    lines = build_attribution_comment_lines("domestic_violence")
    assert len(lines) == 4
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_international_peace_emits_two_lines() -> None:
    """The international_peace category emits exactly one line per
    expected source.

    Per ``INTERNATIONAL_PEACE_PLAN.expected_sources`` the
    international_peace category has 2 expected sources
    (``ucdp``, ``sipri_milex``); the helper must emit exactly
    one line per source so a reviewer can grep for any one of
    them in the CSV.
    """
    lines = build_attribution_comment_lines("international_peace")
    assert len(lines) == 2
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_nuclear_emits_two_lines() -> None:
    """The nuclear category emits exactly one line per expected source.

    Per ``NUCLEAR_PLAN.expected_sources`` the nuclear category
    has 2 expected sources (``fas``, ``sipri_yearbook_ch7``);
    the helper must emit exactly one line per source so a
    reviewer can grep for any one of them in the CSV.
    """
    lines = build_attribution_comment_lines("nuclear")
    assert len(lines) == 2
    for line in lines:
        assert line.startswith(ATTRIBUTION_COMMENT_PREFIX + "Attribution: ")


def test_attribution_helper_unknown_category_returns_empty_tuple() -> None:
    """An unknown ``category_key`` returns ``()`` — the writer must not crash.

    The writer still emits the stable data header in that case;
    the unknown-category case is the CLI's responsibility
    (the dispatcher already fails fast). The helper's contract
    is "no exception on unknown key".
    """
    assert build_attribution_comment_lines("") == ()
    assert build_attribution_comment_lines(None) == ()
    assert build_attribution_comment_lines("corruption") == ()


def test_attribution_helper_omits_client_existing() -> None:
    """The block never includes the ``client_existing`` attribution.

    Per AGENTS.md rule #6 and ``docs/source-attributions.md``
    §3.1, the client 2023 matrix is the validation reference and
    must not appear in the source agreement / source authority /
    source attribution of any deterministic output. The block
    is the deterministic scorer's attribution — the client
    matrix cannot be there.
    """
    mapping_text = " ".join(
        text
        for entries in CATEGORY_SOURCE_ATTRIBUTIONS.values()
        for _, text in entries
    )
    assert "client" not in mapping_text.lower(), (
        "client_existing must not appear in the per-category "
        "attribution block (AGENTS.md rule #6)"
    )
