"""Descriptor factory for Archigos v4.1."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    ARCHIGOS_ATTRIBUTION_KEY,
    ARCHIGOS_COVERAGE_END_YEAR,
    ARCHIGOS_COVERAGE_START_YEAR,
    ARCHIGOS_DEFAULT_VERSION,
    ARCHIGOS_HOMEPAGE_URL,
    ARCHIGOS_SOURCE_KEY,
    ARCHIGOS_SUPPORTED_FAMILIES,
)


def build_archigos_descriptor() -> SourceDescriptor:
    """Build the static Archigos source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=ARCHIGOS_SOURCE_KEY),
        display_name="Archigos v4.1 leader-spell dataset",
        source_type="dataset",
        supported_observation_families=ARCHIGOS_SUPPORTED_FAMILIES,
        default_version=ARCHIGOS_DEFAULT_VERSION,
        homepage_url=ARCHIGOS_HOMEPAGE_URL,
        attribution_key=ARCHIGOS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=ARCHIGOS_COVERAGE_START_YEAR,
            end_year=ARCHIGOS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Archigos v4.1 is leader-spell data, not country-year data. "
                "The clean adapter reads the local Stata 14 file and emits "
                "one observation per leader-spell identity field, keyed by "
                "the spell start year. Data ends in 2015 and cannot validate "
                "2023 leaders."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_archigos_descriptor"]
