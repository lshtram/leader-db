# Testing Guide — Unified Source Interface

This guide covers the `leaders_db.sources` interface slice: the clean source
package boundary, registry seam, minimal runner dispatch, query protocol, and
legacy-access separation. The PWT 10.01 adapter under
`src/leaders_db/sources/adapters/pwt/` is the first source rebuilt under this
interface and the Maddison Project Database 2023 adapter under
`src/leaders_db/sources/adapters/maddison_project/` is the second.
See `docs/architecture/sources.md` §7.1 and `docs/workplan.md` for the
migration history.

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

Optional legacy compatibility smoke:

```bash
pytest -q tests/ingest
```

Verifies the existing legacy ingestion tests remain green after source-interface
changes. The PWT-specific legacy suite
(`tests/ingest/sources/pwt/`) is the regression guard for the legacy
`STAGE2_ADAPTERS["pwt"]` path and must keep passing unchanged.

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
- The third / fourth / ... clean source migrations (WDI, WGI, V-Dem,
  ...). PWT and Maddison Project are the proof-of-pattern; future
  migrations follow the same `src/leaders_db/sources/adapters/<slug>/`
  layout.
