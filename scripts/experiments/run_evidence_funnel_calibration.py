"""Run the experimental three-source evidence-funnel calibration."""

from __future__ import annotations

import argparse
from pathlib import Path

from leaders_db.evidence_funnel.calibration import load_questions, run_calibration
from leaders_db.evidence_funnel.config import load_evidence_funnel_config
from leaders_db.evidence_funnel.ingest import load_frozen_extractions
from leaders_db.evidence_funnel.sources import load_source_descriptors


def main() -> None:
    args = _parser().parse_args()
    project_root = Path(__file__).resolve().parents[2]
    config = load_evidence_funnel_config(args.config)
    extractions = load_frozen_extractions(
        args.frozen_root / "extracted",
        config.frozen_document_ids,
    )
    sources = load_source_descriptors(
        extractions,
        args.frozen_root / "document_reader_experiment.json",
    )
    result = run_calibration(
        project_root=project_root,
        config_path=args.config,
        frozen_root=args.frozen_root,
        config=config,
        extractions=extractions,
        sources=sources,
        questions_payload=load_questions(args.frozen_root / "questions.json"),
        profiles_path=args.profiles,
        output_root=args.output,
        document_ids=(
            tuple(args.documents)
            if args.documents
            else (
                config.frozen_document_ids
                if args.complete_frozen_package
                else config.calibration_document_ids
            )
        ),
    )
    print(result.model_dump_json(indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/evidence-funnel/amlo-2022-5b-v2.json"),
    )
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--documents",
        nargs="+",
        help="Run an explicit ordered subset of configured frozen document IDs.",
    )
    selection.add_argument(
        "--complete-frozen-package",
        action="store_true",
        help="Run all configured frozen documents instead of the calibration trio.",
    )
    return parser


if __name__ == "__main__":
    main()
