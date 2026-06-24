# Testing Guide — Unified Source Interface

This guide covers the `leaders_db.sources` interface slice: the clean source
package boundary, registry seam, minimal runner dispatch, query protocol, and
legacy-access separation. The PWT 10.01 adapter under
`src/leaders_db/sources/adapters/pwt/` is the first source rebuilt under this
interface, the Maddison Project Database 2023 adapter under
`src/leaders_db/sources/adapters/maddison_project/` is the second, and the
World Bank WDI adapter under
`src/leaders_db/sources/adapters/world_bank_wdi/` is the third (API/cache-
backed source). See `docs/architecture/sources.md` §7.1 and `docs/workplan.md`
for the migration history.

## Automated checks

Run the focused source-interface suite:

```bash
pytest -q tests/sources
```

Verifies:

- importing `leaders_db.sources` (and the new
  `leaders_db.sources.adapters.pwt` submodule) does not import legacy
  `leaders_db.ingest`;
- the explicit `leaders_db.sources.legacy` bridge imports legacy lazily;
- legacy `leaders_db.ingest.STAGE2_ADAPTERS` remains accessible;
- `InMemorySourceRegistry` lists, retrieves, and rejects duplicate source slugs;
- `SourceIngestRunner.run(request)` dispatches through the new registry in the
  fixed `check_ready -> read_raw -> transform` order;
- runner dispatch does not call legacy `STAGE2_ADAPTERS`;
- source request, observation, provenance, manifest, warning, and query contracts
  expose the documented fields;
- the query protocol can be implemented by an in-memory fake without rerunning
  ingestion or reading raw files;
- the PWT adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry`;
- the PWT adapter runs end-to-end through the new runner against a fixture
  `raw_root` and produces `NormalizedObservation` records;
- the runner does not consult legacy `STAGE2_ADAPTERS` even when the legacy
  `pwt` slot is monkeypatched to a tracker;
- `years=` / `countries=` filters are honored; `years=(2023,)` (out of
  coverage) emits zero observations plus a `year_absent` warning; `leaders=`
  emits an `unsupported_filter` warning;
- a mismatched `source_version=` (e.g. `"9.99"` against the canonical
  PWT 10.01 bundle) fails readiness with a structured
  `unsupported_version` error per
  `docs/requirements/sources.md` §3 SRC-REQ-009, and the
  `SourceIngestRunner` raises `RuntimeError` before invoking
  `read_raw` / `transform` so the legacy bundle metadata
  cannot be silently overwritten;
- the readiness-failure tests for missing `metadata.json`,
  missing `pwt1001.xlsx`, `checksum_sha256` mismatch, missing
  metadata `source_version`, and mismatched metadata `source_version`
  each prove the runner short-circuits before `read_raw` / `transform`
  (call order verified via the `_SpyPWTAdapter` wrapper);
- canonical metadata `source_version="10.01"` propagates consistently to
  `RawAsset.version` and every emitted `NormalizedObservation.source_version`.

The Maddison Project Database 2023 slice adds the source-specific
coverage semantics on top of the shared contract:

- the Maddison adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes the canonical Maddison Project
  2023 static metadata (source_id `maddison_project`, default version
  `2023`, attribution_key `maddison_project`, dataset type, 1-2022
  coverage hint, `economic_country_year` observation family, canonical
  Maddison Project homepage URL);
- `SourceIngestRunner.run(request)` drives Maddison end-to-end through
  the new registry against a fixture `raw_root` and produces
  `NormalizedObservation` records (21 fixture observations
  round-tripped);
- the runner does not consult legacy `STAGE2_ADAPTERS` even when the
  legacy `maddison_project` slot is monkeypatched to a tracker;
- `years=(2023,)` triggers the documented 1-year-gap proxy mapping
  to 2022 data: every emitted observation carries the `proxy_year`
  quality flag plus `requested_year=2023` / `proxy_source_year=2022`
  in its `extension` payload, and the result envelope surfaces a
  structured `maddison_project_proxy_year` warning naming the
  mapping;
- `years=(2024,)` (out of coverage) emits zero observations plus a
  structured `YEAR_ABSENT` warning -- no multi-year stale-proxy fill
  (SRC-COV-002 / SRC-COV-003);
- `years=` / `countries=` filters are honored; `leaders=` emits an
  `unsupported_filter` warning;
- the readiness-failure tests for missing `metadata.json`, missing
  `mpd2023.xlsx`, `checksum_sha256` mismatch, missing metadata
  `source_version`, and mismatched metadata `source_version` each
  prove the runner short-circuits before `read_raw` / `transform`;
- canonical metadata `source_version="2023"` propagates consistently
  to `RawAsset.version` and every emitted
  `NormalizedObservation.source_version`.

Run focused lint for this slice:

```bash
ruff check src/leaders_db/sources tests/sources docs/requirements/sources.md docs/architecture/sources.md
```

Verifies formatting/import/static-analysis hygiene for the new package, source
tests, and source-interface docs touched by this slice.

The World Bank WDI slice (third clean-source migration, API/cache-backed)
adds the source-specific cache-policy semantics on top of the shared
contract:

- the WDI adapter descriptor is registerable / listable through the
  `InMemorySourceRegistry` and exposes the canonical WDI static metadata
  (source_id `world_bank_wdi`, default version `"World Bank API v2;
  cached indicator responses"`, attribution_key `"world_bank_wdi"`, api
  type, 1960-present coverage hint, both `economic_country_year` and
  `social_country_year` observation families, WDI v2 API homepage URL,
  requires_network=True);
