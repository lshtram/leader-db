"""Immutable correction ledger for code-bound evidence citations."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .artifacts import (
    ArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from .citation_candidate import candidate_from_draft
from .citation_index import FrozenCitationIndex
from .citation_models import (
    BoundEvidenceDraft,
    CitationAttemptBinding,
    CitationDecision,
    CitationSelection,
    EvidenceIntent,
)
from .ingest import FrozenExtraction
from .models import EvidenceCandidate, SourceDescriptor


class CitationLedgerError(ValueError):
    """A citation proposal cannot be safely written or confirmed."""


class CitationLedger:
    """Bind, revise, confirm, or discard exact source spans."""

    def __init__(
        self,
        *,
        root: Path,
        extractions: tuple[FrozenExtraction, ...],
        sources: dict[str, SourceDescriptor],
        segment_characters: int,
        maximum_attempts: int,
    ) -> None:
        self._root = root
        self._store = ArtifactStore(root)
        self._index = FrozenCitationIndex(
            extractions,
            segment_characters=segment_characters,
        )
        self._sources = sources
        self._maximum_attempts = maximum_attempts
        for extraction in extractions:
            source = sources.get(extraction.source_id)
            if source is None or source.source_sha256 != extraction.raw_sha256:
                raise CitationLedgerError(
                    f"source metadata is missing or hash-mismatched: {extraction.source_id}"
                )

    def index_locator(self, source_id: str, locator: str):
        """Persist and return the exact model-readable index for one locator."""
        index = self._index.locator_index(source_id, locator)
        identity = hashlib.sha256(f"{source_id}\x1f{locator}".encode()).hexdigest()[:16]
        self._store.write_immutable(f"inspections/{identity}.json", index)
        return index

    def inspected_index(self, source_id: str, locator: str):
        """Return a previously persisted locator index or fail closed."""
        identity = hashlib.sha256(f"{source_id}\x1f{locator}".encode()).hexdigest()[:16]
        path = self._root / f"inspections/{identity}.json"
        if not path.exists():
            raise CitationLedgerError("inspect this exact source locator first")
        stored = self._index.locator_index(source_id, locator)
        if canonical_json_bytes(stored) != path.read_bytes():
            raise CitationLedgerError("persisted locator inspection changed")
        return stored

    def bind(
        self,
        intent: EvidenceIntent,
        *,
        proposal_id: str | None = None,
    ) -> BoundEvidenceDraft:
        """Write one immutable exact-span attempt and return what code stored."""
        resolved_id = proposal_id or _proposal_id(intent)
        _validate_proposal_id(resolved_id)
        self._ensure_undecided(resolved_id)
        attempts = self._attempts(resolved_id, allow_pending_binding=True)
        if len(attempts) >= self._maximum_attempts:
            raise CitationLedgerError(
                f"{resolved_id} reached the {self._maximum_attempts}-attempt limit"
            )
        if attempts:
            previous = attempts[-1]
            if previous.intent.citation.source_id != intent.citation.source_id:
                raise CitationLedgerError("correction cannot change source identity")
            if _semantic_payload(previous.intent) != _semantic_payload(intent):
                raise CitationLedgerError(
                    "span correction cannot change the semantic evidence intent"
                )
        excerpt, start_char, end_char = self._index.resolve(intent.citation)
        draft = BoundEvidenceDraft(
            proposal_id=resolved_id,
            attempt=len(attempts) + 1,
            intent=intent,
            exact_excerpt=excerpt,
            excerpt_start_char=start_char,
            excerpt_end_char=end_char,
        )
        attempt_path = _attempt_path(draft)
        attempt_sha256 = sha256_bytes(canonical_json_bytes(draft))
        previous_binding_sha256 = (
            sha256_file(self._root / _binding_path(resolved_id, draft.attempt - 1))
            if draft.attempt > 1
            else None
        )
        self._store.write_immutable(
            _binding_path(resolved_id, draft.attempt),
            CitationAttemptBinding(
                proposal_id=resolved_id,
                attempt=draft.attempt,
                attempt_sha256=attempt_sha256,
                previous_binding_sha256=previous_binding_sha256,
            ),
        )
        self._store.write_immutable(attempt_path, draft)
        return draft

    def revise_span(
        self,
        proposal_id: str,
        selection: CitationSelection,
    ) -> BoundEvidenceDraft:
        """Revise only the citation selection of a pending proposal."""
        latest = self._latest(proposal_id)
        return self.bind(
            latest.intent.model_copy(update={"citation": selection}),
            proposal_id=proposal_id,
        )

    def revise_segment_range(
        self,
        proposal_id: str,
        start_segment_id: str,
        end_segment_id: str,
    ) -> BoundEvidenceDraft:
        """Revise only segment bounds while preserving source and locator identity."""

        latest = self._latest(proposal_id)
        citation = latest.intent.citation
        return self.revise_span(
            proposal_id,
            CitationSelection(
                source_id=citation.source_id,
                source_sha256=citation.source_sha256,
                locator=citation.locator,
                start_segment_id=start_segment_id,
                end_segment_id=end_segment_id,
            ),
        )

    def confirm(self, proposal_id: str) -> EvidenceCandidate:
        """Confirm the latest bound attempt and persist a canonical v2 candidate."""
        _validate_proposal_id(proposal_id)
        existing = self._decision(proposal_id)
        if existing is not None:
            return self._confirmed_candidate(proposal_id, existing)
        latest = self._latest(proposal_id)
        candidate = self._candidate_from(latest)
        candidate_path = f"confirmed/{candidate.evidence_id}.json"
        candidate_sha256 = self._store.write_immutable(candidate_path, candidate)
        binding_sha256 = sha256_file(
            self._root / _binding_path(proposal_id, latest.attempt)
        )
        decision = CitationDecision(
            proposal_id=proposal_id,
            attempt=latest.attempt,
            decision="confirmed",
            evidence_id=candidate.evidence_id,
            candidate_sha256=candidate_sha256,
            binding_sha256=binding_sha256,
        )
        self._store.write_immutable(_decision_path(proposal_id), decision)
        return candidate

    def bind_and_confirm(self, intent: EvidenceIntent) -> EvidenceCandidate:
        """Idempotently bind and confirm one immutable normalized intent."""
        proposal_id = _proposal_id(intent)
        attempts = self._attempts(proposal_id, allow_pending_binding=True)
        if attempts:
            if attempts[-1].intent != intent:
                raise CitationLedgerError(
                    "existing proposal intent differs from requested resume"
                )
            if self._decision(proposal_id) is not None:
                return self.confirm(proposal_id)
            if not (
                self._root / _attempt_path(attempts[-1])
            ).exists():
                self.bind(intent, proposal_id=proposal_id)
            return self.confirm(proposal_id)
        return self.confirm(self.bind(intent, proposal_id=proposal_id).proposal_id)

    def confirmed_intents(self) -> tuple[EvidenceIntent, ...]:
        """Return intents only after revalidating every confirmation and hash chain."""
        intents: list[EvidenceIntent] = []
        for path in sorted((self._root / "proposals").glob("*/decision.json")):
            proposal_id = path.parent.name
            decision = self._decision(proposal_id)
            if decision is None or decision.decision != "confirmed":
                continue
            self.confirm(proposal_id)
            intents.append(self._latest(proposal_id).intent)
        return tuple(intents)

    def discard(self, proposal_id: str, reason: str) -> CitationDecision:
        """Discard the latest attempt without creating accepted evidence."""
        _validate_proposal_id(proposal_id)
        self._ensure_undecided(proposal_id)
        latest = self._latest(proposal_id)
        decision = CitationDecision(
            proposal_id=proposal_id,
            attempt=latest.attempt,
            decision="discarded",
            reason=reason,
        )
        self._store.write_immutable(_decision_path(proposal_id), decision)
        return decision

    def _latest(self, proposal_id: str) -> BoundEvidenceDraft:
        attempts = self._attempts(proposal_id)
        if not attempts:
            raise CitationLedgerError(f"unknown proposal {proposal_id}")
        return attempts[-1]

    def _attempts(
        self,
        proposal_id: str,
        *,
        allow_pending_binding: bool = False,
    ) -> list[BoundEvidenceDraft]:
        paths = sorted(
            (self._root / "proposals" / proposal_id).glob("attempt-[0-9][0-9].json")
        )
        attempts: list[BoundEvidenceDraft] = []
        previous_binding_sha256: str | None = None
        for expected_attempt, path in enumerate(paths, start=1):
            expected_name = f"attempt-{expected_attempt:02d}.json"
            if path.name != expected_name:
                raise CitationLedgerError("citation attempt history is not sequential")
            draft = BoundEvidenceDraft.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            if (
                draft.proposal_id != proposal_id
                or draft.attempt != expected_attempt
            ):
                raise CitationLedgerError(
                    "citation attempt identity differs from its artifact path"
                )
            excerpt, start_char, end_char = self._index.resolve(
                draft.intent.citation
            )
            if (
                draft.exact_excerpt != excerpt
                or draft.excerpt_start_char != start_char
                or draft.excerpt_end_char != end_char
            ):
                raise CitationLedgerError(
                    "citation attempt differs from the frozen source span"
                )
            binding_path = self._root / _binding_path(
                proposal_id,
                expected_attempt,
            )
            if not binding_path.exists():
                raise CitationLedgerError("citation attempt lacks its hash binding")
            binding = CitationAttemptBinding.model_validate_json(
                binding_path.read_text(encoding="utf-8")
            )
            if (
                binding.proposal_id != proposal_id
                or binding.attempt != expected_attempt
                or binding.attempt_sha256 != sha256_file(path)
                or binding.previous_binding_sha256 != previous_binding_sha256
            ):
                raise CitationLedgerError("citation attempt hash chain is invalid")
            previous_binding_sha256 = sha256_file(binding_path)
            attempts.append(draft)
        binding_paths = sorted(
            (self._root / "proposals" / proposal_id).glob(
                "attempt-[0-9][0-9].binding.json"
            )
        )
        if len(binding_paths) == len(attempts) + 1:
            expected_pending = f"attempt-{len(attempts) + 1:02d}.binding.json"
            if binding_paths[-1].name != expected_pending:
                raise CitationLedgerError("citation binding history is not sequential")
            if not allow_pending_binding:
                raise CitationLedgerError("citation proposal has an incomplete attempt")
        elif len(binding_paths) != len(attempts):
            raise CitationLedgerError("citation attempt and binding histories diverge")
        return attempts

    def _ensure_undecided(self, proposal_id: str) -> None:
        if (self._root / _decision_path(proposal_id)).exists():
            raise CitationLedgerError(f"proposal {proposal_id} already has a decision")

    def _decision(self, proposal_id: str) -> CitationDecision | None:
        path = self._root / _decision_path(proposal_id)
        if not path.exists():
            return None
        return CitationDecision.model_validate_json(path.read_text(encoding="utf-8"))

    def _confirmed_candidate(
        self,
        proposal_id: str,
        decision: CitationDecision,
    ) -> EvidenceCandidate:
        if decision.decision != "confirmed":
            raise CitationLedgerError(f"proposal {proposal_id} was discarded")
        latest = self._latest(proposal_id)
        binding_path = self._root / _binding_path(proposal_id, latest.attempt)
        if (
            decision.proposal_id != proposal_id
            or decision.attempt != latest.attempt
            or decision.evidence_id is None
            or decision.binding_sha256 != sha256_file(binding_path)
        ):
            raise CitationLedgerError("confirmation decision does not match latest attempt")
        path = self._root / f"confirmed/{decision.evidence_id}.json"
        if (
            not path.exists()
            or sha256_file(path) != decision.candidate_sha256
        ):
            raise CitationLedgerError("confirmed candidate artifact changed or is missing")
        candidate = EvidenceCandidate.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        expected = self._candidate_from(latest)
        if candidate != expected or candidate.evidence_id != decision.evidence_id:
            raise CitationLedgerError("confirmed candidate differs from bound attempt")
        return candidate

    def _candidate_from(self, draft: BoundEvidenceDraft) -> EvidenceCandidate:
        return candidate_from_draft(
            draft,
            self._source(draft.intent.citation.source_id),
        )

    def _source(self, source_id: str) -> SourceDescriptor:
        try:
            return self._sources[source_id]
        except KeyError as error:
            raise CitationLedgerError(f"missing source metadata for {source_id}") from error

def _proposal_id(intent: EvidenceIntent) -> str:
    identity = "\x1f".join((intent.citation.source_id, intent.draft_id)).encode()
    return f"EF-P{hashlib.sha256(identity).hexdigest()[:12]}"


def _validate_proposal_id(proposal_id: str) -> None:
    if re.fullmatch(r"EF-P[0-9a-f]{12}", proposal_id) is None:
        raise CitationLedgerError("invalid proposal ID")


def _semantic_payload(intent: EvidenceIntent) -> dict[str, object]:
    return intent.model_dump(mode="json", exclude={"citation"})


def _attempt_path(draft: BoundEvidenceDraft) -> str:
    return f"proposals/{draft.proposal_id}/attempt-{draft.attempt:02d}.json"


def _decision_path(proposal_id: str) -> str:
    return f"proposals/{proposal_id}/decision.json"


def _binding_path(proposal_id: str, attempt: int) -> str:
    return f"proposals/{proposal_id}/attempt-{attempt:02d}.binding.json"


__all__ = ["CitationLedger", "CitationLedgerError"]
