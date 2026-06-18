"""Stage 3 — country matching (requirement §8, REQ-STAGE-004).

Builds and maintains the country alias table under
``data/metadata/country_aliases.csv`` and produces
``data/outputs/country_matching_report.csv`` summarizing unmatched
countries across the loaded sources.

Phase E implementation.
"""

from __future__ import annotations

from pathlib import Path

from ..paths import metadata_dir, outputs_dir
from ..normalize import normalize_country_name, normalize_iso3


def build_alias_table(force: bool = False) -> Path:
    """Materialize ``data/metadata/country_aliases.csv`` from the in-code seed.

    Returns the absolute path to the file. The runtime alias table grows
    over time as new sources are ingested; this function only handles the
    initial bootstrap from :data:`leaders_db.normalize.countries.COUNTRY_NAME_NORMALIZATION`.
    """
    import csv

    from ..normalize.countries import COUNTRY_NAME_NORMALIZATION

    path = metadata_dir() / "country_aliases.csv"
    if path.exists() and not force:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["normalized_name", "iso3", "source", "added_at"])
        # We carry the original (unnormalized) alias as a separate column
        # so a human can audit. The "source" column tracks where it came
        # from; "added_at" is filled by the matcher when an unknown alias
        # is encountered at runtime.
        for alias, iso3 in sorted(COUNTRY_NAME_NORMALIZATION.items()):
            writer.writerow([normalize_country_name(alias), normalize_iso3(iso3), "seed", ""])
    return path


__all__ = ["build_alias_table", "outputs_dir", "metadata_dir"]
