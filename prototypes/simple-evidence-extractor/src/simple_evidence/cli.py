"""Four-command model-facing evidence CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .models import AccessScope, parse_sentence_id
from .registry import Registry
from .source import load_sources


def main() -> None:
    try:
        socket_path = os.environ.get("EVIDENCE_SOCKET")
        if socket_path:
            from .broker import broker_request

            result = broker_request(
                Path(socket_path),
                arguments=sys.argv[1:],
                capability=os.environ.get("EVIDENCE_CAPABILITY", ""),
            )
        else:
            result = execute_arguments(
                sys.argv[1:],
                role=os.environ.get("EVIDENCE_ROLE", ""),
                registry=_direct_registry(),
                window_id=os.environ.get("EVIDENCE_WINDOW", ""),
            )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc
    print(json.dumps({"ok": True, "entity": result}, ensure_ascii=False, indent=2))


def execute_arguments(
    arguments: list[str],
    *,
    role: str,
    registry: Registry,
    window_id: str,
    scope: AccessScope | None = None,
) -> dict[str, Any]:
    """Execute one parsed action against the runner-owned registry."""

    args = _parser().parse_args(arguments)
    if args.command == "show":
        if args.target.startswith("F-"):
            if args.start is not None or args.end is not None:
                raise ValueError("fact show does not accept sentence bounds")
            _allow_fact(scope, args.target)
            return registry.show_fact(args.target)
        source = registry.sources.get(args.target)
        if source is None:
            raise ValueError(f"unknown manifest source: {args.target}")
        start = 1 if args.start is None else parse_sentence_id(args.start)
        end = (
            min(len(source.sentences), start + 79)
            if args.end is None
            else parse_sentence_id(args.end)
        )
        _allow_range(scope, args.target, start, end)
        return registry.show_source(args.target, start, end, window_id)
    if args.command == "add":
        _require_role(role, "extractor")
        start = parse_sentence_id(args.start)
        end = parse_sentence_id(args.end) if args.end else start
        _allow_range(scope, args.source, start, end)
        return registry.add(
            source_id=args.source,
            start=start,
            end=end,
            summary=args.summary,
            chapters=_chapters(args.chapters),
            fact_type=args.fact_type,
            period_fit=args.period,
            window_id=window_id,
        ).to_dict()
    if args.command == "correct":
        _allow_fact(scope, args.fact_id)
        start = parse_sentence_id(args.start) if args.start else None
        end = parse_sentence_id(args.end) if args.end else None
        if scope is not None and (start is not None or end is not None):
            state = registry.show_fact(args.fact_id)
            _allow_range(
                scope,
                str(state["source_id"]),
                parse_sentence_id(state["start_sentence"]) if start is None else start,
                parse_sentence_id(state["end_sentence"]) if end is None else end,
            )
        return registry.correct(
            args.fact_id,
            role=role,
            start=start,
            end=end,
            summary=args.summary,
            chapters=_chapters(args.chapters) if args.chapters is not None else None,
            fact_type=args.fact_type,
            period_fit=args.period,
        ).to_dict()
    _allow_fact(scope, args.fact_id)
    return registry.confirm(args.fact_id, role).to_dict()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("show")
    show.add_argument("target")
    show.add_argument("start", nargs="?")
    show.add_argument("end", nargs="?")
    add = commands.add_parser("add")
    add.add_argument("source")
    add.add_argument("start")
    add.add_argument("end", nargs="?")
    add.add_argument("--summary", required=True)
    _metadata_arguments(add, defaults=True)
    correct = commands.add_parser("correct")
    correct.add_argument("fact_id")
    correct.add_argument("--start")
    correct.add_argument("--end")
    correct.add_argument("--summary")
    _metadata_arguments(correct, defaults=False)
    confirm = commands.add_parser("confirm")
    confirm.add_argument("fact_id")
    return parser


def _metadata_arguments(parser: argparse.ArgumentParser, *, defaults: bool) -> None:
    parser.add_argument("--chapters")
    parser.add_argument("--type", dest="fact_type", default="unknown" if defaults else None)
    parser.add_argument("--period", default="unknown" if defaults else None)


def _chapters(value: str | None) -> list[str]:
    return [] if not value else value.split(",")


def _required_environment_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is required")
    return Path(value).resolve()


def _direct_registry() -> Registry:
    manifest_path = _required_environment_path("EVIDENCE_MANIFEST")
    registry_path = _required_environment_path("EVIDENCE_REGISTRY")
    return Registry(registry_path, load_sources(manifest_path))


def _require_role(role: str, expected: str) -> None:
    if role != expected:
        raise ValueError(f"command requires {expected} role")


def _allow_range(
    scope: AccessScope | None, source_id: str, start: int, end: int
) -> None:
    if scope is None:
        return
    if (
        source_id != scope.source_id
        or start < scope.start_sentence
        or end > scope.end_sentence
    ):
        raise ValueError("requested source span is outside the assigned range")


def _allow_fact(scope: AccessScope | None, fact_id: str) -> None:
    if scope is not None and fact_id not in scope.fact_ids:
        raise ValueError("fact is outside the assigned allowlist")


if __name__ == "__main__":
    main()
