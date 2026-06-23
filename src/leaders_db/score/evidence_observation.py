"""Per-row evidence types: :class:`EvidenceObservation` and
:class:`MissingObservation`.

One :class:`EvidenceObservation` = one row from a structured source
(``source_observations`` in the canonical schema). One
:class:`MissingObservation` = one expected row that the bundle does
not contain, with the reason and severity recorded.

Both types are pure scalar carriers — no collection fields — so the
frozen dataclass alone is sufficient for immutability. No collection
defensive-copy is needed here.

This module imports only from :mod:`leaders_db.score.evidence_types`
(the vocabulary). It does **not** import from ``evidence_plan`` or
``evidence_bundle``, so the dependency graph stays acyclic:

    evidence_types  <--  evidence_observation  <--  evidence_plan
                                                  <--  evidence_bundle
"""

from __future__ import annotations

from dataclasses import dataclass

from .evidence_types import Direction, MissingReason, MissingSeverity, TemporalKind

# ---------------------------------------------------------------------------
# Evidence observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceObservation:
    """One structured-dataset observation inside an evidence bundle.

    Aligns with ``docs/architecture/overview.md`` §"Evidence Bundle Contract"
    (``EvidenceObservation`` block) and REQ-LAKE-004 ("every source
    observation used in a score shall be traceable back to a raw row,
    cell, API record, or document locator; missing locator information
    shall block high-confidence scoring for that observation").

    All fields are scalar, so the frozen dataclass alone is sufficient
    for immutability — no collection defensive-copy is needed.

    Attributes
    ----------
    source_key:
        Canonical source identifier (e.g. ``"vdem"``).
    source_name:
        Human-readable source name (e.g. ``"V-Dem v16"``).
    variable_name:
        Canonical indicator name (matches the catalog
        ``variable_name`` for the source).
    raw_value:
        Original cell/text from the source. ``None`` when the source row
        exists but the indicator is missing.
    numeric_value:
        Light numeric coercion of ``raw_value`` (``None`` if not
        coercible).
    normalized_value:
        Stage 6 normalized value on the 0..1 comparable scale. ``None``
        when normalization was not run yet (Stage 5 output) or when the
        observation is effectively missing.
    unit:
        Unit string (``"index"``, ``"percent"``, ...); ``None`` when
        dimensionless.
    direction:
        :class:`Direction` for this indicator.
    observation_year:
        Year the source reports the value for (``None`` for
        ``TemporalKind.NOT_AVAILABLE``).
    target_year:
        Year the bundle is being built for (the target ruler-year).
    temporal_kind:
        :class:`TemporalKind` describing how ``observation_year`` maps
        to ``target_year``.
    source_row_reference:
        Raw locator per the source's locator convention (see
        ``docs/architecture/overview.md`` §"Source Locator Table"). ``None`` when
        the locator is unavailable; :attr:`has_locator` returns False in
        that case and the observation cannot be the basis for a
        high-confidence contribution (REQ-LAKE-004).
    authority_score:
        Component-1 quality of the source on the §11 0..100 scale.
    specificity_score:
        Component-3 fit of the observation to country/year/ruler/category
        on the §11 0..100 scale.
    notes:
        Free-form notes for the rationale/audit trail.
    """

    source_key: str
    source_name: str
    variable_name: str
    raw_value: str | None
    numeric_value: float | None
    normalized_value: float | None
    unit: str | None
    direction: Direction
    observation_year: int | None
    target_year: int
    temporal_kind: TemporalKind
    source_row_reference: str | None
    authority_score: int
    specificity_score: int
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.source_key:
            raise ValueError("EvidenceObservation.source_key must be non-empty")
        if not self.source_name:
            raise ValueError("EvidenceObservation.source_name must be non-empty")
        if not self.variable_name:
            raise ValueError("EvidenceObservation.variable_name must be non-empty")
        if not (0 <= self.authority_score <= 100):
            raise ValueError(
                f"authority_score must be in 0..100 (got {self.authority_score})"
            )
        if not (0 <= self.specificity_score <= 100):
            raise ValueError(
                f"specificity_score must be in 0..100 (got {self.specificity_score})"
            )
        if self.temporal_kind is TemporalKind.NOT_AVAILABLE:
            # NOT_AVAILABLE is the explicit placeholder; observation_year may
            # legitimately be None. Other kinds must carry a concrete year.
            return
        if self.observation_year is None:
            raise ValueError(
                f"observation_year is required for temporal_kind={self.temporal_kind!r}"
            )

    @property
    def has_locator(self) -> bool:
        """Return True iff a non-empty raw locator is present.

        REQ-LAKE-004: "every source observation used in a score shall be
        traceable back to a raw row, cell, API record, or document
        locator; missing locator information shall block high-confidence
        scoring for that observation."
        """
        return bool(self.source_row_reference and self.source_row_reference.strip())


# ---------------------------------------------------------------------------
# Missing observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MissingObservation:
    """One expected observation that the bundle does not contain.

    Aligns with ``docs/architecture/overview.md`` §"Evidence Bundle Contract"
    (``MissingObservation`` block) and REQ-STAGE-007 ("Stage 5 shall
    distinguish missingness reasons, including source not implemented,
    raw file absent, country row absent, target year absent, indicator
    null, not applicable, blocked/paywalled, and intentionally excluded
    by configuration").

    Attributes
    ----------
    source_key:
        Canonical source identifier for the missing observation.
    variable_name:
        Canonical indicator name that is missing.
    reason:
        :class:`MissingReason` describing *why* the observation is missing.
    severity:
        :class:`MissingSeverity` describing *how much* the missingness
        hurts the category score and confidence.
    """

    source_key: str
    variable_name: str
    reason: MissingReason
    severity: MissingSeverity

    def __post_init__(self) -> None:
        if not self.source_key:
            raise ValueError("MissingObservation.source_key must be non-empty")
        if not self.variable_name:
            raise ValueError("MissingObservation.variable_name must be non-empty")


__all__ = [
    "EvidenceObservation",
    "MissingObservation",
]
