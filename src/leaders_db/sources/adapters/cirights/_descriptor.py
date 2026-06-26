"""Descriptor factory for CIRIGHTS."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    CIRIGHTS_ATTRIBUTION_KEY,
    CIRIGHTS_COVERAGE_END_YEAR,
    CIRIGHTS_COVERAGE_START_YEAR,
    CIRIGHTS_DEFAULT_VERSION,
    CIRIGHTS_HOMEPAGE_URL,
    CIRIGHTS_OBSERVATION_FAMILY,
    CIRIGHTS_SOURCE_KEY,
    CIRIGHTS_SUPPORTED_FAMILIES,
)


def build_cirights_descriptor() -> SourceDescriptor:
    """Build the static CIRIGHTS source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=CIRIGHTS_SOURCE_KEY),
        display_name="CIRI Human Rights Data Project (CIRIGHTS)",
        source_type="dataset",
        supported_observation_families=CIRIGHTS_SUPPORTED_FAMILIES,
        default_version=CIRIGHTS_DEFAULT_VERSION,
        homepage_url=CIRIGHTS_HOMEPAGE_URL,
        attribution_key=CIRIGHTS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=CIRIGHTS_COVERAGE_START_YEAR,
            end_year=CIRIGHTS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Local/user-managed CIRIGHTS xlsx source. The clean adapter emits "
                f"{CIRIGHTS_OBSERVATION_FAMILY} records for seven physical-integrity, "
                "repression, and civil/political rights indicators. Coverage is "
                "1981-2022; requested 2023 uses 2022 as a one-year proxy while "
                "observations remain labeled with the actual 2022 data year."
            ),
        ),
        requires_manual_approval=True,
        requires_network=False,
    )


__all__ = ["build_cirights_descriptor"]
