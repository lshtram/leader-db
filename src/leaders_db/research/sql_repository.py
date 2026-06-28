"""SQLite-backed research evidence repository."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine

from leaders_db.sources.contracts import (
    EvidenceQuery,
    JsonValue,
    NormalizedObservation,
    ObservationValueType,
    RawLocator,
    SourceAttribution,
    SourceId,
    SourceManifest,
    SourceWarning,
    TransformLocator,
)
from leaders_db.sources.query import EvidenceRepository


class SqlEvidenceRepository(EvidenceRepository):
    """Read normalized observations from SQLite without touching raw files."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def query_observations(self, query: EvidenceQuery) -> tuple[NormalizedObservation, ...]:
        statement = text(
            """
            SELECT *
            FROM normalized_observations
            WHERE (:source_all = 1 OR source_slug IN :source_slugs)
              AND (:family_all = 1 OR observation_family IN :families)
              AND (:indicator_all = 1 OR indicator_code IN :indicators)
              AND (:year_all = 1 OR year IN :years)
              AND (:country_all = 1 OR country_code IN :countries OR country_name IN :countries)
              AND (:leader_all = 1 OR leader_id IN :leaders OR leader_name IN :leaders)
            ORDER BY id
            """
        ).bindparams(
            bindparam("source_slugs", expanding=True),
            bindparam("families", expanding=True),
            bindparam("indicators", expanding=True),
            bindparam("years", expanding=True),
            bindparam("countries", expanding=True),
            bindparam("leaders", expanding=True),
        )
        params = _query_params(query)
        with self._engine.connect() as conn:
            rows = conn.execute(statement, params).mappings().all()
        return tuple(row_to_observation(row) for row in rows)

    def get_manifest(self, source_id: SourceId, run_id: str | None = None) -> SourceManifest:
        raise KeyError(
            f"SqlEvidenceRepository does not store manifests in Increment 5: "
            f"source={source_id.slug!r}, run_id={run_id!r}"
        )

    def get_attributions(self, source_ids: Sequence[SourceId]) -> tuple[SourceAttribution, ...]:
        return ()


def write_observations(engine: Engine, observations: Sequence[NormalizedObservation]) -> None:
    """Insert or replace normalized observations for test/local persistence slices."""

    if not observations:
        return
    statement = text(
        """
        INSERT INTO normalized_observations (
            source_slug, observation_id, observation_family, indicator_code,
            value_json, value_type, year, country_code, country_name,
            leader_id, leader_name, unit, scale, source_version,
            raw_locator_json, transform_locator_json, quality_flags_json,
            warnings_json, extension_json, scope_json
        ) VALUES (
            :source_slug, :observation_id, :observation_family, :indicator_code,
            :value_json, :value_type, :year, :country_code, :country_name,
            :leader_id, :leader_name, :unit, :scale, :source_version,
            :raw_locator_json, :transform_locator_json, :quality_flags_json,
            :warnings_json, :extension_json, :scope_json
        )
        ON CONFLICT(source_slug, observation_id) DO UPDATE SET
            observation_family = excluded.observation_family,
            indicator_code = excluded.indicator_code,
            value_json = excluded.value_json,
            value_type = excluded.value_type,
            year = excluded.year,
            country_code = excluded.country_code,
            country_name = excluded.country_name,
            leader_id = excluded.leader_id,
            leader_name = excluded.leader_name,
            unit = excluded.unit,
            scale = excluded.scale,
            source_version = excluded.source_version,
            raw_locator_json = excluded.raw_locator_json,
            transform_locator_json = excluded.transform_locator_json,
            quality_flags_json = excluded.quality_flags_json,
            warnings_json = excluded.warnings_json,
            extension_json = excluded.extension_json,
            scope_json = excluded.scope_json
        """
    )
    with engine.begin() as conn:
        conn.execute(statement, [observation_to_row(observation) for observation in observations])


