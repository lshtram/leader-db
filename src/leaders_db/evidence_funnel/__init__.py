"""Question-driven, resumable evidence-funnel infrastructure."""

from .citation_ledger import CitationLedger
from .citation_models import EvidenceIntent
from .config import CitationPolicy, EvidenceFunnelConfig, load_evidence_funnel_config
from .models import (
    ChunkRoutingDecision,
    ClaimCluster,
    DocumentSectionMap,
    EvidenceCandidate,
    ExperimentalJudgePacket,
    FunnelRunManifest,
    QuestionEvidenceBrief,
)

__all__ = [
    "ChunkRoutingDecision",
    "CitationLedger",
    "CitationPolicy",
    "ClaimCluster",
    "DocumentSectionMap",
    "EvidenceCandidate",
    "EvidenceFunnelConfig",
    "EvidenceIntent",
    "ExperimentalJudgePacket",
    "FunnelRunManifest",
    "QuestionEvidenceBrief",
    "load_evidence_funnel_config",
]
