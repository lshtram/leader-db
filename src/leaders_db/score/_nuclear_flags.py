"""Flag-detection and rationale helpers for the nuclear scorer.

This module is the **internal** flag-detection logic of the
``nuclear`` deterministic scorer. The facade in
:mod:`leaders_db.score.nuclear` calls
:func:`build_missingness_summary`, :func:`count_proxy_observations`,
:func:`detect_flags`, and :func:`build_rationale` to assemble the
:class:`~leaders_db.score.results.ScoreResult` payload.

The module mirrors the social-wellbeing / integrity /
effectiveness / economic-wellbeing / political-freedom /
domestic-violence / international-peace scorer's flag-detection
shape: :func:`detect_flags` returns the scored-path flag set
(``MISSING_PRIMARY_SOURCE`` / ``SPARSE_DATA`` /
``LOW_CONFIDENCE``), the insufficient-data path in the facade
appends the same set with :attr:`ReviewFlag.INSUFFICIENT_DATA`
prepended so the manual-review queue can sort on "insufficient"
as the strongest signal, and the client-source filter is
applied to the ``MissingObservation`` rollup so a contaminated
bundle cannot inflate ``by_reason`` / ``by_severity`` or
trigger a phantom ``MISSING_PRIMARY_SOURCE``.

Nuclear-specific behaviour
--------------------------

The nuclear category is **lighter** than the 4-group /
3-group / 2-group categories per requirement §6: most countries
are non-nuclear and have no FAS / SIPRI Yearbook Ch.7 row at
all. The scorer therefore carries an additional
:attr:`ReviewFlag.NUCLEAR_CASE` signal that fires when a
country has at least one usable nuclear-source observation in
the score path — this is the manual-review-queue hook the §14
queue prioritizes (REQ-REV-002: "nuclear / global
responsibility cases" is a manual-review trigger).

In the insufficient-data path the rationale carries an
explicit "non-nuclear / no nuclear-source evidence" sentence
so a manual-review reader can distinguish "no nuclear-source
evidence (non-nuclear state)" from "sparse data" without
re-walking the bundle. The rationale **must not** state or
imply a numeric score on this path (the contract requires
``system_proposed_score_1_10 is None``; a non-nuclear state
must never receive an invented numeric score).

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function and helper.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no scratch.
"""

from __future__ import annotations

from collections.abc import Iterable

from ._nuclear_rubric import _SPARSE_OBSERVED_RATIO_THRESHOLD
from .evidence import CategoryEvidenceBundle, EvidenceObservation, TemporalKind
from .results import (
    MissingnessSummary,
    ReviewFlag,
    ScoreComponent,
)
from .source_plans import EXCLUDED_SOURCE_KEYS


def _filter_excluded_missing(
    missing: Iterable,
) -> tuple:
    """Return ``missing`` with client-source rows stripped.

    The Stage 5 bundle builder already excludes client sources
    upstream; this helper is the missing-observation analogue
    of
    :func:`leaders_db.score._nuclear_components.filter_excluded_observations`
    for the rollup paths. A client ``MissingObservation`` row
    (e.g. ``MissingObservation(source_key="client_existing", ...)``)
    would otherwise inflate ``by_reason`` / ``by_severity`` and
    trigger :attr:`ReviewFlag.MISSING_PRIMARY_SOURCE` even
    though the client 2023 matrix is validation reference, not
    an evidence source (AGENTS.md always-on rule #6, requirement
    §3, §9, §12). Returns a fresh tuple — the input is never
    mutated.
    """
    return tuple(
        m for m in missing if m.source_key not in EXCLUDED_SOURCE_KEYS
    )


def build_missingness_summary(
    bundle: CategoryEvidenceBundle,
    observations: Iterable[EvidenceObservation] | None = None,
) -> MissingnessSummary:
    """Compute the :class:`MissingnessSummary` for the result.

    ``total_expected`` is the number of plan indicators
    (:attr:`CategorySourcePlan.expected_indicators`).
    ``total_observed`` is the number of plan variables with at
    least one usable observation (skipping observations whose
    variable is not in the plan's expected set, and skipping
    observations whose ``normalized_value`` is ``None`` — the
    latter is already effectively missing). ``by_reason`` and
    ``by_severity`` are rolled up from the bundle's explicit
    :class:`MissingObservation` rows **after** the
    client-source filter (see :func:`_filter_excluded_missing`).

    The ``observations`` parameter is the **filtered** observation
    set the scorer is actually scoring on — i.e. with
    :data:`~leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
    (``client_existing`` / ``client_matrix``) already stripped.
    The scorer boundary passes this set so a contaminated bundle
    cannot inflate ``total_observed`` and silently suppress the
    :attr:`~leaders_db.score.results.ReviewFlag.SPARSE_DATA`
    flag. The matching missing-observation filter (defence in
    depth against a hand-built contaminated bundle carrying
    ``MissingObservation`` rows with client ``source_key``) is
    applied below so ``by_reason`` / ``by_severity`` /
    primary-missing detection ignore client rows.
    """
    plan = bundle.source_plan
    expected_variables = plan.expected_variables

    observed_variables: set[str] = set()
    source_iter = (
        observations if observations is not None else bundle.observations
    )
    for obs in source_iter:
        if obs.variable_name not in expected_variables:
            continue
        if obs.normalized_value is None:
            continue
        observed_variables.add(obs.variable_name)

    by_reason: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for missing in _filter_excluded_missing(bundle.missing):
        by_reason[missing.reason.value] = by_reason.get(
            missing.reason.value, 0
        ) + 1
        by_severity[missing.severity.value] = by_severity.get(
            missing.severity.value, 0
        ) + 1

    return MissingnessSummary(
        total_expected=len(expected_variables),
        total_observed=len(observed_variables),
        by_reason=tuple(sorted(by_reason.items())),
        by_severity=tuple(sorted(by_severity.items())),
    )


