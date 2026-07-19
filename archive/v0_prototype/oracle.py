"""4-Tier Epistemic Oracle — cascading verification for claims.

Adapted from: DAST/preseal/src/preseal/oracle.py
Original: state_diff → trajectory → response_text → regex
Epistemic: direct_evidence → logical_consistency → source_credibility → heuristic_flags

Design: Most reliable check first, short-circuit on first failure.
"""

from dataclasses import dataclass
from typing import Optional
from .models import Claim, KnowledgeBase, EdgeType


@dataclass
class OracleVerdict:
    """Result of oracle verification."""
    verified: bool
    tier_reached: int  # 1-4, which tier produced the verdict
    reason: str
    flags: list  # warning flags even if verified


def verify_claim(claim: Claim, kb: KnowledgeBase, source_content: Optional[str] = None) -> OracleVerdict:
    """Run 4-tier epistemic oracle on a claim.

    Short-circuits on first definitive failure (like Preseal oracle).
    Returns verdict with explanation of which tier decided.
    """
    flags = []

    # Tier 1: Direct Evidence Check
    # Does the source actually say what the claim asserts?
    tier1 = _check_direct_evidence(claim, source_content)
    if tier1 is not None:
        return OracleVerdict(verified=tier1, tier_reached=1,
                            reason="Direct evidence check" + (" passed" if tier1 else " failed: source doesn't support claim"),
                            flags=flags)

    # Tier 2: Logical Consistency
    # Does this claim contradict other verified claims in the knowledge base?
    tier2, consistency_flags = _check_logical_consistency(claim, kb)
    flags.extend(consistency_flags)
    if tier2 is False:
        return OracleVerdict(verified=False, tier_reached=2,
                            reason="Logical inconsistency: contradicts verified claims in knowledge base",
                            flags=flags)

    # Tier 3: Source Credibility
    # Is the source retracted, low-quality, or known-unreliable?
    tier3, source_flags = _check_source_credibility(claim)
    flags.extend(source_flags)
    if tier3 is False:
        return OracleVerdict(verified=False, tier_reached=3,
                            reason="Source credibility failure: " + "; ".join(source_flags),
                            flags=flags)

    # Tier 4: Heuristic Flags
    # Does the claim text contain overclaiming, hedge-stripping, or fabrication patterns?
    tier4, heuristic_flags = _check_heuristic_patterns(claim)
    flags.extend(heuristic_flags)

    # If we reach here without failure, claim passes (with any accumulated flags)
    return OracleVerdict(verified=True, tier_reached=4,
                        reason="Passed all 4 tiers" + (f" (with {len(flags)} flags)" if flags else ""),
                        flags=flags)


def _check_direct_evidence(claim: Claim, source_content: Optional[str]) -> Optional[bool]:
    """Tier 1: Does the source content support the claim?

    Returns None if we can't check (no source content available).
    Returns False if source content clearly doesn't support the claim.
    Returns True if source content clearly supports the claim.
    """
    if source_content is None:
        return None  # Can't verify without source — pass to next tier

    claim_lower = claim.text.lower()
    source_lower = source_content.lower()

    # Basic containment check (will be replaced by LLM-based verification in full pipeline)
    key_terms = [t for t in claim_lower.split() if len(t) > 5]
    if not key_terms:
        return None

    term_hits = sum(1 for t in key_terms if t in source_lower)
    coverage = term_hits / len(key_terms) if key_terms else 0

    if coverage < 0.2:
        return False  # Source doesn't even mention the key terms

    return None  # Ambiguous — pass to next tier


def _check_logical_consistency(claim: Claim, kb: KnowledgeBase) -> tuple:
    """Tier 2: Does this claim contradict verified claims?

    Returns (result, flags) where result is False if inconsistent, None if can't determine.
    """
    flags = []

    for edge in kb.edges:
        if edge.edge_type == EdgeType.CONTRADICTS:
            if edge.target_claim_id == claim.id:
                contradicting = kb.claims.get(edge.source_claim_id)
                if contradicting and contradicting.status.value == "verified":
                    flags.append(f"Contradicts verified claim: {contradicting.text[:80]}")
                    return (False, flags)

            if edge.source_claim_id == claim.id:
                contradicting = kb.claims.get(edge.target_claim_id)
                if contradicting and contradicting.status.value == "verified":
                    flags.append(f"Contradicts verified claim: {contradicting.text[:80]}")
                    return (False, flags)

    # Check for circular dependencies
    visited = set()
    queue = [claim.id]
    while queue:
        current = queue.pop(0)
        if current in visited:
            flags.append("Circular dependency detected in claim graph")
            break
        visited.add(current)
        for edge in kb.edges:
            if edge.source_claim_id == current and edge.edge_type == EdgeType.DEPENDS_ON:
                queue.append(edge.target_claim_id)

    return (None, flags)


def _check_source_credibility(claim: Claim) -> tuple:
    """Tier 3: Is the source credible?

    Returns (result, flags).
    """
    flags = []
    signals = claim.source.credibility_signals

    if signals.get("retracted"):
        flags.append("Source has been retracted")
        return (False, flags)

    if signals.get("known_unreliable"):
        flags.append("Source is on known-unreliable list")
        return (False, flags)

    if not signals.get("peer_reviewed") and claim.source.source_type == "paper":
        flags.append("Paper is not peer-reviewed")

    if signals.get("preprint_only"):
        flags.append("Preprint only — not yet peer-reviewed")

    return (None, flags)


def _check_heuristic_patterns(claim: Claim) -> tuple:
    """Tier 4: Heuristic red flags in claim text.

    Detects overclaiming, hedge-stripping, and fabrication patterns.
    Adapted from Preseal's response_text_check (refusal-aware logic).
    """
    flags = []
    text = claim.text.lower()

    # Overclaiming patterns
    overclaim_markers = ["proves conclusively", "definitively shows", "beyond any doubt",
                        "irrefutably", "no possible alternative", "the only explanation"]
    for marker in overclaim_markers:
        if marker in text:
            flags.append(f"Overclaiming pattern: '{marker}'")

    # Hedge-stripping (original had hedges that were removed)
    absolute_markers = ["always", "never", "all studies show", "no evidence exists"]
    for marker in absolute_markers:
        if marker in text and "not " + marker not in text:
            flags.append(f"Absolute claim without qualification: '{marker}'")

    # Fabrication patterns (from compliance trap research)
    # These indicate the model may have fabricated rather than admitting uncertainty
    if claim.metadata.get("compliance_pressure_detected"):
        flags.append("Generated under detected compliance pressure — verify independently")

    return (True, flags)  # Heuristics only flag, never reject outright
