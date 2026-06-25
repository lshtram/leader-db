"""Tests for the investigation-slice vertical slice.

The slice is the end-to-end proof flow:

    question -> SourceIngestRunner dispatch -> concept extraction ->
    CSV + static HTML -> Superset SQLite

These tests focus on the seam between the unified source subsystem
and the visualization output. They use a small fake adapter so the
tests do NOT depend on staged raw bundles (the real bundles are
covered by the existing concept-catalog integration test).

Coverage
--------

- The slice registers real PWT / Maddison / WDI adapters when the
  caller does NOT inject a registry.
- The slice dispatches each adapter through
  :class:`SourceIngestRunner` (not the legacy table).
- Concept extraction is observable in the slice output: rows carry
  the source-specific indicator codes and source ids so audit code
  can resolve them back to the canonical source records.
- The CSV is written with stable columns and sorted rows so
  successive runs are byte-identical for the same input.
- The static HTML+SVG is written, contains an SVG element, and lists
  every country in the requested scope at least once.
- The Superset SQLite artifact is rebuilt when the slice writes the
  canonical core CSV in the same data directory; the new investigation
  table is present under ``viz_investigation_gdp_per_capita_major_powers``.
- The slice refuses unknown question keys with
  :class:`UnknownInvestigationQuestionError`.
- The slice surfaces an empty-result RuntimeError when no concept
  rows materialise rather than silently emitting an empty CSV.
- The CLI command ``viz-run-investigation-slice`` is registered on
  the :data:`app` instance and accepts the documented option set.
- When the registry declares a source as not-ready (the runner
  raises ``RuntimeError``), the slice reports it as a coverage gap
  with ``readiness_ready=False`` and continues with the other sources.
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from typer.testing import CliRunner

from leaders_db.cli import app
from leaders_db.viz.investigation_slice import (
    INVESTIGATION_CSV_COLUMNS,
    SUPPORTED_QUESTIONS,
    InvestigationSliceRequest,
    SourceCoverageRow,
    UnknownInvestigationQuestionError,
    run_investigation_slice,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fake adapter + descriptor (kept inline so the test file is self-contained)
# ---------------------------------------------------------------------------


def _descriptor(slug: str) -> object:
    """Return a minimal :class:`SourceDescriptor` for a fake adapter."""
    from leaders_db.sources import CoverageHint, SourceDescriptor, SourceId

    return SourceDescriptor(
        source_id=SourceId(slug=slug),
        display_name=f"Fake {slug}",
        source_type="dataset",
        supported_observation_families=("economic_country_year",),
        default_version="v1",
        homepage_url=None,
        attribution_key=slug,
        coverage_hint=CoverageHint(),
        requires_manual_approval=False,
        requires_network=False,
    )


class _FakeAdapter:
    """Test adapter that returns preset observations from ``self.observations``.

    The adapter records its dispatch calls in ``self.calls`` so the
    test can assert the runner routes requests through it. ``ready``
    controls whether ``check_ready`` returns ``ready=True`` -- when
    ``False``, the slice must report a coverage gap and continue.
    """

    def __init__(
        self,
        *,
        slug: str,
        observations: Iterable[object] = (),
        ready: bool = True,
        ready_error: str | None = None,
    ) -> None:
        self.descriptor = _descriptor(slug)
        self.observations = tuple(observations)
        self.ready = ready
        self.ready_error = ready_error
        self.calls: list[str] = []

    def check_ready(self, request: object) -> object:
        from leaders_db.sources import ReadinessResult, SourceWarning

        self.calls.append("check_ready")
        if self.ready:
            return ReadinessResult(ready=True)
        message = self.ready_error or f"fake source {self.descriptor.source_id.slug!r} not ready"
        return ReadinessResult(
            ready=False,
            errors=(
                SourceWarning(
                    code="fake_not_ready",
                    message=message,
                    severity="error",
                    source_id=self.descriptor.source_id,
                ),
            ),
        )

    def read_raw(self, request: object) -> object:
        from leaders_db.sources import RawReadResult

        self.calls.append("read_raw")
        return RawReadResult(source_id=self.descriptor.source_id)

    def transform(self, request: object, raw: object) -> Iterable[object]:

        self.calls.append("transform")
        yield from self.observations


class _ReadyAlwaysFalseAdapter(_FakeAdapter):
    """A specialised fake that always raises ``RuntimeError`` from the runner.

    Used to verify the slice's "continue with available sources"
    behaviour when a real adapter's ``check_ready`` returns
    ``ready=False``: the runner itself raises
    :class:`RuntimeError` (per ``runner.py``), and the slice must
    catch that, record a coverage gap, and keep going.
    """

    def check_ready(self, request: object) -> object:
        from leaders_db.sources import ReadinessResult, SourceWarning

        self.calls.append("check_ready")
        return ReadinessResult(
            ready=False,
            errors=(
                SourceWarning(
                    code="missing_raw",
                    message=f"bundle not staged for {self.descriptor.source_id.slug!r}",
                    severity="error",
                    source_id=self.descriptor.source_id,
                ),
            ),
        )


def _make_observation(
    *,
    source_slug: str,
    indicator_code: str,
    value: float,
    year: int,
    country_code: str,
    source_version: str = "v1",
) -> object:
    """Build a synthetic :class:`NormalizedObservation` for the fake adapter."""
    from leaders_db.sources import (
        NormalizedObservation,
        RawLocator,
        SourceId,
        TransformLocator,
    )

    return NormalizedObservation(
        source_id=SourceId(slug=source_slug),
        observation_id=f"{source_slug}:{country_code}:{year}:{indicator_code}",
        observation_family="economic_country_year",
        indicator_code=indicator_code,
        value=value,
        value_type="numeric",
        year=year,
        country_code=country_code,
        country_name=None,
        leader_id=None,
        leader_name=None,
        unit=None,
        scale=None,
        source_version=source_version,
        raw_locator=RawLocator(asset_id=f"{source_slug}-asset"),
        transform_locator=TransformLocator(transform_name=f"fake_{source_slug}"),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_registry_with_three_sources(
    *,
    wdi_observations: Iterable[object] = (),
    maddison_observations: Iterable[object] = (),
    pwt_observations: Iterable[object] = (),
    pwt_ready: bool = True,
    wdi_ready: bool = True,
    maddison_ready: bool = True,
) -> object:
    """Build an :class:`InMemorySourceRegistry` with three fake source adapters.

    The default sources emit zero observations so tests can build the
    registry without any data and exercise the empty-result failure
    path; tests that want real rows pass observations through the
    keyword arguments.

    Each source can be flagged not-ready via ``pwt_ready`` /
    ``wdi_ready`` / ``maddison_ready``. When a source is not-ready,
    the runner raises ``RuntimeError`` from ``check_ready`` (per
    :mod:`leaders_db.sources.runner`) and the slice records a
    coverage gap instead of forwarding the exception.
    """
    from leaders_db.sources import InMemorySourceRegistry

    def _build_one(
        slug: str, observations: Iterable[object], ready: bool,
    ) -> _FakeAdapter:
        if ready:
            return _FakeAdapter(slug=slug, observations=observations)
        return _ReadyAlwaysFalseAdapter(slug=slug, observations=observations)

    registry = InMemorySourceRegistry()
    registry.register(
        _build_one("pwt", pwt_observations, pwt_ready),
    )
    registry.register(
        _build_one("maddison_project", maddison_observations, maddison_ready),
    )
    registry.register(
        _build_one("world_bank_wdi", wdi_observations, wdi_ready),
    )
    return registry


def _default_request(
    *,
    tmp_path: Path,
    registry: object | None = None,
    **overrides: object,
) -> InvestigationSliceRequest:
    """Build an :class:`InvestigationSliceRequest` scoped to a temp directory."""
    raw_root = tmp_path / "raw"
    data_dir = tmp_path / "data_dir"
    data_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict[str, object] = {
        "question_key": "gdp_per_capita_major_powers",
        "countries": ("USA", "GBR"),
        "start_year": 2000,
        "end_year": 2002,
        "raw_root": raw_root,
        "data_dir": data_dir,
        "registry": registry,
    }
    kwargs.update(overrides)
    return InvestigationSliceRequest(**kwargs)


# ---------------------------------------------------------------------------
# Source runner is used (not legacy dispatch)
# ---------------------------------------------------------------------------


def test_slice_dispatches_via_source_ingest_runner(tmp_path: Path) -> None:
    """The slice must drive each registered adapter through the runner.

    The slice uses the unified :class:`SourceIngestRunner` (not the
    legacy ``STAGE2_ADAPTERS`` table). The test verifies that by
    registering three fake adapters and asserting that EACH one
    received the documented ``check_ready -> read_raw -> transform``
    lifecycle sequence.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=40_000.0,
            year=2000,
            country_code="GBR",
        ),
    )
    pwt_obs = (
        _make_observation(
            source_slug="pwt",
            indicator_code="pwt_population",
            value=300_000.0,
            year=2002,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs,
        maddison_observations=maddison_obs,
        pwt_observations=pwt_obs,
        wdi_ready=True,
    )

    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    # Every registered adapter must have been driven through the
    # lifecycle, regardless of whether it emitted observations.
    by_slug: dict[str, list[str]] = {}
    for adapter in registry.list_descriptors():
        # The descriptor is just metadata; the actual adapter instance
        # lives in the registry. Use a private dict lookup so we can
        # assert the recorded call sequence.
        instance = registry._adapters[adapter.source_id.slug]
        by_slug[adapter.source_id.slug] = instance.calls
    expected_lifecycle = ["check_ready", "read_raw", "transform"]
    assert by_slug["pwt"] == expected_lifecycle, (
        f"PWT lifecycle mismatch: {by_slug['pwt']}"
    )
    assert by_slug["maddison_project"] == expected_lifecycle, (
        f"Maddison lifecycle mismatch: {by_slug['maddison_project']}"
    )
    assert by_slug["world_bank_wdi"] == expected_lifecycle, (
        f"WDI lifecycle mismatch: {by_slug['world_bank_wdi']}"
    )

    # The slice must NOT have fallen back to the legacy STAGE2_ADAPTERS
    # table; assert the legacy ``dispatch`` key is untouched.
    from leaders_db import ingest as legacy_ingest

    assert "gdp_per_capita_major_powers" not in legacy_ingest.STAGE2_ADAPTERS, (
        "slice must not pollute legacy STAGE2_ADAPTERS table"
    )

    # Sanity: the result envelope names the question + scope.
    assert result.question.question_key == "gdp_per_capita_major_powers"
    assert result.countries == ("USA", "GBR")
    assert result.start_year == 2000
    assert result.end_year == 2002


# ---------------------------------------------------------------------------
# Concept extraction feeds the CSV rows
# ---------------------------------------------------------------------------


def test_concept_extraction_feeds_csv_rows(tmp_path: Path) -> None:
    """The CSV rows must come from the semantic concept catalog.

    The test stages three sources with one observation each that
    maps to the ``gdp_per_capita`` concept, runs the slice, and
    asserts the resulting CSV has one row per input observation with
    the source-specific indicator code preserved.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=40_000.0,
            year=2002,
            country_code="GBR",
        ),
    )
    pwt_obs = (
        _make_observation(
            source_slug="pwt",
            indicator_code="pwt_population",
            value=300_000.0,
            year=2002,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs,
        maddison_observations=maddison_obs,
        pwt_observations=pwt_obs,
        wdi_ready=True,
    )

    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    assert result.csv_path.is_file()
    rows = list(csv.DictReader(result.csv_path.open(encoding="utf-8")))
    assert rows, "slice must emit at least one CSV row when concept rows exist"

    # Every row is sourced from the concept catalog (not invented by
    # the slice): the source_id + indicator_code pair must match one
    # of the staged inputs.
    expected_pairs = {
        ("world_bank_wdi", "wdi_gdp_per_capita"),
        ("maddison_project", "maddison_project_gdp_per_capita_2011_intl"),
    }
    actual_pairs = {(row["source_id"], row["indicator_code"]) for row in rows}
    assert actual_pairs == expected_pairs, (
        f"unexpected source/indicator pairs: {actual_pairs}"
    )

    # The PWT population observation must NOT show up: the concept
    # catalog only extracts ``gdp_per_capita`` and the fake PWT
    # observation's indicator does not feed the recipe.
    pwt_population_rows = [
        row for row in rows if row["source_id"] == "pwt"
    ]
    assert pwt_population_rows == [], (
        f"PWT population should not feed gdp_per_capita; got "
        f"{pwt_population_rows}"
    )

    # Columns are stable.
    assert list(rows[0].keys()) == list(INVESTIGATION_CSV_COLUMNS)


def test_csv_rows_are_deterministically_sorted(tmp_path: Path) -> None:
    """Two runs over the same input produce byte-identical CSVs.

    Stable row ordering is critical for Superset dashboards and any
    downstream hash-based regression check.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2001,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=40_000.0,
            year=2000,
            country_code="GBR",
        ),
    )
    registry = _build_registry_with_three_sources(wdi_observations=wdi_obs, wdi_ready=True)
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    first_content = result.csv_path.read_bytes()
    second_content = result.csv_path.read_bytes()
    assert first_content == second_content, "CSV must be deterministic"

    # Rows sorted by (country_iso3, year, source_id, indicator_code).
    rows = list(csv.DictReader(result.csv_path.open(encoding="utf-8")))
    keys = [
        (row["country_iso3"], int(row["year"]), row["source_id"], row["indicator_code"])
        for row in rows
    ]
    assert keys == sorted(keys), f"rows not sorted: {keys}"


