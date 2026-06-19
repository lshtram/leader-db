"""ISO3 + source-id resolution helpers for the Stage 5 evidence-bundle builder.

Stage 5 scopes every ``SourceObservation`` lookup to a single
**owning** canonical source key (the per-indicator ownership rule
documented in :mod:`leaders_db.score.source_plans` and
:mod:`leaders_db.resolve.indicators`). Before that lookup can run
the orchestrator needs two derived values:

- :func:`normalize_iso3` — turn a user-supplied ISO3 string into the
  canonical upper-case 3-character code used as the
  ``countries.iso3`` lookup key.
- :func:`expected_source_ids` — translate the plan's
  ``expected_sources`` tuple (canonical short keys like ``"undp_hdi"``)
  into a ``{key: source.id}`` map by substring-matching every
  persisted ``Source.source_name`` through
  :func:`leaders_db.score.source_plans.canonical_source_key`.

Client-supplied sources (the 2023 matrix) are excluded at the name
level by :func:`leaders_db.score.source_plans.canonical_source_key`
and therefore cannot appear in the bundle even when a
``SourceObservation`` row points at one (requirement §3, §9, §12).

Style invariants (per ``docs/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- Type hints on every public function parameter and return.
- No mutable defaults.
- No ``print()``, no ``TODO(debug)``, no scratch code.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Source
from ..score.source_plans import canonical_source_key

__all__ = [
    "expected_source_ids",
    "normalize_iso3",
]


# ---------------------------------------------------------------------------
# Country / ISO3 normalisation
# ---------------------------------------------------------------------------


def normalize_iso3(country_iso3: str | None) -> str:
    """Normalize a country ISO3 code to upper case; reject empty / wrong length."""
    if not country_iso3:
        raise ValueError("country_iso3 must be a non-empty 3-character code")
    iso3 = country_iso3.strip().upper()
    if len(iso3) != 3:
        raise ValueError(
            f"country_iso3 must be a 3-character code (got {country_iso3!r})"
        )
    return iso3


# ---------------------------------------------------------------------------
# Source-id resolution
# ---------------------------------------------------------------------------


def expected_source_ids(
    session: Session, expected_source_keys: Sequence[str]
) -> dict[str, int]:
    """Map every expected source key to its persisted :class:`Source` row id.

    Only source keys that have a registered :class:`Source` row are
    returned. The substring match in
    :func:`leaders_db.score.source_plans.canonical_source_key` means
    any client source (``Source.source_name`` containing
    ``"client"``) is excluded at this step and therefore cannot
    leak into the bundle. If two ``Source`` rows map to the same
    canonical key (e.g. two versions of V-Dem), the first match
    wins — the production registration is unique per
    ``(source_name, version)`` so this only fires in tests. The
    returned mapping is deterministic across runs because the
    primary-key ordering on ``Source.id`` is the DB insertion order.
    """
    expected_set = set(expected_source_keys)
    rows = session.execute(
        select(Source).order_by(Source.id)
    ).scalars().all()
    out: dict[str, int] = {}
    for source in rows:
        key = canonical_source_key(source.source_name)
        if key is None or key not in expected_set or key in out:
            continue
        out[key] = int(source.id)
    return out
