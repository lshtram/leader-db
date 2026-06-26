"""Descriptor factory for SIPRI Yearbook Ch.7."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    SIPRI_YEARBOOK_CH7_ATTRIBUTION_KEY,
    SIPRI_YEARBOOK_CH7_COVERAGE_END_YEAR,
    SIPRI_YEARBOOK_CH7_COVERAGE_START_YEAR,
    SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
    SIPRI_YEARBOOK_CH7_HOMEPAGE_URL,
    SIPRI_YEARBOOK_CH7_SOURCE_KEY,
    SIPRI_YEARBOOK_CH7_SUPPORTED_FAMILIES,
)


def build_sipri_yearbook_ch7_descriptor() -> SourceDescriptor:
    """Build the static SIPRI Yearbook Ch.7 source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=SIPRI_YEARBOOK_CH7_SOURCE_KEY),
        display_name="SIPRI Yearbook Chapter 7 (World Nuclear Forces)",
        source_type="document",
        supported_observation_families=SIPRI_YEARBOOK_CH7_SUPPORTED_FAMILIES,
        default_version=SIPRI_YEARBOOK_CH7_DEFAULT_VERSION,
        homepage_url=SIPRI_YEARBOOK_CH7_HOMEPAGE_URL,
        attribution_key=SIPRI_YEARBOOK_CH7_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=SIPRI_YEARBOOK_CH7_COVERAGE_START_YEAR,
            end_year=SIPRI_YEARBOOK_CH7_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "SIPRI Yearbook Ch.7 is a snapshot PDF source for "
                "nuclear country-year facts. The clean adapter reads the "
                "local staged PDF and emits one observation per country and "
                "catalog warhead-count indicator."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_sipri_yearbook_ch7_descriptor"]