def count_proxy_observations(
    observations: Iterable[EvidenceObservation],
) -> int:
    """Return the number of observations with a non-DIRECT temporal kind."""
    return sum(
        1
        for obs in observations
        if obs.temporal_kind in (TemporalKind.PROXY, TemporalKind.STALE)
    )


def detect_flags(
    bundle: CategoryEvidenceBundle,
    *,
    observations: list[EvidenceObservation],
    missingness: MissingnessSummary,
) -> list[ReviewFlag]:
    """Return the :class:`ReviewFlag` set for the result.

    Flags are not mutually exclusive — a result can carry several.
    The set is the join key the manual-review queue sorts on, so
    a missing primary source or a proxy-heavy bundle must surface
    here rather than only in the rationale.

    The forward ``human_review_required`` invariant (set in
    :func:`score_nuclear`) is derived from these flags; if the
    empty list returns here, the result is non-flagged and
    ``human_review_required`` is ``False``.

    ``MISSING_PRIMARY_SOURCE`` only fires for non-client
    ``MissingObservation`` rows — the client 2023 matrix is
    validation reference, not an evidence source (AGENTS.md
    always-on rule #6). Client ``MissingObservation`` rows are
    filtered via :func:`_filter_excluded_missing` before the
    primary-severity check.

    :attr:`ReviewFlag.NUCLEAR_CASE` is **not** added here on the
    scored path — the facade (:func:`score_nuclear`) is
    responsible for adding it after this helper returns because
    the flag fires on the **presence of usable nuclear-source
    observations** (a population split: nuclear-armed vs.
    non-nuclear) rather than on any bundle-level missingness /
    proxy / primary check. Keeping the population split out of
    this helper makes the function easier to reuse on the
    insufficient-data path, where :attr:`ReviewFlag.NUCLEAR_CASE`
    must NOT fire (a non-nuclear state with no observations is
    not a "nuclear case" — it is the absence of one).
    """
    flags: list[ReviewFlag] = []

    # 1. Missing REQUIRED (severity PRIMARY) observation —
    #    client-source rows are filtered out so a contaminated
    #    bundle carrying client ``MissingObservation`` rows
    #    cannot trigger this flag.
    if _filter_excluded_missing(bundle.primary_missing_observations):
        flags.append(ReviewFlag.MISSING_PRIMARY_SOURCE)

    # 2. Substantial missingness: less than half of the plan's
    #    expected indicators observed.
    if missingness.total_expected > 0:
        observed_ratio = (
            missingness.total_observed / missingness.total_expected
        )
        if observed_ratio < _SPARSE_OBSERVED_RATIO_THRESHOLD:
            flags.append(ReviewFlag.SPARSE_DATA)

    # 3. Proxy / stale observations: anything not DIRECT reduces
    #    temporal fit and therefore the §11 confidence. The
    #    consolidated FAS snapshot's ``<meta name="date">`` is
    #    dated 2014-04-30 (per the FAS catalog header) — the
    #    temporal-fit gap to the 2023 target year is large and
    #    Stage 6 / Stage 11 already penalize this; the scorer
    #    surfaces the signal here so the manual-review queue can
    #    sort on it.
    has_proxy = any(
        obs.temporal_kind in (TemporalKind.PROXY, TemporalKind.STALE)
        for obs in observations
    )
    if has_proxy:
        flags.append(ReviewFlag.LOW_CONFIDENCE)

    return flags


