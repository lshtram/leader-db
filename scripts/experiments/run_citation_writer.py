"""Constrained CLI for deterministic evidence citation binding."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from leaders_db.evidence_funnel.citation_ledger import CitationLedger
from leaders_db.evidence_funnel.citation_models import EvidenceIntent
from leaders_db.evidence_funnel.config import load_evidence_funnel_config
from leaders_db.evidence_funnel.ingest import load_frozen_extractions
from leaders_db.evidence_funnel.sources import load_source_descriptors


def main() -> None:
    args = _parser().parse_args()
    config = load_evidence_funnel_config(args.config)
    extractions = load_frozen_extractions(
        args.frozen_root / "extracted",
        config.frozen_document_ids,
    )
    ledger = CitationLedger(
        root=args.ledger,
        extractions=extractions,
        sources=load_source_descriptors(
            extractions,
            args.frozen_root / "document_reader_experiment.json",
        ),
        segment_characters=config.citations.segment_characters,
        maximum_attempts=config.citations.maximum_binding_attempts,
    )
    if args.command == "inspect":
        result = ledger.index_locator(args.source_id, args.locator)
    elif args.command == "record":
        payload = args.intent_json_option or args.intent_json
        if args.intent_json_option is not None and args.intent_json is not None:
            raise ValueError("record accepts one JSON payload")
        if payload is None:
            raise ValueError("record requires one JSON payload")
        result = ledger.bind(_intent(payload, ledger, config.methodology_ids))
    elif args.command == "revise":
        result = ledger.revise_segment_range(
            args.proposal_id,
            args.start_segment_id,
            args.end_segment_id,
        )
    else:
        result = ledger.confirm(args.proposal_id)
    print(result.model_dump_json(indent=2))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("source_id")
    inspect.add_argument("locator")
    record = subparsers.add_parser("record")
    record.add_argument("intent_json", nargs="?")
    record.add_argument("--json", dest="intent_json_option")
    revise = subparsers.add_parser("revise")
    revise.add_argument("proposal_id")
    revise.add_argument("start_segment_id")
    revise.add_argument("end_segment_id")
    finish = subparsers.add_parser("finish")
    finish.add_argument("proposal_id")
    return parser


def _intent(
    payload: str,
    ledger: CitationLedger,
    methodology_ids: tuple[str, ...],
) -> EvidenceIntent:
    raw = json.loads(payload)
    if "citation" in raw:
        intent = EvidenceIntent.model_validate(raw)
        index = ledger.inspected_index(
            intent.citation.source_id,
            intent.citation.locator,
        )
        if intent.citation.source_sha256 != index.source_sha256:
            raise ValueError("citation source hash does not match the inspected source")
        questions = intent.question_ids
        if not questions or not set(questions).issubset(methodology_ids):
            raise ValueError("question IDs must belong to the configured chapter")
        return intent
    source_id = str(raw.pop("source_id"))
    locator = str(raw.pop("locator"))
    index = ledger.inspected_index(source_id, locator)
    questions = raw.pop("question_ids")
    if not questions or not set(questions).issubset(methodology_ids):
        raise ValueError("question IDs must belong to the configured chapter")
    start_segment_id = raw.pop("start_segment_id")
    end_segment_id = raw.pop("end_segment_id")
    mechanism = raw.pop("mechanism", "[not separately decomposed]")
    outcome = raw.pop("outcome", "[not separately decomposed]")
    attribution = raw.pop("attribution", source_id)
    period_fit = raw.pop("period_fit", "target ruler-period")
    return EvidenceIntent.model_validate(
        {
            **raw,
            "citation": {
                "source_id": source_id,
                "source_sha256": index.source_sha256,
                "locator": locator,
                "start_segment_id": start_segment_id,
                "end_segment_id": end_segment_id,
            },
            "question_ids": questions,
            "mechanism": mechanism,
            "outcome": outcome,
            "attribution": attribution,
            "period_fit": period_fit,
        }
    )


if __name__ == "__main__":
    main()
