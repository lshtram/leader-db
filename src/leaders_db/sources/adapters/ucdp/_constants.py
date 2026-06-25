"""Shared constants for the unified-source UCDP adapter.

This module owns the small set of source-specific constants
shared across the per-row observation-emission / construction
modules so the cross-module import graph stays acyclic.

The constants are also re-exported from the package root
:mod:`leaders_db.sources.adapters.ucdp` so callers can
``from leaders_db.sources.adapters.ucdp import UCDP_TRANSFORM_NAME``
without knowing which submodule the symbol lives in.
"""

from __future__ import annotations

# Transform-name string carried on every NormalizedObservation's
# ``transform_locator``. Surfaces the legacy reader /
# transform that produced the observation so downstream
# scoring can audit the parse path. The legacy
# ``read_ucdp`` reader + ``aggregate_events_to_country_year``
# aggregator are the production transform pipeline.
UCDP_TRANSFORM_NAME: str = "read_ucdp"

# Quality-flag string carried on every observation's
# ``quality_flags`` tuple. Documents that the UCDP
# observation is an event-level aggregation rather than a
# direct country-year measurement; downstream audit code
# can recognize the locator convention from this flag
# without re-reading the catalog.
UCDP_AGGREGATE_QUALITY_FLAG: str = "ucdp_aggregated_from_events"


__all__ = [
    "UCDP_AGGREGATE_QUALITY_FLAG",
    "UCDP_TRANSFORM_NAME",
]
