"""Area / controlled-area column population for the row builder.

Split out of :mod:`row_builder` during the Increment 3 reviewer-gate
follow-up so :mod:`row_builder` stays under the documented 400-line
convention. See
``docs/country-year-chronicle-increment-3.md`` §9 and
``docs/workplan.md`` for the module-layout rationale.

Public helpers:

- :func:`populate_area_placeholders` — emit the Increment 1
  placeholder columns (no area; ``missing_area`` flag handled by
  :func:`assemble_flags`).
- :func:`populate_area_fields` — populate the area columns from
  :class:`CShapesSource` with the conservative controlled-area
  fallback (``controlled_area_km2 = country_area_km2``); returns the
  three flag bits the row builder forwards to
  :func:`assemble_flags`.

Increment 5 (all-country condensed export): the existence-window
check now falls back to the optional ``country_scope_entry``
when the iso3 has no pilot metadata. The pilot metadata still
wins for historical identities that V-Dem does not code
separately (SUN).
"""

from __future__ import annotations

from ._area_source import CShapesSource
from ._formatters import coerce_float, coerce_int, safe_int
from .constants import COUNTRY_METADATA, SOURCE_NA
from .country_scope import CountryScopeEntry


def populate_area_placeholders(row: dict[str, str]) -> tuple[bool, bool, bool]:
    """Populate the area / controlled-area columns with the Increment 1 placeholders.

    Returns ``(has_area, controlled_area_country_only, area_proxy_used)``.
    Both booleans are ``False`` in the Increment 1 placeholder path.
    """
    row["country_area_km2"] = ""
    row["controlled_area_km2"] = ""
    row["area_source"] = SOURCE_NA
    row["area_source_year_used"] = ""
    row["controlled_area_note"] = (
        "controlled_area not modeled in Increment 1; standard area empty "
        "pending a vetted static area source."
    )
    return False, False, False


def populate_area_fields(
    row: dict[str, str],
    *,
    iso3: str,
    year: int,
    cshapes: CShapesSource | None,
    country_scope_entry: CountryScopeEntry | None = None,
) -> tuple[bool, bool, bool]:
    """Populate the area / controlled-area columns from CShapes.

    The conservative controlled-area fallback is documented in the
    Increment 3 spec: ``controlled_area_km2`` is set to
    ``country_area_km2`` when country area is available. The
    ``controlled_area_country_only`` flag is added on top of
    ``controlled_area_not_modeled`` so the audit trail records both
    facts (imperial summing deferred; controlled value equals the
    country territory only).

    The helper respects the country's existence window from
    :data:`COUNTRY_METADATA`: rows outside the ``start_year`` /
    ``end_year`` window do NOT receive a CShapes area even when
    the dispatch has a matching row. Concretely, a SUN row for
    1921 (pre-existence, since SUN started 1922-12-30) is left
    blank with the ``pre_existence_gap`` flag, even though the
    CShapes GW 365 dispatch has a 1921-1945 row that covers
    part of SUN's territory. The conservative interpretation is
    that "SUN did not exist in 1921" so the row should not carry
    SUN's territory as a SUN-area value.

    When the iso3 is NOT in the pilot metadata, the existence-
    window check falls back to the optional
    ``country_scope_entry`` so V-Dem-derived windows still
    produce a blank area for years outside the source-backed
    existence window.

    Returns ``(has_area, controlled_area_country_only, area_proxy_used)``.
    """
    metadata = COUNTRY_METADATA.get(iso3, {})
    if "start_year" in metadata or "end_year" in metadata:
        start_year = safe_int(metadata.get("start_year"))
        end_year = safe_int(metadata.get("end_year"))
    elif country_scope_entry is not None:
        start_year = country_scope_entry.start_year
        end_year = country_scope_entry.end_year
    else:
        start_year = None
        end_year = None
    if start_year is not None and year < start_year:
        # Pre-existence gap; skip CShapes lookup and keep the
        # area placeholders. The pre_existence_gap flag is added
        # by ``assemble_flags``.
        return populate_area_placeholders(row)
    if end_year is not None and year > end_year:
        # Post-existence gap; same treatment.
        return populate_area_placeholders(row)
    if cshapes is None or cshapes.frame.empty:
        return populate_area_placeholders(row)
    area_km2, source_year, is_proxy = cshapes.lookup_area(iso3, year)
    if area_km2 is None:
        return populate_area_placeholders(row)
    # Country area: real CShapes hit.
    row["country_area_km2"] = coerce_float(area_km2, decimals=0)
    row["area_source"] = "cshapes"
    row["area_source_year_used"] = coerce_int(source_year)
    # Controlled area: conservative fallback = country area.
    row["controlled_area_km2"] = coerce_float(area_km2, decimals=0)
    row["controlled_area_note"] = (
        "controlled_area_km2 equals country_area_km2; imperial / "
        "dependency summing is deferred (Increment 4 work item; no "
        "vetted dependency-controller mapping was staged in "
        "Increment 3)."
    )
    return True, True, is_proxy


__all__ = [
    "populate_area_fields",
    "populate_area_placeholders",
]
