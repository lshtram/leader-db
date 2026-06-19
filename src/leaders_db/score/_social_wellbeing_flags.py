"""Flag-detection and rationale helpers for the social-wellbeing scorer.

This module is the **internal** flag-detection logic of the
social-wellbeing deterministic scorer. The facade in
:mod:`leaders_db.score.social_wellbeing` calls
:func:`build_missingness_summary`, :func:`count_proxy_observations`,
:func:`detect_flags`, and :func:`build_rationale` to assemble the
:class:`~leaders_db.score.results.ScoreResult` payload.

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference
  safety.
- Type hints on every public function and helper.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no scratch.
"""

from __future__ import annotations

from collections.abc import Iterable

from ._social_wellbeing_rubric import _SPARSE_OBSERVED_RATIO_THRESHOLD
from .evidence import CategoryEvidenceBundle, EvidenceObservation, TemporalKind
from .results import (
    MissingnessSummary,
    ReviewFlag,
    ScoreComponent,
)


def build_missingness_summary(
    bundle: CategoryEvidenceBundle,
    observations: Iterable[EvidenceObservation] | None = None,
) -> MissingnessSummary:
    """Compute the :class:`MissingnessSummary` for the result.

    ``total_expected`` is the number of plan indicators
    (:attr:`CategorySourcePlan.expected_indicators`). ``total_observed``
    is the number of plan variables with at least one usable
    observation (skipping observations whose variable is not in the
    plan's expected set, and skipping observations whose
    ``normalized_value`` is ``None`` — the latter is already
    effectively missing). ``by_reason`` and ``by_severity`` are
    rolled up from the bundle's explicit :class:`MissingObservation`
    rows.

    The ``observations`` parameter is the **filtered** observation
    set the scorer is actually scoring on — i.e. with
    :data:`~leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
    (``client_existing`` / ``client_matrix``) already stripped. The
    scorer boundary passes this set so a contaminated bundle cannot
    inflate ``total_observed`` and silently suppress the
    :attr:`~leaders_db.score.results.ReviewFlag.SPARSE_DATA` flag.
    The parameter defaults to ``None`` (use
    :attr:`CategoryEvidenceBundle.observations`) for any direct
    caller that has not yet been audited for client contamination;
    the production scorer always passes the filtered set explicitly.
    """
    plan = bundle.source_plan
    expected_variables = plan.expected_variables

    # Distinct plan variables that have at least one usable
    # observation. Observations whose variable is not in the plan
    # (defence in depth) are skipped.
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

    # Count the missing observations by reason and severity.
    by_reason: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for missing in bundle.missing:
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
    The set is the join key the manual-review queue sorts on, so a
    missing primary source or a proxy-heavy bundle must surface here
    rather than only in the rationale.

    The forward ``human_review_required`` invariant (set in
    :func:`score_social_wellbeing`) is derived from these flags; if
    the empty list returns here, the result is non-flagged and
    ``human_review_required`` is ``False``.
    """
    flags: list[ReviewFlag] = []

    # 1. Missing REQUIRED (severity PRIMARY) observation.
    if bundle.primary_missing_observations:
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
    #    temporal fit and therefore the §11 confidence.
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
) -> str:
    """Compose the short human-readable rationale.

    1-3 sentences; surfaces the scale mapping (1..10 vs 0..10), the
    observed indicator count, and any flag-triggering condition in
    plain language so a reviewer scanning the manual-review queue
    sees the rubric state without re-walking the bundle.
    """
    parts: list[str] = []
    parts.append(
        f"Social-wellbeing score {score_1_10}/10 on the 1..10 prototype "
        f"scale (normalized {normalized:.2f}, mapping "
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
            "Primary (REQUIRED) indicator missing — undp_hdi_hdi absent."
        )
    if ReviewFlag.SPARSE_DATA in flags:
        parts.append(
            "Sparse data: fewer than half of plan indicators observed."
        )
    if ReviewFlag.INSUFFICIENT_DATA in flags:
        parts.append(
            "Bundle fell below the plan's minimum-viable source count; "
            "no score emitted."
        )

    return " ".join(parts)


__all__ = [
    "build_missingness_summary",
    "build_rationale",
    "count_proxy_observations",
    "detect_flags",
]
