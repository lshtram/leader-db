"""Text parser for EIU Democracy Index report table rows.

The PDF boundary extracts page text. This module is deliberately pure and small
so tests can prove row parsing with synthetic representative table text without
redistributing copyrighted PDF content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER_RE = re.compile(r"(?<!\w)-?\d+(?:\.\d+)?=?")
_REGIME_TYPES = (
    "Full democracy",
    "Flawed democracy",
    "Hybrid regime",
    "Authoritarian",
    "Authoritarian regime",
)
_SKIP_PREFIXES = (
    "Democracy Index",
    "Table ",
    "Overall ",
    "score ",
    "Rank ",
    "Source:",
    "Regional score",
    "© ",
)


@dataclass(frozen=True)
class EiuDemocracyIndexRow:
    """Source-native country row parsed from an EIU table text page."""

    country_name: str
    overall_score: float
    rank: int | None
    rank_change: int | None
    electoral_process_pluralism: float
    functioning_government: float
    political_participation: float
    political_culture: float
    civil_liberties: float
    regime_type: str | None
    raw_row_text: str
    page_number: int | None = None


def parse_eiu_democracy_index_rows(
    text: str,
    *,
    page_number: int | None = None,
) -> tuple[EiuDemocracyIndexRow, ...]:
    """Parse representative EIU Democracy Index country rows from page text.

    The parser handles the common text-extraction shape where a country row has:
    country name, overall score, global rank, rank-change-or-regional-rank, five
    category scores, and an optional regime type. The third numeric column is
    interpreted as ``rank_change`` only on pages whose header says
    ``Change in rank``; appendix pages usually use that position for regional
    rank and therefore leave ``rank_change`` as ``None``.
    """
    has_rank_change = "Change in rank" in text
    rows: list[EiuDemocracyIndexRow] = []
    pending_regime: str | None = None
    lines = [_normalise_spaces(line) for line in text.splitlines()]
    for index, line in enumerate(lines):
        if not line or _should_skip(line):
            continue
        if line in {"Full", "Flawed", "Hybrid"}:
            pending_regime = line
            continue
        row_text = line
        previous_line = lines[index - 1] if index > 0 else ""
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        country_fragment = _country_fragment_before_first_number(line)
        if (
            _looks_like_country_fragment(previous_line)
            and (
                _looks_like_continued_country(country_fragment)
                or (
                    not country_fragment
                    and _looks_like_incomplete_country(previous_line)
                )
            )
            and len(_NUMBER_RE.findall(line)) >= 8
        ):
            row_text = f"{previous_line} {row_text}"
            country_fragment = _country_fragment_before_first_number(row_text)
        if pending_regime is not None:
            if _looks_like_continued_country(country_fragment):
                pending_regime = None
                continue
            row_text = f"{pending_regime} {row_text}"
        if next_line in {"democracy", "regime"}:
            row_text = f"{row_text} {next_line}"
        elif (
            _looks_like_country_fragment(next_line)
            and _looks_like_incomplete_country(country_fragment)
            and len(_NUMBER_RE.findall(row_text)) >= 8
        ):
            row_text = _insert_country_suffix_before_first_number(row_text, next_line)
        row = _parse_row(row_text, has_rank_change=has_rank_change, page_number=page_number)
        if row is None:
            continue
        pending_regime = None
        rows.append(row)
    return tuple(rows)


def _parse_row(
    row_text: str,
    *,
    has_rank_change: bool,
    page_number: int | None,
) -> EiuDemocracyIndexRow | None:
    matches = list(_NUMBER_RE.finditer(row_text))
    if len(matches) < 8:
        return None
    first = matches[0]
    country = row_text[: first.start()].strip(" -")
    regime = _extract_regime_type(row_text[matches[7].end() :].strip())
    country = _strip_leading_regime_fragment(country)
    if not country or country.casefold() == "regional":
        return None
    values = [_parse_number(match.group()) for match in matches[:8]]
    rank = int(values[1]) if values[1] is not None else None
    third_column = int(values[2]) if values[2] is not None else None
    return EiuDemocracyIndexRow(
        country_name=country,
        overall_score=float(values[0]),
        rank=rank,
        rank_change=third_column if has_rank_change else None,
        electoral_process_pluralism=float(values[3]),
        functioning_government=float(values[4]),
        political_participation=float(values[5]),
        political_culture=float(values[6]),
        civil_liberties=float(values[7]),
        regime_type=regime,
        raw_row_text=row_text,
        page_number=page_number,
    )


def _parse_number(value: str) -> float | None:
    cleaned = value.rstrip("=")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_regime_type(suffix: str) -> str | None:
    normalised = _normalise_spaces(suffix)
    for regime_type in _REGIME_TYPES:
        if normalised.startswith(regime_type):
            return regime_type
    return None


def _strip_leading_regime_fragment(country: str) -> str:
    for fragment in ("Full ", "Flawed ", "Hybrid "):
        if country.startswith(fragment):
            return country.removeprefix(fragment).strip()
    return country


def _normalise_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _should_skip(line: str) -> bool:
    return any(line.startswith(prefix) for prefix in _SKIP_PREFIXES)


def _looks_like_country_fragment(line: str) -> bool:
    if not line or _should_skip(line) or _NUMBER_RE.search(line):
        return False
    if line in {"Full", "Flawed", "Hybrid", "democracy", "regime"}:
        return False
    return len(line.split()) <= 4


def _insert_country_suffix_before_first_number(row_text: str, suffix: str) -> str:
    match = _NUMBER_RE.search(row_text)
    if match is None:
        return row_text
    return f"{row_text[:match.start()].strip()} {suffix} {row_text[match.start():].strip()}"


def _country_fragment_before_first_number(line: str) -> str:
    match = _NUMBER_RE.search(line)
    if match is None:
        return line.strip()
    return line[: match.start()].strip()


def _looks_like_continued_country(country_fragment: str) -> bool:
    first_word = country_fragment.split(maxsplit=1)[0] if country_fragment else ""
    return first_word in {
        "Arab",
        "Bissau",
        "Hercegovina",
        "Macedonia",
        "Republic",
        "States",
        "Tobago",
        "Zealand",
    }


def _looks_like_incomplete_country(country_fragment: str) -> bool:
    return country_fragment.endswith(
        (
            " and",
            " Arab",
            "Central",
            "Czech",
            "Democratic",
            "Dominican",
            "Equatorial",
            "Guinea-",
            "Kyrgyz",
            "New",
            "North",
            "of",
            "Papua New",
            "Republic",
            "Saudi",
            "South",
            "Trinidad and",
            "United",
            "United Arab",
        ),
    )


__all__ = ["EiuDemocracyIndexRow", "parse_eiu_democracy_index_rows"]
