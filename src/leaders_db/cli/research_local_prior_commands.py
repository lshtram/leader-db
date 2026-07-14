"""Local structured-prior research CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from sqlalchemy.exc import SQLAlchemyError

from ..research.local_prior_schema import LOCAL_PRIOR_METHOD_VERSION
from .research_common import fail


def register_local_prior_commands(research_app: typer.Typer) -> None:
    research_app.command("build-local-prior")(research_build_local_prior_cmd)
    research_app.command("build-local-prior-slice")(research_build_local_prior_slice_cmd)
    research_app.command("local-evidence")(research_local_evidence_cmd)


def research_local_evidence_cmd(
    methodology_id: str = typer.Option(..., "--methodology-id"),
    iso3: list[str] | None = typer.Option(None, "--iso3"),
    year: int | None = typer.Option(None, "--year"),
    start_year: int | None = typer.Option(None, "--start-year"),
    end_year: int | None = typer.Option(None, "--end-year"),
    output_json: bool = typer.Option(False, "--json"),
    db_url: str | None = typer.Option(None, "--db-url"),
) -> None:
    """Safely read local structured evidence for internet-research workers."""

    from collections import Counter

    from ..db.engine import build_engine
    from ..db.readiness import DatabaseReadinessError, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.local_structured_prior import (
        LocalPriorPeriod,
        LocalStructuredPriorRequest,
        build_local_structured_prior,
    )

    try:
        period = LocalPriorPeriod(year=year, start_year=start_year, end_year=end_year)
    except ValueError as exc:
        _emit_local_evidence_error(
            str(exc),
            methodology_id=methodology_id,
            year=year,
            start_year=start_year,
            end_year=end_year,
            output_json=output_json,
        )

    requested_iso3s = tuple(dict.fromkeys(code.upper().strip() for code in (iso3 or ())))
    if not requested_iso3s:
        _emit_local_evidence_error(
            "At least one --iso3 is required; this command will not dump all local DB "
            "rows by default.",
            methodology_id=methodology_id,
            year=year,
            start_year=start_year,
            end_year=end_year,
            output_json=output_json,
        )

    try:
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(
            engine,
            required_tables=("countries", "country_years", "country_year_facts"),
        )
        records = [
            build_local_structured_prior(
                engine,
                LocalStructuredPriorRequest(
                    methodology_id=methodology_id,
                    iso3=code,
                    period=period,
                ),
            ).model_dump(mode="json")
            for code in requested_iso3s
        ]
    except (DatabaseReadinessError, SQLAlchemyError, ValueError) as exc:
        _emit_local_evidence_error(
            str(exc),
            methodology_id=methodology_id,
            year=year,
            start_year=start_year,
            end_year=end_year,
            output_json=output_json,
        )

    counts = Counter(str(record["status"]) for record in records)
    payload = {
        "method_version": "local_evidence_v1",
        "methodology_id": methodology_id,
        "period": {"year": year, "start_year": start_year, "end_year": end_year},
        "requested_iso3": list(requested_iso3s),
        "record_count": len(records),
        "status_counts": dict(sorted(counts.items())),
        "client_matrix_policy": "excluded_as_evidence",
        "records": records,
    }
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        if counts.get("error"):
            raise typer.Exit(1)
        return
    typer.echo(f"local_evidence_records: {len(records)}; statuses: {payload['status_counts']}")
    if counts.get("error"):
        raise typer.Exit(1)


def research_build_local_prior_cmd(
    methodology_id: str = typer.Option(..., "--methodology-id"),
    iso3: str = typer.Option(..., "--iso3"),
    year: int | None = typer.Option(None, "--year"),
    start_year: int | None = typer.Option(None, "--start-year"),
    end_year: int | None = typer.Option(None, "--end-year"),
    leader_name: str | None = typer.Option(None, "--leader"),
    leader_id: int | None = typer.Option(None, "--leader-id"),
    period_label: str | None = typer.Option(None, "--period-label"),
    output_path: Path | None = typer.Option(None, "--output", "-o", dir_okay=False, writable=True),
    output_json: bool = typer.Option(False, "--json"),
    db_url: str | None = typer.Option(None, "--db-url"),
) -> None:
    """Build a local structured-prior artifact for an internet/manual task."""

    from ..db.engine import build_engine
    from ..db.readiness import DatabaseReadinessError, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.local_structured_prior import (
        LeaderPriorMetadata,
        LocalPriorPeriod,
        LocalStructuredPriorRequest,
        build_local_structured_prior,
    )

    try:
        period = LocalPriorPeriod(year=year, start_year=start_year, end_year=end_year)
        request = LocalStructuredPriorRequest(
            methodology_id=methodology_id,
            iso3=iso3,
            period=period,
            leader=LeaderPriorMetadata(
                name=leader_name,
                leader_id=leader_id,
                period_label=period_label,
            ),
        )
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(
            engine,
            required_tables=("countries", "country_years", "country_year_facts"),
        )
        artifact = build_local_structured_prior(engine, request)
    except (DatabaseReadinessError, SQLAlchemyError, ValueError) as exc:
        _fail_local_prior(
            str(exc), methodology_id=methodology_id, iso3=iso3, year=year,
            start_year=start_year, end_year=end_year, leader_name=leader_name,
            leader_id=leader_id, period_label=period_label, output_path=output_path,
            output_json=output_json,
        )

    payload = artifact.model_dump(mode="json")
    _write_json_if_requested(payload, output_path)
    if artifact.status == "error":
        _emit_error_artifact(payload, output_json=output_json)
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    if output_path is not None:
        typer.echo(f"local_prior_written: {output_path}")
        return
    typer.echo(f"status: {artifact.status}; local_facts: {len(artifact.local_facts)}")


def research_build_local_prior_slice_cmd(
    methodology_id: str = typer.Option(..., "--methodology-id"),
    year: int = typer.Option(..., "--year"),
    output_dir: Path = typer.Option(
        ...,
        "--output-dir",
        dir_okay=True,
        file_okay=False,
        writable=True,
    ),
    shard_size: int = typer.Option(10, "--shard-size", min=1),
    output_json: bool = typer.Option(False, "--json"),
    db_url: str | None = typer.Option(None, "--db-url"),
) -> None:
    """Build local-prior artifacts for every included country-year in a slice."""

    from ..db.engine import build_engine
    from ..db.readiness import DatabaseReadinessError, assert_database_ready
    from ..db.session import default_sqlite_url
    from ..research.local_prior_slice import build_local_prior_slice_package

    try:
        engine = build_engine(db_url or default_sqlite_url())
        assert_database_ready(
            engine,
            required_tables=(
                "countries", "country_years", "leaders", "ruler_years",
                "ruler_identity_adjudications", "country_year_facts",
            ),
        )
        manifest = build_local_prior_slice_package(
            engine,
            methodology_id=methodology_id,
            year=year,
            output_dir=output_dir,
            shard_size=shard_size,
        )
    except (DatabaseReadinessError, SQLAlchemyError, ValueError) as exc:
        fail(str(exc), output_json=output_json)

    payload = manifest.model_dump(mode="json")
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(
        f"local_prior_slice_written: {output_dir}; artifacts: {manifest.artifact_count}; "
        f"statuses: {manifest.status_counts}"
    )


def _write_json_if_requested(payload: dict[str, object], output_path: Path | None) -> None:
    if output_path is None:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _emit_error_artifact(payload: dict[str, object], *, output_json: bool) -> None:
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"error: {payload['missing_or_empty_reason']}")
    raise typer.Exit(1)


def _fail_local_prior(message: str, **kwargs: object) -> None:
    output_path = kwargs.pop("output_path")
    output_json = bool(kwargs.pop("output_json"))
    payload = {
        "methodology_id": kwargs["methodology_id"],
        "question_text": "",
        "category": "",
        "country": {"iso3": str(kwargs["iso3"]).upper().strip(), "name": None},
        "period": {
            "year": kwargs["year"],
            "start_year": kwargs["start_year"],
            "end_year": kwargs["end_year"],
        },
        "leader": {
            "name": kwargs["leader_name"],
            "leader_id": kwargs["leader_id"],
            "period_label": kwargs["period_label"],
        },
        "status": "error",
        "local_facts": [],
        "missing_or_empty_reason": message,
        "recommended_research_instructions": [
            "The local structured-prior builder failed; inspect missing_or_empty_reason "
            "before launching dependent research workers."
        ],
        "client_matrix_policy": "excluded_as_evidence",
        "method_version": LOCAL_PRIOR_METHOD_VERSION,
        "mapping_note": None,
    }
    _write_json_if_requested(payload, output_path if isinstance(output_path, Path) else None)
    _emit_error_artifact(payload, output_json=output_json)


def _emit_local_evidence_error(
    message: str,
    *,
    methodology_id: str,
    year: int | None,
    start_year: int | None,
    end_year: int | None,
    output_json: bool,
) -> None:
    payload = {
        "method_version": "local_evidence_v1",
        "methodology_id": methodology_id,
        "period": {"year": year, "start_year": start_year, "end_year": end_year},
        "requested_iso3": [],
        "record_count": 0,
        "status": "error",
        "status_counts": {"error": 1},
        "client_matrix_policy": "excluded_as_evidence",
        "records": [],
        "missing_or_empty_reason": message,
    }
    if output_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"error: {message}")
    raise typer.Exit(1)


__all__ = [
    "register_local_prior_commands",
    "research_build_local_prior_cmd",
    "research_build_local_prior_slice_cmd",
    "research_local_evidence_cmd",
]
