"""Public API for the semantic indicator concept catalog.

The public functions are:

- :func:`list_concepts` -- return the canonical ordered list of
  :class:`ConceptDescriptor` records.
- :func:`resolve_concept` -- return the :class:`ConceptMapping`
  records for a concept key, optionally narrowed by source.
- :func:`extract_concept` -- return zero or more
  :class:`ConceptObservation` rows from a sequence of provided
  :class:`NormalizedObservation` records. The minimal public
  shape: a flat tuple of observations.
- :func:`extract_concept_result` -- the diagnostic helper that
  returns a :class:`ConceptExtractionResult` carrying both the
  emitted observations AND the structured warnings raised by
  direct mappings (per-row ``missing_value`` warnings) and the
  derived mapping (per-scope drop reasons for missing /
  ambiguous / non-numeric / zero / missing-source-version /
  mismatched-year inputs).

All four are pure functions over the static catalog data + the
provided observation sequence. The API surface never imports
``leaders_db.ingest`` and never reads raw files; the
``tests/sources/test_concepts.py::test_concepts_module_does_not_import_legacy_ingest_at_import``
test enforces that boundary by AST inspection.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..contracts import NormalizedObservation, SourceId, SourceWarning
from ._catalog import (
    KNOWN_CONCEPT_KEYS,
    build_concept_descriptors,
    build_concept_mappings,
)
from ._dataclasses import (
    ConceptDescriptor,
    ConceptExtractionResult,
    ConceptMapping,
    ConceptObservation,
    UnknownConceptError,
    UnsupportedConceptSourceError,
)
from ._derived import (
    emit_derived_observations_with_warnings,
)
from ._direct import emit_direct_observations

# Module-level immutable catalog snapshots. Built once at import
# time so callers can rely on identical descriptors / mappings
# across the lifetime of a single Python process.
_CONCEPT_DESCRIPTORS: tuple[ConceptDescriptor, ...] = build_concept_descriptors()
_CONCEPT_MAPPINGS: tuple[ConceptMapping, ...] = build_concept_mappings()


def _coerce_source_id(source_id: SourceId | str | None) -> SourceId | None:
    """Return ``source_id`` as a :class:`SourceId` or ``None``.

    Accepts a :class:`SourceId`, a source-slug string, or ``None``
    (no filter). Other types raise :class:`TypeError` so a typo or
    wrong input shape surfaces a clear error rather than failing
    later with a confusing lookup miss.
    """
    if source_id is None:
        return None
    if isinstance(source_id, SourceId):
        return source_id
    if isinstance(source_id, str):
        return SourceId(slug=source_id)
    raise TypeError(
        f"source_id must be a SourceId, source-slug string, or None; "
        f"got {type(source_id).__name__}: {source_id!r}",
    )


def list_concepts() -> tuple[ConceptDescriptor, ...]:
    """Return the canonical ordered list of stable concept descriptors.

    The order is the same canonical order declared by
    :data:`KNOWN_CONCEPT_KEYS`. Tests / docs that iterate the result
    can rely on the order being deterministic across runs.

    The function is intentionally side-effect free: it does not
    import any source adapter, does not consult the legacy
    ``leaders_db.ingest`` subsystem, and does not read raw files or
    DB rows. The descriptors are static metadata.
    """
    return _CONCEPT_DESCRIPTORS


def resolve_concept(
    concept_key: str,
    source_id: SourceId | str | None = None,
) -> tuple[ConceptMapping, ...]:
    """Return the source-specific concept mappings for ``concept_key``.

    Parameters
    ----------
    concept_key:
        Stable concept key. Unknown keys raise
        :class:`UnknownConceptError` with the list of known keys so
        callers can fix typos without reading source code.
    source_id:
        Optional source filter. Accepts a :class:`SourceId`, a
        source-slug string, or ``None`` (no filter). When set, the
        result is narrowed to mappings for that source; an unknown
        combination raises :class:`UnsupportedConceptSourceError`
        with the list of supported sources so a developer can either
        pick a supported source or extend the catalog.

    Returns
    -------
    tuple[ConceptMapping, ...]
        Ordered mappings. The order mirrors the canonical
        registration order in :func:`build_concept_mappings`.

    Raises
    ------
    UnknownConceptError
        ``concept_key`` is not in the catalog.
    UnsupportedConceptSourceError
        ``concept_key`` is known but ``source_id`` is not mapped for
        it (e.g. ``client_existing``, which deliberately has no
        concept mappings per SRC-CONCEPT-010).
    """
    if concept_key not in KNOWN_CONCEPT_KEYS:
        raise UnknownConceptError(concept_key, KNOWN_CONCEPT_KEYS)

    if source_id is None:
        return tuple(
            mapping for mapping in _CONCEPT_MAPPINGS
            if mapping.concept_key == concept_key
        )

    target = _coerce_source_id(source_id)
    assert target is not None  # for type-checkers
    matches = tuple(
        mapping for mapping in _CONCEPT_MAPPINGS
        if mapping.concept_key == concept_key
        and mapping.source_id.slug == target.slug
    )
    if not matches:
        supported = tuple(
            mapping.source_id
            for mapping in _CONCEPT_MAPPINGS
            if mapping.concept_key == concept_key
        )
        raise UnsupportedConceptSourceError(
            concept_key,
            target,
            supported,
        )
    return matches


def extract_concept(
    observations: Sequence[NormalizedObservation],
    concept_key: str,
    source_id: SourceId | str | None = None,
) -> tuple[ConceptObservation, ...]:
    """Extract :class:`ConceptObservation` rows from provided observations.

    Parameters
    ----------
    observations:
        Sequence of :class:`NormalizedObservation` records. The
        function never reads raw files, calls source adapters,
        instantiates :class:`SourceIngestRunner`, or imports
        ``leaders_db.ingest``; it only consumes the provided
        records. Callers typically source this from an in-memory
        :class:`EvidenceRepository` result.
    concept_key:
        Stable concept key. Unknown keys raise
        :class:`UnknownConceptError`.
    source_id:
        Optional source filter (SourceId, slug string, or None).
        Unknown combinations raise
        :class:`UnsupportedConceptSourceError`.

    Returns
    -------
    tuple[ConceptObservation, ...]
        Zero or more extracted rows.

        - Direct mappings produce one row per matching observation.
        - Derived mappings produce one row per valid scope; missing,
          non-numeric, zero, ambiguous, source-version-mismatched,
          or year-mismatched inputs produce zero rows for that scope
          (no silent guesses).
        - Direct mappings do NOT silently drop non-numeric cells:
          the row is emitted with ``value=None`` and
          ``value_type="missing"`` and a structured
          ``missing_value`` warning attached to the row's
          ``warnings`` tuple.

        This is the minimal / flat-tuple shape. Callers that need
        structured diagnostic warnings for derivation drop reasons
        should use :func:`extract_concept_result` instead.

    Raises
    ------
    UnknownConceptError
        ``concept_key`` is not in the catalog.
    UnsupportedConceptSourceError
        ``concept_key`` is known but ``source_id`` is not mapped for
        it.
    """
    return extract_concept_result(
        observations,
        concept_key,
        source_id,
    ).observations


def extract_concept_result(
    observations: Sequence[NormalizedObservation],
    concept_key: str,
    source_id: SourceId | str | None = None,
) -> ConceptExtractionResult:
    """Extract :class:`ConceptObservation` rows AND surface diagnostics.

    Parameters
    ----------
    observations:
        Sequence of :class:`NormalizedObservation` records. The
        function never reads raw files, calls source adapters,
        instantiates :class:`SourceIngestRunner`, or imports
        ``leaders_db.ingest``; it only consumes the provided
        records.
    concept_key:
        Stable concept key. Unknown keys raise
        :class:`UnknownConceptError`.
    source_id:
        Optional source filter (SourceId, slug string, or None).
        Unknown combinations raise
        :class:`UnsupportedConceptSourceError`.

    Returns
    -------
    :class:`ConceptExtractionResult`
        A frozen dataclass with two tuple fields:

        - ``observations``: zero or more extracted
          :class:`ConceptObservation` rows (same shape as
          :func:`extract_concept`).
        - ``warnings``: structured :class:`SourceWarning` records
          for every per-row direct-mapping diagnostic AND every
          per-scope derived-mapping drop reason
          (missing numerator / denominator, ambiguous pair,
          non-numeric numerator / denominator, zero denominator,
          missing or mismatched ``source_version``, defensive
          year mismatch). The convenience
          :func:`extract_concept` wrapper discards these so the
          minimal public API stays flat.

        ``warnings`` is empty when every scope is valid.

    Raises
    ------
    UnknownConceptError
        ``concept_key`` is not in the catalog.
    UnsupportedConceptSourceError
        ``concept_key`` is known but ``source_id`` is not mapped for
        it.
    """
    mappings = resolve_concept(concept_key, source_id)

    emitted: list[ConceptObservation] = []
    warnings: list[SourceWarning] = []
    for mapping in mappings:
        if mapping.mapping_type == "direct":
            direct_rows = emit_direct_observations(
                observations=observations,
                mapping=mapping,
            )
            emitted.extend(direct_rows)
            for row in direct_rows:
                warnings.extend(row.warnings)
        elif mapping.mapping_type == "derived":
            derived_rows, derived_warnings = (
                emit_derived_observations_with_warnings(
                    observations=observations,
                    mapping=mapping,
                )
            )
            emitted.extend(derived_rows)
            warnings.extend(derived_warnings)
        # Unknown future mapping types are intentionally ignored;
        # the catalog refuses to invent a recipe on the fly.
    return ConceptExtractionResult(
        observations=tuple(emitted),
        warnings=tuple(warnings),
    )


__all__ = [
    "extract_concept",
    "extract_concept_result",
    "list_concepts",
    "resolve_concept",
]
