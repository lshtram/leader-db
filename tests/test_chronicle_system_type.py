"""Tests for the conservative system-type classifier.

These tests pin down the documented behavior of
:func:`classify_system_type`:

1. SUN 1922-1991 -> ``Communist one-party state`` (curated).
2. CHN 1949-2026 -> ``Communist one-party state`` (curated).
3. IND 1858-1946 -> ``Colonial administration`` (curated).
4. RUS 1992+ has no curated mapping -> regime-bucket fallback
   (Full/Flawed democracy -> ``Liberal capitalist democracy``;
   Hybrid/Authoritarian -> ``Mixed / unclear``; Unknown -> ``Unknown``).
5. Democratic regime bucket (Full / Flawed democracy) with no curated
   mapping -> ``Liberal capitalist democracy`` (regime-bucket fallback).
6. Hybrid / Authoritarian -> ``Mixed / unclear``.
7. Unknown -> ``Unknown`` + ``system_type_low_confidence``.
"""

from __future__ import annotations

from leaders_db.chronicle.constants import (
    CURATED_SYSTEM_TYPE_CONFIDENCE,
    FALLBACK_SYSTEM_TYPE_CONFIDENCE,
    FLAG_SYSTEM_TYPE_LOW_CONFIDENCE,
    SOURCE_TAG_CURATED,
    SOURCE_TAG_VDEM,
)
from leaders_db.chronicle.system_type import (
    SystemTypeResult,
    classify_system_type,
)

# ---------------------------------------------------------------------------
# Curated country-period mappings
# ---------------------------------------------------------------------------


def test_sun_soviet_period_is_communist_one_party() -> None:
    """SUN 1922-1991 maps to Communist one-party state at curated confidence."""
    result = classify_system_type(
        iso3="SUN", year=1950, regime_bucket="Authoritarian"
    )
    assert isinstance(result, SystemTypeResult)
    assert result.primary == "Communist one-party state"
    assert result.source == SOURCE_TAG_CURATED
    assert result.confidence == CURATED_SYSTEM_TYPE_CONFIDENCE
    assert "1922-1991" in result.notes
    assert FLAG_SYSTEM_TYPE_LOW_CONFIDENCE not in result.flags


def test_sun_outside_soviet_period_uses_regime_fallback() -> None:
    """SUN in 2000 (post-existence, but no curated mapping matches) falls
    through to the regime-bucket default."""
    result = classify_system_type(
        iso3="SUN", year=2000, regime_bucket="Authoritarian"
    )
    # No curated mapping matches; the fallback path runs.
    assert result.primary == "Mixed / unclear"
    assert result.source == SOURCE_TAG_VDEM


def test_chn_post_1949_is_communist_one_party() -> None:
    """CHN 1949+ maps to Communist one-party state at curated confidence."""
    result = classify_system_type(
        iso3="CHN", year=1980, regime_bucket="Authoritarian"
    )
    assert result.primary == "Communist one-party state"
    assert result.source == SOURCE_TAG_CURATED
    assert result.confidence == CURATED_SYSTEM_TYPE_CONFIDENCE


def test_chn_pre_1949_falls_back_to_regime_default() -> None:
    """CHN 1948 is before the curated mapping start year; the regime
    bucket fallback applies."""
    result = classify_system_type(
        iso3="CHN", year=1948, regime_bucket="Authoritarian"
    )
    # No curated mapping for 1948; fallback runs.
    assert result.primary == "Mixed / unclear"
    assert result.source == SOURCE_TAG_VDEM


def test_ind_pre_1947_is_colonial_administration() -> None:
    """IND 1946 maps to Colonial administration at curated confidence."""
    result = classify_system_type(
        iso3="IND", year=1946, regime_bucket="Authoritarian"
    )
    assert result.primary == "Colonial administration"
    assert result.source == SOURCE_TAG_CURATED
    assert result.confidence == CURATED_SYSTEM_TYPE_CONFIDENCE


def test_ind_post_1947_falls_through_to_regime_default() -> None:
    """IND 1947+ has no curated mapping; the regime-bucket default applies."""
    result = classify_system_type(
        iso3="IND", year=1950, regime_bucket="Flawed democracy"
    )
    assert result.primary == "Liberal capitalist democracy"
    assert result.source == SOURCE_TAG_VDEM


