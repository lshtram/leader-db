"""Strict-JSON LLM adapter.

The LLM is invoked **only** for ambiguous interpretation (requirement §10).
This package provides:

- Pydantic schemas for the LLM input/output contract (see :mod:`schemas`).
- A thin caller wrapper that validates the response before persisting
  (see :mod:`caller`).

The ``llm`` extra is **not** installed by default. The package remains
importable and runnable without an LLM; the caller returns a deterministic
"stub" response when ``RunConfig.llm.enabled`` is ``False``.
"""

from __future__ import annotations

from .caller import LLMRunner, LLMUnavailableError, build_default_runner
from .schemas import (
    LLMScoreInput,
    LLMScoreOutput,
    ScoreBand,
    band_for_confidence,
)

__all__ = [
    "LLMRunner",
    "LLMUnavailableError",
    "build_default_runner",
    "LLMScoreInput",
    "LLMScoreOutput",
    "ScoreBand",
    "band_for_confidence",
]
