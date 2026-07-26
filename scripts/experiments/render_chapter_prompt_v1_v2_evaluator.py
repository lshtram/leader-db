"""Render one order of the blind AMLO v1/v2 deep-research evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    """Print the rubric and concealed X/Y artifacts."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("order", choices=("forward", "reverse"))
    args = parser.parse_args()
    experiment_dir = args.experiment_dir.resolve()
    label_map = json.loads(
        (
            experiment_dir / "evaluation" / args.order / "label-map.json"
        ).read_text(encoding="utf-8")
    )
    rubric = (experiment_dir / "frozen/evaluator-rubric.md").read_text(
        encoding="utf-8"
    )
    print(rubric)
    print(
        "\nThe two researchers received identical frozen case inputs, model, reasoning "
        "profile, web permissions, and isolation controls. Return Markdown.\n"
    )
    for label in ("X", "Y"):
        version = label_map[label]
        output = (
            experiment_dir / version / "run-01/output.md"
        ).read_text(encoding="utf-8")
        print(f"\n# Artifact {label}\n\n{output}")


if __name__ == "__main__":
    main()
