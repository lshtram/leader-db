"""Descriptor factory for the SIPRI Arms Transfers clean adapter.

This module owns the canonical :class:`SourceDescriptor` for the
SIPRI Arms Transfers Database. The descriptor advertises the
static source metadata the registry exposes for source
discovery (SRC-ID-003): the canonical slug
``sipri_arms_transfers``, the SIPRI homepage URL, the canonical
1950-2025 coverage envelope, the BOTH-families observation
support (``arms_transfer_register_row`` +
``arms_transfer_country_year_aggregate``), and the cache-only
network policy.

Coverage envelope
-----------------

The SIPRI Arms Transfers Database covers transfers of major
conventional arms from 1950 to the most recent full calendar
year. As of probe (2026-03-09 SIPRI page snapshot), the
database covers 1950-2025. The descriptor advertises the
canonical envelope; the readiness gate surfaces a structured
``YEAR_ABSENT`` warning on out-of-coverage year requests so the
runner never silently proxies an out-of-coverage year to the
nearest in-coverage year (SRC-COV-002 / SRC-COV-003).

Source-type semantics
---------------------

The descriptor advertises ``source_type="api"`` because the
SIPRI Arms Transfers data is delivered through a backend API
(``https://atbackend.sipri.org/api/p/trades/trade-register-csv/``)
plus the SIPRI public app
(``https://armstransfers.sipri.org/ArmsTransfer``) -- even though
the unified adapter in this slice is cache-only /
offline-only, the underlying source-type is API-backed. The
descriptor advertises ``requires_network=False`` because the
unified adapter never invokes the network; the readiness gate
blocks ``cache_policy="refresh"`` / ``"no_cache"`` with a
structured ``unsupported_cache_policy`` error so the runner
refuses to dispatch ``read_raw`` / ``transform`` rather than
silently surfacing an HTTP-fetched payload.

Observation-family shape
------------------------

The descriptor advertises BOTH
``arms_transfer_register_row`` and
``arms_transfer_country_year_aggregate`` so downstream query
code can filter by family without consulting the per-source
catalog. The ``arms_transfer_register_row`` family is the
canonical per-transfer raw evidence unit (one observation per
cached transfer row); the ``arms_transfer_country_year_aggregate``
family is the deterministic per-``(role, country, year)``
aggregate computed on the transform side from the parsed
row-level frame (sum of TIV delivered over all transfers in the
cached bundle where the country appears as supplier (resp.
recipient) and the delivery year matches the year).

Attribution caveat
------------------

The descriptor's ``coverage_hint.notes`` carries the explicit
SIPRI Arms Transfers caveat: arms-transfer data is evidence of
arms flows between recorded supplier / recipient countries and
is NOT direct proof of aggression, proxy sponsorship, or
illegality. The downstream scoring code MUST NOT silently treat
arms-transfer TIV totals as a proxy for aggression /
responsibility without an explicit secondary-source corroboration
step (UCODP external support, sanctions records, expert-panel
reports, manual evidence). This is the documented caveat the
``docs/methodology/ranking-evaluation-criteria.md`` Chapter 2
proxy-aggression question applies to arms-transfer evidence.

Attribution text
----------------

The unified ``SIPRI_ARMS_TRANSFERS_ATTRIBUTION_TEXT`` constant
is byte-identical to the ``sipri_arms_transfers`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_sipri_arms_transfers_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity. The attribution text is
intentionally distinct from the ``sipri_milex`` and
``sipri_yearbook_ch7`` attribution strings -- SIPRI Arms
Transfers is a separate SIPRI sub-dataset.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY,
    SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
    SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
    SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
    SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
    SIPRI_ARMS_TRANSFERS_INDICATOR_CODES,
    SIPRI_ARMS_TRANSFERS_SOURCE_KEY,
    SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES,
)


def build_sipri_arms_transfers_descriptor() -> SourceDescriptor:
    """Build the canonical SIPRI Arms Transfers :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes
    for source discovery (SRC-ID-003). The values mirror the
    canonical citation block in ``docs/sources/attributions.md``
    ``sipri_arms_transfers`` section (Rule #15).

    The descriptor advertises ``source_type="api"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally
    for SIPRI Arms Transfers (the unified adapter is cache-only
    in this slice; the cache-policy gate blocks unsupported
    policies with a structured ``unsupported_cache_policy``
    error).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=SIPRI_ARMS_TRANSFERS_SOURCE_KEY),
        display_name=(
            "SIPRI Arms Transfers Database "
            "(Stockholm International Peace Research Institute 2026)"
        ),
        source_type="api",
        supported_observation_families=SIPRI_ARMS_TRANSFERS_SUPPORTED_FAMILIES,
        default_version=SIPRI_ARMS_TRANSFERS_DEFAULT_VERSION,
        homepage_url=SIPRI_ARMS_TRANSFERS_HOMEPAGE_URL,
        attribution_key=SIPRI_ARMS_TRANSFERS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=SIPRI_ARMS_TRANSFERS_COVERAGE_START_YEAR,
            end_year=SIPRI_ARMS_TRANSFERS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "SIPRI Arms Transfers Database (Trade Register): "
                "per-transfer records of major conventional arms "
                "transfers, 1950-2025 (canonical documented coverage "
                "as of the 2026-03-09 SIPRI update). The clean adapter "
                "reads a single cached CSV export (or a cached JSON "
                "wrapper containing base64 CSV bytes) from "
                "`data/raw/sipri_arms_transfers/trade_register.csv` "
                "(or `trade_register.json`) plus a runtime-local "
                "`metadata.json` (gitignored per Always-On Rule #9). "
                "SIPRI copyright; database use must be non-commercial "
                "and in line with SIPRI fair-use policy; commercial "
                "use requires licence / permission; attribution "
                "required. The descriptor advertises TWO observation "
                "families: `arms_transfer_register_row` (canonical "
                "per-transfer raw evidence unit; 3 per-row indicators "
                "`sipri_arms_transfers_tiv_delivered` / "
                "`sipri_arms_transfers_tiv_ordered` / "
                "`sipri_arms_transfers_number_delivered`) and "
                "`arms_transfer_country_year_aggregate` "
                "(deterministic per-`(role, country, year)` aggregate; "
                "sum of TIV delivered over the cached bundle; 2 "
                "per-aggregate indicators "
                "`sipri_arms_transfers_supplier_year_tiv_delivered` / "
                "`sipri_arms_transfers_recipient_year_tiv_delivered`). "
                "**Important caveat:** SIPRI Arms Transfers data is "
                "evidence of recorded arms flows between supplier / "
                "recipient countries and is NOT direct proof of "
                "aggression, proxy sponsorship, or illegality. "
                "Downstream scorers MUST NOT silently treat "
                "arms-transfer TIV totals as a proxy for aggression "
                "/ responsibility without an explicit secondary-source "
                "corroboration step (UCDP external support, sanctions "
                "records, expert-panel reports, manual evidence). The "
                "unified adapter is offline / cache-only in this "
                "slice (`requires_network=False`); live fetch is NOT "
                "supported -- `cache_policy='refresh'` / "
                "`'no_cache'` fails readiness with a structured "
                "`sipri_arms_transfers_unsupported_cache_policy` error "
                "BEFORE `read_raw` / `transform` are called. The "
                "canonical SIPRI Arms Transfers homepage is "
                "`https://www.sipri.org/databases/armstransfers`; "
                "the canonical public app is "
                "`https://armstransfers.sipri.org/ArmsTransfer`; "
                "the canonical backend API is "
                "`https://atbackend.sipri.org/api/p/trades/trade-register-csv/`. "
                "The clean adapter never invokes the network in this "
                "slice. Cached CSV column validation enforces the 8 "
                "required columns `Supplier` / `Recipient` / `Order year` "
                "/ `Delivery year` / `Designation` / `Status` / "
                "`Numbers delivered` / `TIV (delivered)`; missing "
                "required columns fail readiness with a structured "
                "`sipri_arms_transfers_schema_error` error so the "
                "transform layer does NOT silently emit partial "
                "output on a schema contract violation."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_sipri_arms_transfers_descriptor"]


# Re-export the indicator-codes tuple so downstream consumers can
# import the canonical catalog via the descriptor module without
# reaching into ``_constants``.
SIPRI_ARMS_TRANSFERS_DESCRIPTOR_INDICATOR_CODES = (
    SIPRI_ARMS_TRANSFERS_INDICATOR_CODES
)
