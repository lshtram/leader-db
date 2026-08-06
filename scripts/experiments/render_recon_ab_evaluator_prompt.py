"""Render a blinded evaluator prompt for the reconnaissance A/B experiment."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    """Print both ruler comparisons with labels in the requested order."""

    parser = argparse.ArgumentParser()
    parser.add_argument("experiment_dir", type=Path)
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Present B as X and A as Y to test position sensitivity.",
    )
    parser.add_argument(
        "--challenger",
        choices=("b", "c"),
        default="b",
        help="Variant compared with the current A prompt.",
    )
    args = parser.parse_args()
    first, second = (
        (args.challenger, "a") if args.reverse else ("a", args.challenger)
    )

    print(
        """Evaluate two reconnaissance research memos for each of two rulers.

The memos were produced from the same identity, local factual briefing, model, web
access, and execution settings. Their prompts differed. Judge the research artifacts,
not their writing style and not their length by itself. Do not search for additional
information.

For each memo score 0-10 on:

1. useful and material evidence discovered;
2. source authority, independence, and diversity;
3. underlying-source inspection and locator quality;
4. factual precision and period fit;
5. ruler attribution and authority limits;
6. favorable, adverse, and contrary evidence balance;
7. information-environment and reporting-bias analysis;
8. duplication control and distinction between sources and underlying facts;
9. usefulness to later deep researchers;
10. efficiency: useful research delivered relative to apparent volume and complexity.

Identify concrete strengths and defects with examples. Count neither URLs nor words as
quality by themselves. Penalize source lists that were merely discovered rather than
opened, vague locators, unsupported claims, repetition, and breadth that displaces
careful extraction. Credit additional material only when it is credible and useful.

For each ruler:

- give the ten component scores and an overall score for X and Y;
- name the better memo, or a tie;
- explain whether the difference is large enough to justify changing the prompt;
- identify valuable features from the weaker memo that should be preserved.

Finish with one overall recommendation. Return Markdown.
"""
    )
    for case in ("putin", "tshisekedi"):
        case_dir = args.experiment_dir / case
        print(f"\n# Case: {case}\n")
        print(
            "\n## Memo X\n\n",
            (case_dir / first / "output.md").read_text(encoding="utf-8"),
            sep="",
        )
        print(
            "\n## Memo Y\n\n",
            (case_dir / second / "output.md").read_text(encoding="utf-8"),
            sep="",
        )


if __name__ == "__main__":
    main()
