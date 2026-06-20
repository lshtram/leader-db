"""Stage 9 ``score-category`` command + its ``--all-countries`` helper.

The :func:`score_category` Typer command is the public Stage 9 entry
point. It dispatches between three mutually-exclusive paths:

- ``--country <ISO3>`` — the narrow single-country read-only seam
  (:func:`leaders_db.score.stage9.score_category_for_country`). Opens
  a session on the configured DB, builds the Stage 5 evidence bundle
  for the requested (country, year, category), and prints a concise
  result summary. No ``ruler_scores`` row is persisted.
- ``--all-countries`` — the all-countries batch seam
  (:func:`leaders_db.score.stage9.score_category_for_all_countries`).
  Writes a one-row-per-country CSV with the canonical missingness
  columns so a reviewer can quantify how much data is missing and
  where the gaps live. Default output path
  ``data/outputs/<category>_<year>_scores.csv``;
  ``--output`` overrides it.
- Neither flag — preserves the existing batch "not implemented yet"
  placeholder so existing callers see no behaviour change. Full
  multi-country / multi-category scoring remains a Phase E item.

The :func:`_run_score_category_all_countries` helper is extracted
from the Typer callback so the command body stays under the
50-statement convention. The helper owns the unsupported-category
guard, the default-output resolution, the seam invocation, and the
concise summary print so the Typer callback remains a thin
dispatcher.

``--country`` and ``--all-countries`` are mutually exclusive.
"""

from __future__ import annotations

from pathlib import Path

import typer

from ..config import default_config_path
from ._app import app
from ._helpers import _safe_load_config


@app.command("score-category")
def score_category(
    year: int = typer.Option(..., "--year", "-y"),
    category: str = typer.Option(
        ...,
        "--category",
        help=(
            "One of: political_freedom, economic_wellbeing, "
            "social_wellbeing, integrity, effectiveness, "
            "domestic_violence, international_peace"
        ),
    ),
    country: str | None = typer.Option(
        None,
        "--country",
        "--country-iso3",
        help=(
            "Optional ISO3 of a single country (e.g. MEX). When supplied "
            "with a Stage 9 dispatcher-registered category, the command "
            "runs the Stage 9 production seam against the configured "
            "DB and prints a concise score summary. Unsupported "
            "categories fail with a clear error listing the supported "
            "set. Mutually exclusive with --all-countries; omit both "
            "to keep the batch not-implemented placeholder (Phase E)."
        ),
    ),
    all_countries: bool = typer.Option(
        False,
        "--all-countries",
        help=(
            "Score the configured category for every country in the DB "
            "for the given year. Only categories registered in the "
            "Stage 9 dispatcher are accepted; an unsupported category fails with a clear "
            "error listing the supported set. Writes a one-row-per-"
            "country CSV with missingness columns. Mutually "
            "exclusive with --country; omit both to keep the batch "
            "not-implemented placeholder."
        ),
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Destination CSV path for the --all-countries batch. "
            "Defaults to data/outputs/<category>_<year>_scores.csv. "
            "Parent directories are created if missing. Ignored when "
            "--all-countries is not set."
        ),
    ),
    config: Path = typer.Option(default_config_path(), "--config", "-c"),
) -> None:
    """Stage 9–10: score one category for one year.

    With ``--country <ISO3>`` the command runs the **narrow single-
    country read-only Stage 9 seam** for a dispatcher-registered
    deterministic scorer. It opens a session on
    the configured DB, builds the Stage 5 evidence bundle for the
    requested (country, year, category), and prints a concise result
    summary (country/year/category/score or insufficient-data,
    human_review_required, flags, observed/expected counts). No
    ``ruler_scores`` row is persisted in this step — that wiring is
    a follow-on once the Stage 4 leader resolver lands.

    With ``--all-countries`` the command runs the **all-countries
    batch seam** for the requested category/year: one
    :class:`ScoreResult` per :class:`Country` row in ``iso3`` order,
    countries with no eligible observations emit a clean
    ``is_insufficient_data=True`` row rather than being dropped.
    The command writes a one-row-per-country CSV with the canonical
    missingness columns so a reviewer can quantify how much data is
    missing and where the gaps live. The default output path is
    ``data/outputs/<category>_<year>_scores.csv``; ``--output``
    overrides it. The command prints a concise summary (rows,
    scored_count, insufficient_count, output path).

    ``--country`` and ``--all-countries`` are mutually exclusive.
    With neither set the command prints the existing batch
    "not implemented yet" placeholder; full multi-country / multi-
    category scoring remains a Phase E item.
    """
    from ._helpers import _not_implemented_yet

    # Mutual exclusion: --country and --all-countries are two
    # production paths; running both would silently disagree on the
    # scope (one country vs every country).
    if country is not None and all_countries:
        raise typer.BadParameter(
            "--country and --all-countries are mutually exclusive; "
            "use --country for a single ISO3 or --all-countries for "
            "the per-DB batch."
        )

    cfg = _safe_load_config(config)

    # Single-country production path. Only the registered categories
    # in ``leaders_db.score.dispatch`` are accepted; unsupported
    # categories fail fast with a typer.BadParameter listing the
    # supported set so the user can pick the right category without
    # reading the package source.
    if country is not None:
        from ..db.session import session_scope
        from ..score.dispatch import supported_score_categories
        from ..score.stage9 import score_category_for_country

        iso3 = country.strip().upper()
        supported = supported_score_categories()
        if category not in supported:
            raise typer.BadParameter(
                f"unsupported category {category!r}. Supported categories: "
                f"[{', '.join(supported)}]."
            )

        typer.echo(
            f"[Stage 9] score category {category!r} for country "
            f"{iso3} year {year}"
        )

        try:
            with session_scope(cfg.database.url) as session:
                result = score_category_for_country(
                    session,
                    country_iso3=iso3,
                    year=year,
                    category_key=category,
                )
        except ValueError as exc:
            # Surface the underlying ``ValueError`` (unknown country /
            # unknown category) as a typer.BadParameter so the user
            # sees a clear error rather than a Python traceback. The
            # dispatcher's error message already lists the supported
            # categories for the unsupported-category case; for the
            # unknown-country case the bundle builder names the
            # missing ISO3.
            raise typer.BadParameter(str(exc)) from exc

        typer.echo(f"  country:           {result.iso3}")
        typer.echo(f"  category:          {result.category_key}")
        typer.echo(f"  year:              {result.year}")
        if result.is_insufficient_data:
            typer.echo("  score:             insufficient_data")
        else:
            assert result.system_proposed_score_1_10 is not None
            assert result.normalized_score_0_1 is not None
            typer.echo(
                f"  score:             {result.system_proposed_score_1_10}/10 "
                f"(normalized={result.normalized_score_0_1:.4f})"
            )
        if result.missingness is not None:
            typer.echo(
                f"  observed/expected: "
                f"{result.missingness.total_observed}/"
                f"{result.missingness.total_expected}"
            )
        typer.echo(f"  human_review:      {result.human_review_required}")
        if result.review_flags:
            flags_str = ", ".join(flag.value for flag in result.review_flags)
            typer.echo(f"  review_flags:      {flags_str}")
        typer.echo(
            f"  observation_refs:  {len(result.observation_refs)}"
        )
        return

    # All-countries batch production path. This is the 2022 all-
    # country social_wellbeing vertical slice (and the canonical
    # reusable pattern for the per-category slices that follow).
    # Only registered categories are accepted; unsupported
    # categories fail fast with the supported set listed. The
    # CSV is the single missingness-investigation artifact; the
    # command prints a concise summary after the write so the
    # user can spot a problem without re-opening the file.
    if all_countries:
        _run_score_category_all_countries(
            category=category,
            year=year,
            database_url=cfg.database.url,
            output=output,
        )
        return

    typer.echo(f"[Stage 9] score category {category!r} for year {year}")
    _not_implemented_yet(
        f"score/{category}.py",
        "Phase E. Each category lives in its own module per requirement §9.",
    )


