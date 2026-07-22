"""Offline, evidence-backed source readiness audit for Stage 0."""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from leaders_db.research.local_evidence_summary import DEFAULT_RULER_EVIDENCE_CONCEPTS
from leaders_db.research.local_prior_schema import LOCAL_PRIOR_MAPPINGS
from leaders_db.sources.concepts import list_concepts, resolve_concept
from leaders_db.sources.registry import build_default_source_registry

from ..paths import processed_dir, raw_dir

_RAW_ALIASES = {"pts": "political_terror_scale"}
_STATES = (
    "identified",
    "vetted",
    "raw_available",
    "adapter_works",
    "normalized",
    "persisted",
    "country_matched",
    "concept_mapped",
    "researcher_routed",
    "validated",
)


@dataclass(frozen=True)
class SourceReadinessRow:
    """One truthful source state assembled from local artifacts only."""

    source_slug: str
    raw_folder: str
    registered: bool
    identified: bool
    vetted: bool
    raw_available: bool
    adapter_works: bool
    normalized: bool
    persisted: bool
    country_matched: bool
    concept_mapped: bool
    researcher_routed: bool
    validated: bool
    available: bool
    observation_count: int
    country_count: int
    year_min: int | None
    year_max: int | None
    indicators: str
    observation_families: str
    raw_files: str
    processed_manifest: str
    blocking_issue: str


def check_all_sources(
    year: int,
    *,
    raw_root: Path | None = None,
    processed_root: Path | None = None,
    catalog_path: Path | None = None,
) -> tuple[SourceReadinessRow, ...]:
    """Audit every registered source and every locally present raw source folder."""

    raw_base = raw_root or raw_dir()
    processed_base = processed_root or processed_dir()
    database_profiles = _database_profiles(
        catalog_path or raw_base.parent / "catalog" / "leaders_db.sqlite"
    )
    fact_profiles = _published_fact_profiles(
        catalog_path or raw_base.parent / "catalog" / "leaders_db.sqlite"
    )
    registry = build_default_source_registry()
    descriptors = {item.source_id.slug: item for item in registry.list_descriptors()}
    raw_names = (
        {path.name for path in raw_base.iterdir() if path.is_dir()} if raw_base.exists() else set()
    )
    reverse_aliases = {folder: slug for slug, folder in _RAW_ALIASES.items()}
    slugs = set(descriptors)
    slugs.update(reverse_aliases.get(name, name) for name in raw_names)
    slugs.update(database_profiles)
    return tuple(
        _audit_source(
            slug,
            descriptor=descriptors.get(slug),
            raw_base=raw_base,
            processed_base=processed_base,
            target_year=year,
            database_profile=database_profiles.get(slug),
            fact_profile=fact_profiles.get(slug),
        )
        for slug in sorted(slugs)
    )


