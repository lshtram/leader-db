"""Stage 0 — source availability probe (requirement §8, REQ-STAGE-001).

For every priority source in §6, this stage probes:

- Whether the canonical download URL is reachable.
- Whether the file requires a login or paywall.
- The license / terms of use.
- The local folder presence and ``metadata.json`` validity.
- The known coverage limits (years and countries).

Outputs:
- ``data/outputs/source_availability_report.csv``
- ``data/outputs/source_availability_report.md``

Phase B (source vetting) precedes Stage 0 implementation; see
``docs/workplan.md``. The runner will land here during Phase C once the
probe checklist in ``docs/sources/vetting/plan.md`` is finalized.
"""

from __future__ import annotations

from ..paths import PRIORITY_SOURCES, outputs_dir


def check_all_sources(year: int) -> dict[str, str]:
    """Return a per-source verdict map.

    Implemented during Phase C (data acquisition).
    """
    raise NotImplementedError(
        "check_all_sources is not implemented yet. Phase B (source vetting) "
        "precedes this; see docs/workplan.md."
    )


__all__ = ["PRIORITY_SOURCES", "check_all_sources", "outputs_dir"]
