"""Public surface for the UNSD SNAAMA source adapter."""

from .adapter import (
    ATTRIBUTION,
    ITEM_INDICATORS,
    SOURCE_KEY,
    VERSION,
    UnSnaamaAdapter,
    build_un_snaama_descriptor,
    create_un_snaama_adapter,
    register_un_snaama,
)

__all__ = [
    "ATTRIBUTION",
    "ITEM_INDICATORS",
    "SOURCE_KEY",
    "VERSION",
    "UnSnaamaAdapter",
    "build_un_snaama_descriptor",
    "create_un_snaama_adapter",
    "register_un_snaama",
]
