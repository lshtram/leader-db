"""Descriptor factory for the clean CTBTO Treaty Status adapter.

This module owns the canonical :class:`SourceDescriptor` for
the CTBTO States Signatories source. The descriptor advertises
the static source metadata the registry exposes for source
discovery (SRC-ID-003): the canonical slug
``ctbto_treaty_status``, the canonical CTBTO homepage URL, the
single-point 2024 coverage envelope (the canonical snapshot
date is 2024-03-13), the single
``nuclear_treaty_status_country`` observation family, and the
offline / cache-only network policy.

Coverage envelope
-----------------

The CTBTO States Signatories page is a single-point
treaty-status snapshot -- the canonical probed stamp is
"status as of 13 March 2024" (the date of the latest ratifying
state Papua New Guinea). The descriptor advertises a
single-year envelope (``start_year == end_year == 2024``) so
downstream query code can refuse to dispatch out-of-coverage
year requests. The readiness envelope surfaces a structured
``YEAR_ABSENT`` warning on out-of-coverage year requests so
the runner never silently proxies an out-of-coverage year to
the nearest in-coverage year (SRC-COV-002 / SRC-COV-003). The
prototype's target year 2023 falls OUTSIDE the canonical
envelope; the readiness gate fires the ``YEAR_ABSENT`` warning
and the transform emits zero observations for that year (no
stale-proxy fill).

Source-type semantics
---------------------

The descriptor advertises ``source_type="document"`` because
the canonical CTBTO States Signatories page is delivered as a
public HTML table (and the typical user-staged cached export
is a CSV derived from that table). The unified adapter in
this slice is offline / cache-only (``requires_network=False``);
the readiness gate blocks ``cache_policy="refresh"`` /
``"no_cache"`` with a structured
``ctbto_treaty_status_unsupported_cache_policy`` error so the
runner refuses to dispatch ``read_raw`` / ``transform`` rather
than silently surfacing an HTTP-fetched payload.

Observation-family shape
------------------------

The descriptor advertises a single observation family
(``nuclear_treaty_status_country``) so downstream query code
can filter by family without consulting the per-source
catalog. The catalog carries 2 source-derived status
indicators by default -- one per date-bearing column in the
canonical CTBTO page:

- ``ctbto_treaty_status_signature_status`` -- the source-
  derived signature status: ``"signed"`` iff a signature date
  is present in the cached row, ``"not_signed"`` otherwise.
- ``ctbto_treaty_status_ratification_status`` -- the source-
  derived ratification status: ``"ratified"`` iff a
  ratification date is present in the cached row,
  ``"not_ratified"`` otherwise.

The catalog deliberately does NOT include a default
``ctbto_treaty_status_annex_2_status`` indicator: the canonical
CTBTO States Signatories page does NOT carry an Annex 2 flag
column (Annex 2 refers to the 44 States that the CTBTO PrepCom
identified as needing to ratify the CTBT for the Treaty to
enter into force, but the public table does NOT surface an
Annex 2 status column); the adapter never invents an Annex 2
flag from missing source-native data. The transform layer
preserves an OPTIONAL Annex 2 indicator emission when the
cached fixture / source-native data carries an explicit Annex 2
flag column, but the default 2-indicator catalog does NOT
include the Annex 2 indicator.

Legal caveat
------------

CTBTO signature / ratification status is a TREATY-STATUS
observation, NOT direct proof of nuclear behaviour, compliance,
or non-compliance. The descriptor's ``coverage_hint.notes``
carries the explicit caveat. Downstream scorers MUST NOT
silently treat an unsigned / unratified status cell as proof
of nuclear activity or non-cooperation; the Stage 11 confidence
formula penalises the temporal-fit gap between the cached
snapshot date (2024-03-13) and the prototype's target year
(2023).

Attribution text
----------------

The unified ``CTBTO_TREATY_STATUS_ATTRIBUTION_TEXT`` constant
is byte-identical to the ``ctbto_treaty_status`` section in
``docs/sources/attributions.md`` (Always-On Rule #15). The
:func:`test_ctbto_treaty_status_attribution_text_matches_attributions_doc`
drift guard enforces byte-identity.
"""

from __future__ import annotations

from leaders_db.sources.contracts import (
    CoverageHint,
    SourceDescriptor,
    SourceId,
)

from ._constants import (
    CTBTO_TREATY_STATUS_ATTRIBUTION_KEY,
    CTBTO_TREATY_STATUS_COVERAGE_END_YEAR,
    CTBTO_TREATY_STATUS_COVERAGE_START_YEAR,
    CTBTO_TREATY_STATUS_CSV_NAME,
    CTBTO_TREATY_STATUS_DEFAULT_VERSION,
    CTBTO_TREATY_STATUS_HOMEPAGE_URL,
    CTBTO_TREATY_STATUS_HTML_NAME,
    CTBTO_TREATY_STATUS_INDICATOR_CODES,
    CTBTO_TREATY_STATUS_SNAPSHOT_DATE,
    CTBTO_TREATY_STATUS_SOURCE_KEY,
    CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES,
    CTBTO_TREATY_STATUS_TERMS_URL,
)


