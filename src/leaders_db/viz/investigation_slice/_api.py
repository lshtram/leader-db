"""Public entry point and internal helpers for the investigation slice.

This module exposes :func:`run_investigation_slice`, which drives the
documented ``check_ready -> read_raw -> transform`` lifecycle for every
adapter registered in the supplied :class:`SourceRegistry`, flattens
the resulting :class:`NormalizedObservation` tuples, runs the semantic
concept catalog against the stream, and writes the chart-ready CSV +
dependency-free HTML+SVG graph. It also refreshes the read-only
Superset-facing SQLite artifact when requested.

Per-source helpers (canonical-question lookup, year expansion, default
registry builder, lifecycle driver, scope filter, Superset rebuild)
live alongside the public entry point because the orchestration is
small enough that splitting them further would only obscure the read
order. Concept-row counting and coverage-row finalisation live in
:mod:`._models` because they are tightly coupled to
:class:`SourceCoverageRow`.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from ...sources.concepts import (
    ConceptObservation,
    extract_concept_result,
)
from ...sources.contracts import (
    NormalizedObservation,
    SourceId,
    SourceIngestRequest,
    SourceWarning,
)
from ...sources.registry import (
    InMemorySourceRegistry,
)
from ...sources.runner import SourceIngestRunner
from ..superset_db import (
    build_superset_sqlite_db,
    default_superset_db_path,
    default_viz_data_dir,
)
from ._csv import write_concept_csv
from ._html import write_static_line_chart
from ._models import (
    SUPPORTED_QUESTIONS,
    InvestigationQuestion,
    InvestigationSliceRequest,
    InvestigationSliceResult,
    SourceCoverageRow,
    UnknownInvestigationQuestionError,
    concept_rows_by_source,
    finalize_coverage_rows,
)


def run_investigation_slice(
    request: InvestigationSliceRequest,
) -> InvestigationSliceResult:
    """Execute the constrained vertical slice for ``request``.

    The function is intentionally synchronous and pure with respect
    to global state: the only filesystem effects are the CSV, the
    HTML, and (when ``rebuild_superset_db`` is true) the Superset
    SQLite artifact. The slice never imports ``leaders_db.ingest``
    directly -- it talks to source adapters exclusively through the
    registered :class:`SourceRegistry` seam.

    Each registered adapter is driven through the documented
    ``check_ready -> read_raw -> transform`` lifecycle. A not-ready
    adapter is reported as a coverage gap and the slice continues
    with the remaining adapters; a runtime failure inside
    ``read_raw`` or ``transform`` propagates so the slice's caller
    can see real source-side bugs rather than have them hidden as a
    coverage gap.

    Raises
    ------
    UnknownInvestigationQuestionError
        ``request.question_key`` is not in :data:`SUPPORTED_QUESTIONS`.
    RuntimeError
        The slice completed but extracted zero concept rows for the
        requested scope. This is treated as a hard failure so a
        silently-empty artefact never ships.
    """
    question = _resolve_question(request.question_key)
    years = _expand_years(request.start_year, request.end_year)

    registry = request.registry
    runner = request.runner
    owns_registry = registry is None
    owns_runner = runner is None
    if registry is None:
        registry = _build_default_registry()
    if runner is None:
        runner = SourceIngestRunner(registry=registry)

    source_ids = tuple(
        descriptor.source_id for descriptor in registry.list_descriptors()
    )

    raw_root = Path(request.raw_root)
    raw_root.mkdir(parents=True, exist_ok=True)

    data_dir = (
        Path(request.data_dir)
        if request.data_dir is not None
        else default_viz_data_dir()
    )
    data_dir.mkdir(parents=True, exist_ok=True)

    all_observations: list[NormalizedObservation] = []
    coverage_rows: list[SourceCoverageRow] = []

    for source_id in source_ids:
        coverage, observations = _run_one_source(
            runner=runner,
            source_id=source_id,
            countries=request.countries,
            years=years,
            raw_root=raw_root,
        )
        coverage_rows.append(coverage)
        all_observations.extend(observations)

    extraction = extract_concept_result(
        tuple(all_observations),
        question.concept_key,
    )
    concept_rows = tuple(
        _filter_concept_rows(
            extraction.observations,
            countries=request.countries,
            start_year=request.start_year,
            end_year=request.end_year,
        )
    )
    concept_warnings: list[SourceWarning] = list(extraction.warnings)

    # Fill each coverage row's ``concept_rows`` with the actual number
    # of concept rows that came from this source inside the requested
    # scope. The per-source dispatcher cannot know this count -- it
    # only sees the raw NormalizedObservation stream -- so the caller
    # owns the count. Without this pass, ``concept_rows`` would always
    # be 0 and the per-source coverage summary would lie.
    per_source_counts = concept_rows_by_source(concept_rows)
    finalized_coverage_rows = finalize_coverage_rows(
        coverage_rows,
        per_source_counts,
    )

    if not concept_rows:
        # Surface coverage so a developer can see why nothing came
        # back; then raise so the empty CSV never silently ships.
        coverage_summary = ", ".join(
            f"{row.source_id}={row.emitted}/{row.requested}" for row in finalized_coverage_rows
        )
        raise RuntimeError(
            f"Investigation slice for question "
            f"{request.question_key!r} produced zero concept rows "
            f"for the requested scope "
            f"(countries={request.countries}, "
            f"years={request.start_year}-{request.end_year}). "
            f"Source coverage: {coverage_summary}. "
            f"Warnings: {len(concept_warnings)}."
        )

    csv_path = data_dir / f"viz_investigation_{request.question_key}.csv"
    write_concept_csv(
        csv_path,
        concept_rows,
        question_key=request.question_key,
    )

    html_path = data_dir / f"viz_investigation_{request.question_key}.html"
    write_static_line_chart(
        html_path=html_path,
        title=question.display_title,
        concept_rows=concept_rows,
        countries=request.countries,
    )

    superset_db_path, superset_tables = _maybe_rebuild_superset_db(
        request=request,
        data_dir=data_dir,
    )

    # Help garbage-collector-friendly teardown when the slice built
    # its own registry / runner (mostly relevant for tests).
    del runner
    if owns_runner and owns_registry:
        del registry

    return InvestigationSliceResult(
        question=question,
        countries=request.countries,
        start_year=request.start_year,
        end_year=request.end_year,
        csv_path=csv_path,
        html_path=html_path,
        concept_rows=concept_rows,
        source_coverage=finalized_coverage_rows,
        concept_warnings=tuple(concept_warnings),
        superset_db_path=superset_db_path,
        superset_db_tables=superset_tables,
    )


def _maybe_rebuild_superset_db(
    *,
    request: InvestigationSliceRequest,
    data_dir: Path,
) -> tuple[Path | None, tuple[str, ...]]:
    """Rebuild the read-only Superset SQLite artifact when conditions allow.

    ``build_superset_sqlite_db`` requires the canonical core CSV to
    be present (it is marked required in ``VIZ_CSV_TABLES``); when
    the slice runs against an empty data directory the assertion
    would fail. The slice is a proof flow, not a replacement for the
    chronicle builder; when the core CSV is absent we skip the
    Superset rebuild and surface the skip in the result so callers
    can decide.
    """
    if not request.rebuild_superset_db:
        return None, ()
    db_output = (
        Path(request.superset_db_path)
        if request.superset_db_path is not None
        else default_superset_db_path(data_dir)
    )
    core_csv = data_dir / "viz_country_year_metrics.csv"
    if not core_csv.is_file():
        return None, ()
    build = build_superset_sqlite_db(
        data_dir=data_dir,
        output_path=db_output,
    )
    return build.output_path, build.tables_written


def _resolve_question(question_key: str) -> InvestigationQuestion:
    """Return the canonical :class:`InvestigationQuestion` for ``question_key``."""
    if question_key not in SUPPORTED_QUESTIONS:
        raise UnknownInvestigationQuestionError(question_key)
    return SUPPORTED_QUESTIONS[question_key]


def _expand_years(start_year: int, end_year: int) -> tuple[int, ...]:
    """Return the inclusive ``(start, ..., end)`` integer range as a tuple."""
    if end_year < start_year:
        raise ValueError(
            f"end_year ({end_year}) must be >= start_year ({start_year})"
        )
    return tuple(range(start_year, end_year + 1))


def _build_default_registry() -> InMemorySourceRegistry:
    """Register the default source set for the vertical slice.

    The default set covers the three sources the concept catalog
    documents for ``gdp_per_capita``: WDI (current USD + PPP constant
    2017), Maddison Project Database 2023 (2011 intl $), and PWT 10.01
    (derived via real GDP output side / population). WGI and V-Dem do
    not currently map to ``gdp_per_capita`` per the concept catalog
    and are therefore omitted.
    """
    registry = InMemorySourceRegistry()
    try:
        from ...sources.adapters.maddison_project import (
            register_maddison_project,
        )
        from ...sources.adapters.pwt import register_pwt
        from ...sources.adapters.world_bank_wdi import (
            register_world_bank_wdi,
        )
    except ImportError as exc:  # pragma: no cover -- defensive guard
        raise RuntimeError(
            "Failed to import default source adapters; the unified "
            "source subsystem is required for the investigation "
            "slice."
        ) from exc

    register_pwt(registry)
    register_maddison_project(registry)
    register_world_bank_wdi(registry)
    return registry


def _run_one_source(
    *,
    runner: SourceIngestRunner,
    source_id: SourceId,
    countries: Sequence[str],
    years: Sequence[int],
    raw_root: Path,
) -> tuple[SourceCoverageRow, tuple[NormalizedObservation, ...]]:
    """Run a single source through the registry and return coverage + observations.

    The function uses :attr:`SourceIngestRunner.registry` (the same
    seam :class:`SourceIngestRunner` uses internally) to resolve the
    adapter and drive the documented ``check_ready -> read_raw ->
    transform`` lifecycle. The flow is intentionally split instead of
    using :meth:`SourceIngestRunner.run` so the slice can distinguish:

    - A structured "not ready" outcome (``check_ready`` returned
      ``ready=False``): surfaced as a coverage gap with the readiness
      warnings attached. This is a normal source-bundle gap.
    - A runtime failure from ``read_raw`` or ``transform``: a real
      source-side bug. These exceptions propagate so the slice's
      caller sees the failure rather than having it silently logged
      as a coverage gap.
    """
    request = SourceIngestRequest(
        source_id=source_id,
        years=tuple(years),
        countries=tuple(countries),
        raw_root=raw_root,
    )
    requested_scope = len(countries) * len(years)
    warning_messages: list[str] = []

    adapter = runner.registry.get_adapter(source_id)
    readiness = adapter.check_ready(request)
    if not readiness.ready:
        for warning in readiness.warnings:
            warning_messages.append(warning.message)
        for warning in readiness.errors:
            warning_messages.append(warning.message)
        return (
            SourceCoverageRow(
                source_id=source_id.slug,
                requested=requested_scope,
                emitted=0,
                concept_rows=0,  # filled by caller after concept extraction
                readiness_ready=False,
                warnings=tuple(warning_messages),
            ),
            (),
        )

    # Ready -- drive the read/transform lifecycle. Any exception
    # (including ``RuntimeError``) raised inside ``read_raw`` or
    # ``transform`` is a bug, not a coverage gap, and MUST propagate
    # so the slice's caller sees the failure rather than having it
    # silently logged as a readiness gap.
    raw = adapter.read_raw(request)
    observations = tuple(adapter.transform(request, raw))
    for warning in readiness.warnings:
        warning_messages.append(warning.message)
    for warning in readiness.errors:
        warning_messages.append(warning.message)
    for warning in raw.warnings:
        warning_messages.append(warning.message)
    return (
        SourceCoverageRow(
            source_id=source_id.slug,
            requested=requested_scope,
            emitted=len(observations),
            concept_rows=0,  # filled by caller after concept extraction
            readiness_ready=True,
            warnings=tuple(warning_messages),
        ),
        observations,
    )


def _filter_concept_rows(
    observations: Iterable[ConceptObservation],
    *,
    countries: Sequence[str],
    start_year: int,
    end_year: int,
) -> Iterable[ConceptObservation]:
    """Yield concept rows whose ``(country, year)`` is in the requested scope.

    Concept rows whose country/year are outside the slice scope are
    dropped here rather than at extraction time so the concept
    catalog stays a pure transformation over the provided
    observations. The dropped rows are NOT surfaced as warnings
    because the slice explicitly requests the narrower scope via
    the request's ``countries`` and ``years``; the catalog has no
    way to know the request scope.
    """
    country_set = set(countries)
    for row in observations:
        if row.country_code is None or row.country_code not in country_set:
            continue
        if row.year is None:
            continue
        if row.year < start_year or row.year > end_year:
            continue
        yield row


__all__ = [
    "run_investigation_slice",
]
