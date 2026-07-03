"""Descriptor for the EIU Democracy Index clean-source adapter."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT,
    EIU_DEMOCRACY_INDEX_COVERAGE_END_YEAR,
    EIU_DEMOCRACY_INDEX_COVERAGE_START_YEAR,
    EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
    EIU_DEMOCRACY_INDEX_HOMEPAGE_URL,
    EIU_DEMOCRACY_INDEX_INDICATORS,
    EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,
    EIU_DEMOCRACY_INDEX_SOURCE_KEY,
)


def build_eiu_democracy_index_descriptor() -> SourceDescriptor:
    """Return the static descriptor for staged local EIU PDF reports."""
    return SourceDescriptor(
        source_id=SourceId(EIU_DEMOCRACY_INDEX_SOURCE_KEY),
        display_name="Economist Intelligence Unit Democracy Index",
        source_type="document",
        supported_observation_families=(EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,),
        default_version=EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
        homepage_url=EIU_DEMOCRACY_INDEX_HOMEPAGE_URL,
        attribution_key=EIU_DEMOCRACY_INDEX_SOURCE_KEY,
        coverage_hint=CoverageHint(
            start_year=EIU_DEMOCRACY_INDEX_COVERAGE_START_YEAR,
            end_year=EIU_DEMOCRACY_INDEX_COVERAGE_END_YEAR,
            notes=(
                "Local user-managed copyrighted PDF reports. Staged years are "
                "2006, 2008, 2010-2019, and 2021-2024; 2020 is currently "
                "missing and 2007/2009 are not expected. Indicators: "
                f"{', '.join(EIU_DEMOCRACY_INDEX_INDICATORS)}. Attribution: "
                f"{EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT}"
            ),
        ),
        requires_manual_approval=True,
        requires_network=False,
    )


__all__ = ["build_eiu_democracy_index_descriptor"]
