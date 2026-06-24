"""World Bank WDI cache-only ``read_raw`` body.

Owns the body of :meth:`WDIAdapter.read_raw` extracted into
a free function :func:`read_world_bank_wdi_cache` so the
adapter class module stays focused on lifecycle wiring +
registration. The function opens the staged per-(year,
indicator) JSON cache via the local cache-only read path
(:func:`_read_cached_wdi_responses` in
:mod:`._cache_reader`) and returns the canonical
:class:`RawReadResult` envelope (wide-format DataFrame +
:class:`RawAsset`).

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi.adapter`
so the adapter class file stays under the 400-line
convention while preserving the same end-to-end behaviour
the reviewer gate requires (no network invocation, full
asset / payload / metadata envelope).

Offline / cache-only contract
-----------------------------

The unified WDI adapter is offline / cache-only in this
slice: ``read_raw`` NEVER invokes the network. It uses the
local :func:`_read_cached_wdi_responses` cache-only read
path (a local parser + long-to-wide shaping over
staged per-(year, indicator) JSON cache payloads).
The staged cache schema is interpreted directly; network
paths are not consulted even when cache is incomplete or
corrupt.

For ``years=None`` (all-available-years semantics per
SRC-REQ-003), the function enumerates the cache root for
valid ``(year, indicator)`` JSON files via the readiness
gate's :func:`_enumerate_cache_files` helper and reads
exactly those ``(year, indicator)`` pairs through the
cache-only path. For explicit ``years=``, the readiness
gate has already validated that every catalog indicator
has a complete, valid cache file under each requested
year dir; ``read_raw`` then reads those exact files.

The wide-format DataFrame (one row per ``(iso3, year)``
with one column per catalog ``variable_name``) is carried
in :attr:`RawReadResult.payload` under ``"wide_df"`` for
the transform layer. The ``read_raw`` call does NOT apply
request year / country filters -- the transform layer does
that on the wide frame so the request-scoping semantics
stay in one place.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from leaders_db.sources.contracts import (
    RawAsset,
    RawReadResult,
    SourceIngestRequest,
)

from ._descriptor import (
    WORLD_BANK_WDI_CACHE_DIR_NAME,
    WORLD_BANK_WDI_COVERAGE_START_YEAR,
    WORLD_BANK_WDI_DEFAULT_VERSION,
    WORLD_BANK_WDI_HOMEPAGE_URL,
    WORLD_BANK_WDI_SOURCE_KEY,
)
from ._paths import (
    _cache_dir,
    _metadata_path,
    _read_metadata_payload,
    _resolve_indicator_codes_from_catalog,
    _resolve_spec_by_variable_name,
)
from ._readiness import _enumerate_cache_files
from ._transform import _read_cached_wdi_responses


def read_world_bank_wdi_cache(
    request: SourceIngestRequest,
) -> RawReadResult:
    """Open the staged per-(year, indicator) JSON cache and
    return the wide-format DataFrame + :class:`RawAsset`.

    See the module docstring for the offline / cache-only
    contract. The function NEVER invokes the network.
    """
    cache_root = _cache_dir(request)

    # Resolve the catalog spec mapping so the cache-only read
    # path can rename raw WDI codes (``SP.POP.TOTL``) to
    # canonical variable names (``wdi_population``). Lazy
    # import to preserve the package boundary
    # (docs/architecture/sources.md §10.1).
    spec_by_variable_name: Mapping[str, Any] | None = None
    try:
        spec_by_variable_name = _resolve_spec_by_variable_name(
            catalog_path=None,
        )
    except FileNotFoundError:
        # The catalog gate already fired in ``check_ready``
        # so this branch is defensive: ``read_raw`` is only
        # reachable when the readiness gate passed, which
        # requires the catalog to be present. If the catalog
        # disappeared between ``check_ready`` and
        # ``read_raw`` (race), fall back to raw-code columns
        # so the read path still works without the network.
        spec_by_variable_name = None

    # For ``years=None``, enumerate the cache files via the
    # readiness-gate helper so the read path operates on
    # exactly the validated ``(year, indicator)`` pairs (no
    # opportunistic file discovery that could miss a file
    # the gate did not inspect). The enumeration is idempotent
    # and fast (one ``iterdir`` per year dir + one
    # ``json.loads`` per file); we deliberately do not cache
    # it across calls because the cache may have changed
    # between ``check_ready`` and ``read_raw``.
    if not request.years:
        discovered_pairs, _malformed = _enumerate_cache_files(
            cache_root,
        )
    else:
        # Explicit ``years=``: the readiness gate has already
        # validated that every catalog indicator has a
        # complete, valid cache file under each requested year
        # dir. Enumerate the (year, catalog_indicator) pairs
        # directly so the read path is deterministic and does
        # not need to re-validate shape. We do NOT request a
        # re-enumeration here because the catalog names ARE
        # the file names per the canonical WDI cache layout
        # (``<year>/<CODE>.json`` where CODE is the catalog's
        # ``raw_column``).
        discovered_pairs = []
        for year in request.years:
            year_int = int(year)
            if year_int < WORLD_BANK_WDI_COVERAGE_START_YEAR:
                continue
            year_dir = cache_root / str(year_int)
            if not year_dir.is_dir():
                continue
            for code in _resolve_indicator_codes_from_catalog(
                catalog_path=None,
            ):
                cache_file = year_dir / f"{code}.json"
                if cache_file.is_file():
                    discovered_pairs.append(
                        (year_int, code, cache_file),
                    )

    wide_df = _read_cached_wdi_responses(
        cache_root,
        years=request.years,
        discovered_pairs=discovered_pairs or None,
        spec_by_variable_name=spec_by_variable_name,
    )
    metadata = _read_metadata_payload(_metadata_path(request))

    # Surface the cached/fetched counts the local read path
    # attached to ``df.attrs`` so the result envelope carries
    # them for downstream audits. ``indicators_fetched`` is
    # always 0 because the cache-only read path never invokes
    # the network.
    indicators_cached = int(
        getattr(wide_df, "attrs", {}).get("indicators_cached", 0),
    )
    indicators_fetched = int(
        getattr(wide_df, "attrs", {}).get("indicators_fetched", 0),
    )

    asset = RawAsset(
        asset_id=f"{WORLD_BANK_WDI_SOURCE_KEY}:{WORLD_BANK_WDI_CACHE_DIR_NAME}",
        source_id=request.source_id,
        version=WORLD_BANK_WDI_DEFAULT_VERSION,
        media_type="application/json",
        path=cache_root,
        url=WORLD_BANK_WDI_HOMEPAGE_URL,
        checksum_sha256=None,
        retrieved_at=None,
        immutable=True,
    )
    return RawReadResult(
        source_id=request.source_id,
        assets=(asset,),
        payload={
            "wide_df": wide_df,
            "metadata": metadata,
            "cache_root": cache_root,
            "indicators_cached": indicators_cached,
            "indicators_fetched": indicators_fetched,
            "discovered_pairs": tuple(discovered_pairs),
        },
        warnings=(),
    )


__all__ = ["read_world_bank_wdi_cache"]