def _run_score_category_all_countries(
    *,
    category: str,
    year: int,
    database_url: str,
    output: Path | None,
) -> None:
    """Execute the ``score-category --all-countries`` body.

    Extracted from :func:`score_category` so the Typer command
    body stays under the 50-statement convention. The function
    owns the unsupported-category guard, the default-output
    resolution, the seam invocation, and the concise summary
    print so the Typer callback remains a thin dispatcher.
    """
    from ..db.session import session_scope
    from ..paths import outputs_dir
    from ..score.dispatch import supported_score_categories
    from ..score.stage9 import (
        score_category_for_all_countries,
        write_score_results_csv,
    )

    supported = supported_score_categories()
    if category not in supported:
        raise typer.BadParameter(
            f"unsupported category {category!r}. Supported categories: "
            f"[{', '.join(supported)}]."
        )

    target_path = (
        output.resolve()
        if output is not None
        else (outputs_dir() / f"{category}_{year}_scores.csv")
    )

    typer.echo(
        f"[Stage 9] score category {category!r} for all countries "
        f"year {year} -> {target_path}"
    )

    try:
        with session_scope(database_url) as session:
            results = score_category_for_all_countries(
                session,
                year=year,
                category_key=category,
            )
    except ValueError as exc:
        # The unsupported-category case is already filtered
        # above; the remaining ``ValueError`` is from the bundle
        # builder. There are no "missing countries" in the batch
        # path (the DB is the country source), so this surfaces a
        # structural seam error rather than a data gap.
        raise typer.BadParameter(str(exc)) from exc

    written = write_score_results_csv(results, target_path, category_key=category)

    scored = sum(1 for r in results if not r.is_insufficient_data)
    insufficient = sum(1 for r in results if r.is_insufficient_data)
    typer.echo("Done. Summary:")
    typer.echo(f"  rows:              {len(results)}")
    typer.echo(f"  scored_count:      {scored}")
    typer.echo(f"  insufficient_count: {insufficient}")
    typer.echo(f"  output_path:       {written}")


__all__ = ["_run_score_category_all_countries", "score_category"]
