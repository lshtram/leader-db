# Testing Guide — Unified Source Interface

This guide covers the first `leaders_db.sources` interface slice: the clean source
package boundary, registry seam, minimal runner dispatch, query protocol, and
legacy-access separation.

## Automated checks

Run the focused source-interface suite:

```bash
pytest -q tests/sources
```

Verifies:

- importing `leaders_db.sources` does not import legacy `leaders_db.ingest`;
- the explicit `leaders_db.sources.legacy` bridge imports legacy lazily;
- legacy `leaders_db.ingest.STAGE2_ADAPTERS` remains accessible;
- `InMemorySourceRegistry` lists, retrieves, and rejects duplicate source slugs;
- `SourceIngestRunner.run(request)` dispatches through the new registry in the
  fixed `check_ready -> read_raw -> transform` order;
- runner dispatch does not call legacy `STAGE2_ADAPTERS`;
- source request, observation, provenance, manifest, warning, and query contracts
  expose the documented fields;
- the query protocol can be implemented by an in-memory fake without rerunning
  ingestion or reading raw files.

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
changes.

## Manual / boundary checks

Use a fresh Python process to confirm the import boundary:

```bash
python - <<'PY'
import importlib
import sys

importlib.import_module("leaders_db.sources")
leaked = sorted(name for name in sys.modules if name.startswith("leaders_db.ingest"))
print(leaked)
assert leaked == []
PY
```

Expected: `[]`.

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

- Real source migration into `src/leaders_db/sources/adapters/`.
- Processed-file persistence, database writes, manifest writing, and shared
  validation beyond the current contract envelope.
- New CLI commands under `leaders-db sources ...`.
- Moving or deleting legacy `src/leaders_db/ingest/` code.
