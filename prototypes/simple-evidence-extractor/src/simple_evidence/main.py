"""Human-facing standalone CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .registry import Registry
from .source import load_sources
from .worker import run_evidence_job


def main() -> None:
    args = _parser().parse_args()
    if args.command == "prepare":
        sources = load_sources(args.manifest)
        result = {
            source_id: {
                "title": item.spec.title,
                "extracted_sha256": item.extracted_sha256,
                "original_sha256": item.original_sha256,
                "sentence_count": len(item.sentences),
            }
            for source_id, item in sources.items()
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    elif args.command == "materialize":
        result = Registry(
            args.registry, load_sources(args.manifest)
        ).materialize(args.output)
    else:
        result = run_evidence_job(
            manifest_path=args.manifest,
            config_path=args.config,
            output_dir=args.output,
            source_filter=tuple(args.sources or ()),
            maximum_windows=args.max_windows,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="simple-evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    materialize = commands.add_parser("materialize")
    materialize.add_argument("--manifest", type=Path, required=True)
    materialize.add_argument("--registry", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--sources", nargs="+")
    run.add_argument("--max-windows", type=int)
    return parser


if __name__ == "__main__":
    main()

