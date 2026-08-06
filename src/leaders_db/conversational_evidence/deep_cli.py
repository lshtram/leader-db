"""Command-line entry point for the candidate-heavy research experiment."""

from __future__ import annotations

import argparse
from pathlib import Path

from .deep_collector import collect_deep


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ruler", required=True)
    parser.add_argument("--country", required=True)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--local-priors", required=True, type=Path)
    parser.add_argument("--researcher", default="gpt-5.4-mini")
    parser.add_argument("--workflow", type=Path)
    args = parser.parse_args()
    profile = collect_deep(
        args.ruler,
        args.country,
        args.iso3,
        args.year,
        args.output_dir,
        args.local_priors,
        researcher=args.researcher,
        workflow_path=args.workflow,
    )
    print(profile)


if __name__ == "__main__":
    main()
