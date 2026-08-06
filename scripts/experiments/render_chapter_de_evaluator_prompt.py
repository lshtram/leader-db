"""Render a blinded evaluator prompt for the chapter D/E experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Print all D/E comparisons with labels in the requested order."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    first, second = ("e", "d") if args.reverse else ("d", "e")
    manifest = json.loads(
        (args.experiment_dir / "manifest.json").read_text(encoding="utf-8")
    )

    print(
        """Evaluate two deep chapter-research artifacts for each of ten ruler cases.

The paired researchers received the same frozen ruler, period, chapter questions,
evidence environment, known-resource list, model, web access, and isolation controls.
Their prompts differed. Judge the artifacts, not prose style or length by itself. Do
not search for more information and do not score the rulers.

For each artifact score 0-10 on:

1. material coverage of the ten chapter questions;
2. source authority, independence, and diversity;
3. underlying-source inspection and stable locator quality;
4. factual precision, target-period fit, and retrospective separation;
5. ruler attribution, practical authority, inherited baseline, and external shocks;
6. favorable, adverse, contrary, and reporting-bias balance;
7. distinction between independent facts, repeated coverage, allegations, procedural
   actions, and final findings;
8. honesty and usefulness of unresolved gaps, rejections, and access blockers;
9. reusability, atomicity, inspection-state accuracy, and machine-record validity;
10. efficiency: useful evidence and analytical value relative to tokens, volume, and
    complexity.

Counts are measurements, not quality targets. Penalize padding, artificial record
splitting, inaccurate inspection labels, unstable locators, repeated underlying facts,
unsupported causal claims, generic context presented as ruler conduct, and later
evidence presented as contemporaneous. Credit additional records only when they add a
material and defensible fact.

For each case:

- give ten component scores and an overall score for X and Y;
- name the better artifact or a tie;
- identify concrete strengths and defects with examples;
- say whether any quality loss is compensated by a meaningful efficiency gain; and
- identify valuable features from the weaker artifact that should be preserved.

Finish with an overall recommendation. Promotion requires no meaningful quality
regression, better evidence engineering, and a worthwhile efficiency improvement.
Return Markdown.
"""
    )
    for case_id, case in manifest["cases"].items():
        print(
            f"\n# {case['ruler_name']} — {case['chapter_id']} "
            f"({case['country_name']})\n"
        )
        print("\n## Artifact X\n\n", _output(args.experiment_dir, case_id, case, first))
        print("\n## Artifact Y\n\n", _output(args.experiment_dir, case_id, case, second))


def _output(
    experiment_dir: Path,
    case_id: str,
    case: dict[str, object],
    variant: str,
) -> str:
    if variant == "d":
        return (PROJECT_ROOT / str(case["baseline_output"])).read_text(
            encoding="utf-8"
        )
    return (experiment_dir / case_id / "e/output.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    main()
