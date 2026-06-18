"""Leaders Database — AI-agent data collection and validation prototype.

The package implements Stages 0–15 of the pipeline described in
``docs/top-level-requirements.md`` §8. Module boundaries are normative; see
``docs/architecture.md`` for the system design and ``docs/requirements-core.md``
for the locally tracked REQ-* / NFR-* baseline.

The package is split into composition roots (CLI, config, env, paths),
the database layer (``db/``), the pipeline stages (Stage 0–2 in ``ingest/``,
Stage 3–5 in ``resolve/``, Stage 9–11 in ``score/``, Stage 12–15 in
``validate/``), the strict-JSON LLM adapter (``llm/``), and export helpers
(``export/``). ``normalize/`` holds shared country / leader-name / year
helpers used by multiple stages.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
