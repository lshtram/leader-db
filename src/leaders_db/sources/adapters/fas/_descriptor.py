"""Descriptor factory for the clean FAS Nuclear Notebook adapter.

The FAS public "Status of World Nuclear Forces" page
(``https://programs.fas.org/ssp/nukes/nuclearweapons/nukestatus.html``)
is a single parseable HTML table with the 9 nuclear-armed states and
5 numeric columns. The unified adapter is local-file only
(``requires_network=False``); the descriptor advertises
``source_type="document"`` because the canonical Stage 2 access path
is the staged HTML document, augmented by the local ``metadata.json``
bundle metadata.

The descriptor advertises the canonical FAS static metadata (source_id
``fas``, default version ``"consolidated status table"``,
attribution_key ``fas``, document type, ``requires_network=False``,
2014 snapshot coverage hint -- the consolidated snapshot year parsed
from the page's ``<meta name="date">`` element on the live page as of
probe 2026-06-19), and the single observation family
``nuclear_country_year``.
"""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    FAS_ATTRIBUTION_KEY,
    FAS_COVERAGE_END_YEAR,
    FAS_COVERAGE_START_YEAR,
    FAS_DEFAULT_VERSION,
    FAS_HOMEPAGE_URL,
    FAS_OBSERVATION_FAMILY,
    FAS_SNAPSHOT_YEAR,
    FAS_SOURCE_KEY,
    FAS_SUPPORTED_FAMILIES,
)


def build_fas_descriptor() -> SourceDescriptor:
    """Build the canonical FAS :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes for
    source discovery (SRC-ID-003). The values mirror the canonical
    catalog and citation block in ``docs/sources/attributions.md``
    (Rule #15).

    The descriptor advertises ``source_type="document"`` because the
    canonical Stage 2 access path is a single local HTML page (the
    FAS consolidated status page snapshot) plus a JSON ``metadata.json``
    bundle. ``requires_network=False`` because the unified adapter
    is local-file only -- the legacy HTTP layer is intentionally
    NEVER invoked by the unified read path.
    """
    return SourceDescriptor(
        source_id=SourceId(slug=FAS_SOURCE_KEY),
        display_name="FAS Nuclear Notebook (Status of World Nuclear Forces)",
        source_type="document",
        supported_observation_families=FAS_SUPPORTED_FAMILIES,
        default_version=FAS_DEFAULT_VERSION,
        homepage_url=FAS_HOMEPAGE_URL,
        attribution_key=FAS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=FAS_COVERAGE_START_YEAR,
            end_year=FAS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                f"FAS Nuclear Notebook single-snapshot HTML document source. "
                f"The clean adapter reads the staged local HTML cache "
                f"(<raw_root>/fas/fas_status.html) through lazy legacy "
                f"parser imports and emits 5 "
                f"{FAS_OBSERVATION_FAMILY} records (operational strategic, "
                f"operational nonstrategic, reserve/nondeployed, military "
                f"stockpile, total inventory) per non-missing country row. "
                f"The consolidated snapshot year is parsed from the page's "
                f"<meta name=\"date\"> element and recorded on every "
                f"observation's extension.snapshot_year field. As of probe "
                f"2026-06-19 the live page snapshot is "
                f"{FAS_SNAPSHOT_YEAR} per the meta date element; Stage 11 "
                f"confidence penalises the temporal-fit gap between the "
                f"snapshot year and the prototype's target year (2023). "
                f"FAS is local-file only (requires_network=False); the "
                f"unified adapter never invokes the network."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_fas_descriptor"]
