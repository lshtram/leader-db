"""Descriptor factory for REIGN 2021-8."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    REIGN_ATTRIBUTION_KEY,
    REIGN_COVERAGE_END_YEAR,
    REIGN_COVERAGE_START_YEAR,
    REIGN_DEFAULT_VERSION,
    REIGN_HOMEPAGE_URL,
    REIGN_SOURCE_KEY,
    REIGN_SUPPORTED_FAMILIES,
)


def build_reign_descriptor() -> SourceDescriptor:
    """Build the static REIGN source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=REIGN_SOURCE_KEY),
        display_name="REIGN 2021-8 leader-month dataset",
        source_type="dataset",
        supported_observation_families=REIGN_SUPPORTED_FAMILIES,
        default_version=REIGN_DEFAULT_VERSION,
        homepage_url=REIGN_HOMEPAGE_URL,
        attribution_key=REIGN_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=REIGN_COVERAGE_START_YEAR,
            end_year=REIGN_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "REIGN 2021-8 is leader-month data. The clean adapter emits "
                "one observation per leader-month identity/governance field "
                "under leader_identity_month. Coverage ends in 2021-08 and "
                "cannot validate 2023 leaders."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_reign_descriptor"]