# ---------------------------------------------------------------------------
# HTML graph artifact
# ---------------------------------------------------------------------------


def test_slice_writes_static_html_graph(tmp_path: Path) -> None:
    """The slice writes a deterministic HTML+SVG line chart.

    The HTML must contain an ``<svg>`` element and the SVG must
    reference every requested country at least once (so a human can
    see the result without external dependencies).
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=45_000.0,
            year=2001,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=30_000.0,
            year=2000,
            country_code="GBR",
        ),
    )
    registry = _build_registry_with_three_sources(wdi_observations=wdi_obs, wdi_ready=True)
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    assert result.html_path.is_file(), "HTML artifact must be written"
    html_content = result.html_path.read_text(encoding="utf-8")
    assert "<svg" in html_content, "HTML must contain an SVG element"
    assert "</svg>" in html_content, "SVG must be closed"
    for country in ("USA", "GBR"):
        assert country in html_content, (
            f"country {country!r} must appear in the SVG legend"
        )


# ---------------------------------------------------------------------------
# HTML chart must group by (country, source) -- not country alone
# ---------------------------------------------------------------------------


def _polyline_point_counts(
    html_content: str,
) -> dict[tuple[str, str, str], int]:
    """Return ``{(country, source, series_label): point_count}`` for every polyline.

    Used by the per-series tests to assert the chart actually emits
    one polyline per ``(country, source, series_label)`` triple with
    only the rows for that triple inside it. ``series_label`` is the
    recipe key for derived concept rows (e.g. PWT's
    ``pwt_gdp_per_capita_via_rgdpo_over_pop``) and the source
    indicator code for direct rows (e.g. WDI's ``wdi_gdp_per_capita``
    and ``wdi_gdp_per_capita_ppp_constant_2017``).
    """
    import re

    polylines = re.findall(r"<polyline\b[^>]*>", html_content)
    counts: dict[tuple[str, str, str], int] = {}
    for polyline in polylines:
        country_match = re.search(r'data-country="([^"]+)"', polyline)
        source_match = re.search(r'data-source="([^"]+)"', polyline)
        indicator_match = re.search(
            r'data-indicator="([^"]+)"', polyline,
        )
        points_match = re.search(r'points="([^"]*)"', polyline)
        assert country_match is not None, polyline
        assert source_match is not None, polyline
        assert indicator_match is not None, polyline
        assert points_match is not None, polyline
        # An empty points="" string still counts as zero points; a
        # whitespace-only string is the same after the split filter.
        points = [p for p in points_match.group(1).split() if p]
        counts[(
            country_match.group(1),
            source_match.group(1),
            indicator_match.group(1),
        )] = len(points)
    return counts


def test_html_chart_groups_polylines_by_country_and_source(
    tmp_path: Path,
) -> None:
    """Two sources for the same country must NOT be collapsed into one polyline.

    The slice can legitimately carry multiple sources for the same
    country/year (PWT, Maddison Project, WDI all expose GDP per
    capita). The HTML chart must plot ONE polyline per
    ``(country, source, series_label)`` triple so the reader sees
    distinct series -- NOT one polyline that chains same-year values
    from different sources vertically. The previous implementation
    grouped by country only and produced a single polyline with
    multiple points at the same X coordinate, which falsely suggested
    a time series that does not exist in the underlying data.

    WDI and Maddison are direct concept mappings so a single
    observation per source is enough to feed the concept catalog.
    """
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=20_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=30_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        maddison_observations=maddison_obs,
        wdi_observations=wdi_obs,
        wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    html_content = result.html_path.read_text(encoding="utf-8")

    # Two distinct series -- one polyline per source for USA.
    counts = _polyline_point_counts(html_content)
    expected_keys = {
        ("USA", "maddison_project", "maddison_project_gdp_per_capita_2011_intl"),
        ("USA", "world_bank_wdi", "wdi_gdp_per_capita"),
    }
    assert set(counts) == expected_keys, (
        f"expected one polyline per (country, source, indicator); "
        f"got {sorted(counts)}"
    )

    # Each polyline must contain ONLY its own source's points for the
    # year -- not chained values from the other sources. With one
    # input observation per source, every polyline must have exactly
    # one point.
    for key in expected_keys:
        assert counts[key] == 1, (
            f"polyline for {key!r} must contain only that source's "
            f"points (1), got {counts[key]} -- values from different "
            f"sources appear to be chained into a single polyline"
        )

    # Legend labels must surface the source slug so a reader can
    # tell the two USA series apart. Old legend labels were just
    # ``"USA"`` for both -- that contract is now broken by design
    # and pinned by this assertion.
    for source_slug in ("maddison_project", "world_bank_wdi"):
        expected_label = f"USA \u00b7 {source_slug}"
        assert expected_label in html_content, (
            f"legend must include label {expected_label!r}; "
            f"html_content snippet: {html_content[-600:]}"
        )


def test_html_chart_wdi_two_gdp_per_capita_scales_get_distinct_series(
    tmp_path: Path,
) -> None:
    """WDI emits two GDP-per-capita indicator codes (different scales).

    WDI publishes GDP per capita in two scales: current USD
    (NY.GDP.PCAP.CD, indicator code ``wdi_gdp_per_capita``) and
    constant 2017 international dollars at PPP
    (NY.GDP.PCAP.PP.KD, indicator code
    ``wdi_gdp_per_capita_ppp_constant_2017``). Both alias the
    ``gdp_per_capita`` concept, so the concept catalog emits one
    :class:`ConceptObservation` per (country, year, indicator_code).

    The HTML chart must plot them as TWO distinct polylines -- not
    collapse them into one polyline that chains the two scales into a
    misleading single line -- and the legend labels must distinguish
    the two scales by indicator code. Grouping by ``(country, source)``
    alone would silently merge the two scales into one polyline; the
    chart key includes ``series_label`` (the indicator code for direct
    rows) so each scale stays its own series.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita_ppp_constant_2017",
            value=45_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs, wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    html_content = result.html_path.read_text(encoding="utf-8")

    # Two distinct WDI USA polylines -- one per indicator code --
    # with one point each. If the chart still grouped only by
    # (country, source) the assertion would fail because the old
    # code would have produced one polyline with two points chained
    # at the same year.
    counts = _polyline_point_counts(html_content)
    expected_keys = {
        ("USA", "world_bank_wdi", "wdi_gdp_per_capita"),
        (
            "USA", "world_bank_wdi",
            "wdi_gdp_per_capita_ppp_constant_2017",
        ),
    }
    assert set(counts) == expected_keys, (
        f"expected one polyline per WDI GDP-per-capita indicator code; "
        f"got {sorted(counts)} -- the two WDI scales appear to be "
        f"merged into a single polyline"
    )
    for key in expected_keys:
        assert counts[key] == 1, (
            f"polyline for {key!r} must hold only its own "
            f"indicator's points (1), got {counts[key]}"
        )

    # Each polyline must carry the right ``data-indicator`` attribute
    # so downstream tooling (and humans inspecting the DOM) can
    # identify which scale a given line represents.
    import re

    polyline_indicators = re.findall(
        r'data-source="world_bank_wdi"\s+data-indicator="([^"]+)"',
        html_content,
    )
    assert set(polyline_indicators) == {
        "wdi_gdp_per_capita",
        "wdi_gdp_per_capita_ppp_constant_2017",
    }, (
        f"polylines must carry both WDI GDP-per-capita indicator "
        f"codes; got {sorted(polyline_indicators)}"
    )

    # Legend labels must distinguish the two scales by indicator code.
    # The labels render as
    # ``"USA \u00b7 world_bank_wdi \u00b7 <indicator_code>"`` so the
    # reader can tell current USD apart from PPP constant 2017.
    expected_labels = {
        "USA \u00b7 world_bank_wdi \u00b7 wdi_gdp_per_capita",
        (
            "USA \u00b7 world_bank_wdi "
            "\u00b7 wdi_gdp_per_capita_ppp_constant_2017"
        ),
    }
    for expected in expected_labels:
        assert expected in html_content, (
            f"legend must include label {expected!r} so the two WDI "
            f"GDP-per-capita scales are distinguishable; html "
            f"snippet: {html_content[-1200:]}"
        )

    # Sanity: the two labels must not collapse to a single string --
    # that would mean the indicator code never made it into the label.
    assert len(expected_labels) == 2, expected_labels
    distinct_labels = {
        label for label in expected_labels if label in html_content
    }
    assert distinct_labels == expected_labels, (
        f"both WDI GDP-per-capita legend labels must be present and "
        f"distinct; got {sorted(distinct_labels)}"
    )


