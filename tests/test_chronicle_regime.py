"""Tests for the political-regime bucket derivation.

These tests cover the deterministic mapping from a V-Dem
:class:`RegimeSource` to a CYC :class:`RegimeBucketResult`. The
mapping follows Increment 0 §5.1:

1. Direct ``v2x_regime`` integer -> the canonical bucket.
2. Polyarchy fallback when ``v2x_regime`` is missing.
3. ``Unknown`` + ``regime_source_gap`` when both are missing.
"""

from __future__ import annotations

import pytest

from leaders_db.chronicle.constants import (
    FLAG_PROXY_YEAR_USED,
    FLAG_REGIME_SOURCE_GAP,
    SOURCE_TAG_VDEM,
    VDEM_DIRECT_CONFIDENCE,
    VDEM_PROXY_CONFIDENCE,
)
from leaders_db.chronicle.regime import (
    RegimeBucketResult,
    derive_regime_bucket,
)
from leaders_db.chronicle.sources import RegimeSource

# ---------------------------------------------------------------------------
# Direct v2x_regime mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("regime", "expected_bucket"),
    [
        (0, "Authoritarian"),
        (1, "Hybrid regime"),
        (2, "Flawed democracy"),
        (3, "Full democracy"),
    ],
)
def test_direct_regime_int_maps_to_canonical_bucket(
    regime: int, expected_bucket: str
) -> None:
    """Each V-Dem ``v2x_regime`` integer maps to the documented CYC bucket."""
    src = RegimeSource(
        regime=float(regime),
        polyarchy=None,
        libdem=None,
        source_year_used=2023,
        is_proxy=False,
    )
    result = derive_regime_bucket(src)
    assert isinstance(result, RegimeBucketResult)
    assert result.bucket == expected_bucket
    assert result.raw_score == str(regime)
    assert result.source == SOURCE_TAG_VDEM
    assert result.source_year_used == 2023
    assert result.confidence == VDEM_DIRECT_CONFIDENCE
    assert FLAG_REGIME_SOURCE_GAP not in result.flags


def test_direct_regime_int_one_decimal_form_is_accepted() -> None:
    """V-Dem ``v2x_regime`` is sometimes stored as ``2.0``; the mapping
    must coerce to int and accept it."""
    src = RegimeSource(
        regime=2.0,
        polyarchy=None,
        libdem=None,
        source_year_used=2023,
        is_proxy=False,
    )
    result = derive_regime_bucket(src)
    assert result.bucket == "Flawed democracy"
    assert result.raw_score == "2"


def test_direct_regime_unrecognized_value_falls_through() -> None:
    """An out-of-range ``v2x_regime`` value falls through to the
    polyarchy path (or to Unknown when polyarchy is also missing)."""
    src = RegimeSource(
        regime=7.0,
        polyarchy=None,
        libdem=None,
        source_year_used=2023,
        is_proxy=False,
    )
    result = derive_regime_bucket(src)
    assert result.bucket == "Unknown"
    assert FLAG_REGIME_SOURCE_GAP in result.flags


# ---------------------------------------------------------------------------
# Polyarchy fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("polyarchy", "expected_bucket"),
    [
        (0.85, "Full democracy"),
        (0.55, "Flawed democracy"),
        (0.40, "Hybrid regime"),
        (0.10, "Authoritarian"),
        (0.00, "Authoritarian"),
    ],
)
def test_polyarchy_fallback_maps_to_canonical_bucket(
    polyarchy: float, expected_bucket: str
) -> None:
    """When ``v2x_regime`` is missing, the polyarchy thresholds apply."""
    src = RegimeSource(
        regime=None,
        polyarchy=polyarchy,
        libdem=None,
        source_year_used=2023,
        is_proxy=False,
    )
    result = derive_regime_bucket(src)
    assert result.bucket == expected_bucket
    assert FLAG_REGIME_SOURCE_GAP in result.flags
    # Polyarchy-derived confidence is 10 below direct (per the implementation).
    assert result.confidence < VDEM_DIRECT_CONFIDENCE


def test_polyarchy_fallback_threshold_boundaries() -> None:
    """The boundaries between polyarchy buckets are respected."""
    # 0.70 is the inclusive lower bound for Full democracy.
    full = derive_regime_bucket(
        RegimeSource(None, 0.70, None, 2023, False)
    )
    assert full.bucket == "Full democracy"
    # 0.69999 falls into Flawed democracy.
    flawed = derive_regime_bucket(
        RegimeSource(None, 0.6999, None, 2023, False)
    )
    assert flawed.bucket == "Flawed democracy"


# ---------------------------------------------------------------------------
# Both missing -> Unknown + flag
# ---------------------------------------------------------------------------


