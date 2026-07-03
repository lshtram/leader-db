"""Unified-source EIU Democracy Index PDF adapter."""

from __future__ import annotations

from ._constants import (
    EIU_DEMOCRACY_INDEX_ADAPTER_VERSION,
    EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT,
    EIU_DEMOCRACY_INDEX_DEFAULT_VERSION,
    EIU_DEMOCRACY_INDEX_INDICATORS,
    EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY,
    EIU_DEMOCRACY_INDEX_SOURCE_KEY,
)
from ._descriptor import build_eiu_democracy_index_descriptor
from ._parser import EiuDemocracyIndexRow, parse_eiu_democracy_index_rows
from .adapter import (
    EiuDemocracyIndexAdapter,
    EiuDemocracyIndexTextPage,
    create_eiu_democracy_index_adapter,
    register_eiu_democracy_index,
)

__all__ = [
    "EIU_DEMOCRACY_INDEX_ADAPTER_VERSION",
    "EIU_DEMOCRACY_INDEX_ATTRIBUTION_TEXT",
    "EIU_DEMOCRACY_INDEX_DEFAULT_VERSION",
    "EIU_DEMOCRACY_INDEX_INDICATORS",
    "EIU_DEMOCRACY_INDEX_OBSERVATION_FAMILY",
    "EIU_DEMOCRACY_INDEX_SOURCE_KEY",
    "EiuDemocracyIndexAdapter",
    "EiuDemocracyIndexRow",
    "EiuDemocracyIndexTextPage",
    "build_eiu_democracy_index_descriptor",
    "create_eiu_democracy_index_adapter",
    "parse_eiu_democracy_index_rows",
    "register_eiu_democracy_index",
]
