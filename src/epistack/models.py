"""Core data models for Epistack-Adversarial."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import hashlib
import json
from datetime import datetime


class EdgeType(Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    QUALIFIES = "qualifies"
    SUPERSEDES = "supersedes"
    DEPENDS_ON = "depends_on"


class ClaimStatus(Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    REFUTED = "refuted"
    SUPERSEDED = "superseded"
    VERIFIED = "verified"


class ConfidenceLevel(Enum):
    HIGH = "high"          # Wilson CI lower > 0.8
    MEDIUM = "medium"      # Wilson CI lower 0.5-0.8
    LOW = "low"            # Wilson CI lower 0.2-0.5
    CONTESTED = "contested"  # Cross-model disagreement > 40%
    UNKNOWN = "unknown"    # Insufficient trials


@dataclass
class Source:
    url: str
    title: str
    source_type: str  # paper, blog, debate_transcript, official_doc, dataset
    accessed_at: str
    content_hash: str  # SHA-256 of source content at extraction time
    author: Optional[str] = None
    date_published: Optional[str] = None
    credibility_signals: dict = field(default_factory=dict)  # citation_count, retraction_status, etc.

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()


@dataclass
class Claim:
    id: str
    text: str
    source: Source
    extracted_by: str  # model that extracted this claim
    extraction_context: str  # surrounding text / page number / timestamp
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: ClaimStatus = ClaimStatus.ACTIVE
    confidence: Optional["ClaimConfidence"] = None
    evolution_history: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "source": {"url": self.source.url, "title": self.source.title, "type": self.source.source_type},
            "extracted_by": self.extracted_by,
            "status": self.status.value,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "created_at": self.created_at,
        }


@dataclass
class ClaimConfidence:
    evidence_strength: float  # [0,1] from Pass3 multi-trial
    evidence_ci: tuple  # (lower, upper) Wilson CI
    logical_consistency: float  # [0,1] from DAG consistency check
    adversarial_robustness: float  # [0,1] survived N/M attacks
    source_quality: float  # [0,1] from source credibility signals
    cross_model_agreement: float  # [0,1] agreement across model families
    trials_run: int = 0
    models_checked: list = field(default_factory=list)

    @property
    def composite_score(self) -> float:
        """Multiplicative scoring — any zero kills total."""
        return (
            self.evidence_strength
            * self.logical_consistency
            * self.adversarial_robustness
            * self.source_quality
            * self.cross_model_agreement
        )

    @property
    def level(self) -> ConfidenceLevel:
        if self.cross_model_agreement < 0.6:
            return ConfidenceLevel.CONTESTED
        if self.trials_run < 3:
            return ConfidenceLevel.UNKNOWN
        lower = self.evidence_ci[0] if self.evidence_ci else 0
        if lower > 0.8:
            return ConfidenceLevel.HIGH
        if lower > 0.5:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW

    def to_dict(self) -> dict:
        return {
            "composite": round(self.composite_score, 3),
            "level": self.level.value,
            "dimensions": {
                "evidence_strength": round(self.evidence_strength, 3),
                "evidence_ci": [round(x, 3) for x in self.evidence_ci] if self.evidence_ci else None,
                "logical_consistency": round(self.logical_consistency, 3),
                "adversarial_robustness": round(self.adversarial_robustness, 3),
                "source_quality": round(self.source_quality, 3),
                "cross_model_agreement": round(self.cross_model_agreement, 3),
            },
            "trials_run": self.trials_run,
            "models_checked": self.models_checked,
        }


@dataclass
class Edge:
    source_claim_id: str
    target_claim_id: str
    edge_type: EdgeType
    evidence: str  # why this relationship exists
    confidence: float = 1.0
    created_by: str = ""  # model or human


@dataclass
class Position:
    """A position in a discourse map — one side of a contested question."""
    id: str
    question: str
    stance: str  # e.g., "Lab leak origin" or "Natural spillover"
    strongest_cases: list = field(default_factory=list)  # claim IDs
    biggest_holes: list = field(default_factory=list)  # weakness descriptions
    supporting_claims: list = field(default_factory=list)  # claim IDs


@dataclass
class DiscourseMap:
    """Maps the state of discourse on a question."""
    question: str
    positions: list = field(default_factory=list)  # Position objects
    consensus_claims: list = field(default_factory=list)  # claim IDs all positions agree on
    live_cruxes: list = field(default_factory=list)  # the actual points of disagreement
    empty_chairs: list = field(default_factory=list)  # perspectives not represented


@dataclass
class VerificationTrial:
    """Record of a single verification trial."""
    claim_id: str
    trial_number: int
    model: str
    prompt_variant: str
    result: bool  # verified or not
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    compliance_pressure_detected: bool = False
    defense_applied: Optional[str] = None  # M2, M3, or None


@dataclass
class KnowledgeBase:
    """The full output artifact — a navigable knowledge base."""
    case_name: str
    claims: dict = field(default_factory=dict)  # id -> Claim
    edges: list = field(default_factory=list)  # Edge objects
    discourse_maps: list = field(default_factory=list)  # DiscourseMap objects
    verification_trials: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def add_claim(self, claim: Claim):
        self.claims[claim.id] = claim

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def get_claim_graph(self) -> dict:
        """Return adjacency list representation."""
        graph = {cid: [] for cid in self.claims}
        for edge in self.edges:
            graph.setdefault(edge.source_claim_id, []).append(
                {"target": edge.target_claim_id, "type": edge.edge_type.value, "confidence": edge.confidence}
            )
        return graph

    def export_json(self) -> str:
        return json.dumps({
            "case": self.case_name,
            "claims": {cid: c.to_dict() for cid, c in self.claims.items()},
            "edges": [{"source": e.source_claim_id, "target": e.target_claim_id,
                       "type": e.edge_type.value, "evidence": e.evidence} for e in self.edges],
            "discourse_maps": [{"question": dm.question, "positions": len(dm.positions),
                                "live_cruxes": dm.live_cruxes} for dm in self.discourse_maps],
            "metadata": self.metadata,
        }, indent=2)
