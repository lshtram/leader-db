"""Strict response-schema normalization shared by execution and resume."""

from __future__ import annotations


def make_strict_response_schema(value: object) -> None:
    """Require every object property for OpenAI strict structured output."""

    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            required = value.get("required")
            if (
                not isinstance(required, list)
                or len(required) != len(properties)
                or set(required) != set(properties)
            ):
                value["required"] = list(properties)
        value.pop("default", None)
        for nested in value.values():
            make_strict_response_schema(nested)
    elif isinstance(value, list):
        for nested in value:
            make_strict_response_schema(nested)


__all__ = ["make_strict_response_schema"]