def build_ctbto_treaty_status_descriptor() -> SourceDescriptor:
    """Build the canonical CTBTO Treaty Status :class:`SourceDescriptor`.

    The descriptor is the static metadata the registry exposes
    for source discovery (SRC-ID-003). The values mirror the
    canonical citation block in ``docs/sources/attributions.md``
    (Rule #15).

    The descriptor advertises ``source_type="document"`` and
    ``requires_network=False`` so downstream query code and the
    runner can refuse to dispatch network I/O unconditionally
    for CTBTO Treaty Status (the unified adapter is offline /
    cache-only in this slice; the cache-policy gate blocks
    unsupported policies with a structured
    ``ctbto_treaty_status_unsupported_cache_policy`` error).
    """
    return SourceDescriptor(
        source_id=SourceId(slug=CTBTO_TREATY_STATUS_SOURCE_KEY),
        display_name=(
            "CTBTO States Signatories, Comprehensive Nuclear-Test-"
            "Ban Treaty signature and ratification status "
            "(Comprehensive Nuclear-Test-Ban Treaty Organization, "
            f"status as of {CTBTO_TREATY_STATUS_SNAPSHOT_DATE})"
        ),
        source_type="document",
        supported_observation_families=CTBTO_TREATY_STATUS_SUPPORTED_FAMILIES,
        default_version=CTBTO_TREATY_STATUS_DEFAULT_VERSION,
        homepage_url=CTBTO_TREATY_STATUS_HOMEPAGE_URL,
        attribution_key=CTBTO_TREATY_STATUS_ATTRIBUTION_KEY,
        coverage_hint=CoverageHint(
            start_year=CTBTO_TREATY_STATUS_COVERAGE_START_YEAR,
            end_year=CTBTO_TREATY_STATUS_COVERAGE_END_YEAR,
            countries=None,
            leaders=None,
            notes=(
                "CTBTO States Signatories, Comprehensive Nuclear-Test-"
                "Ban Treaty signature and ratification status: a "
                "single-point treaty-status snapshot covering ~196 "
                f"States, status as of {CTBTO_TREATY_STATUS_SNAPSHOT_DATE}. "
                f"The clean adapter reads the runtime-local staged "
                f"CSV (`{CTBTO_TREATY_STATUS_CSV_NAME}`) "
                f"(optionally a cached HTML export at "
                f"`{CTBTO_TREATY_STATUS_HTML_NAME}`) from "
                "`data/raw/ctbto_treaty_status/` plus a runtime-local "
                "`metadata.json` (gitignored per Always-On Rule #9). "
                "The descriptor advertises ONE observation family "
                "(`nuclear_treaty_status_country`) and the default "
                "2-indicator catalog "
                "(`ctbto_treaty_status_signature_status`, "
                "`ctbto_treaty_status_ratification_status`); the "
                "optional `ctbto_treaty_status_annex_2_status` "
                "indicator is only emitted when the cached fixture "
                "carries an explicit Annex 2 flag column (the "
                "canonical CTBTO page does NOT carry an Annex 2 flag, "
                "so the adapter never invents an Annex 2 status from "
                "missing source-native data). Signature status is "
                "`signed` iff a signature date is present in the "
                "cached row, `not_signed` otherwise; ratification "
                "status is `ratified` iff a ratification date is "
                "present in the cached row, `not_ratified` otherwise; "
                "the transform never inverts these rules. Raw "
                "signature / ratification dates are preserved verbatim "
                "as strings on the audit-trail extension payload "
                "(the adapter does not coerce them to numeric years "
                "that could mislead Stage 11 confidence calculations). "
                "**Important caveat:** CTBTO signature / ratification "
                "status is a TREATY-STATUS observation -- the "
                "presence / status of a State signature and "
                "ratification of the Comprehensive Nuclear-Test-Ban "
                "Treaty -- and is NOT direct proof of nuclear "
                "behaviour, compliance, or non-compliance. Downstream "
                "scorers MUST NOT silently treat an unsigned / "
                "unratified status cell as proof of nuclear activity "
                "or non-cooperation; the descriptor's "
                "`coverage_hint.notes` carries the explicit caveat "
                "and the Stage 11 confidence formula penalises the "
                "temporal-fit gap between the cached snapshot date "
                f"({CTBTO_TREATY_STATUS_SNAPSHOT_DATE}) and the "
                "prototype's target year (2023). The unified adapter "
                "preserves the source-native State display name "
                "verbatim and does NOT invent ISO3 codes "
                "(`country_code` remains `None` until later matching "
                "/ resolution stages introduce a canonical ISO3 "
                "mapping). The canonical CTBTO States Signatories "
                f"page is `{CTBTO_TREATY_STATUS_HOMEPAGE_URL}`; the "
                "canonical CTBTO terms-of-use page that governs the "
                "use of the cached CTBTO material is "
                f"`{CTBTO_TREATY_STATUS_TERMS_URL}`. The CTBTO terms "
                "permit download / copy / use with acknowledgement "
                "for personal, non-commercial, research / teaching "
                "use; the pipeline does NOT redistribute the copied "
                "full table in public outputs. The clean adapter "
                "never invokes the network in this slice. "
                "`cache_policy='refresh'` / `'no_cache'` fails "
                "readiness with a structured "
                "`ctbto_treaty_status_unsupported_cache_policy` "
                "error BEFORE `read_raw` / `transform` are called."
            ),
        ),
        requires_manual_approval=False,
        requires_network=False,
    )


__all__ = ["build_ctbto_treaty_status_descriptor"]


# Re-export the indicator-codes tuple so downstream consumers can
# import the canonical catalog via the descriptor module without
# reaching into ``_constants``.
CTBTO_TREATY_STATUS_DESCRIPTOR_INDICATOR_CODES = (
    CTBTO_TREATY_STATUS_INDICATOR_CODES
)