- `SourceIngestRunner.run(request)` drives WDI end-to-end through the
  new registry against a fixture `raw_root` and produces
  `NormalizedObservation` records (125 fixture observations round-tripped
  for the unfiltered run; 61 for `years=(2023,)`; 25 for
  `countries=('USA',)`; 12 for `years=(2023,) + countries=('USA',)`);
- the runner does not consult legacy `STAGE2_ADAPTERS` even when the
  legacy `world_bank_wdi` slot is monkeypatched to a tracker;
- `cache_policy="offline_only"` / `"prefer_cache"` with explicit `years=`
  and missing / incomplete cache fails readiness with a structured
  `network_cache_unavailable` / `missing_raw` error BEFORE `read_raw` /
  `transform` are called; the new runner is offline / cache-first by
  default and never silently hits the network;
- `cache_policy="refresh"` / `"no_cache"` opts in to the legacy HTTP
  path (not exercised by tests);
- `years=None` skips the cache gate so the runner can enumerate all
  available years at read time (SRC-REQ-003);
- `years=` outside the 1960+ coverage envelope emits zero observations
  plus a structured `YEAR_ABSENT` warning -- no stale-proxy fill
  (SRC-COV-002 / SRC-COV-003);
- `years=` / `countries=` filters are honored; `leaders=` emits an
  `unsupported_filter` warning;
- the readiness-failure tests for missing `metadata.json`,
  missing metadata `source_version`, mismatched metadata
  `source_version`, and unsupported request `source_version` each
  prove the runner short-circuits before `read_raw` / `transform`;
- the canonical metadata `source_version="World Bank API v2; cached
  indicator responses"` propagates consistently to
  `RawAsset.version` and every emitted
  `NormalizedObservation.source_version`;
- the per-observation `RawLocator` carries the cache file path +
  `api_endpoint` template + `json_pointer` so downstream audit code
  can resolve the canonical WDI v2 URL for each (year, indicator,
  country) row;
- the per-observation `extension` payload carries the raw WDI
  indicator code (e.g. `NY.GDP.MKTP.CD`) as `wdi_raw_indicator_code`,
  plus the canonical attribution text (Rule #15).

Optional legacy compatibility smoke:

```bash
pytest -q tests/ingest
```

Verifies the existing legacy ingestion tests remain green after source-interface
changes. The PWT-specific legacy suite
(`tests/ingest/sources/pwt/`) is the regression guard for the legacy
`STAGE2_ADAPTERS["pwt"]` path and must keep passing unchanged. The
WDI legacy suite (`tests/test_ingest_wdi.py`) is the regression guard
for the legacy `STAGE2_ADAPTERS["world_bank_wdi"]` path; the new
`tests/sources/test_world_bank_wdi_adapter.py` slice asserts that
the legacy `STAGE2_ADAPTERS["world_bank_wdi"]` slot is never invoked
by the new runner (`test_wdi_runner_does_not_consult_legacy_stage2_adapters`)
and that the legacy constant `WDI_ATTRIBUTION` is byte-identical to
the new `WORLD_BANK_WDI_ATTRIBUTION_TEXT`
(`test_wdi_attribution_text_matches_legacy_constant`).

## Manual / boundary checks

Use a fresh Python process to confirm the import boundary:

```bash
python - <<'PY'
import importlib
import sys

importlib.import_module("leaders_db.sources.adapters.pwt")
leaked = sorted(name for name in sys.modules if name.startswith("leaders_db.ingest"))
print(leaked)
assert leaked == []
PY
```

Expected: `[]`. The PWT adapter module imports cleanly without pulling in
the legacy ingest package.

Use the explicit lazy bridge only when legacy access is needed:

```bash
python - <<'PY'
from leaders_db.sources.legacy import get_legacy_stage2_adapters

adapters = get_legacy_stage2_adapters()
print(len(adapters), "pwt" in adapters)
assert "pwt" in adapters
PY
```

Expected: a positive adapter count and `True` for `pwt`.

## Out of scope for this slice

- Processed-file persistence, database writes, manifest writing, and shared
  validation beyond the current contract envelope.
- New CLI commands under `leaders-db sources ...`.
- Moving or deleting legacy `src/leaders_db/ingest/` code.
- The fourth / fifth / ... clean source migrations (WGI, V-Dem,
  ...). PWT, Maddison Project, and World Bank WDI are the
  proof-of-pattern across dataset (PWT), historical xlsx (Maddison),
  and API/cache (WDI) source shapes; future migrations follow the
  same `src/leaders_db/sources/adapters/<slug>/` layout.
