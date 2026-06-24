"""World Bank WDI offline cache-only read path.

Owns the per-(year, indicator) cache-file parsing + long-to-
wide pivot that backs :meth:`WDIAdapter.read_raw`. The
functions in this module NEVER invoke the network; they read
the staged per-(year, indicator) JSON cache files directly
and produce the wide-format DataFrame the existing transform
layer already consumes.

Split out of
:mod:`leaders_db.sources.adapters.world_bank_wdi._transform`
so the observation-emission module stays focused on the
:class:`NormalizedObservation` build loop + raw-locator
construction. The split keeps each module under the 400-line
convention.

The local parser + pivot is intentionally explicit and constrained
to the staged cache contract so the unified adapter can keep its
no-network guarantee independent from historical execution paths.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

# Local mirror of the WDI v2 aggregate-region ISO3 denylist. The
# canonical authoritative list lives in
# :data:`leaders_db.ingest.wdi_io._WDI_AGGREGATE_ISO3_CODES`. We
# keep a local copy so the cache-only read path does NOT have to
# import :mod:`leaders_db.ingest.wdi_io` (which would pull in the
# full ingest package and ``requests``).
# Derived on 2026-06-18 from the live ``/v2/country`` response;
# any aggregate added by WDI in the future must be appended in
# BOTH places. This local copy is authoritative for the
# staged cache reader.
_LOCAL_WDI_AGGREGATE_ISO3_CODES: frozenset[str] = frozenset({
    "AFE", "AFR", "AFW", "ARB", "BEA", "BEC", "BHI", "BLA", "BMN",
    "BSS", "CAA", "CEA", "CEB", "CEU", "CLA", "CME", "CSA", "CSS",
    "DEA", "DEC", "DLA", "DMN", "DNS", "DSA", "DSF", "DSS", "EAP",
    "EAR", "EAS", "ECA", "ECS", "EMU", "EUU", "FCS", "FXS", "HIC",
    "HPC", "IBB", "IBD", "IBT", "IDA", "IDB", "IDX", "INX", "LAC",
    "LCN", "LDC", "LIC", "LMC", "LMY", "LTE", "MDE", "MEA", "MIC",
    "MNA", "NAC", "NAF", "NRS", "NXS", "OED", "OSS", "PRE", "PSS",
    "PST", "RRS", "SAS", "SSA", "SSF", "SST", "SXZ", "TEA", "TEC",
    "TLA", "TMN", "TSA", "TSS", "UMC", "WLD", "XZN",
})


def _parse_cached_wdi_payload(
    payload: list[Any],
    *,
    code: str,
    year: int,
) -> pd.DataFrame:
    """Parse one already-loaded WDI v2 cache payload into a long-format
    DataFrame.

    Parses the same WDI v2 cache response shape and value
    fields as the historical cache contract so downstream
    semantics remain stable. This parser is local to
    the unified adapter and does not import any HTTP
    dependency.

    Returns a frame with columns ``["iso3", "year",
    "indicator_code", "value"]``. Rows where ``value`` is
    ``None`` (WDI's null) are kept; the orchestrator handles
    NaN conversion + aggregate filter + long-to-wide pivot.
    Raises ``ValueError`` on shape mismatch (defensive only --
    the caller validates JSON shape in
    :func:`_validate_cached_json_shape` before invoking this
    helper).
    """
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError(
            f"WDI cached payload for {code} year {year} is not a "
            f"2-element array; got {type(payload).__name__}"
        )
    data = payload[1]
    if not isinstance(data, list):
        raise ValueError(
            f"WDI cached payload for {code} year {year} data slot "
            f"is not a list; got {type(data).__name__}"
        )
    rows: list[dict[str, object]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        iso3 = entry.get("countryiso3code")
        if not iso3:
            continue
        rows.append(
            {
                "iso3": str(iso3),
                "year": int(entry.get("date", year)),
                "indicator_code": str(
                    entry.get("indicator", {}).get("id", code) or code
                ),
                "value": entry.get("value", None),
            }
        )
    return pd.DataFrame(
        rows, columns=["iso3", "year", "indicator_code", "value"],
    )


def _empty_wide_dataframe() -> pd.DataFrame:
    """Return the empty wide-format DataFrame used when no cache
    files are available.

    Carries the canonical ``indicators_cached`` /
    ``indicators_fetched`` ``df.attrs`` so callers consume the
    frame with the same accessor contract expected by existing
    WDI transform logic.
    """
    df = pd.DataFrame(columns=["iso3", "year"])
    df.attrs["indicators_cached"] = 0
    df.attrs["indicators_fetched"] = 0
    return df


def _read_cached_wdi_responses(
    cache_root: Path,
    *,
    years: tuple[int, ...] | None,
    discovered_pairs: Iterable[tuple[int, str, Path]] | None = None,
    spec_by_variable_name: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Read WDI v2 JSON cache files directly and return a wide-format
    DataFrame.

    The function is the unified WDI adapter's offline /
    cache-only read path. It NEVER invokes the network; it
    reads only the per-(year, indicator) JSON files staged
    under ``cache_root`` and produces the wide-format
    ``DataFrame`` consumed by the transform layer,
    including the ``df.attrs["indicators_cached"]`` /
    ``indicators_fetched`` counter contract.

    ``cache_root``: staged per-(year, indicator) JSON cache
    root, e.g. ``<raw_root>/world_bank_wdi/cache``. ``years``:
    optional explicit years (None = all years present).
    ``discovered_pairs``: optional readiness-validated
    ``(year, code, path)`` tuples; when provided the read path
    uses exactly these and never re-enumerates the cache root.
    ``spec_by_variable_name``: optional rename map from raw
    WDI codes (``SP.POP.TOTL``) to canonical ``variable_name``
    columns (``wdi_population``).
    """
    pair_list = _resolve_cache_pairs(
        cache_root,
        discovered_pairs=discovered_pairs,
        years=years,
    )
    if not pair_list:
        return _empty_wide_dataframe()

    long_frames, cached_codes = _read_cached_payloads(pair_list)
    if not long_frames:
        return _empty_wide_dataframe()

    wide = _pivot_long_to_wide(long_frames)
    wide = _rename_wide_columns(wide, spec_by_variable_name)
    wide = _coerce_wide_types(wide)

    wide.attrs["indicators_cached"] = len(cached_codes)
    wide.attrs["indicators_fetched"] = 0
    return wide


def _resolve_cache_pairs(
    cache_root: Path,
    *,
    discovered_pairs: Iterable[tuple[int, str, Path]] | None,
    years: tuple[int, ...] | None,
) -> list[tuple[int, str, Path]]:
    """Resolve the list of ``(year, code, path)`` tuples the read
    path will consume.

    Honors the readiness-gate-discovered pairs when supplied
    (the "enumerate valid cache files and pass only those
    exact years/indicator codes" seam). Falls back to a
    defensive cache-root enumeration when no discovered pairs
    are provided. Applies the ``years=`` filter as the last
    step so explicit years always narrow the work list before
    cache files are opened.
    """
    if discovered_pairs is not None:
        pair_list = list(discovered_pairs)
    else:
        pair_list = _enumerate_cache_pairs_fallback(cache_root)
    if years is None:
        return pair_list
    year_set = {int(y) for y in years}
    return [
        (y, code, path)
        for (y, code, path) in pair_list
        if y in year_set
    ]


def _enumerate_cache_pairs_fallback(
    cache_root: Path,
) -> list[tuple[int, str, Path]]:
    """Defensive cache-root enumeration when readiness did not
    pre-validate the work list.

    Only considers files with a numeric year directory and a
    ``.json`` extension. Does NOT validate JSON shape
    (readiness owns that gate).
    """
    pair_list: list[tuple[int, str, Path]] = []
    if not cache_root.is_dir():
        return pair_list
    for year_dir in sorted(cache_root.iterdir(), key=lambda p: p.name):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year_int = int(year_dir.name)
        for cache_file in sorted(
            year_dir.iterdir(), key=lambda p: p.name,
        ):
            if not cache_file.is_file() or cache_file.suffix != ".json":
                continue
            pair_list.append((year_int, cache_file.stem, cache_file))
    return pair_list


def _read_cached_payloads(
    pair_list: list[tuple[int, str, Path]],
) -> tuple[list[pd.DataFrame], set[str]]:
    """Read every (year, indicator) cache file into a long-format
    DataFrame.

    Defensive: a corrupt file is silently skipped rather than
    triggering any fallback path -- that's the point of the
    cache-only contract. The readiness gate should have blocked
    before ``read_raw`` was reached; this guard covers races
    where a file is corrupted between readiness and read.
    """
    long_frames: list[pd.DataFrame] = []
    cached_codes: set[str] = set()
    for year_int, code, cache_file in pair_list:
        try:
            payload_obj = json.loads(
                cache_file.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload_obj, list) or len(payload_obj) < 2:
            continue
        try:
            long_frames.append(
                _parse_cached_wdi_payload(
                    payload_obj, code=code, year=year_int,
                ),
            )
        except ValueError:
            continue
        cached_codes.add(code)
    return long_frames, cached_codes


def _pivot_long_to_wide(
    long_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    """Concatenate + filter aggregate ISO3 codes + pivot to wide
    format for downstream transformation.
    """
    long_df = pd.concat(long_frames, ignore_index=True)
    long_df = long_df.loc[
        ~long_df["iso3"].isin(_LOCAL_WDI_AGGREGATE_ISO3_CODES)
    ].reset_index(drop=True)
    return long_df.pivot_table(
        index=["iso3", "year"],
        columns="indicator_code",
        values="value",
        aggfunc="first",
    )


def _rename_wide_columns(
    wide: pd.DataFrame,
    spec_by_variable_name: Mapping[str, Any] | None,
) -> pd.DataFrame:
    """Rename raw WDI codes to catalog ``variable_name`` columns.

    ``spec_by_variable_name`` is keyed by ``variable_name``; we
    invert it to a ``raw_column -> variable_name`` rename map.
    Unknown raw codes keep their raw names so the transform
    layer's ``_DEFAULT_INDICATOR_UNITS`` fallback still applies.
    """
    if spec_by_variable_name is None:
        return wide
    raw_to_variable: dict[str, str] = {}
    for variable_name, spec in spec_by_variable_name.items():
        raw_code = getattr(spec, "raw_column", None)
        if (
            isinstance(raw_code, str)
            and raw_code.strip()
            and isinstance(variable_name, str)
            and variable_name.strip()
        ):
            raw_to_variable[raw_code] = variable_name
    if not raw_to_variable:
        return wide
    return wide.rename(columns=raw_to_variable)


def _coerce_wide_types(wide: pd.DataFrame) -> pd.DataFrame:
    """Coerce wide-frame columns to canonical dtypes.

    Resets the index (so ``iso3`` / ``year`` are regular
    columns), coerces ``year`` to ``int``, and coerces every
    indicator column to ``float`` (NaN for absent cells).
    """
    wide = wide.reset_index()
    wide["year"] = wide["year"].astype(int)
    for col in wide.columns:
        if col in {"iso3", "year"}:
            continue
        wide[col] = pd.to_numeric(wide[col], errors="coerce").astype(float)
    return wide


def load_wdi_cache_index(
    cache_file: Path,
) -> dict[str, int] | None:
    """Return ``{countryiso3code: numeric_index}`` for a WDI v2
    cache file, or ``None`` on any read / shape error.

    The WDI v2 2-element response array (``[metadata, data]``)
    stores country records as numeric indices under
    ``payload[1]``. Each entry carries a ``countryiso3code``
    field. The readiness + audit contract
    (``docs/requirements/sources.md`` §6 SRC-PROV-001) requires
    every emitted observation to carry a JSON pointer that
    resolves to the underlying raw record; the only stable
    pointer is ``/1/<numeric_index>`` because
    ``countryiso3code`` is data (and an aggregate filter may
    drop entries between the upstream cache and the emitted
    observation). The pointer is intentionally a numeric
    offset, not an ISO3 key, so audit code can re-parse the
    cache file and recover the canonical raw record byte-for-byte.

    Returns ``None`` when the cache file is missing /
    unreadable / non-JSON / not the documented 2-element
    shape, or when entries lack a non-empty ``countryiso3code``
    (skipped silently -- the cache can carry pre-filter
    aggregates that are dropped by the same aggregate-filter
    contract).
    Callers handle a ``None`` return by setting the
    per-observation ``raw_locator.json_pointer`` to ``None``.
    """
    if not cache_file.is_file():
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    data = payload[1]
    if not isinstance(data, list):
        return None
    index: dict[str, int] = {}
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            continue
        iso3 = entry.get("countryiso3code")
        if not isinstance(iso3, str) or not iso3.strip():
            continue
        # When the cache file carries the same country twice
        # (WDI does not, but a malformed cache might), the
        # first seen entry keeps the canonical pointer.
        index.setdefault(iso3.strip(), i)
    return index


__all__ = [
    "_enumerate_cache_pairs_fallback",
    "_parse_cached_wdi_payload",
    "_read_cached_payloads",
    "_read_cached_wdi_responses",
    "_resolve_cache_pairs",
    "load_wdi_cache_index",
]