def write_source_readiness_report(
    rows: tuple[SourceReadinessRow, ...], output_dir: Path, *, target_year: int
) -> tuple[Path, Path, Path]:
    """Write JSON, CSV, and Markdown views of the same audit rows."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "source_readiness_report.json"
    csv_path = output_dir / "source_availability_report.csv"
    markdown_path = output_dir / "source_availability_report.md"
    payload = {
        "schema_version": "source_readiness_audit_v1",
        "target_year": target_year,
        "state_order": list(_STATES),
        "available_definition": "validated and researcher_routed",
        "sources": [asdict(row) for row in rows],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(asdict(rows[0])) if rows else [],
            lineterminator="\n",
        )
        if rows:
            writer.writeheader()
            writer.writerows(asdict(row) for row in rows)
    markdown_path.write_text(_markdown(rows, target_year), encoding="utf-8")
    return json_path, csv_path, markdown_path


def _audit_source(
    slug: str,
    *,
    descriptor: Any | None,
    raw_base: Path,
    processed_base: Path,
    target_year: int,
    database_profile: dict[str, Any] | None,
    fact_profile: dict[str, Any] | None,
) -> SourceReadinessRow:
    raw_folder = _RAW_ALIASES.get(slug, slug)
    source_raw = raw_base / raw_folder
    metadata = _read_object(source_raw / "metadata.json")
    raw_files = (
        sorted(
            str(path.relative_to(source_raw))
            for path in source_raw.rglob("*")
            if path.is_file() and path.name != "metadata.json" and not path.name.startswith(".")
        )
        if source_raw.exists()
        else []
    )
    manifest_path, manifest = _latest_manifest(processed_base / slug)
    observation_path = _manifest_observation_path(manifest, processed_base / slug)
    parquet_profile = _observation_profile(observation_path)
    profile = (
        database_profile
        if database_profile and database_profile["count"] >= parquet_profile["count"]
        else parquet_profile
    )
    count = int(profile["count"])
    registered = descriptor is not None
    identified = registered or source_raw.exists()
    vetted = registered and bool(
        metadata and descriptor.display_name and descriptor.attribution_key
    )
    raw_available = bool(raw_files)
    adapter_works = count > 0
    normalized = bool(profile["count"] > 0 and profile["families"] and profile["indicators"])
    persisted = bool((observation_path and observation_path.is_file()) or database_profile)
    identity_family = any("leader_identity" in item for item in profile["families"])
    published_fact_count = int((fact_profile or {}).get("count", 0))
    country_matched = normalized and (
        profile["country_count"] > 0 or published_fact_count > 0 or identity_family
    )
    concept_sources = {
        mapping.source_id.slug
        for concept in list_concepts()
        for mapping in resolve_concept(concept.concept_key)
    }
    concept_mapped = slug in concept_sources
    routed_sources = {
        mapping.source_id.slug
        for concept_key in DEFAULT_RULER_EVIDENCE_CONCEPTS
        for mapping in resolve_concept(concept_key)
    }
    routed_field_keys = {
        field_key for mapping in LOCAL_PRIOR_MAPPINGS for field_key in mapping.field_keys
    }
    published_fields = set((fact_profile or {}).get("field_keys", ()))
    researcher_routed = bool(published_fields.intersection(routed_field_keys)) or (
        slug in routed_sources and concept_mapped
    )
    validated = all(
        (
            identified,
            vetted,
            raw_available,
            adapter_works,
            normalized,
            persisted,
            country_matched,
            concept_mapped,
            researcher_routed,
        )
    )
    blocker = _first_blocker(
        identified=identified,
        vetted=vetted,
        raw_available=raw_available,
        adapter_works=adapter_works,
        normalized=normalized,
        persisted=persisted,
        country_matched=country_matched,
        concept_mapped=concept_mapped,
        researcher_routed=researcher_routed,
    )
    years = profile["years"] or tuple(manifest.get("coverage", {}).get("years", ()))
    return SourceReadinessRow(
        source_slug=slug,
        raw_folder=raw_folder,
        registered=registered,
        identified=identified,
        vetted=vetted,
        raw_available=raw_available,
        adapter_works=adapter_works,
        normalized=normalized,
        persisted=persisted,
        country_matched=country_matched,
        concept_mapped=concept_mapped,
        researcher_routed=researcher_routed,
        validated=validated,
        available=validated,
        observation_count=count,
        country_count=max(
            int(profile["country_count"]), int((fact_profile or {}).get("country_count", 0))
        ),
        year_min=min(years) if years else None,
        year_max=max(years) if years else None,
        indicators="|".join(profile["indicators"]),
        observation_families="|".join(profile["families"]),
        raw_files="|".join(raw_files),
        processed_manifest=_display_path(manifest_path),
        blocking_issue=blocker,
    )


def _latest_manifest(folder: Path) -> tuple[Path | None, dict[str, Any]]:
    paths = sorted(folder.glob("manifest-*.json"), key=lambda path: path.stat().st_mtime)
    if not paths:
        return None, {}
    return paths[-1], _read_object(paths[-1])


def _manifest_observation_path(manifest: dict[str, Any], folder: Path) -> Path | None:
    for asset in manifest.get("output_assets", ()):  # type: ignore[union-attr]
        path = Path(str(asset.get("path", "")))
        if path.suffix == ".parquet":
            return path if path.is_absolute() else Path.cwd() / path
    paths = sorted(folder.glob("observations-*.parquet"))
    return paths[-1] if paths else None


def _observation_profile(path: Path | None) -> dict[str, Any]:
    empty = {"count": 0, "country_count": 0, "years": (), "families": (), "indicators": ()}
    if path is None or not path.is_file():
        return empty
    try:
        from pyarrow import parquet

        table = parquet.read_table(
            path, columns=["year", "country_code", "observation_family", "indicator_code"]
        )
    except (ImportError, OSError, ValueError):
        return empty
    values = table.to_pydict()
    return {
        "count": table.num_rows,
        "country_count": len({item for item in values["country_code"] if item}),
        "years": tuple(sorted({int(item) for item in values["year"] if item is not None})),
        "families": tuple(sorted({str(item) for item in values["observation_family"] if item})),
        "indicators": tuple(sorted({str(item) for item in values["indicator_code"] if item})),
    }


def _database_profiles(path: Path) -> dict[str, dict[str, Any]]:
    """Read persisted normalized coverage without mutating the catalog."""

    if not path.is_file():
        return {}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT source_slug, COUNT(*), COUNT(DISTINCT country_code),
                   MIN(year), MAX(year),
                   GROUP_CONCAT(DISTINCT observation_family),
                   GROUP_CONCAT(DISTINCT indicator_code)
            FROM normalized_observations
            GROUP BY source_slug
            """
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    return {
        str(slug): {
            "count": int(count),
            "country_count": int(countries),
            "years": tuple(
                range(int(year_min), int(year_max) + 1)
                if year_min is not None and year_max is not None
                else ()
            ),
            "families": tuple(sorted(str(families or "").split(","))) if families else (),
            "indicators": tuple(sorted(str(indicators or "").split(","))) if indicators else (),
        }
        for slug, count, countries, year_min, year_max, families, indicators in rows
    }