def observation_to_row(observation: NormalizedObservation) -> dict[str, Any]:
    """Serialize a source-layer observation to DB parameters."""

    scope = {
        "country": observation.country_code,
        "country_name": observation.country_name,
        "leader": observation.leader_id,
        "leader_name": observation.leader_name,
        "year": observation.year,
    }
    return {
        "source_slug": observation.source_id.slug,
        "observation_id": observation.observation_id,
        "observation_family": observation.observation_family,
        "indicator_code": observation.indicator_code,
        "value_json": _dumps(observation.value),
        "value_type": observation.value_type,
        "year": observation.year,
        "country_code": observation.country_code,
        "country_name": observation.country_name,
        "leader_id": observation.leader_id,
        "leader_name": observation.leader_name,
        "unit": observation.unit,
        "scale": observation.scale,
        "source_version": observation.source_version,
        "raw_locator_json": _dumps(asdict(observation.raw_locator)),
        "transform_locator_json": _dumps(asdict(observation.transform_locator)),
        "quality_flags_json": _dumps(observation.quality_flags),
        "warnings_json": _dumps(tuple(_warning_to_json(w) for w in observation.warnings)),
        "extension_json": _dumps(observation.extension),
        "scope_json": _dumps({key: value for key, value in scope.items() if value is not None}),
    }


def row_to_observation(row: Mapping[str, Any]) -> NormalizedObservation:
    """Deserialize a DB row mapping to a source-layer observation."""

    return NormalizedObservation(
        source_id=SourceId(slug=str(row["source_slug"])),
        observation_id=str(row["observation_id"]),
        observation_family=str(row["observation_family"]),
        indicator_code=str(row["indicator_code"]),
        value=_loads(row["value_json"]),
        value_type=_observation_value_type(row["value_type"]),
        year=row["year"],
        country_code=row["country_code"],
        country_name=row["country_name"],
        leader_id=row["leader_id"],
        leader_name=row["leader_name"],
        unit=row["unit"],
        scale=row["scale"],
        source_version=row["source_version"],
        raw_locator=RawLocator(**_loads(row["raw_locator_json"])),
        transform_locator=TransformLocator(**_loads(row["transform_locator_json"])),
        quality_flags=tuple(_loads(row["quality_flags_json"])),
        warnings=tuple(_warning_from_json(item) for item in _loads(row["warnings_json"])),
        extension=_loads(row["extension_json"]),
    )


def _query_params(query: EvidenceQuery) -> dict[str, Any]:
    source_slugs = tuple(source_id.slug for source_id in query.source_ids or ())
    return {
        "source_all": int(query.source_ids is None),
        "source_slugs": source_slugs,
        "family_all": int(query.observation_families is None),
        "families": query.observation_families or (),
        "indicator_all": int(query.indicator_codes is None),
        "indicators": query.indicator_codes or (),
        "year_all": int(query.years is None),
        "years": query.years or (),
        "country_all": int(query.countries is None),
        "countries": query.countries or (),
        "leader_all": int(query.leaders is None),
        "leaders": query.leaders or (),
    }


def _warning_to_json(warning: SourceWarning) -> dict[str, Any]:
    payload = asdict(warning)
    payload["source_id"] = warning.source_id.slug if warning.source_id is not None else None
    return payload


def _warning_from_json(payload: Mapping[str, Any]) -> SourceWarning:
    source_slug = payload.get("source_id")
    return SourceWarning(
        code=str(payload["code"]),
        message=str(payload["message"]),
        severity=payload.get("severity", "warning"),
        source_id=SourceId(slug=str(source_slug)) if source_slug is not None else None,
        context=payload.get("context", {}),
    )


def _observation_value_type(value_type: Any) -> ObservationValueType:
    if value_type in {"numeric", "categorical", "text", "boolean", "json", "missing"}:
        return value_type
    raise ValueError(f"Unknown observation value_type: {value_type!r}")


def _dumps(value: JsonValue | Sequence[JsonValue] | Mapping[str, JsonValue]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads(value: Any) -> Any:
    return json.loads(str(value))
