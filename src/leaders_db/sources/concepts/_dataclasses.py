"""Public dataclasses, type aliases, and exceptions for the concept catalog.

The module owns:

- The ``ConceptMappingType`` literal (mirrors the documented
  ``direct`` / ``derived`` distinction).
- The frozen dataclasses :class:`ConceptDescriptor`,
  :class:`ConceptMapping`, and :class:`ConceptObservation`.
- The :class:`UnknownConceptError` and
  :class:`UnsupportedConceptSourceError` exceptions + the common
  :class:`ConceptCatalogError` base.

The dataclasses are intentionally frozen so downstream code can rely
on immutability for caching / memoization without copying. The
exception classes are :class:`ValueError` subclasses so generic
exception handling (e.g. Pydantic validation) still catches them,
but each subclass is specific enough that callers can branch on it
without reading string messages.

The module does NOT import ``leaders_db.ingest``. It only depends on
the unified :class:`NormalizedObservation` /
:class:`SourceWarning` contracts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from ..contracts import (
    JsonValue,
    RawLocator,
    SourceId,
    SourceWarning,
    TransformLocator,
)

ConceptMappingType = Literal["direct", "derived"]
"""Type alias for the documented mapping kinds.

- ``direct``: the concept is an alias for one or more
  source-specific indicator codes; extraction returns one
  :class:`ConceptObservation` per matching observation.
- ``derived``: the concept is a recipe over same-source,
  same-entity, same-year observations; extraction may emit
  a row or may emit zero rows + structured warnings when
  inputs are missing or ambiguous.
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConceptCatalogError(ValueError):
    """Base class for concept-catalog errors.

    Defined so callers can catch every concept-catalog failure with
    a single ``except`` clause when they want to. The two specific
    subclasses (:class:`UnknownConceptError` and
    :class:`UnsupportedConceptSourceError`) are the ones tests /
    application code should branch on for actionable handling.
    """


class UnknownConceptError(ConceptCatalogError):
    """Raised when a concept key is not in the catalog.

    The message names the offending key and the list of known keys
    so callers can fix the typo or extend the catalog without
    reading source code.
    """

    def __init__(self, concept_key: str, known_keys: object) -> None:
        self.concept_key = concept_key
        self.known_keys = tuple(known_keys)  # type: ignore[arg-type]
        super().__init__(
            f"Unknown concept key {concept_key!r}; known concepts: "
            f"{list(self.known_keys)}",
        )


class UnsupportedConceptSourceError(ConceptCatalogError):
    """Raised when a concept/source pair has no mapping.

    Per SRC-CONCEPT-008, the catalog refuses to silently invent a
    mapping for an unsupported concept/source pair. The message
    names both the concept and the source id so a developer can
    either pick a supported source or extend the catalog.
    """

    def __init__(
        self,
        concept_key: str,
        source_id: SourceId | str,
        available_sources: object,
    ) -> None:
        self.concept_key = concept_key
        self.source_id_str = (
            source_id.slug if isinstance(source_id, SourceId) else str(source_id)
        )
        self.available_sources = tuple(
            s.slug if isinstance(s, SourceId) else str(s)
            for s in available_sources  # type: ignore[union-attr]
        )
        super().__init__(
            f"Concept {concept_key!r} has no mapping for source "
            f"{self.source_id_str!r}; supported sources: "
            f"{list(self.available_sources)}",
        )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConceptExtractionResult:
    """Diagnostic-friendly result of a concept extraction call.

    Carries the emitted :class:`ConceptObservation` rows plus a
    separate ``warnings`` tuple that aggregates every per-row
    warning AND every per-scope drop reason from the derivation
    helpers. The minimal :func:`extract_concept` API returns only
    ``observations`` (the legacy flat-tuple shape). The diagnostic
    :func:`extract_concept_result` API returns this dataclass so
    callers can surface missing / ambiguous / non-numeric /
    divide-by-zero / source-version / mismatched-year inputs as
    actionable structured records rather than discovering the gap
    by the absence of an emitted row.

    ``observations`` and ``warnings`` are both tuples so they can
    be compared / hashed for test assertions and iterated directly
    by downstream scorers.
    """

    observations: tuple[ConceptObservation, ...]
    warnings: tuple[SourceWarning, ...] = ()


@dataclass(frozen=True)
class ConceptDescriptor:
    """Stable, source-agnostic description of one concept.

    A descriptor is the catalog entry that an analyst or scorer sees
    when listing the supported concepts. It carries the stable key,
    a human-readable display name, a description of what the concept
    means, and the canonical unit/scale convention the catalog
    recommends for downstream consumers. The catalog does NOT
    promise that every value produced by ``extract_concept`` will
    land in the canonical unit (source-specific scales vary); the
    descriptor documents the recommended convention only.
    """

    concept_key: str
    display_name: str
    description: str
    unit: str | None = None
    scale: str | None = None


@dataclass(frozen=True)
class ConceptMapping:
    """Source-specific direct or derived mapping for one concept.

    Direct mappings declare one or more source-specific indicator
    codes that alias the concept. Derived mappings declare the
    inputs (and a recipe key) for a deterministic arithmetic
    transformation over same-source, same-entity, same-year
    observations.
    """

    concept_key: str
    source_id: SourceId
    mapping_type: ConceptMappingType
    indicator_codes: tuple[str, ...]
    output_unit: str | None = None
    output_scale: str | None = None
    # When ``mapping_type == "derived"``, ``recipe_key`` identifies
    # the recipe (a stable string). When ``mapping_type == "direct"``,
    # ``recipe_key`` is None.
    recipe_key: str | None = None
    # Human-readable description of the recipe / direct alias; surfaced
    # in debugging output and in research logs. Optional.
    notes: str | None = None


@dataclass(frozen=True)
class ConceptObservation:
    """Per-observation result row produced by ``extract_concept``.

    A ``ConceptObservation`` is the canonical, query-time-normalized
    payload. It carries:

    - the source id + source version (propagated from the input(s)),
    - the concept key + value + value_type + unit + scale,
    - the source-specific indicator codes consumed (1+ for direct,
      1+ for derived),
    - the input observation ids that contributed to this row,
    - the raw locators + transform locators of those inputs so audit
      code can resolve the source-native raw cells,
    - explicit quality flags (e.g. ``derived_concept`` for derived
      rows) and structured warnings,
    - an ``extension`` payload for source-/recipe-specific extras
      (e.g. recipe key, numerator/denominator pair info).

    The dataclass is frozen so downstream code can rely on
    immutability for caching / memoization without copying.
    """

    concept_key: str
    source_id: SourceId
    value: float | int | None
    value_type: Literal["numeric", "missing"]
    year: int | None
    country_code: str | None
    country_name: str | None
    leader_id: str | None
    leader_name: str | None
    unit: str | None
    scale: str | None
    source_version: str | None
    source_indicator_codes: tuple[str, ...]
    input_observation_ids: tuple[str, ...]
    raw_locators: tuple[RawLocator, ...]
    transform_locators: tuple[TransformLocator, ...]
    quality_flags: tuple[str, ...] = ()
    warnings: tuple[SourceWarning, ...] = ()
    mapping_type: ConceptMappingType = "direct"
    recipe_key: str | None = None
    extension: Mapping[str, JsonValue] = field(default_factory=dict)


__all__ = [
    "ConceptCatalogError",
    "ConceptDescriptor",
    "ConceptExtractionResult",
    "ConceptMapping",
    "ConceptMappingType",
    "ConceptObservation",
    "UnknownConceptError",
    "UnsupportedConceptSourceError",
]
