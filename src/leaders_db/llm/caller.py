"""LLM caller — thin wrapper that validates and persists responses.

The default runner is a "stub" that returns a deterministic
:class:`LLMScoreOutput` based on the input. This keeps the package
runnable and testable without any LLM credentials.

To use a real provider:

1. ``pip install -e ".[llm]"`` (or ``uv pip install ...``) to install the
   optional provider libraries.
2. Set ``LEADERSDB_LLM_API_KEY`` in ``.env``.
3. Set ``llm.provider`` in your run config to ``openai`` / ``anthropic`` /
   ``ollama`` and ``llm.model`` to the desired model name.

The caller always validates the response against :class:`LLMScoreOutput`
before returning. A provider error or a validation failure raises
:class:`LLMUnavailableError` (or the underlying provider's exception) and
the caller logs the failure; the caller does not silently fall back to
garbage output.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..config import LLMConfig
from .schemas import LLMScoreInput, LLMScoreOutput, band_for_confidence

_log = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM adapter cannot produce a validated output."""


class LLMRunner(Protocol):
    """Provider-agnostic interface for a strict-JSON LLM call."""

    def score(self, payload: LLMScoreInput) -> LLMScoreOutput: ...


# ---------------------------------------------------------------------------
# Stub runner — used when llm.enabled is False or no provider is wired.
# ---------------------------------------------------------------------------


class StubRunner:
    """Deterministic stub runner used by the default CLI and tests.

    Returns a low-confidence, human-review-required response based only on
    the structured indicators in the input — never an invented score.
    """

    def score(self, payload: LLMScoreInput) -> LLMScoreOutput:
        # Heuristic: if the input has at least one structured indicator,
        # suggest a neutral score; otherwise mark for review. This is the
        # safest "non-invented" stub possible.
        if not payload.structured_indicators:
            return LLMScoreOutput(
                proposed_score=0,
                confidence=0,
                rationale=(
                    "Stub runner: no structured indicators supplied; "
                    "cannot propose a score without LLM access."
                ),
                main_supporting_evidence=[],
                main_contradicting_evidence=[],
                human_review_required=True,
                review_reason="LLM disabled and no structured indicators available",
            )

        # The stub returns a neutral proposed score; the real runner must
        # be wired in via leaders_db.llm.providers for production use.
        return LLMScoreOutput(
            proposed_score=5,
            confidence=30,
            rationale=(
                "Stub runner: structured indicators were supplied but no LLM "
                "provider is configured. Configure llm.provider in your run "
                "config to enable real scoring."
            ),
            main_supporting_evidence=payload.structured_indicators[:3],
            main_contradicting_evidence=[],
            human_review_required=True,
            review_reason="LLM disabled (stub runner in use)",
        )


# ---------------------------------------------------------------------------
# Default factory
# ---------------------------------------------------------------------------


def build_default_runner(cfg: LLMConfig) -> LLMRunner:
    """Return the configured LLM runner.

    Currently only the stub runner is wired. Real providers will be added
    in :mod:`leaders_db.llm.providers` during Phase C (data acquisition)
    or Phase E (activation), depending on which requires LLM scoring.
    """
    if not cfg.enabled:
        _log.debug("LLM disabled; returning stub runner")
        return StubRunner()

    provider = cfg.provider
    if provider == "stub":
        return StubRunner()

    # Real providers will be added here during the data-acquisition phase.
    # We raise rather than silently fall back, because silently swapping
    # the runner would violate the "no silent overwrites" rule.
    raise LLMUnavailableError(
        f"LLM provider {provider!r} is configured but not implemented yet. "
        f"Implement leaders_db.llm.providers.{provider} or set "
        f"llm.provider=stub in your run config."
    )


__all__ = ["LLMRunner", "StubRunner", "LLMUnavailableError", "build_default_runner"]
