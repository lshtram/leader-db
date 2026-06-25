"""Evidence query interfaces for downstream consumers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from .contracts import (
    EvidenceQuery,
    NormalizedObservation,
    SourceAttribution,
    SourceId,
    SourceManifest,
)


@runtime_checkable
class EvidenceRepository(Protocol):
    """Read-only source-evidence query boundary."""

    def query_observations(self, query: EvidenceQuery) -> Sequence[NormalizedObservation]:
        """Return observations matching ``query`` without rerunning ingestion."""
        ...

    def get_manifest(self, source_id: SourceId, run_id: str | None = None) -> SourceManifest:
        """Return a source manifest by source and optional run id."""
        ...

    def get_attributions(self, source_ids: Sequence[SourceId]) -> Sequence[SourceAttribution]:
        """Return normative attribution records for ``source_ids``."""
        ...


class InMemoryEvidenceRepository:
    """In-memory, read-only implementation of :class:`EvidenceRepository`.

    The repository is the canonical concrete implementation of the
    ``EvidenceRepository`` Protocol for this slice. It is intended for
    tests, research scripts, and concept-extraction flows that already
    hold materialized ``NormalizedObservation`` / ``SourceManifest`` /
    ``SourceAttribution`` records in memory.

    Design rules (mirrors ``docs/architecture/sources.md`` §5.7 and
    ``docs/requirements/sources.md`` §10 SRC-QUERY-006..012):

    - The constructor accepts three sequences (``observations``,
      ``manifests``, ``attributions``) and copies each into an internal
      tuple so caller-owned lists are never mutated.
    - ``query_observations`` filters by every documented filter
      dimension. ``None`` means "unfiltered"; an empty tuple ``()`` is
      a deliberate filter that returns no observations for that
      dimension (natural membership semantics). The input observation
      order is preserved in the result tuple. ``source_ids`` match
      against the stored ``SourceId.slug``. ``leaders`` match against
      either ``leader_id`` or ``leader_name`` so callers can query by
      either dimension until leader IDs are stable.
    - ``get_manifest(source_id, run_id)`` performs an exact
      ``(slug, run_id)`` lookup when ``run_id`` is provided. When
      ``run_id`` is ``None``, the repository returns the only stored
      manifest for the source if exactly one exists, and raises
      ``KeyError`` (actionable message naming the available run ids)
      when multiple manifests exist for the same source. A missing
      manifest always raises ``KeyError`` naming the source slug and
      the known run ids.
    - ``get_attributions(source_ids)`` returns attributions in the
      order of the requested ``source_ids`` argument; sources without
      a stored attribution are silently skipped.
    - The repository never imports ``leaders_db.ingest``, never
      instantiates ``SourceIngestRunner``, never calls source adapters,
      never reads raw files, and never writes processed/DB output.
      That boundary is enforced by the canonical import-boundary
      submodule list in
      ``tests/sources/test_import_boundary.py`` plus the monkeypatched
      ``SourceIngestRunner.__init__`` + ``Path.open`` / ``Path.read_*``
      sentinels in ``tests/sources/test_query_repository.py``.
    - The four ``EvidenceQuery.include_*`` flags
      (``include_raw_locators``, ``include_warnings``,
      ``include_quality_flags``, ``include_attribution``,
      ``include_manifests``) are advisory in this slice: the
      repository always returns the full stored observation. The
      flags exist on the contract so a future persistence-backed
      repository can honor them without changing the
      ``EvidenceRepository`` surface.
    """

    __slots__ = (
        "_attributions_by_slug",
        "_manifests_by_key",
        "_manifests_by_slug",
        "_observations",
    )

    def __init__(
        self,
        *,
        observations: Sequence[NormalizedObservation] = (),
        manifests: Sequence[SourceManifest] = (),
        attributions: Sequence[SourceAttribution] = (),
    ) -> None:
        # Defensive tuple copies -- caller-owned sequences are never
        # mutated. The empty sequence ``()`` literal is the documented
        # default so ``InMemoryEvidenceRepository()`` is a valid
        # empty repository for tests that only exercise manifests /
        # attributions.
        self._observations: tuple[NormalizedObservation, ...] = tuple(observations)
        # Two manifest indices: by ``(slug, run_id)`` for the explicit
        # ``run_id`` path, and by ``slug`` for the "no run_id" path
        # that returns the only manifest when there is exactly one.
        # Last-write-wins for duplicate ``(slug, run_id)`` keys; the
        # documented contract does not forbid it and the slice is
        # deterministic so the behaviour is predictable.
        manifests_by_key: dict[tuple[str, str | None], SourceManifest] = {}
        manifests_by_slug: dict[str, tuple[SourceManifest, ...]] = {}
        for manifest in manifests:
            key = (manifest.source_id.slug, manifest.run_id)
            manifests_by_key[key] = manifest
            slug = manifest.source_id.slug
            manifests_by_slug[slug] = (*manifests_by_slug.get(slug, ()), manifest)
        self._manifests_by_key: dict[tuple[str, str | None], SourceManifest] = (
            manifests_by_key
        )
        self._manifests_by_slug: dict[str, tuple[SourceManifest, ...]] = (
            manifests_by_slug
        )
        # Attributions are keyed by source slug. The documented
        # contract (SRC-QUERY-010) does not promise a one-to-one
        # correspondence between source ids and attributions, so this
        # is the simplest deterministic mapping; if a future slice
        # needs multiple attributions per source, a list-valued
        # mapping can replace it without breaking the public API.
        attributions_by_slug: dict[str, SourceAttribution] = {}
        for attribution in attributions:
            attributions_by_slug[attribution.source_id.slug] = attribution
        self._attributions_by_slug: dict[str, SourceAttribution] = attributions_by_slug

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query_observations(
        self, query: EvidenceQuery,
    ) -> tuple[NormalizedObservation, ...]:
        """Return observations matching ``query`` from the stored state.

        ``None`` filter values are "unfiltered"; an empty tuple ``()``
        is a deliberate filter that returns no observations for that
        dimension (natural membership semantics). The input observation
        order is preserved in the result tuple.

        The four ``EvidenceQuery.include_*`` flags are advisory in
        this slice: the repository always returns the full stored
        observation. See ``docs/architecture/sources.md`` §5.7.
        """
        return tuple(
            obs for obs in self._observations if _matches(obs, query) is not None
        )

    def get_manifest(
        self, source_id: SourceId, run_id: str | None = None,
    ) -> SourceManifest:
        """Return a stored manifest for ``source_id``.

        Lookup rules (per ``docs/architecture/sources.md`` §5.7):

        - If ``run_id`` is provided, perform an exact
          ``(slug, run_id)`` lookup; missing combinations raise
          ``KeyError``.
        - If ``run_id`` is ``None`` and exactly one manifest is stored
          for the source, return it.
        - If ``run_id`` is ``None`` and multiple manifests are stored
          for the same source, raise ``KeyError`` with an actionable
          message naming the available run ids so the caller can pass
          an explicit run id.
        - If no manifest is stored for the source, raise ``KeyError``
          naming the source slug and the known run ids.
        """
        slug = source_id.slug
        if run_id is not None:
            key = (slug, run_id)
            try:
                return self._manifests_by_key[key]
            except KeyError as exc:
                known_runs = sorted(
                    m.run_id
                    for m in self._manifests_by_slug.get(slug, ())
                )
                raise KeyError(
                    f"No manifest stored for source {slug!r} with "
                    f"run_id {run_id!r}; known run ids for this "
                    f"source: {known_runs}"
                ) from exc

        stored = self._manifests_by_slug.get(slug, ())
        if not stored:
            # Distinguish "no manifests for this source" from
            # "manifest exists but only under different run ids"; the
            # repository has nothing at all under this slug, so we
            # name the slug only.
            raise KeyError(
                f"No manifest stored for source {slug!r}; the "
                f"in-memory repository has no manifest under that slug"
            )
        if len(stored) == 1:
            return stored[0]
        # Multiple manifests under the same slug: refuse to guess.
        # The slice prefers explicit ambiguity over silent picking.
        known_runs = sorted(m.run_id for m in stored)
        raise KeyError(
            f"Multiple manifests ({len(stored)}) stored for source "
            f"{slug!r}; pass an explicit run_id to disambiguate. "
            f"Known run ids: {known_runs}"
        )

    def get_attributions(
        self, source_ids: Sequence[SourceId],
    ) -> tuple[SourceAttribution, ...]:
        """Return stored attributions in the order of ``source_ids``.

        Sources without a stored attribution are silently skipped (per
        ``docs/requirements/sources.md`` §10 SRC-QUERY-010). The result
        is a tuple so callers can rely on deterministic iteration
        order regardless of the input ``source_ids`` container shape.
        """
        return tuple(
            attribution
            for source_id in source_ids
            if (attribution := self._attributions_by_slug.get(source_id.slug))
            is not None
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _matches(
    observation: NormalizedObservation,
    query: EvidenceQuery,
) -> NormalizedObservation | None:
    """Return ``observation`` if it matches ``query``; otherwise ``None``.

    A ``None`` filter value means "unfiltered"; an empty tuple ``()``
    means "no observations match that dimension" (natural membership
    semantics: no value can be a member of the empty set). The check
    is intentionally a single helper so the rules are documented in
    one place; the public ``query_observations`` method preserves the
    input observation order by iterating ``self._observations``
    linearly and dropping non-matching rows.
    """
    # ``source_ids``: match by ``SourceId.slug`` so callers that pass
    # freshly-built ``SourceId`` instances still hit the right rows.
    # ``leaders`` matches against either ``leader_id`` or
    # ``leader_name`` because leader identity is unstable across
    # sources today (per ``docs/requirements/sources.md`` §10
    # SRC-QUERY-008); when leader IDs stabilise, the slice can
    # tighten the match to ``leader_id`` only without breaking the
    # contract. ``years`` stored ``year=None`` (non-country-year
    # scope) never matches an explicit year filter. ``countries``
    # matches against either ``country_code`` or ``country_name``.
    matches = (
        query.source_ids is None
        or observation.source_id.slug in {
            source_id.slug for source_id in query.source_ids
        }
    ) and (
        query.observation_families is None
        or observation.observation_family in query.observation_families
    ) and (
        query.indicator_codes is None
        or observation.indicator_code in query.indicator_codes
    ) and (
        query.years is None
        or (
            observation.year is not None
            and observation.year in query.years
        )
    ) and (
        query.countries is None
        or observation.country_code in query.countries
        or observation.country_name in query.countries
    ) and (
        query.leaders is None
        or observation.leader_id in query.leaders
        or observation.leader_name in query.leaders
    )
    return observation if matches else None


__all__ = [
    "EvidenceRepository",
    "InMemoryEvidenceRepository",
]
