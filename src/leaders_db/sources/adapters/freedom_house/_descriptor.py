"""Descriptor factory for Freedom House Freedom in the World."""

from __future__ import annotations

from leaders_db.sources.contracts import CoverageHint, SourceDescriptor, SourceId

from ._constants import (
    FREEDOM_HOUSE_ATTRIBUTION_KEY,
    FREEDOM_HOUSE_COVERAGE_END_YEAR,
    FREEDOM_HOUSE_COVERAGE_START_YEAR,
    FREEDOM_HOUSE_DEFAULT_VERSION,
    FREEDOM_HOUSE_HOMEPAGE_URL,
    FREEDOM_HOUSE_SOURCE_KEY,
    FREEDOM_HOUSE_SUPPORTED_FAMILIES,
)


def build_freedom_house_descriptor() -> SourceDescriptor:
    """Build the static FIW source descriptor."""
    return SourceDescriptor(
        source_id=SourceId(slug=FREEDOM_HOUSE_SOURCE_KEY),
        display_name="Freedom House Freedom in the World (FIW) 2026",
        source_type="dataset",
        supported_observation_families=FREEDOM_HOUSE_SUPPORTED_FAMILIES,
        default_version=FREEDOM_HOUSE_DEFAULT_VERSION,
        homepage_url=FREEDOM_HOUSE_HOMEPAGE_URL,
        attribution_key=FREEDOM_HOUSE_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=FREEDOM_HOUSE_COVERAGE_START_YEAR,
            end_year=FREEDOM_HOUSE_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "Local/user-managed FIW 2026 workbook source. The clean adapter "
                "reads Country_and_Territory_Ratings_and_Statuses_FIW_1973-2026.xlsx "
                "from data/raw/freedom_house and emits political rights, civil "
                "liberties, and Freedom House status observations for country and "
                "territory survey-edition years 1973-2026. Raw workbooks are not "
                "redistributable; derived public outputs must cite Freedom House."
            ),
        ),
        requires_manual_approval=True,
        requires_network=False,
    )


__all__ = ["build_freedom_house_descriptor"]
