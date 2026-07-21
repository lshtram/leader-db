"""CLI for the isolated one-chapter saturation pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .saturation import SaturationPolicy, run_chapter_saturation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ruler", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--researcher", default="gpt-5.4-mini")
    parser.add_argument("--cost-ceiling-usd", default=3.0, type=float)
    parser.add_argument("--candidate-target-per-wave", default=35, type=int)
    parser.add_argument("--opened-target-per-wave", default=20, type=int)
    parser.add_argument("--accepted-url-min", default=20, type=int)
    parser.add_argument("--accepted-url-max", default=35, type=int)
    parser.add_argument("--domain-min", default=10, type=int)
    parser.add_argument("--marginal-url-stop", default=2, type=int)
    parser.add_argument("--max-waves", default=4, type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    result = run_chapter_saturation(
        project_root=root,
        output_dir=args.output_dir,
        ruler=args.ruler,
        country=args.country,
        iso3=args.iso3,
        year=args.year,
        chapter_id=args.chapter.upper(),
        researcher_name=args.researcher,
        cost_ceiling_usd=args.cost_ceiling_usd,
        policy=SaturationPolicy(
            candidate_target_per_wave=args.candidate_target_per_wave,
            opened_target_per_wave=args.opened_target_per_wave,
            accepted_url_min=args.accepted_url_min,
            accepted_url_max=args.accepted_url_max,
            domain_min=args.domain_min,
            marginal_url_stop=args.marginal_url_stop,
            max_waves=args.max_waves,
        ),
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