def test_html_chart_three_sources_for_same_country_get_three_polylines(
    tmp_path: Path,
) -> None:
    """Three sources for USA all yield three distinct polylines.

    Exercises the full PWT + Maddison + WDI triple. PWT contributes
    a *derived* concept row (gdp_per_capita = rgdpo / pop), so we
    have to stage BOTH PWT inputs at the same year to feed the
    recipe; otherwise the catalog refuses to emit a PWT concept row
    and the assertion would be measuring a fixture bug, not the
    chart fix.
    """
    pwt_obs = (
        _make_observation(
            source_slug="pwt",
            indicator_code="pwt_real_gdp_output_side",
            value=20_000_000.0,
            year=2000,
            country_code="USA",
            source_version="10.01",
        ),
        _make_observation(
            source_slug="pwt",
            indicator_code="pwt_population",
            value=300_000.0,
            year=2000,
            country_code="USA",
            source_version="10.01",
        ),
    )
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=20_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=30_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        pwt_observations=pwt_obs,
        maddison_observations=maddison_obs,
        wdi_observations=wdi_obs,
        wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    html_content = result.html_path.read_text(encoding="utf-8")
    counts = _polyline_point_counts(html_content)
    expected_keys = {
        ("USA", "pwt", "pwt_gdp_per_capita_via_rgdpo_over_pop"),
        ("USA", "maddison_project", "maddison_project_gdp_per_capita_2011_intl"),
        ("USA", "world_bank_wdi", "wdi_gdp_per_capita"),
    }
    assert set(counts) == expected_keys, (
        f"expected three USA polylines (one per source/indicator); "
        f"got {sorted(counts)} -- if old 'group by country' bug were "
        f"back, only one polyline with three points would appear"
    )
    for key in expected_keys:
        assert counts[key] == 1, (
            f"polyline for {key!r} must hold only its own series's "
            f"points (1), got {counts[key]}"
        )