def test_no_regime_or_polyarchy_yields_unknown() -> None:
    """When both ``v2x_regime`` and ``v2x_polyarchy`` are missing the
    bucket is ``Unknown`` with ``regime_source_gap``."""
    src = RegimeSource(
        regime=None,
        polyarchy=None,
        libdem=None,
        source_year_used=2023,
        is_proxy=False,
    )
    result = derive_regime_bucket(src)
    assert result.bucket == "Unknown"
    assert result.raw_score == ""
    assert FLAG_REGIME_SOURCE_GAP in result.flags


# ---------------------------------------------------------------------------
# Proxy behavior
# ---------------------------------------------------------------------------


def test_proxy_year_used_flag_and_lower_confidence() -> None:
    """When the source was a proxy, ``proxy_year_used`` is added and the
    confidence drops to :data:`VDEM_PROXY_CONFIDENCE`."""
    src = RegimeSource(
        regime=3.0,
        polyarchy=None,
        libdem=None,
        source_year_used=2025,
        is_proxy=True,
    )
    result = derive_regime_bucket(src)
    assert result.bucket == "Full democracy"
    assert result.confidence == VDEM_PROXY_CONFIDENCE
    assert FLAG_PROXY_YEAR_USED in result.flags


def test_proxy_polyarchy_path_includes_both_flags() -> None:
    """A polyarchy-derived bucket from the proxy year carries both
    ``regime_source_gap`` and ``proxy_year_used``."""
    src = RegimeSource(
        regime=None,
        polyarchy=0.62,
        libdem=None,
        source_year_used=2025,
        is_proxy=True,
    )
    result = derive_regime_bucket(src)
    assert result.bucket == "Flawed democracy"
    assert FLAG_REGIME_SOURCE_GAP in result.flags
    assert FLAG_PROXY_YEAR_USED in result.flags
    assert result.confidence == VDEM_PROXY_CONFIDENCE


# ---------------------------------------------------------------------------
# Confidence ordering
# ---------------------------------------------------------------------------


def test_confidence_ordering_direct_gt_proxy() -> None:
    """Direct values outrank proxy values for the same regime."""
    direct = derive_regime_bucket(
        RegimeSource(2.0, None, None, 2023, False)
    )
    proxy = derive_regime_bucket(
        RegimeSource(2.0, None, None, 2025, True)
    )
    assert direct.confidence > proxy.confidence


# ---------------------------------------------------------------------------
# RegimeSource.from_vdem_lookup — proxy logic
# ---------------------------------------------------------------------------


class _StubVDem:
    """A minimal stub that satisfies the V-Dem source lookup protocol.

    The :meth:`RegimeSource.from_vdem_lookup` static method only calls
    ``vdem.lookup(iso3, year)``. A real :class:`VDemSource` requires a
    non-empty ``frame``; this stub uses Python's duck typing.
    """

    def __init__(
        self,
        year_to_payload: dict[int, tuple[float | None, float | None, float | None]],
    ) -> None:
        self._year_to_payload = year_to_payload

    def lookup(self, iso3: str, year: int) -> tuple[float | None, float | None, float | None]:
        return self._year_to_payload.get(
            year, (None, None, None)
        )


def test_from_vdem_lookup_direct_match() -> None:
    """A direct hit returns a non-proxy RegimeSource."""
    stub = _StubVDem({2023: (3.0, 0.85, 0.90)})
    src = RegimeSource.from_vdem_lookup(stub, "USA", 2023)  # type: ignore[arg-type]
    assert src.is_proxy is False
    assert src.regime == 3.0
    assert src.source_year_used == 2023


def test_from_vdem_lookup_proxy_for_year_beyond_coverage() -> None:
    """A request for 2026 reads the 2025 proxy and tags is_proxy=True."""
    stub = _StubVDem({2025: (2.0, 0.55, 0.6)})
    src = RegimeSource.from_vdem_lookup(stub, "USA", 2026)  # type: ignore[arg-type]
    assert src.is_proxy is True
    assert src.regime == 2.0
    assert src.source_year_used == 2025


def test_from_vdem_lookup_no_match_returns_empty() -> None:
    """No match at all returns a fully-empty RegimeSource."""
    stub = _StubVDem({})
    src = RegimeSource.from_vdem_lookup(stub, "USA", 2023)  # type: ignore[arg-type]
    assert src.regime is None
    assert src.polyarchy is None
    assert src.is_proxy is False


def test_from_vdem_lookup_year_within_coverage_no_match() -> None:
    """A year within V-Dem coverage with no row returns a non-proxy empty source."""
    stub = _StubVDem({2020: (3.0, 0.85, 0.9)})
    src = RegimeSource.from_vdem_lookup(stub, "ZZZ", 2019)  # type: ignore[arg-type]
    assert src.regime is None
    assert src.is_proxy is False
    assert src.source_year_used == 2019