def test_rus_post_1991_falls_through_to_regime_default() -> None:
    """RUS has no curated mapping; the regime-bucket default applies for
    both democratic and Hybrid/Authoritarian buckets.

    RUS 1992+ is intentionally not in the curated country-period list.
    The classifier must therefore route RUS through the regime-bucket
    fallback for every documented bucket value.
    """
    # Full democracy -> Liberal capitalist democracy (regime-bucket default).
    result_full = classify_system_type(
        iso3="RUS", year=2010, regime_bucket="Full democracy"
    )
    assert result_full.primary == "Liberal capitalist democracy"
    assert result_full.source == SOURCE_TAG_VDEM
    assert result_full.confidence == FALLBACK_SYSTEM_TYPE_CONFIDENCE
    # Hybrid regime -> Mixed / unclear (regime-bucket default).
    result_hybrid = classify_system_type(
        iso3="RUS", year=2010, regime_bucket="Hybrid regime"
    )
    assert result_hybrid.primary == "Mixed / unclear"
    # Authoritarian -> Mixed / unclear (regime-bucket default).
    result_auth = classify_system_type(
        iso3="RUS", year=2010, regime_bucket="Authoritarian"
    )
    assert result_auth.primary == "Mixed / unclear"


# ---------------------------------------------------------------------------
# Regime-bucket fallback
# ---------------------------------------------------------------------------


def test_full_democracy_default_is_liberal_capitalist_democracy() -> None:
    """A Full democracy bucket with no curated mapping defaults to
    'Liberal capitalist democracy'."""
    result = classify_system_type(
        iso3="USA", year=1990, regime_bucket="Full democracy"
    )
    assert result.primary == "Liberal capitalist democracy"
    assert result.source == SOURCE_TAG_VDEM
    assert result.confidence == FALLBACK_SYSTEM_TYPE_CONFIDENCE
    assert FLAG_SYSTEM_TYPE_LOW_CONFIDENCE not in result.flags


def test_flawed_democracy_default_is_liberal_capitalist_democracy() -> None:
    """A Flawed democracy bucket defaults to 'Liberal capitalist democracy'."""
    result = classify_system_type(
        iso3="USA", year=2025, regime_bucket="Flawed democracy"
    )
    assert result.primary == "Liberal capitalist democracy"


def test_hybrid_regime_default_is_mixed_unclear() -> None:
    """A Hybrid regime bucket defaults to 'Mixed / unclear'."""
    result = classify_system_type(
        iso3="IND", year=1990, regime_bucket="Hybrid regime"
    )
    assert result.primary == "Mixed / unclear"


def test_authoritarian_default_is_mixed_unclear() -> None:
    """An Authoritarian bucket defaults to 'Mixed / unclear'."""
    result = classify_system_type(
        iso3="RUS", year=1980, regime_bucket="Authoritarian"
    )
    assert result.primary == "Mixed / unclear"


def test_unknown_bucket_yields_unknown_with_low_confidence_flag() -> None:
    """An Unknown bucket yields 'Unknown' with ``system_type_low_confidence``."""
    result = classify_system_type(
        iso3="SUN", year=2025, regime_bucket="Unknown"
    )
    assert result.primary == "Unknown"
    assert FLAG_SYSTEM_TYPE_LOW_CONFIDENCE in result.flags


# ---------------------------------------------------------------------------
# Notes content
# ---------------------------------------------------------------------------


def test_notes_mention_curated_mapping_when_used() -> None:
    """Curated matches include a notes string documenting the mapping."""
    result = classify_system_type(
        iso3="CHN", year=1980, regime_bucket="Authoritarian"
    )
    assert "Curated mapping" in result.notes
    assert "CHN" in result.notes
    assert "1949-2026" in result.notes


def test_notes_mention_regime_bucket_for_fallback() -> None:
    """Fallback matches document the regime bucket in the notes string."""
    result = classify_system_type(
        iso3="USA", year=1990, regime_bucket="Full democracy"
    )
    assert "regime bucket" in result.notes
    assert "Full democracy" in result.notes


# ---------------------------------------------------------------------------
# Secondary field
# ---------------------------------------------------------------------------


def test_secondary_field_is_empty_in_increment_1() -> None:
    """The secondary system-type label is always empty in Increment 1."""
    for iso3, year, bucket in (
        ("SUN", 1950, "Authoritarian"),
        ("CHN", 1980, "Authoritarian"),
        ("IND", 1946, "Authoritarian"),
        ("USA", 1990, "Full democracy"),
        ("GBR", 2020, "Full democracy"),
    ):
        result = classify_system_type(iso3=iso3, year=year, regime_bucket=bucket)
        assert result.secondary == "", (
            f"unexpected secondary for {iso3}/{year}/{bucket}: "
            f"{result.secondary!r}"
        )
