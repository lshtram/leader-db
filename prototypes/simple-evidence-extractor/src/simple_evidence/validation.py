"""Deterministic semantic guards that do not require a model."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


def require_numeric_support(summary: str, excerpt: str) -> None:
    """Require every summary number to occur in the exact stored span."""

    missing = sorted(_numbers(summary) - _numbers(excerpt))
    if missing:
        raise ValueError(f"summary numbers absent from the exact excerpt: {missing}")

    _require_supported_terms(summary, excerpt)


def _require_supported_terms(summary: str, excerpt: str) -> None:
    summary_lower = summary.casefold()
    excerpt_lower = excerpt.casefold()
    guarded_terms = {
        "signed": ("signed", "signature", "firm", "rúbrica", "rubrica", "suscrib"),
    }
    unsupported = [
        claim
        for claim, markers in guarded_terms.items()
        if re.search(rf"\b{re.escape(claim)}\b", summary_lower)
        and not any(marker in excerpt_lower for marker in markers)
    ]
    if unsupported:
        raise ValueError(
            f"summary legal-action terms absent from the exact excerpt: {unsupported}"
        )


def _numbers(value: str) -> set[str]:
    result = set()
    for token in re.findall(r"(?<!\w)\d[\d,]*(?:\.\d+)?", value):
        try:
            result.add(str(Decimal(token.replace(",", "")).normalize()))
        except InvalidOperation:
            continue
    return result


__all__ = ["require_numeric_support"]
