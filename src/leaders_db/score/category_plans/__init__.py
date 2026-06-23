"""Category source plans for the per-category rating modules.

This subpackage contains one :class:`CategorySourcePlan` per
rating category from requirement §4 (``docs/requirements/top-level-requirements.md``
§4). The full list of categories the prototype ships:

- :data:`NUCLEAR_PLAN`
- :data:`INTERNATIONAL_PEACE_PLAN`
- :data:`DOMESTIC_VIOLENCE_PLAN`
- :data:`POLITICAL_FREEDOM_PLAN`
- :data:`ECONOMIC_WELLBEING_PLAN`
- :data:`SOCIAL_WELLBEING_PLAN`
- :data:`INTEGRITY_PLAN`
- :data:`EFFECTIVENESS_PLAN`

The :data:`CATEGORY_SOURCE_PLANS` registry and the
:func:`get_category_source_plan` accessor live in
:mod:`leaders_db.score.source_plans` (the public facade). This
subpackage is **internal** to the scoring layer; consumers should
import from :mod:`leaders_db.score` (the package root) so the
backwards-compat re-exports keep working.

Each per-category module declares:

- the ``<CATEGORY>_INDICATORS`` tuple — the :class:`IndicatorSpec`
  rows for the category, with the owning source key set explicitly
  (per the per-indicator ownership rule in
  :mod:`leaders_db.score.source_plans`),
- the ``<CATEGORY>_PLAN`` constant — the
  :class:`CategorySourcePlan` instance for the category.

Style invariants (per ``docs/process/coding-guidelines.md``):

- ``from __future__ import annotations`` for forward-reference safety.
- No mutable defaults; no ``print()``, no ``TODO(debug)``, no scratch.
- Each file declares one category plan only (the 400-line convention
  would otherwise be exceeded once all 8 are colocated).
"""

from __future__ import annotations

from collections.abc import Mapping

from ..evidence import CategorySourcePlan
from .domestic_violence import (
    DOMESTIC_VIOLENCE_INDICATORS,
    DOMESTIC_VIOLENCE_PLAN,
)
from .economic_wellbeing import (
    ECONOMIC_WELLBEING_INDICATORS,
    ECONOMIC_WELLBEING_PLAN,
)
from .effectiveness import EFFECTIVENESS_INDICATORS, EFFECTIVENESS_PLAN
from .integrity import INTEGRITY_INDICATORS, INTEGRITY_PLAN
from .international_peace import (
    INTERNATIONAL_PEACE_INDICATORS,
    INTERNATIONAL_PEACE_PLAN,
)
from .nuclear import NUCLEAR_INDICATORS, NUCLEAR_PLAN
from .political_freedom import (
    POLITICAL_FREEDOM_INDICATORS,
    POLITICAL_FREEDOM_PLAN,
)
from .social_wellbeing import (
    SOCIAL_WELLBEING_INDICATORS,
    SOCIAL_WELLBEING_PLAN,
)

#: Registry of every category source plan this subpackage ships.
#: The builder looks up the plan here by ``category_key``; the
#: :func:`leaders_db.score.source_plans.get_category_source_plan`
#: accessor raises :class:`ValueError` for a key that is not present.
CATEGORY_SOURCE_PLANS: Mapping[str, CategorySourcePlan] = {
    NUCLEAR_PLAN.category_key: NUCLEAR_PLAN,
    INTERNATIONAL_PEACE_PLAN.category_key: INTERNATIONAL_PEACE_PLAN,
    DOMESTIC_VIOLENCE_PLAN.category_key: DOMESTIC_VIOLENCE_PLAN,
    POLITICAL_FREEDOM_PLAN.category_key: POLITICAL_FREEDOM_PLAN,
    ECONOMIC_WELLBEING_PLAN.category_key: ECONOMIC_WELLBEING_PLAN,
    SOCIAL_WELLBEING_PLAN.category_key: SOCIAL_WELLBEING_PLAN,
    INTEGRITY_PLAN.category_key: INTEGRITY_PLAN,
    EFFECTIVENESS_PLAN.category_key: EFFECTIVENESS_PLAN,
}

__all__ = [
    "CATEGORY_SOURCE_PLANS",
    "DOMESTIC_VIOLENCE_INDICATORS",
    "DOMESTIC_VIOLENCE_PLAN",
    "ECONOMIC_WELLBEING_INDICATORS",
    "ECONOMIC_WELLBEING_PLAN",
    "EFFECTIVENESS_INDICATORS",
    "EFFECTIVENESS_PLAN",
    "INTEGRITY_INDICATORS",
    "INTEGRITY_PLAN",
    "INTERNATIONAL_PEACE_INDICATORS",
    "INTERNATIONAL_PEACE_PLAN",
    "NUCLEAR_INDICATORS",
    "NUCLEAR_PLAN",
    "POLITICAL_FREEDOM_INDICATORS",
    "POLITICAL_FREEDOM_PLAN",
    "SOCIAL_WELLBEING_INDICATORS",
    "SOCIAL_WELLBEING_PLAN",
]