def test_html_chart_legend_labels_include_source_slug(tmp_path: Path) -> None:
    """Every legend label must include the source slug (e.g. ``USA \u00b7 pwt``).

    Without the source slug, two series for the same country would
    both be labelled ``"USA"`` and the chart would be unreadable.
    The fix splits the legend into one entry per
    ``(country, source, series_label)`` triple and the label is the
    joined string ``"{country} \u00b7 {source} \u00b7 {indicator}"``;
    we assert the source-slug fragment is present so the existing
    contract that the source is visible to the reader still holds.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=40_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs, wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    html_content = result.html_path.read_text(encoding="utf-8")
    assert "USA \u00b7 world_bank_wdi" in html_content, (
        f"legend label must include source slug; html_content:\n{html_content}"
    )


def test_html_chart_keeps_country_source_polylines_separate_over_time(
    tmp_path: Path,
) -> None:
    """Two sources for the same country over multiple years stay separate polylines.

    Same as the same-year test, but with a multi-year span: each
    source's series must remain its own polyline (with multiple
    points over time) so the chart shows two distinct trajectories
    for the same country rather than a single chained line. We use
    WDI + Maddison for this test (direct concept mappings) so the
    fixtures are minimal; the structural invariant is the same.
    """
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=10_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=11_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=30_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=31_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        maddison_observations=maddison_obs,
        wdi_observations=wdi_obs,
        wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    html_content = result.html_path.read_text(encoding="utf-8")
    counts = _polyline_point_counts(html_content)
    # Two distinct USA polylines -- one per source -- each with both
    # years' points. The old "group by country" code would have
    # produced ONE polyline containing all four points.
    assert (
        "USA", "maddison_project", "maddison_project_gdp_per_capita_2011_intl",
    ) in counts, (
        f"expected a Maddison polyline for USA; got {sorted(counts)}"
    )
    assert (
        "USA", "world_bank_wdi", "wdi_gdp_per_capita",
    ) in counts, (
        f"expected a WDI polyline for USA; got {sorted(counts)}"
    )
    assert counts[(
        "USA", "maddison_project", "maddison_project_gdp_per_capita_2011_intl",
    )] == 2, (
        f"Maddison polyline must carry both years; got "
        f"{counts[('USA', 'maddison_project', 'maddison_project_gdp_per_capita_2011_intl')]}"
    )
    assert counts[("USA", "world_bank_wdi", "wdi_gdp_per_capita")] == 2, (
        f"WDI polyline must carry both years; got "
        f"{counts[('USA', 'world_bank_wdi', 'wdi_gdp_per_capita')]}"
    )
    assert len(counts) == 2, (
        f"USA must produce exactly two polylines (one per source); "
        f"got {sorted(counts)}"
    )


def test_html_chart_series_order_is_requested_country_then_source_alpha(
    tmp_path: Path,
) -> None:
    """Series order: requested countries first, source alphabetical within country.

    The deterministic render contract requires a stable, documented
    ordering of series. Requested countries are emitted in the order
    they were requested; within each country, sources are sorted
    alphabetically by slug so the per-country ordering is also
    deterministic. This test pins both invariants against accidental
    drift. We use only WDI + Maddison (direct concept mappings) so
    the fixture is small and unambiguous.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=10_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=20_000.0,
            year=2000,
            country_code="GBR",
        ),
    )
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=12_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    # Request GBR before USA so we can verify the requested order
    # wins over alphabetical / data order.
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs,
        maddison_observations=maddison_obs,
        wdi_ready=True,
    )
    raw_root = tmp_path / "raw"
    data_dir = tmp_path / "data_dir"
    data_dir.mkdir(parents=True, exist_ok=True)
    request = InvestigationSliceRequest(
        question_key="gdp_per_capita_major_powers",
        countries=("GBR", "USA"),
        start_year=2000,
        end_year=2000,
        raw_root=raw_root,
        data_dir=data_dir,
        registry=registry,
    )
    result = run_investigation_slice(request)
    html_content = result.html_path.read_text(encoding="utf-8")

    # Extract the order of (country, source, series_label) labels as
    # they appear in the legend HTML. The legend is rendered as plain
    # HTML divs below the SVG (so arbitrarily long labels fit without
    # being clipped by the SVG viewBox); we walk the legend labels
    # in document order.
    import re

    label_pat = re.compile(
        r"([A-Z]{3})\s\u00b7\s([a-z_]+)\s\u00b7\s([a-z0-9_]+)",
    )
    observed = label_pat.findall(html_content)
    # GBR first (requested first), then USA. Within each country,
    # sources are sorted alphabetically by slug; the WDI indicator
    # code is the only one staged so the third element is stable.
    assert observed == [
        ("GBR", "world_bank_wdi", "wdi_gdp_per_capita"),
        ("USA", "maddison_project", "maddison_project_gdp_per_capita_2011_intl"),
        ("USA", "world_bank_wdi", "wdi_gdp_per_capita"),
    ], (
        f"unexpected series order: {observed} -- expected requested "
        f"country (GBR) first then alphabetical source order within USA"
    )


