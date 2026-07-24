"""Render a blinded evaluator prompt for the deep chapter A/C experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    """Print the three comparisons with labels in the requested order."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument("--reverse", action="store_true")
    args = parser.parse_args()
    first, second = ("c", "a") if args.reverse else ("a", "c")
    manifest = json.loads(
        (args.experiment_dir / "manifest.json").read_text(encoding="utf-8")
    )

    print(
        """Evaluate two deep chapter-research artifacts for each of three ruler cases.

The paired researchers received the same ruler, period, chapter questions, evidence
environment, known-resource list, model, web access, and execution controls. Their
prompts differed. Judge the research artifacts, not their prose style or length by
itself. Do not search for more information and do not score the rulers.

For each artifact score 0-10 on:

1. material coverage of the ten chapter questions;
2. source authority, independence, and diversity;
3. underlying-source inspection and stable locator quality;
4. factual precision, target-period fit, and retrospective separation;
5. ruler attribution, practical authority, inherited baseline, and external shocks;
6. favorable, adverse, contrary, and reporting-bias balance;
7. distinction between independent facts, repeated coverage, allegations, and findings;
8. honesty and usefulness of unresolved gaps, rejections, and access blockers;
9. reusability of atomic evidence records and their machine appendix;
10. efficiency: useful evidence and analytical value relative to volume and complexity.

Counts are measurements, not quality targets. Penalize padding, arbitrary stopping,
unopened leads presented as evidence, unstable locators, repeated underlying facts,
unsupported causal claims, generic country context presented as ruler conduct, and
later evidence presented as if contemporaneous. Credit additional records only when
they add a material and defensible fact.

For each case:

- give ten component scores and an overall score for X and Y;
- name the better artifact or a tie;
- explain whether the difference justifies changing the prompt;
- identify concrete strengths and defects with examples;
- identify valuable features from the weaker artifact that should be preserved.

Finish with an overall recommendation, including whether more cases are needed before
production promotion. Return Markdown.
"""
    )
    for case_id, case in manifest["cases"].items():
        case_dir = args.experiment_dir / case_id
        print(
            f"\n# {case['ruler_name']} — {case['chapter_id']} "
            f"({case['country_name']})\n"
        )
        print(
            "\n## Artifact X\n\n",
            (case_dir / first / "output.md").read_text(encoding="utf-8"),
            sep="",
        )
        print(
            "\n## Artifact Y\n\n",
            (case_dir / second / "output.md").read_text(encoding="utf-8"),
            sep="",
        )


if __name__ == "__main__":
    main()
