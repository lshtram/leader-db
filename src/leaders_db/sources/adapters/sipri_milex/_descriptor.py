"""Descriptor factory for SIPRI Milex."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    SIPRI_MILEX_ATTRIBUTION_KEY,
    SIPRI_MILEX_COVERAGE_END_YEAR,
    SIPRI_MILEX_COVERAGE_START_YEAR,
    SIPRI_MILEX_DEFAULT_VERSION,
    SIPRI_MILEX_HOMEPAGE_URL,
    SIPRI_MILEX_SOURCE_KEY,
    SIPRI_MILEX_SUPPORTED_FAMILIES,
)


def build_sipri_milex_descriptor() -> SourceDescriptor:
    """Build the static SIPRI Milex source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=SIPRI_MILEX_SOURCE_KEY),
        display_name="SIPRI Military Expenditure Database",
        source_type="dataset",
        supported_observation_families=SIPRI_MILEX_SUPPORTED_FAMILIES,
        default_version=SIPRI_MILEX_DEFAULT_VERSION,
        homepage_url=SIPRI_MILEX_HOMEPAGE_URL,
        attribution_key=SIPRI_MILEX_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=SIPRI_MILEX_COVERAGE_START_YEAR,
            end_year=SIPRI_MILEX_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "SIPRI Milex is country-year military expenditure data. "
                "The clean adapter reads the local staged xlsx and emits one "
                "observation per non-missing country, year, and catalog indicator."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_sipri_milex_descriptor"]