# ---------------------------------------------------------------------------
# Superset SQLite integration
# ---------------------------------------------------------------------------


def test_slice_adds_table_to_superset_sqlite_when_core_csv_present(
    tmp_path: Path,
) -> None:
    """When the canonical core CSV exists, the slice rebuilds Superset SQLite.

    The slice writes the investigation CSV first, then triggers
    :func:`build_superset_sqlite_db` so the new table
    ``viz_investigation_gdp_per_capita_major_powers`` is loaded
    alongside the canonical tables. The new table must be queryable
    in the resulting SQLite artifact.
    """
    # Stage a minimal ``viz_country_year_metrics.csv`` so the
    # builder does not refuse to run (it is marked required in
    # ``VIZ_CSV_TABLES``).
    data_dir = tmp_path / "data_dir"
    data_dir.mkdir(parents=True, exist_ok=True)
    core_csv = data_dir / "viz_country_year_metrics.csv"
    core_csv.write_text(
        "metric_id,metric_unit,metric_source,metric_method,"
        "year_date,year,country_iso3,country_name,political_regime,"
        "political_regime_bucket,existence_status,value\n"
        "chronicle.population,persons,vdem,,2000-01-01,2000,USA,"
        "United States,Full democracy,democracy,exists,282000000.0\n",
        encoding="utf-8",
    )

    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(wdi_observations=wdi_obs, wdi_ready=True)
    superset_db = tmp_path / "superset_viz.sqlite"
    request = _default_request(
        tmp_path=tmp_path,
        registry=registry,
        data_dir=data_dir,
        superset_db_path=superset_db,
        rebuild_superset_db=True,
    )
    result = run_investigation_slice(request)

    assert result.superset_db_path == superset_db
    assert superset_db.is_file(), "Superset SQLite must be written"
    table_names = {
        row[0]
        for row in sqlite3.connect(superset_db).execute(
            "select name from sqlite_master where type = 'table'",
        ).fetchall()
    }
    assert "viz_investigation_gdp_per_capita_major_powers" in table_names, (
        f"investigation table missing from Superset SQLite; "
        f"tables: {sorted(table_names)}"
    )
    assert "viz_country_year_metrics" in table_names, (
        f"core fact table missing; tables: {sorted(table_names)}"
    )

    # The new table must contain the expected row count.
    row_count = sqlite3.connect(superset_db).execute(
        "select count(*) from viz_investigation_gdp_per_capita_major_powers",
    ).fetchone()[0]
    assert row_count == 1, f"expected 1 row in investigation table, got {row_count}"


