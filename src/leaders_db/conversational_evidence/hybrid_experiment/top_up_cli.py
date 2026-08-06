"""Run generic post-curation top-ups for one complete ruler dossier."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .top_up import run_top_ups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--researcher", default="gpt-5.4-mini")
    parser.add_argument("--cost-ceiling-usd", default=7.5, type=float)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    report = run_top_ups(
        project_root=root,
        output_dir=args.output_dir,
        researcher_name=args.researcher,
        cost_ceiling_usd=args.cost_ceiling_usd,
    )
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
