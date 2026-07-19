"""Command-line entry point for the isolated collector."""

from __future__ import annotations

import argparse
from pathlib import Path

from .collector import collect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ruler")
    parser.add_argument("country")
    parser.add_argument("year", type=int)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--researcher", default="minimax-m3")
    args = parser.parse_args()
    evidence, mappings = collect(
        args.ruler,
        args.country,
        args.year,
        args.output_dir,
        researcher=args.researcher,
    )
    print(evidence)
    print(mappings)


if __name__ == "__main__":
    main()