def build_rationale(
    *,
    bundle: CategoryEvidenceBundle,
    normalized: float,
    score_1_10: int,
    components: list[ScoreComponent],
    missingness: MissingnessSummary,
    flags: list[ReviewFlag],
    proxy_count: int,
    has_nuclear_source_evidence: bool,
) -> str:
    """Compose the short human-readable rationale (1-3 sentences).

    Surfaces the scale mapping (1..10 vs 0..10), the observed
    indicator count, and any flag-triggering condition in plain
    language so a reviewer scanning the manual-review queue sees
    the rubric state without re-walking the bundle.

    Insufficient-data contract
    --------------------------

    When :attr:`ReviewFlag.INSUFFICIENT_DATA` is in ``flags`` the
    result has :attr:`ScoreResult.system_proposed_score_1_10`
    ``None`` — no numeric score was emitted. The rationale **must
    not** state or imply a numeric score (the prior prototype
    versions interpolated ``score_1_10=1`` as a placeholder,
    producing a misleading "Nuclear score 1/10 on the 1..10
    prototype scale ..." for every insufficient-data row). The
    insufficient-data sentence is the canonical signal ("No
    nuclear-source evidence was found in the bundle; non-nuclear
    state (or no nuclear-source row available); no score
    emitted.") so the score sentence is suppressed entirely on
    this path.

    Nuclear-specific rationale wording
    ---------------------------------

    On the insufficient-data path the rationale explicitly says
    the row is a **non-nuclear / no nuclear-source evidence**
    case rather than a generic "insufficient" gate. This is the
    "non-nuclear states must not receive an invented numeric
    score" reviewer guard: a manual-review reader can tell from
    the rationale text whether the absence of a score reflects
    a non-nuclear state (the expected case for ~190 of the ~200
    countries in the prototype) or a sparse-bundle pathology
    (e.g. a country whose FAS / SIPRI row arrived but did not
    normalize). The two sentences are kept separate so the CSV
    export's pipe-separated ``review_flags`` column and the
    rationale text tell the same story.
    """
    parts: list[str] = []
    # Insufficient-data results carry ``system_proposed_score_1_10``
    # = ``None``. Emitting a numeric score sentence here would
    # mislead the manual-review reader (and would silently
    # invent a numeric score for a non-nuclear state); suppress
    # it entirely and rely on the "no score emitted" line
    # below. ``normalized`` / ``score_1_10`` are still required
    # parameters so the scored path keeps its single-call
    # signature; we simply don't use them on the
    # insufficient-data branch.
    if ReviewFlag.INSUFFICIENT_DATA not in flags:
        parts.append(
            f"Nuclear score {score_1_10}/10 on the 1..10 "
            f"prototype scale (normalized {normalized:.2f}, mapping "
            f"round(1 + 9 * normalized))."
        )

    if components:
        parts.append(
            f"Based on {len(components)} observation(s) across "
            f"{missingness.total_observed}/{missingness.total_expected} "
            f"plan indicator(s)."
        )
    else:
        parts.append(
            f"No usable observation(s); "
            f"{missingness.total_observed}/{missingness.total_expected} "
            f"plan indicator(s) observed."
        )

    if proxy_count > 0:
        parts.append(
            f"{proxy_count} observation(s) used a proxy/stale year; "
            f"temporal fit reduced."
        )

    if ReviewFlag.MISSING_PRIMARY_SOURCE in flags:
        parts.append(
            "Primary (REQUIRED) indicator missing — at least one of "
            "fas_total_inventory, sipri_yearbook_ch7_nuclear_warheads_"
            "total_inventory absent."
        )
    if ReviewFlag.SPARSE_DATA in flags:
        parts.append(
            "Sparse data: fewer than half of plan indicators observed."
        )
    if ReviewFlag.INSUFFICIENT_DATA in flags:
        # The nuclear-specific phrasing explicitly names the
        # "non-nuclear / no nuclear-source evidence" cause. The
        # ``has_nuclear_source_evidence`` flag is propagated from
        # the facade so the rationale can distinguish a
        # non-nuclear state (no FAS / SIPRI row at all, the
        # common case for ~190 countries) from a sparse-bundle
        # pathology (e.g. a country whose nuclear-source row
        # arrived but did not normalize). Both paths return
        # ``is_insufficient_data=True`` and never invent a
        # numeric score; the rationale text is the only signal a
        # manual-review reader has to tell them apart.
        if has_nuclear_source_evidence:
            parts.append(
                "Bundle fell below the plan's minimum-viable source "
                "count; nuclear-source evidence was present but "
                "insufficient; no score emitted."
            )
        else:
            parts.append(
                "Bundle fell below the plan's minimum-viable source "
                "count; no nuclear-source evidence found (non-nuclear "
                "state or no FAS / SIPRI Yearbook Ch.7 row); no score "
                "emitted."
            )

    return " ".join(parts)


__all__ = [
    "build_missingness_summary",
    "build_rationale",
    "count_proxy_observations",
    "detect_flags",
]