def _published_fact_profiles(path: Path) -> dict[str, dict[str, Any]]:
    """Return source coverage that has reached published country-year facts."""

    if not path.is_file():
        return {}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT f.country_id, f.field_key, f.source_slugs_json
            FROM country_year_facts f
            """
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        connection.close()
    profiles: dict[str, dict[str, Any]] = {}
    for country_id, field_key, raw_slugs in rows:
        try:
            slugs = json.loads(raw_slugs or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(slugs, list):
            continue
        for slug_value in slugs:
            slug = str(slug_value)
            profile = profiles.setdefault(
                slug, {"count": 0, "country_ids": set(), "field_keys": set()}
            )
            profile["count"] += 1
            profile["country_ids"].add(int(country_id))
            profile["field_keys"].add(str(field_key))
    return {
        slug: {
            "count": profile["count"],
            "country_count": len(profile["country_ids"]),
            "field_keys": tuple(sorted(profile["field_keys"])),
        }
        for slug, profile in profiles.items()
    }


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _first_blocker(**states: bool) -> str:
    messages = {
        "identified": "source is neither registered nor locally staged",
        "vetted": "clean adapter registration or valid local metadata is missing",
        "raw_available": "no non-metadata raw files are staged",
        "adapter_works": "no successful processed manifest with observations",
        "normalized": "no readable normalized observations",
        "persisted": "normalized observation asset is not persisted",
        "country_matched": "observations lack matched country identity",
        "concept_mapped": "observation families do not map to research concepts",
        "researcher_routed": "no executable research question routes this source",
    }
    return next((messages[key] for key, value in states.items() if not value), "")


def _display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _markdown(rows: tuple[SourceReadinessRow, ...], year: int) -> str:
    lines = [
        f"# Source readiness audit — target year {year}",
        "",
        "`available` means the source reached every state through researcher routing.",
        "",
        "| Source | Observations | Years | Countries | Available | Blocking issue |",
        "|---|---:|---|---:|---|---|",
    ]
    for row in rows:
        years = f"{row.year_min}–{row.year_max}" if row.year_min is not None else "—"
        lines.append(
            f"| {row.source_slug} | {row.observation_count} | {years} | "
            f"{row.country_count} | {'yes' if row.available else 'no'} | "
            f"{row.blocking_issue or '—'} |"
        )
    return "\n".join(lines) + "\n"


__all__ = ["SourceReadinessRow", "check_all_sources", "write_source_readiness_report"]
