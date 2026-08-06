"""Codex PreToolUse hook that permits only one citation-writer command prefix."""

from __future__ import annotations

import argparse
import json
import shlex
import sys


def main() -> None:
    args = _parser().parse_args()
    event = json.load(sys.stdin)
    command = event.get("tool_input", {}).get("command")
    allowed = json.loads(args.allowed_prefix_json)
    if not isinstance(command, str) or not _matches(command, allowed):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "Only the configured evidence citation CLI is permitted."
                        ),
                    }
                }
            )
        )


def _matches(command: str, allowed: list[str]) -> bool:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="();<>|&")
        lexer.whitespace_split = True
        lexer.commenters = ""
        actual = list(lexer)
    except ValueError:
        return False
    if "$" in command:
        return False
    suffix = actual[len(allowed) :]
    if actual[: len(allowed)] != allowed or not suffix:
        return False
    operators = {";", "&&", "||", "|", "&", ">", ">>", "<", "<<", "(", ")"}
    if any(token in operators for token in actual):
        return False
    if any("$(" in token or "`" in token or "\n" in token for token in actual):
        return False
    arities = {"inspect": 3, "revise": 4, "finish": 2}
    return (
        suffix[0] == "record"
        and (len(suffix) == 2 or (len(suffix) == 3 and suffix[1] == "--json"))
    ) or (suffix[0] in arities and len(suffix) == arities[suffix[0]])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allowed-prefix-json", required=True)
    return parser


if __name__ == "__main__":
    main()
