"""Descriptor factory for the clean IAEA Safeguards status-list adapter.

This module owns the canonical :class:`SourceDescriptor` for the
IAEA Safeguards status-list source. The descriptor advertises
the static source metadata the registry exposes for source
discovery (SRC-ID-003): the canonical slug ``iaea_safeguards``,
the canonical IAEA homepage URL, the single-point 2025 coverage
envelope (the canonical status date is 2025-12-31), the single
``nuclear_safeguards_status_country`` observation family, and
the offline / cache-only network policy.

Coverage envelope
-----------------

The IAEA Safeguards Status List is a single-point legal / status
snapshot -- the canonical probed stamp is "as of 31 December
2025". The descriptor advertises a single-year envelope
(``start_year == end_year == 2025``) so downstream query code
can refuse to dispatch out-of-coverage year requests. The
readiness envelope surfaces a structured ``YEAR_ABSENT``
warning on out-of-coverage year requests so the runner never
silently proxies an out-of-coverage year to the nearest
in-coverage year (SRC-COV-002 / SRC-COV-003). The prototype's
target year 2023 falls OUTSIDE the canonical envelope; the
readiness gate fires the ``YEAR_ABSENT`` warning and the
transform emits zero observations for that year (no stale-proxy
fill).

Source-type semantics
---------------------

The descriptor advertises ``source_type="document"`` because the
canonical status-list is delivered as a public PDF document. The
unified adapter in this slice is offline / cache-only
(``requires_network=False``); the readiness gate blocks
``cache_policy="refresh"`` / ``"no_cache"`` with a structured
``unsupported_cache_policy`` error so the runner refuses to
dispatch ``read_raw`` / ``transform`` rather than silently
surfacing an HTTP-fetched payload.

Observation-family shape
------------------------

The descriptor advertises a single observation family
(``nuclear_safeguards_status_country``) so downstream query code
can filter by family without consulting the per-source catalog.
The catalog carries 4 source-native indicators -- one per
non-State column in the cached PDF table
(``Safeguards Agreement`` / ``INFCIRC`` /
``Additional Protocol`` / ``Small Quantities Protocol``). The
catalog deliberately does NOT include a separate
``iaea_safeguards_safeguards_agreement_type`` indicator: the
canonical IAEA table has a single ``Safeguards Agreement``
column carrying the composite status label (e.g. ``In Force:
153`` / ``Not in Force: 66`` / ``N/A``), NOT a separate type
column; the adapter never invents a type column from the
composite label. The catalog is preserved on
:data:`IAEA_SAFEGUARDS_INDICATOR_CODES`.

Attribution caveat
------------------

The descriptor's ``coverage_hint.notes`` carries the explicit
caveat that this source captures safeguards / legal / status
evidence and is NOT a direct nuclear-weapons score or proof of
safeguards compliance / non-compliance by itself. Downstream
scorers MUST NOT silently treat a ``"not in force"`` AP cell as
proof of non-cooperation; the descriptor's coverage notes carry
the caveat per the IAEA's "download/copy/use with
acknowledgement" terms, and the Stage 11 confidence formula
penalises the temporal-fit gap between the cached status date
and the prototype's target year.

Attribution text
----------------

The unified ``IAEA_SAFEGUARDS_ATTRIBUTION_TEXT`` constant is
byte-identical to the ``iaea_safeguards`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_iaea_safeguards_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    IAEA_SAFEGUARDS_ATTRIBUTION_KEY,
    IAEA_SAFEGUARDS_COVERAGE_END_YEAR,
    IAEA_SAFEGUARDS_COVERAGE_START_YEAR,
    IAEA_SAFEGUARDS_DEFAULT_VERSION,
    IAEA_SAFEGUARDS_HOMEPAGE_URL,
    IAEA_SAFEGUARDS_INDICATOR_CODES,
    IAEA_SAFEGUARDS_PDF_NAME,
    IAEA_SAFEGUARDS_PDF_URL,
    IAEA_SAFEGUARDS_SOURCE_KEY,
    IAEA_SAFEGUARDS_STATUS_DATE,
    IAEA_SAFEGUARDS_SUPPORTED_FAMILIES,
)


def build_iaea_safeguards_descriptor() -> SourceDescriptor:
    """Build the canonical IAEA Safeguards :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes
    for source discovery (SRC-ID-003). The values mirror the
    canonical citation block in ``docs/sources/attributions.md``
    (Rule #15).

    The descriptor advertises ``source_type="document"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally
    for IAEA Safeguards (the unified adapter is offline /
    cache-only in this slice; the cache-policy gate blocks
    unsupported policies with a structured
    ``unsupported_cache_policy`` error).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=IAEA_SAFEGUARDS_SOURCE_KEY),
        display_name=(
            "IAEA Safeguards Status List "
            "(International Atomic Energy Agency, status as of "
            "31 December 2025)"
        ),
        source_type="document",
        supported_observation_families=IAEA_SAFEGUARDS_SUPPORTED_FAMILIES,
        default_version=IAEA_SAFEGUARDS_DEFAULT_VERSION,
        homepage_url=IAEA_SAFEGUARDS_HOMEPAGE_URL,
        attribution_key=IAEA_SAFEGUARDS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=IAEA_SAFEGUARDS_COVERAGE_START_YEAR,
            end_year=IAEA_SAFEGUARDS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "IAEA Safeguards Status List, Conclusion of Safeguards "
                "Agreements, Additional Protocols and Small Quantities "
                "Protocols: a single-point legal / status snapshot "
                "covering ~190 States, status as of "
                f"{IAEA_SAFEGUARDS_STATUS_DATE}. The clean adapter "
                "reads the runtime-local staged PDF "
                f"(`{IAEA_SAFEGUARDS_PDF_NAME}`) from "
                "`data/raw/iaea_safeguards/` plus a runtime-local "
                "`metadata.json` (gitignored per Always-On Rule #9). "
                "The descriptor advertises ONE observation family "
                "(`nuclear_safeguards_status_country`) and 4 "
                "source-native catalog indicators -- one per "
                "non-State column in the cached PDF table "
                "(`iaea_safeguards_safeguards_agreement_status`, "
                "`iaea_safeguards_infcirc_number`, "
                "`iaea_safeguards_additional_protocol_status`, "
                "`iaea_safeguards_small_quantities_protocol_status`). "
                "The catalog deliberately does NOT include a "
                "separate `iaea_safeguards_safeguards_agreement_type` "
                "indicator: the canonical IAEA table has a single "
                "`Safeguards Agreement` column carrying the composite "
                "status label (e.g. `In Force: 153` / "
                "`Not in Force: 66` / `N/A`), NOT a separate type "
                "column; the adapter never invents a type column "
                "from the composite label. **Important caveat:** "
                "this source captures safeguards legal / status "
                "evidence -- the presence / status of a Comprehensive "
                "Safeguards Agreement (the composite label), the "
                "status of an Additional Protocol (signed / approved "
                "/ in force / not in force / not signed), the status "
                "of a Small Quantities Protocol (modified / original "
                "/ not applicable / not in force), and the INFCIRC "
                "document identifier -- and is NOT a direct "
                "nuclear-weapons score or proof of compliance / "
                "non-compliance by itself. Downstream scorers MUST "
                "NOT silently treat a `not in force` AP cell as "
                "proof of non-cooperation; the Stage 11 confidence "
                "formula penalises the temporal-fit gap between the "
                "cached status date and the prototype's target year "
                "(2023). The unified adapter preserves the "
                "source-native country display names verbatim and "
                "does NOT invent ISO3 codes (`country_code` remains "
                "`None` until later matching / resolution stages). "
                "The canonical IAEA Safeguards homepage is "
                f"`{IAEA_SAFEGUARDS_HOMEPAGE_URL}`; the canonical "
                f"public status-list PDF is `{IAEA_SAFEGUARDS_PDF_URL}`. "
                "The clean adapter never invokes the network in this "
                "slice. `cache_policy='refresh'` / `'no_cache'` fails "
                "readiness with a structured "
                "`iaea_safeguards_unsupported_cache_policy` error "
                "BEFORE `read_raw` / `transform` are called."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_iaea_safeguards_descriptor"]


# Re-export the indicator-codes tuple so downstream consumers can
# import the canonical catalog via the descriptor module without
# reaching into ``_constants``.
IAEA_SAFEGUARDS_DESCRIPTOR_INDICATOR_CODES = IAEA_SAFEGUARDS_INDICATOR_CODES