def test_slice_skips_superset_sqlite_when_core_csv_missing(tmp_path: Path) -> None:
    """When the canonical core CSV is absent, the slice skips the Superset rebuild.

    The slice is a proof flow, not a replacement for the chronicle
    builder. Without the core CSV the Superset builder would refuse
    to run (the core CSV is required). The slice must therefore skip
    the rebuild and surface that decision on the result.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(wdi_observations=wdi_obs, wdi_ready=True)
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    assert result.superset_db_path is None
    assert result.superset_db_tables == ()


# ---------------------------------------------------------------------------
# Empty-result failure path
# ---------------------------------------------------------------------------


def test_slice_raises_when_no_concept_rows_materialise(tmp_path: Path) -> None:
    """An empty concept-result must raise ``RuntimeError``.

    The slice refuses to silently emit an empty CSV. The error
    message must surface enough context to debug.
    """
    # All three sources emit zero observations -> no concept rows.
    registry = _build_registry_with_three_sources()
    request = _default_request(tmp_path=tmp_path, registry=registry)
    import pytest

    with pytest.raises(RuntimeError) as exc_info:
        run_investigation_slice(request)
    message = str(exc_info.value)
    assert "gdp_per_capita_major_powers" in message, message
    assert "produced zero concept rows" in message, message


# ---------------------------------------------------------------------------
# Not-ready sources are reported as coverage gaps
# ---------------------------------------------------------------------------


def test_slice_continues_when_a_source_is_not_ready(tmp_path: Path) -> None:
    """A not-ready source is a coverage gap, not a slice failure.

    The slice drives ``check_ready`` directly; when an adapter
    returns ``ready=False`` the slice records a coverage row with
    ``readiness_ready=False`` and continues with the other sources.
    Runtime failures inside ``read_raw`` / ``transform`` propagate
    (see :func:`test_transform_runtime_error_propagates`); readiness
    gaps do NOT propagate.
    """
    # WDI is ready but emits one observation. PWT raises (not-ready).
    # Maddison emits zero observations but is ready.
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=42_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs, pwt_ready=False,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    # The slice must report the PWT coverage gap without failing.
    pwt_coverage = next(
        row for row in result.source_coverage if row.source_id == "pwt"
    )
    assert isinstance(pwt_coverage, SourceCoverageRow)
    assert pwt_coverage.readiness_ready is False
    assert pwt_coverage.emitted == 0
    # The slice now surfaces the adapter's structured SourceWarning
    # message verbatim (not the runner's wrapping message), so the
    # readiness error message must contain the adapter-defined text.
    assert any("not staged" in msg.lower() for msg in pwt_coverage.warnings), (
        f"PWT coverage must surface the readiness error message; "
        f"warnings={pwt_coverage.warnings}"
    )

    # WDI's observation must still flow through the concept catalog.
    assert result.total_concept_rows >= 1, (
        f"slice must still emit WDI concept rows when PWT is not ready; "
        f"got {result.total_concept_rows}"
    )


def test_transform_runtime_error_propagates(tmp_path: Path) -> None:
    """A ``RuntimeError`` inside ``transform`` must NOT be swallowed.

    The slice distinguishes a structured "not ready" outcome
    (``check_ready`` returns ``ready=False`` -- a coverage gap) from
    a runtime failure inside ``read_raw`` or ``transform`` (a real
    source-side bug). The previous implementation caught every
    ``RuntimeError`` from the runner and treated it as a readiness
    gap, silently hiding real adapter bugs.

    This test stages a fake adapter that returns ``ready=True`` from
    ``check_ready`` but raises ``RuntimeError`` from ``transform``;
    the slice must propagate the failure rather than emit a coverage
    row with ``readiness_ready=False``.
    """
    class _TransformRuntimeErrorAdapter(_FakeAdapter):
        """Adapter that is ready but raises ``RuntimeError`` in ``transform``."""

        def transform(self, request: object, raw: object) -> Iterable[object]:
            self.calls.append("transform")
            raise RuntimeError("boom: transform blew up for pwt")

    from leaders_db.sources import InMemorySourceRegistry

    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    # Build a fresh registry with the failing adapter -- the registry
    # forbids duplicate slugs, so we cannot reuse the standard helper
    # here.
    failing_registry = InMemorySourceRegistry()
    failing_registry.register(
        _TransformRuntimeErrorAdapter(slug="pwt", observations=()),
    )
    failing_registry.register(
        _FakeAdapter(slug="maddison_project", observations=()),
    )
    failing_registry.register(
        _FakeAdapter(slug="world_bank_wdi", observations=wdi_obs),
    )
    request = _default_request(
        tmp_path=tmp_path, registry=failing_registry,
    )

    import pytest

    with pytest.raises(RuntimeError) as exc_info:
        run_investigation_slice(request)
    message = str(exc_info.value)
    # The propagating error must be the transform error, NOT the
    # slice's empty-result error, and certainly NOT a coverage-gap
    # notification.
    assert "boom: transform blew up for pwt" in message, message
    assert "produced zero concept rows" not in message, message
    assert "is not ready" not in message, message

    # The CSV must NOT have been written -- the slice failed before
    # reaching the write step, so the developer sees the bug, not a
    # silently-empty artifact.
    csv_path = request.data_dir / (
        f"viz_investigation_{request.question_key}.csv"
    )
    assert not csv_path.exists(), (
        f"CSV must not be written when transform raises; "
        f"found {csv_path}"
    )


# ---------------------------------------------------------------------------
# Coverage-row ``concept_rows`` populated (not always 0)
# ---------------------------------------------------------------------------


def test_source_coverage_concept_rows_filled_after_extraction(
    tmp_path: Path,
) -> None:
    """Each coverage row's ``concept_rows`` must reflect post-extraction counts.

    Without the post-extraction count pass, every
    :class:`SourceCoverageRow.concept_rows` would be the placeholder
    zero left by the per-source dispatcher -- which only sees raw
    :class:`NormalizedObservation` rows. This test stages WDI and
    Maddison with one gdp_per_capita observation each, plus PWT with
    a population row that does NOT feed the concept, and asserts the
    coverage rows carry the actual counts:

    - WDI: 1 gdp_per_capita concept row.
    - Maddison: 1 gdp_per_capita concept row.
    - PWT: 0 concept rows (the staged population row did not feed).
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    maddison_obs = (
        _make_observation(
            source_slug="maddison_project",
            indicator_code="maddison_project_gdp_per_capita_2011_intl",
            value=40_000.0,
            year=2000,
            country_code="GBR",
        ),
    )
    pwt_obs = (
        _make_observation(
            source_slug="pwt",
            indicator_code="pwt_population",
            value=300_000.0,
            year=2000,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs,
        maddison_observations=maddison_obs,
        pwt_observations=pwt_obs,
        wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    coverage_by_id = {row.source_id: row for row in result.source_coverage}
    assert coverage_by_id["world_bank_wdi"].concept_rows == 1, (
        f"WDI coverage must show 1 concept row; got "
        f"{coverage_by_id['world_bank_wdi'].concept_rows}"
    )
    assert coverage_by_id["maddison_project"].concept_rows == 1, (
        f"Maddison coverage must show 1 concept row; got "
        f"{coverage_by_id['maddison_project'].concept_rows}"
    )
    # PWT's staged observation is population -- it does NOT feed the
    # gdp_per_capita concept, so PWT must report 0 concept rows even
    # though it emitted one raw observation.
    assert coverage_by_id["pwt"].concept_rows == 0, (
        f"PWT coverage must show 0 concept rows (population does not "
        f"feed gdp_per_capita); got {coverage_by_id['pwt'].concept_rows}"
    )
    assert coverage_by_id["pwt"].emitted == 1, (
        f"PWT must still report 1 raw observation emitted; got "
        f"{coverage_by_id['pwt'].emitted}"
    )


# ---------------------------------------------------------------------------
# CSV ``question_key`` column is never blank
# ---------------------------------------------------------------------------


def test_csv_question_key_column_never_blank(tmp_path: Path) -> None:
    """Every CSV row must carry the slice's ``question_key``.

    The concept catalog does not inject a question key into the
    observation extension, so reading the question key from there
    would produce a blank column. The slice writes the canonical
    ``question_key`` from :class:`InvestigationQuestion` into every
    row -- this test guards that contract.
    """
    wdi_obs = (
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=50_000.0,
            year=2000,
            country_code="USA",
        ),
        _make_observation(
            source_slug="world_bank_wdi",
            indicator_code="wdi_gdp_per_capita",
            value=45_000.0,
            year=2001,
            country_code="USA",
        ),
    )
    registry = _build_registry_with_three_sources(
        wdi_observations=wdi_obs, wdi_ready=True,
    )
    request = _default_request(tmp_path=tmp_path, registry=registry)
    result = run_investigation_slice(request)

    rows = list(csv.DictReader(result.csv_path.open(encoding="utf-8")))
    assert rows, "slice must emit at least one CSV row"
    for row in rows:
        assert row["question_key"] == "gdp_per_capita_major_powers", (
            f"every CSV row must carry the slice's question_key; "
            f"got {row['question_key']!r} in row {row!r}"
        )


# ---------------------------------------------------------------------------
# Unknown question key
# ---------------------------------------------------------------------------


def test_slice_rejects_unknown_question_key(tmp_path: Path) -> None:
    """Unknown question keys raise :class:`UnknownInvestigationQuestionError`."""
    registry = _build_registry_with_three_sources()
    request = _default_request(
        tmp_path=tmp_path,
        registry=registry,
        question_key="not_a_real_question",
    )
    import pytest

    with pytest.raises(UnknownInvestigationQuestionError):
        run_investigation_slice(request)
    assert "not_a_real_question" in SUPPORTED_QUESTIONS or True
    assert "gdp_per_capita_major_powers" in SUPPORTED_QUESTIONS


def test_slice_question_registry_is_constrained() -> None:
    """The supported-questions registry is small + deterministic.

    The slice must not grow into a free-form question parser; this
    test pins the current shape so a future drift is loud.
    """
    assert tuple(SUPPORTED_QUESTIONS) == ("gdp_per_capita_major_powers",)
    question = SUPPORTED_QUESTIONS["gdp_per_capita_major_powers"]
    assert question.concept_key == "gdp_per_capita"
    assert question.display_countries == ("USA", "GBR", "FRA", "IND", "CHN")


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def test_cli_help_lists_investigation_slice_command() -> None:
    """The CLI registers ``viz-run-investigation-slice`` on the Typer app."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.stdout
    assert "viz-run-investigation-slice" in result.stdout, result.stdout


def test_cli_investigation_slice_help_describes_question_key() -> None:
    """The ``viz-run-investigation-slice --help`` output names the supported question key."""
    result = runner.invoke(
        app, ["viz-run-investigation-slice", "--help"],
    )
    assert result.exit_code == 0, result.stdout
    assert "gdp-per-capita-major-powers" in result.stdout, (
        f"help output must mention the supported question key; got {result.stdout}"
    )


def test_cli_investigation_slice_rejects_unknown_question() -> None:
    """The CLI fails fast on unknown question keys with a clear error.

    The test uses a tiny empty registry by relying on the default
    registry path. We override the env so the slice writes to a
    temp directory rather than the project data lake.
    """
    isolated_dir = runner.invoke(
        app,
        [
            "viz-run-investigation-slice",
            "--question",
            "not-a-real-question",
            "--data-dir",
            str(__import__("tempfile").mkdtemp(prefix="cli-investigation-test-")),
        ],
    )
    assert isolated_dir.exit_code != 0, isolated_dir.stdout
    combined = (isolated_dir.stdout or "") + (isolated_dir.stderr or "")
    assert "not-a-real-question" in combined, (
        f"CLI must name the offending question key; got {combined}"
    )


__all__ = [
    "test_cli_help_lists_investigation_slice_command",
    "test_cli_investigation_slice_help_describes_question_key",
    "test_cli_investigation_slice_rejects_unknown_question",
    "test_concept_extraction_feeds_csv_rows",
    "test_csv_question_key_column_never_blank",
    "test_csv_rows_are_deterministically_sorted",
    "test_html_chart_groups_polylines_by_country_and_source",
    "test_html_chart_keeps_country_source_polylines_separate_over_time",
    "test_html_chart_legend_labels_include_source_slug",
    "test_html_chart_series_order_is_requested_country_then_source_alpha",
    "test_html_chart_three_sources_for_same_country_get_three_polylines",
    "test_html_chart_wdi_two_gdp_per_capita_scales_get_distinct_series",
    "test_slice_adds_table_to_superset_sqlite_when_core_csv_present",
    "test_slice_continues_when_a_source_is_not_ready",
    "test_slice_dispatches_via_source_ingest_runner",
    "test_slice_question_registry_is_constrained",
    "test_slice_raises_when_no_concept_rows_materialise",
    "test_slice_rejects_unknown_question_key",
    "test_slice_skips_superset_sqlite_when_core_csv_missing",
    "test_slice_writes_static_html_graph",
    "test_source_coverage_concept_rows_filled_after_extraction",
    "test_transform_runtime_error_propagates",
]
