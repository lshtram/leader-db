"""Chart-ready dataframe output contract for visualization queries."""

from __future__ import annotations

VIZ_OUTPUT_REQUIRED_COLUMNS: tuple[str, ...] = (
    "query_id",
    "metric_id",
    "metric_label",
    "grain",
    "year",
    "country_iso3",
    "country_name",
    "leader_name",
    "category_key",
    "value",
    "value_unit",
    "aggregation",
    "transform",
    "source_keys",
    "source_row_references",
    "attribution_texts",
    "provenance_json",
    "coverage_status",
    "confidence_score",
    "missingness_flags",
    "client_matrix_policy",
    "client_score",
    "system_proposed_score",
    "final_score",
    "score_delta_vs_client",
)


__all__ = ["VIZ_OUTPUT_REQUIRED_COLUMNS"]
