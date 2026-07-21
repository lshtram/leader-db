"""CLI for the isolated budgeted hybrid experiment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .depth_models import SaturationPolicy
from .runner import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ruler", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--ruler-id", default="")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--researcher", default="gpt-5.4-mini")
    parser.add_argument("--cost-ceiling-usd", default=7.0, type=float)
    parser.add_argument("--saturation-v3", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    result = run_experiment(
        project_root=root,
        output_dir=args.output_dir,
        ruler=args.ruler,
        country=args.country,
        iso3=args.iso3,
        year=args.year,
        ruler_id=args.ruler_id,
        researcher_name=args.researcher,
        cost_ceiling_usd=args.cost_ceiling_usd,
        saturation_policy=(
            SaturationPolicy(
                candidate_target_per_wave=50,
                opened_target_per_wave=30,
            )
            if args.saturation_v3
            else None
        ),
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
