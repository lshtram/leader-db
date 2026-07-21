"""Curate and activate one complete controlled hybrid ruler dossier."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .full_curation import curate_full_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--researcher", default="gpt-5.4-mini")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    report = curate_full_run(
        project_root=root,
        output_dir=args.output_dir,
        researcher_name=args.researcher,
    )
    sys.stdout.write(json.dumps(report, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
