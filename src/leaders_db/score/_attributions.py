"""Per-category source-attribution block emitted by the Stage 9
all-countries CSV writer.

The mapping below is the **single source of truth** for which
external sources a Stage 9 public-output CSV must declare under
its `# Attribution: ...` comment block (per AGENTS.md rule #15 and
``docs/source-attributions.md`` §3.2 / §3.6). The mapping is
normative:

- The ``attribution_text`` strings are the **"Attribution text in
  reports"** strings from ``docs/source-attributions.md`` §1,
  byte-for-byte. Do NOT paraphrase or invent — the doc is the
  canonical reference.
- The keys in each category's tuple are the canonical source keys
  from :data:`leaders_db.score.source_plans.SOURCE_KEY_BY_NAME`
  (``"undp_hdi"``, ``"who_gho_api"``, ``"world_bank_wdi"``,
  ``"vdem"`` for :data:`social_wellbeing
  <leaders_db.score.category_plans.social_wellbeing.SOCIAL_WELLBEING_PLAN>`,
  ``"wgi"``, ``"ti_cpi"`` for :data:`integrity
  <leaders_db.score.category_plans.integrity.INTEGRITY_PLAN>`).
- ``client_existing`` is **never** listed. The client 2023 matrix
  is the validation reference, not an evidence source (always-on
  rule #6, ``docs/source-attributions.md`` §3.1: the
  ``client_existing`` line is included only for reports that quote
  or compare against client values).

Scope
-----

``social_wellbeing`` (the first per-category vertical slice),
``integrity`` (the second deterministic scorer),
``effectiveness`` (the third deterministic scorer),
``economic_wellbeing`` (the fourth deterministic scorer),
``political_freedom`` (the fifth deterministic scorer),
``domestic_violence`` (the sixth deterministic scorer),
``international_peace`` (the seventh deterministic scorer), and
``nuclear`` (the eighth deterministic scorer) are mapped today.
Adding a new category is a one-entry edit in this module; no
other module changes are needed because the writer
(:func:`leaders_db.score.stage9.write_score_results_csv`) consumes
this mapping through the :func:`build_attribution_comment_lines`
helper.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Module-level constants are typed as :class:`typing.Final` so the
  values are read-only.
- No mutable defaults; no ``print()``, no ``TODO(debug)``.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Comment line prefix
# ---------------------------------------------------------------------------
#
# Per ``docs/source-attributions.md`` §3.2 the manual-review queue
# CSV uses a ``# Sources: ...`` comment line; we adopt the same
# prefix for the Stage 9 all-countries CSV so any downstream
# consumer can treat both files the same way (skip lines starting
# with ``#``). Each line is ``"# Attribution: <text>"`` so a
# reviewer who opens the CSV in a spreadsheet sees a clean column
# header on the line immediately after the comment block.
ATTRIBUTION_COMMENT_PREFIX: Final[str] = "# "

#: The exact substring that flags a line as an attribution comment
#: line in the CSV header. Exposed as a constant so the writer and
#: the test helpers can share the same string and the contract is
#: auditable from one place.
ATTRIBUTION_LINE_KEY: Final[str] = "Attribution: "


# ---------------------------------------------------------------------------
# Per-category attribution block
# ---------------------------------------------------------------------------
#
# Mapping from canonical ``category_key`` (the same string the
# Stage 9 dispatcher registers in
# :data:`leaders_db.score.dispatch._SCORERS` and the Stage 5 plan
# uses) to the tuple of ``(source_key, attribution_text)`` pairs
# that must appear as ``# Attribution: <text>`` comment lines at
# the top of the CSV. Order is stable (matches the corresponding
# ``<CATEGORY>_PLAN.expected_sources``) so a reviewer can grep for
# a specific source. New categories are added by appending one
# tuple here.
CATEGORY_SOURCE_ATTRIBUTIONS: Final[
    dict[str, tuple[tuple[str, str], ...]]
] = {
    # ``social_wellbeing`` — the first deterministic scorer and the
    # first per-category vertical slice. Expected sources per
    # ``SOCIAL_WELLBEING_PLAN.expected_sources``:
    # ``("undp_hdi", "who_gho_api", "world_bank_wdi", "vdem")``.
    "social_wellbeing": (
        (
            "undp_hdi",
            "UNDP HDR 2023-24 (United Nations Development Programme 2024).",
        ),
        (
            "who_gho_api",
            "WHO Global Health Observatory (World Health Organization).",
        ),
        (
            "world_bank_wdi",
            "World Bank WDI (World Bank 2024).",
        ),
        (
            "vdem",
            "V-Dem v16 (Coppedge et al. 2026).",
        ),
    ),
    # ``integrity`` — the second per-category deterministic scorer.
    # Expected sources per ``INTEGRITY_PLAN.expected_sources``:
    # ``("wgi", "vdem", "ti_cpi")``. The WGI Control of Corruption
    # is the canonical integrity signal; V-Dem political-corruption
    # indices are the expert-coded cross-validator; Transparency
    # International CPI 2023 is the perception-based cross-validator.
    "integrity": (
        (
            "wgi",
            "World Bank WGI (World Bank 2023).",
        ),
        (
            "vdem",
            "V-Dem v16 (Coppedge et al. 2026).",
        ),
        (
            "ti_cpi",
            "Transparency International CPI 2023.",
        ),
    ),
    # ``effectiveness`` — the third per-category deterministic scorer.
    # Expected sources per ``EFFECTIVENESS_PLAN.expected_sources``:
    # ``("wgi", "vdem", "bti")``. The WGI governance group (5
    # indicators excluding Control of Corruption) is the canonical
    # effectiveness signal; V-Dem governance / executive-constraint
    # indicators cross-validate; BTI 2026 provides the biennial
    # expert-coded governance composite.
    "effectiveness": (
        (
            "wgi",
            "World Bank WGI (World Bank 2023).",
        ),
        (
            "vdem",
            "V-Dem v16 (Coppedge et al. 2026).",
        ),
        (
            "bti",
            "BTI 2026 (Bertelsmann Stiftung 2026).",
        ),
    ),
    # ``economic_wellbeing`` — the fourth per-category deterministic
    # scorer. Expected sources per
    # ``ECONOMIC_WELLBEING_PLAN.expected_sources``:
    # ``("world_bank_wdi", "bti")``. World Bank WDI carries the
    # per-capita prosperity / scale / openness / investment
    # signals; BTI 2026 carries the three expert-coded economic-
    # transformation questions (Q6, Q7, Q11).
    "economic_wellbeing": (
        (
            "world_bank_wdi",
            "World Bank WDI (World Bank 2024).",
        ),
        (
            "bti",
            "BTI 2026 (Bertelsmann Stiftung 2026).",
        ),
    ),
    # ``political_freedom`` — the fifth per-category deterministic
    # scorer. Expected sources per
    # ``POLITICAL_FREEDOM_PLAN.expected_sources``:
    # ``("vdem", "rsf_press_freedom", "bti")``. V-Dem v16 carries
    # the polyarchy / liberal-democracy / civil-liberties family
    # (the canonical political-freedom signal); RSF carries the
    # press / media-freedom sub-signal; BTI 2026 carries the
    # expert-coded political-transformation composites / questions.
    "political_freedom": (
        (
            "vdem",
            "V-Dem v16 (Coppedge et al. 2026).",
        ),
        (
            "rsf_press_freedom",
            "RSF World Press Freedom Index (Reporters Without Borders 2026).",
        ),
        (
            "bti",
            "BTI 2026 (Bertelsmann Stiftung 2026).",
        ),
    ),
    # ``domestic_violence`` — the sixth per-category deterministic
    # scorer. Expected sources per
    # ``DOMESTIC_VIOLENCE_PLAN.expected_sources``:
    # ``("pts", "cirights", "ucdp", "vdem")``. PTS carries the
    # expert-coded state-terror scores (Amnesty / HRW / US State
    # Department); CIRIGHTS carries the 7 physical-integrity and
    # repression indicators (PhysInt + the 4 components Disap /
    # Kill / PolPris / Tort + the Repression and CivPol additive
    # indices); UCDP carries the event-based one-sided violence
    # signals; V-Dem carries the civil-liberties / repression
    # indicators as the 4th-source cross-check.
    "domestic_violence": (
        (
            "pts",
            "Political Terror Scale (Wood, Gibney, et al.).",
        ),
        (
            "cirights",
            "CIRI Human Rights Data Project v3.12.10.24 (Cingranelli, Richards, and Crepaz 2024).",
        ),
        (
            "ucdp",
            "UCDP GED 23.1 (Davies et al. 2023).",
        ),
        (
            "vdem",
            "V-Dem v16 (Coppedge et al. 2026).",
        ),
    ),
    # ``international_peace`` — the seventh per-category deterministic
    # scorer. Expected sources per
    # ``INTERNATIONAL_PEACE_PLAN.expected_sources``:
    # ``("ucdp", "sipri_milex")``. UCDP carries the 4 event-based
    # state-based + internationalized conflict indicators (events
    # + fatalities); SIPRI Military Expenditure Database carries
    # the 4 share / scale military-burden indicators (share of GDP,
    # per capita, constant USD, share of govt spending).
    "international_peace": (
        (
            "ucdp",
            "UCDP GED 23.1 (Davies et al. 2023).",
        ),
        (
            "sipri_milex",
            "SIPRI milex (Stockholm International Peace Research Institute 2026).",
        ),
    ),
    # ``nuclear`` — the eighth per-category deterministic scorer
    # and the **lighter** nuclear-responsibility module (per
    # requirement §6: most countries are non-nuclear so a smaller
    # rubric is appropriate). Expected sources per
    # ``NUCLEAR_PLAN.expected_sources``:
    # ``("fas", "sipri_yearbook_ch7")``. The FAS consolidated
    # "Status of World Nuclear Forces" snapshot covers the 9
    # nuclear-armed states with 5 indicator columns; SIPRI
    # Yearbook Chapter 7 Table 7.1 covers the same population
    # with 3 indicators (total inventory, deployed, retired).
    "nuclear": (
        (
            "fas",
            "FAS Nuclear Notebook (Federation of American Scientists).",
        ),
        (
            "sipri_yearbook_ch7",
            "SIPRI Yearbook 2024 Ch.7 (Stockholm International Peace Research Institute 2024).",
        ),
    ),
}


# ---------------------------------------------------------------------------
# Comment-line builder
# ---------------------------------------------------------------------------


def build_attribution_comment_lines(
    category_key: str | None,
) -> tuple[str, ...]:
    """Return the ``# Attribution: ...`` comment lines for ``category_key``.

    Returns an empty tuple if ``category_key`` is ``None`` / empty
    or is not registered in
    :data:`CATEGORY_SOURCE_ATTRIBUTIONS`. The writer still emits the
    stable data header in those cases so the downstream consumer
    sees the canonical :data:`SCORE_RESULTS_CSV_COLUMNS
    <leaders_db.score.stage9.SCORE_RESULTS_CSV_COLUMNS>` shape
    unchanged — the comment block is purely additive metadata.

    Parameters
    ----------
    category_key:
        Canonical category identifier (e.g. ``"social_wellbeing"``).
        The function does not validate that the category is
        registered in the Stage 9 dispatcher; an unknown category
        simply yields no attribution lines (the writer still
        writes the data header).

    Returns
    -------
    tuple[str, ...]
        One ``"# Attribution: <text>"`` line per source in the
        category's :data:`CATEGORY_SOURCE_ATTRIBUTIONS` entry. The
        lines are returned in the order the mapping declares
        (stable across runs). ``()`` for unknown / empty
        ``category_key``.
    """
    if not category_key:
        return ()
    attributions = CATEGORY_SOURCE_ATTRIBUTIONS.get(category_key)
    if attributions is None:
        return ()
    return tuple(
        f"{ATTRIBUTION_COMMENT_PREFIX}{ATTRIBUTION_LINE_KEY}{text}"
        for _source_key, text in attributions
    )


__all__ = [
    "ATTRIBUTION_COMMENT_PREFIX",
    "ATTRIBUTION_LINE_KEY",
    "CATEGORY_SOURCE_ATTRIBUTIONS",
    "build_attribution_comment_lines",
]
