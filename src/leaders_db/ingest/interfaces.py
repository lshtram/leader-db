"""Shared Stage 2 ingestion interface and payload models.

This module defines the typed contract used by protocol-based Stage 2
sources:

- :class:`IngestRequest`
- :class:`SourceReadiness`
- :class:`RawSourceBundle`
- :class:`NormalizedSourceFrame`
- :class:`IngestResult`
- :class:`SourceAdapter`

The Penn World Table 10.01 adapter is the first production implementation of
this protocol. Later slices should reuse the same shared contract.

The registry in :mod:`leaders_db.ingest.registry` is an opt-in protocol
entry-point; the primary CLI dispatch path still resolves sources through
``STAGE2_ADAPTERS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class IngestRequest(BaseModel):
    """Typed input contract for every Stage 2 adapter call.

    The :attr:`source_key` is the canonical key (matches the
    ``STAGE2_ADAPTERS`` dispatch table + the ``data/raw/<key>/``
    folder). The ``year`` / ``years`` pair follows the contract
    spelled out in ``docs/sources/ingestion-plan.md``: callers may
    set EITHER ``year`` (a single year filter) OR ``years`` (a
    tuple of years to include), but NOT both inconsistently. The
    cross-field validator below rejects ``year not in years``
    when both are supplied.

    Durable fields:

    - :attr:`country_filter`: ISO3 tuple limiting ingestion to
      specific countries (default: empty tuple = no filter).
    - :attr:`raw_root` / :attr:`processed_root`: optional
      overrides for the data-lake roots (default: project defaults
      resolved through :mod:`leaders_db.paths`).
    - :attr:`parquet_path`: optional EXACT output parquet path
      override (default: ``None`` = use ``<processed_root>/<source>/``
      canonical layout). When set, the writer persists the parquet
      at this exact path -- useful for callers that want a
      non-default filename or a layout outside the
      ``<processed_root>/<source>/`` convention.
    - :attr:`catalog_path`: optional EXACT indicator catalog path
      override (default: ``None`` = use the per-source
      ``catalog.csv``). When set, the transform layer reads the
      catalog from this exact path.
    - :attr:`database_url`: optional SQLAlchemy URL override
      (default: ``None`` = use the run-config's database URL).
    - :attr:`force_refresh`: when ``True``, adapters that cache
      remote fetches bypass the cache and re-fetch (default:
      ``False``).
    - :attr:`allow_network`: when ``False``, adapters that would
      otherwise reach the network raise (default: ``False``;
      Stage 2 is local-first per ``docs/architecture/local-data-store.md``).
    """

    source_key: str
    year: int | None = None
    years: tuple[int, ...] = ()
    country_filter: tuple[str, ...] = ()
    raw_root: Path | None = None
    processed_root: Path | None = None
    parquet_path: Path | None = None
    catalog_path: Path | None = None
    database_url: str | None = None
    force_refresh: bool = False
    allow_network: bool = False

    @property
    def effective_years(self) -> tuple[int, ...]:
        """Return the sorted-unique effective year filter.

        - ``years`` set (non-empty) -> sorted unique ``years``.
        - ``year`` set, ``years`` empty -> ``(year,)``.
        - Both set consistent (``year in years``) -> sorted
          unique ``years``.
        - Both set inconsistent (``year not in years``) -> the
          model validator raises before this property is reached.
        - Neither set -> empty tuple (no year filter).
        """
        if self.years:
            return tuple(sorted(set(self.years)))
        if self.year is not None:
            return (self.year,)
        return ()

    @model_validator(mode="after")
    def _validate_year_consistency(self) -> IngestRequest:
        """Reject ``year`` + ``years`` disagreement.

        The model only raises a plain :class:`ValueError`; Pydantic
        wraps it in :class:`pydantic.ValidationError` at
        construction time.
        """
        if self.year is not None and self.years:
            if self.year not in self.years:
                raise ValueError(
                    f"year={self.year} disagrees with years="
                    f"{list(self.years)}; either drop year= or "
                    "include year in years="
                )
        return self


# ---------------------------------------------------------------------------
# Readiness model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceReadiness:
    """Pre-flight check result returned by ``SourceAdapter.check_ready``.

    When ``ready=False`` the registry runner refuses to call
    ``read()`` and surfaces :attr:`blocker` to the caller (the
    CLI + manual-review queue both surface the blocker verbatim
    so a developer can fix the upstream issue without reading
    source code).

    When ``ready=True`` the optional :attr:`attribution` may
    carry the canonical citation text (Rule #15) so the registry
    can stamp it on the processed parquet without re-reading the
    bundle's ``metadata.json``.
    """

    ready: bool
    blocker: str | None = None
    attribution: str | None = None


# ---------------------------------------------------------------------------
# Pipeline payload models
# ---------------------------------------------------------------------------


@dataclass
class RawSourceBundle:
    """Verbatim payload returned by ``SourceAdapter.read``.

    For local-file sources (PWT, Maddison, BTI, CIRIGHTS, ...),
    :attr:`payload` is the in-memory parsed dataframe + the
    bundle metadata. For API-backed sources (WDI, WHO GHO,
    Wikidata, ...), :attr:`payload` is the cached JSON. The
    shape is intentionally loose (``Any``) so each adapter can
    carry its source-specific parsed form without forcing every
    adapter through a single dataframe contract at the read
    layer — the canonical long-frame contract lives on
    :class:`NormalizedSourceFrame`.
    """

    source_key: str
    payload: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedSourceFrame:
    """Canonical long-format frame returned by ``SourceAdapter.transform``.

    Every adapter must emit the long-frame shape documented in
    ``docs/sources/ingestion-plan.md`` (one row per
    ``(iso3, year, variable_name)`` triple, with the source's
    attribution in file-level metadata). The :attr:`rows`
    payload is the in-memory long-format DataFrame; the registry
    runner does not inspect it — :meth:`SourceAdapter.write`
    consumes it.
    """

    source_key: str
    rows: Any = None
    attribution: str | None = None


class IngestResult(BaseModel):
    """End-of-run summary returned by ``SourceAdapter.write``.

    The CLI prints the fields surfaced by ``commands_stage2.py``
    (source_id, parquet_path, observation_rows, countries, years,
    indicators) and the :attr:`attribution` block (Rule #15).

    Pydantic BaseModel (not a dataclass) so the result can cross
    a CLI / file / network boundary safely; field validators
    enforce non-negative counts and the ``source_id`` / ``years``
    invariants.

    Runtime fields:

    - :attr:`manifest_path` -- the run-manifest JSON path
      (typically ``data/processed/<source>/<source>_run_manifest.json``).
      Production adapters should persist this when they write outputs.
    - :attr:`attribution` -- the canonical citation text
      (Rule #15) the runner surfaces in the CLI end-of-run
      echo. ``None`` for sources that have not set an
      attribution; the test suite enforces the canonical
      ``sources/attributions.md`` drift guard.
    - :attr:`warnings` -- a tuple of structured warning dicts
      (e.g. ``{"code": "requested_year_out_of_coverage", ...}``)
      the runner surfaces in the CLI end-of-run echo. The
      ``year=2023`` out-of-coverage test asserts a
      ``requested_year_out_of_coverage`` entry is present.
    """

    source_key: str
    source_id: int = Field(0, ge=0)
    observation_rows: int = Field(0, ge=0)
    parquet_path: Path | None = None
    manifest_path: Path | None = None
    countries: int = Field(0, ge=0)
    years: tuple[int, ...] = ()
    indicators: int = Field(0, ge=0)
    warnings: tuple[dict[str, Any], ...] = ()
    attribution: str | None = None

    @model_validator(mode="after")
    def _validate_years_are_sorted_unique_ints(self) -> IngestResult:
        if list(self.years) != sorted(set(self.years)):
            raise ValueError(
                "years must be a sorted tuple of unique ints"
            )
        for one_year in self.years:
            if not isinstance(one_year, int):
                raise ValueError(
                    f"years must contain ints, got "
                    f"{type(one_year).__name__}"
                )
        return self


# ---------------------------------------------------------------------------
# Adapter Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SourceAdapter(Protocol):
    """The shared Stage 2 connector contract.

    The registry runner drives this protocol in the exact order
    :meth:`check_ready` -> :meth:`read` -> :meth:`transform` ->
    :meth:`write`. Short-circuit on ``ready=False`` is enforced
    by :func:`leaders_db.ingest.registry.ingest_source`; per-
    source adapters must not call :meth:`read` if their own
    :meth:`check_ready` returns ``ready=False``.

    The convenience :meth:`ingest` method wraps the full
    pipeline on a single adapter instance and returns the
    :class:`IngestResult` directly. The PWT per-source package
    (Increment B) is the first proof of the convenience method;
    the registry runner is the primary entry point for
    consumers that hold a registry key.

    :meth:`check_ready` receives the :class:`IngestRequest` so
    the readiness gate can resolve request-scoped
    ``raw_root`` / ``processed_root`` overrides (per the
    source-ingestion-plan "per-source package layout" section).
    The registry runner passes the same ``IngestRequest`` to
    every protocol method, so a per-call ``raw_root`` is
    honored consistently across ``check_ready`` /
    ``read`` / ``transform`` / ``write``.
    """

    source_key: str

    def check_ready(self, request: IngestRequest) -> SourceReadiness: ...

    def read(self, request: IngestRequest) -> RawSourceBundle: ...

    def transform(
        self,
        bundle: RawSourceBundle,
        request: IngestRequest,
    ) -> NormalizedSourceFrame: ...

    def write(
        self,
        frame: NormalizedSourceFrame,
        request: IngestRequest,
    ) -> IngestResult: ...

    def ingest(self, request: IngestRequest) -> IngestResult: ...


__all__ = [
    "IngestRequest",
    "IngestResult",
    "NormalizedSourceFrame",
    "RawSourceBundle",
    "SourceAdapter",
    "SourceReadiness",
]
