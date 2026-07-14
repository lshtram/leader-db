"""Trusted execution-usage parsing and provider price equivalents."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dossier_models import DossierUsage

UNKNOWN = "unknown_not_exposed_by_tool"


class TokenRates(BaseModel):
    """Per-million-token rates for one provider tier."""

    model_config = ConfigDict(extra="forbid")

    uncached_input: float = Field(ge=0)
    cached_input: float = Field(ge=0)
    cache_write_input: float | None = Field(default=None, ge=0)
    output: float = Field(ge=0)


class LongContextPricing(BaseModel):
    """Rates applied when an underlying request exceeds a token threshold."""

    model_config = ConfigDict(extra="forbid")

    threshold_input_tokens: int = Field(gt=0)
    rates: TokenRates


class ModelPricing(BaseModel):
    """Official rate-card metadata for one exact provider/model pair."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    billing_mode: str
    source_url: str
    retrieved_date: str
    usd: TokenRates
    long_context: LongContextPricing | None = None
    codex_credits: TokenRates | None = None


class SearchPricing(BaseModel):
    """Optional separately billed search-tool rate for legacy cost records."""

    model_config = ConfigDict(extra="forbid")

    usd_per_search: float = Field(ge=0)
    source_url: str
    retrieved_date: str


class ResearchPricing(BaseModel):
    """Versioned price-card registry used for reproducible estimates."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    effective_date: str
    models: dict[str, ModelPricing]
    parallel_search: SearchPricing

    @model_validator(mode="after")
    def _unique_provider_models(self) -> ResearchPricing:
        pairs = [(item.provider, item.model) for item in self.models.values()]
        if len(pairs) != len(set(pairs)):
            raise ValueError("pricing provider/model pairs must be unique")
        return self


def load_research_pricing(path: Path) -> ResearchPricing:
    """Load and validate an official-price snapshot."""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid research pricing YAML: {path}") from exc
    return ResearchPricing.model_validate(payload)


def price_usage(
    usage: DossierUsage,
    *,
    provider: str,
    model: str,
    pricing: ResearchPricing,
    parallel_searches: int = 0,
) -> DossierUsage:
    """Attach trusted rate-card equivalents without claiming subscription billing."""

    if parallel_searches < 0:
        raise ValueError("parallel_searches cannot be negative")
    search_cost = round(parallel_searches * pricing.parallel_search.usd_per_search, 6)
    match = next(
        (
            item
            for item in pricing.models.values()
            if item.provider == provider and item.model == model
        ),
        None,
    )
    if match is None or not all(
        isinstance(value, int)
        for value in (
            usage.input_tokens,
            usage.cached_input_tokens,
            usage.output_tokens,
        )
    ):
        return usage.model_copy(
            update={
                "parallel_search_cost_usd": search_cost,
                "pricing_version": pricing.version,
                "cost_certainty": "unknown",
                "estimated_cost_usd": UNKNOWN,
            }
        )
    input_tokens = int(usage.input_tokens)
    cached_tokens = int(usage.cached_input_tokens)
    if cached_tokens > input_tokens:
        raise ValueError("cached input tokens cannot exceed input tokens")
    uncached_tokens = input_tokens - cached_tokens
    output_tokens = int(usage.output_tokens)
    standard = _token_cost(
        uncached_tokens, cached_tokens, output_tokens, match.usd
    ) + search_cost
    upper_rates = match.usd
    certainty: Literal["exact", "range"] = "exact"
    if match.long_context is not None and input_tokens > match.long_context.threshold_input_tokens:
        upper_rates = match.long_context.rates
        certainty = "range"
    cache_write_rate = upper_rates.cache_write_input
    upper_uncached_rate = upper_rates.uncached_input
    if cache_write_rate is not None and cache_write_rate != upper_uncached_rate:
        upper_uncached_rate = max(upper_uncached_rate, cache_write_rate)
        certainty = "range"
    upper = _token_cost(
        uncached_tokens,
        cached_tokens,
        output_tokens,
        upper_rates,
        uncached_rate=upper_uncached_rate,
    ) + search_cost
    credits_lower: float | str = UNKNOWN
    credits_upper: float | str = UNKNOWN
    if match.codex_credits is not None:
        credits_lower = _token_cost(
            uncached_tokens, cached_tokens, output_tokens, match.codex_credits
        )
        credits_upper = credits_lower
    return usage.model_copy(
        update={
            "uncached_input_tokens": uncached_tokens,
            "payg_equivalent_cost_usd_lower": round(standard, 6),
            "payg_equivalent_cost_usd_upper": round(upper, 6),
            "codex_equivalent_credits_lower": credits_lower,
            "codex_equivalent_credits_upper": credits_upper,
            "parallel_search_cost_usd": search_cost,
            "actual_billed_cost_usd": UNKNOWN,
            "pricing_version": pricing.version,
            "cost_certainty": certainty,
            "estimated_cost_usd": UNKNOWN,
        }
    )


def combine_priced_usage(usages: tuple[DossierUsage, ...]) -> DossierUsage:
    """Combine separately priced execution passes without repricing mixed models."""

    if not usages:
        raise ValueError("at least one priced usage record is required")

    def sum_int(field_name: str) -> int | str:
        values = [getattr(item, field_name) for item in usages]
        return sum(int(value) for value in values) if all(
            isinstance(value, int) for value in values
        ) else UNKNOWN

    def sum_float(field_name: str) -> float | str:
        values = [getattr(item, field_name) for item in usages]
        return round(sum(float(value) for value in values), 6) if all(
            isinstance(value, (int, float)) for value in values
        ) else UNKNOWN

    input_tokens = sum_int("input_tokens")
    output_tokens = sum_int("output_tokens")
    total_tokens = (
        input_tokens + output_tokens
        if isinstance(input_tokens, int) and isinstance(output_tokens, int)
        else UNKNOWN
    )
    certainties = {item.cost_certainty for item in usages}
    certainty: Literal["exact", "range", "unknown"] = (
        "unknown" if "unknown" in certainties else "range" if "range" in certainties else "exact"
    )

    def common_value(field_name: str) -> int | str:
        values = {getattr(item, field_name) for item in usages}
        return next(iter(values)) if len(values) == 1 else UNKNOWN

    return DossierUsage(
        input_tokens=input_tokens,
        cached_input_tokens=sum_int("cached_input_tokens"),
        uncached_input_tokens=sum_int("uncached_input_tokens"),
        output_tokens=output_tokens,
        reasoning_output_tokens=sum_int("reasoning_output_tokens"),
        total_tokens=total_tokens,
        estimated_cost_usd=UNKNOWN,
        payg_equivalent_cost_usd_lower=sum_float("payg_equivalent_cost_usd_lower"),
        payg_equivalent_cost_usd_upper=sum_float("payg_equivalent_cost_usd_upper"),
        codex_equivalent_credits_lower=sum_float("codex_equivalent_credits_lower"),
        codex_equivalent_credits_upper=sum_float("codex_equivalent_credits_upper"),
        parallel_search_cost_usd=sum_float("parallel_search_cost_usd"),
        actual_billed_cost_usd=UNKNOWN,
        pricing_version=max(
            (int(item.pricing_version) for item in usages if isinstance(item.pricing_version, int)),
            default=UNKNOWN,
        ),
        pricing_sha256=common_value("pricing_sha256"),
        pricing_effective_date=common_value("pricing_effective_date"),
        cost_certainty=certainty,
    )


def _token_cost(
    uncached_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    rates: TokenRates,
    *,
    uncached_rate: float | None = None,
) -> float:
    return (
        uncached_tokens * (rates.uncached_input if uncached_rate is None else uncached_rate)
        + cached_tokens * rates.cached_input
        + output_tokens * rates.output
    ) / 1_000_000


__all__ = [
    "ResearchPricing",
    "combine_priced_usage",
    "load_research_pricing",
    "price_usage",
]
