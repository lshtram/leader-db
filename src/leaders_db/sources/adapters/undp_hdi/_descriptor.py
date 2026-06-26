"""Descriptor factory for UNDP HDI."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    UNDP_HDI_ATTRIBUTION_KEY,
    UNDP_HDI_COVERAGE_END_YEAR,
    UNDP_HDI_COVERAGE_START_YEAR,
    UNDP_HDI_DEFAULT_VERSION,
    UNDP_HDI_HOMEPAGE_URL,
    UNDP_HDI_OBSERVATION_FAMILY,
    UNDP_HDI_SOURCE_KEY,
    UNDP_HDI_SUPPORTED_FAMILIES,
)


def build_undp_hdi_descriptor() -> SourceDescriptor:
    """Build the static UNDP HDI source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=UNDP_HDI_SOURCE_KEY),
        display_name="UNDP Human Development Index (HDR 2023-24)",
        source_type="dataset",
        supported_observation_families=UNDP_HDI_SUPPORTED_FAMILIES,
        default_version=UNDP_HDI_DEFAULT_VERSION,
        homepage_url=UNDP_HDI_HOMEPAGE_URL,
        attribution_key=UNDP_HDI_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=UNDP_HDI_COVERAGE_START_YEAR,
            end_year=UNDP_HDI_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Local/user-managed HDR 2023-24 wide CSV source. The clean adapter "
                f"emits {UNDP_HDI_OBSERVATION_FAMILY} records for HDI, life "
                "expectancy, schooling, and income indicators in the social_wellbeing "
                "category. Coverage is 1990-2022; requested 2023 uses 2022 as a "
                "one-year proxy while observations remain labeled with the actual "
                "2022 data year."
            ),
        ),
        requires_manual_approval=True,
        requires_network=False,
    )


__all__ = ["build_undp_hdi_descriptor"]
