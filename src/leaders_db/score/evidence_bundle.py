"""The :class:`CategoryEvidenceBundle` — the full Stage 5 evidence
bundle for one country/year/category.

Aligns with ``docs/architecture/overview.md`` §"Evidence Bundle Contract"
(``CategoryEvidenceBundle`` block) and REQ-STAGE-006/007. The bundle
is the single object a Stage 9-10 category scorer consumes; it carries
every expected source, every available observation with its raw
locator and normalized value, every missing observation with its
reason and severity, the source plan that defines the
minimum-viable threshold, and a small read-only
:attr:`category_metadata` slot for category-specific audit-trail
context (e.g. rubric edition, weight-set version).

The bundle is the **terminal** type in the evidence module: it
imports from ``evidence_types``, ``evidence_observation``, and
``evidence_plan``, and is re-exported through
:mod:`leaders_db.score.evidence`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from .evidence_observation import EvidenceObservation, MissingObservation
from .evidence_plan import CategorySourcePlan
from .evidence_types import MissingSeverity

# ---------------------------------------------------------------------------
# Module-level empty sentinels for sequence fields
# ---------------------------------------------------------------------------
#
# These are immutable and safe to share across instances. The frozen
# dataclass uses them as defaults so empty bundles do not allocate
# fresh containers per instance.

_EMPTY_OBSERVATIONS: tuple[EvidenceObservation, ...] = ()
_EMPTY_MISSING: tuple[MissingObservation, ...] = ()

# ---------------------------------------------------------------------------
# Excluded source keys (defence-in-depth at the bundle boundary)
# ---------------------------------------------------------------------------
#
# The bundle builder excludes the client 2023 matrix upstream
# (requirement §3, §9, §12; AGENTS.md always-on rule #6). The bundle
# also re-filters here so the :attr:`CategoryEvidenceBundle.usable_observations`
# view never carries client-matrix rows even if a contaminated
# bundle is hand-built. We duplicate the frozenset locally rather
# than importing it to avoid an import cycle (the bundle is imported
# by ``source_plans``).
_EXCLUDED_SOURCE_KEYS: frozenset[str] = frozenset(
    {"client_existing", "client_matrix"}
)


# ---------------------------------------------------------------------------
# Category evidence bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryEvidenceBundle:
    """The full Stage 5 evidence bundle for one country/year/category.

    Attributes
    ----------
    country_iso3:
        Three-character ISO 3166-1 alpha-3 code (e.g. ``"MEX"``).
    country_name:
        Human-readable country name (e.g. ``"Mexico"``).
    leader_name:
        Canonical leader name in office for ``year``, or ``None`` when
        no leader can be resolved.
    year:
        Target year (1900..2100) the bundle is being built for.
    category_key:
        Canonical category identifier (must match
        :attr:`CategorySourcePlan.category_key`).
    source_plan:
        The :class:`CategorySourcePlan` that defines the expected
        source set, minimum-viable threshold, and rubric metadata.
    observations:
        Available :class:`EvidenceObservation` rows from the plan's
        expected sources. The constructor accepts any sequence; the
        stored value is a tuple.
    missing:
        :class:`MissingObservation` records for expected observations
        that the bundle does not contain. The constructor accepts any
        sequence; the stored value is a tuple.
    category_metadata:
        Small read-only mapping for category-specific audit-trail
        context (e.g. ``{"rubric_year": "2023", "edition": "v1"}``).
        The constructor accepts any ``Mapping`` (or ``None``), copies
        its contents into a fresh dict, and stores a
        :class:`types.MappingProxyType` view of that copy. The
        defensive copy is applied **unconditionally** — even when the
        caller passes a ``MappingProxyType`` wrapping a mutable backing
        dict — so later mutation of the caller's container cannot leak
        into the bundle (REQ-NFR-AUDIT-001).
    """

    country_iso3: str
    country_name: str
    leader_name: str | None
    year: int
    category_key: str
    source_plan: CategorySourcePlan
    observations: Sequence[EvidenceObservation] = _EMPTY_OBSERVATIONS
    missing: Sequence[MissingObservation] = _EMPTY_MISSING
    category_metadata: Mapping[str, str] | None = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        # Defensive copy: convert any sequence to a tuple.
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "missing", tuple(self.missing))

        # Defensive copy: normalise the metadata mapping to a true
        # read-only view of a **fresh** dict copy. This applies
        # unconditionally — even when the caller passes a
        # ``MappingProxyType`` that wraps a mutable backing dict.
        # ``MappingProxyType`` is itself a ``Mapping``, so a single
        # ``isinstance`` check covers both plain ``dict`` and
        # proxy-wrapped inputs; ``dict(md)`` then snapshots the
        # current contents into a new dict the caller no longer holds.
        md = self.category_metadata
        if md is None:
            md = MappingProxyType({})
        elif isinstance(md, Mapping):
            md = MappingProxyType(dict(md))
        else:
            raise TypeError(
                f"category_metadata must be a Mapping or None "
                f"(got {type(md).__name__})"
            )
        object.__setattr__(self, "category_metadata", md)

        if not self.country_iso3 or len(self.country_iso3) != 3:
            raise ValueError(
                f"country_iso3 must be a 3-character code (got {self.country_iso3!r})"
            )
        if not self.country_name:
            raise ValueError("country_name must be non-empty")
        if not self.category_key:
            raise ValueError("category_key must be non-empty")
        if not (1900 <= self.year <= 2100):
            raise ValueError(f"year must be in 1900..2100 (got {self.year})")
        if self.category_key != self.source_plan.category_key:
            raise ValueError(
                f"bundle category_key={self.category_key!r} does not match "
                f"source_plan.category_key={self.source_plan.category_key!r}"
            )

    @property
    def available_count(self) -> int:
        """Return the number of available observations in the bundle."""
        return len(self.observations)

    @property
    def missing_count(self) -> int:
        """Return the number of explicitly missing observations."""
        return len(self.missing)

    @property
    def has_minimum_viable_evidence(self) -> bool:
        """Return True iff the bundle satisfies the plan's minimum-viable threshold.

        Counts **all** distinct source keys present in the bundle's
        observations — including rows whose ``normalized_value`` is
        ``None`` (i.e. the source row exists but normalization did not
        produce a comparable 0..1 value). This is the loose "any
        evidence present" gate; per-category scorers that need to
        score on actually-comparable values must use
        :attr:`has_minimum_viable_usable_evidence` instead.

        Delegates to :meth:`CategorySourcePlan.minimum_viable_met`.
        """
        return self.source_plan.minimum_viable_met(self.observations)

    @property
    def usable_observations(self) -> tuple[EvidenceObservation, ...]:
        """Return the subset of observations the scorer can actually use.

        An observation is "usable" iff **all three** of:

        - its ``normalized_value`` is not ``None`` — Stage 6
          normalization either produced a 0..1 value or flagged the
          row as effectively missing;
        - its ``variable_name`` is in the plan's expected indicator
          set (defence-in-depth against out-of-plan variables — the
          bundle builder already enforces per-indicator ownership);
        - its ``source_key`` is **not** in
          :data:`~leaders_db.score.source_plans.EXCLUDED_SOURCE_KEYS`
          (defence-in-depth against the client 2023 matrix being
          treated as evidence; the bundle builder already excludes
          client source keys upstream).

        Per REQ-SCORE-004 the scorer must not invent a value for a
        ``None`` normalized row, so the scorer gates its
        minimum-viable threshold on **usable** observations only (the
        loose :attr:`has_minimum_viable_evidence` gate would
        otherwise count a source that contributed only a
        ``normalized_value=None`` row as viable evidence, or a
        client-matrix row as a real evidence source).
        """
        expected_variables = set(self.source_plan.expected_variables)
        return tuple(
            obs
            for obs in self.observations
            if obs.normalized_value is not None
            and obs.variable_name in expected_variables
            and obs.source_key not in _EXCLUDED_SOURCE_KEYS
        )

    @property
    def has_minimum_viable_usable_evidence(self) -> bool:
        """Return True iff the bundle has enough distinct sources of usable observations.

        "Usable" means ``normalized_value`` is not ``None`` and the
        variable is in the plan's expected indicator set — see
        :attr:`usable_observations`. Per-category scorers that gate on
        ``minimum_viable_sources`` to decide between a provisional
        score and :attr:`~leaders_db.score.results.ScoreResult.is_insufficient_data`
        must use this property; the loose
        :attr:`has_minimum_viable_evidence` gate is the wrong tool
        because it counts sources that contributed only a
        ``normalized_value=None`` row.

        Delegates to :meth:`CategorySourcePlan.minimum_viable_met`
        with the usable subset.
        """
        return self.source_plan.minimum_viable_met(self.usable_observations)

    @property
    def primary_missing_observations(self) -> tuple[MissingObservation, ...]:
        """Return the subset of missing observations with severity PRIMARY.

        Used by the Stage 14 manual-review queue builder to prioritize
        bundles whose primary indicators are absent (REQ-REV-002:
        "missing primary sources" is a manual-review trigger).
        """
        return tuple(m for m in self.missing if m.severity is MissingSeverity.PRIMARY)


__all__ = ["CategoryEvidenceBundle"]
