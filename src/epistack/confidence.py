"""Dual confidence model: independent corroboration × quality dimensions.

Evidence combination:
- Cluster correlated evidence (provenance-path overlap)
- Within-cluster: effective sample size + noisy-OR
- Across clusters: noisy-OR (independent lines strengthen)

Quality dimensions:
- Weakest-link product (any zero kills total)
- Source quality, logical consistency, quote verification

Final = evidence_score × dimension_score

Design sources:
- IMPLEMENTATION_PLAN.md §6.2
- DEG trust.py (confidence-gated supersession, FPF arXiv:2601.21116)
- Bayesian networks (noisy-OR standard)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import structlog

from .config import get_config
from .store import EpistemicStore

log = structlog.get_logger()


@dataclass
class ConfidenceResult:
    """Result of confidence computation for a single claim."""
    claim_id: str
    final_confidence: float
    level: str  # very_high, high, medium, low, very_low
    evidence_score: float
    dimension_score: float
    cluster_count: int
    weakest_dimension: str | None
    bottleneck: str  # "evidence" or "quality"


def compute_all_confidences(store: EpistemicStore) -> list[ConfidenceResult]:
    """Compute confidence for all active claims in the store.

    Updates claim confidence in-place via rank_changed events.
    """
    cfg = get_config()
    results = []

    for claim_id, claim in store.claims.items():
        if claim.get("status") != "active":
            continue

        result = compute_claim_confidence(claim_id, store, cfg)
        results.append(result)

        # Update store if confidence changed significantly
        old_conf = claim.get("confidence", 0.5)
        if abs(result.final_confidence - old_conf) > 0.05:
            store.append(
                event_type="claim.rank_changed",
                payload={
                    "claim_id": claim_id,
                    "confidence": result.final_confidence,
                    "confidence_level": result.level,
                    "evidence_score": result.evidence_score,
                    "dimension_score": result.dimension_score,
                    "cluster_count": result.cluster_count,
                    "weakest_dimension": result.weakest_dimension,
                },
                actor="pipeline:confidence",
                method="dual_model",
            )

    log.info("confidence_computed", claims=len(results),
             avg_confidence=round(sum(r.final_confidence for r in results) / max(1, len(results)), 3))
    return results


def compute_claim_confidence(
    claim_id: str,
    store: EpistemicStore,
    cfg=None,
) -> ConfidenceResult:
    """Compute confidence for a single claim using dual model."""
    cfg = cfg or get_config()
    claim = store.claims[claim_id]
    category = claim.get("category", "empirical")

    # Gather supporting evidence lines
    evidence_lines = _gather_evidence(claim_id, store, cfg)

    # Compute evidence score (noisy-OR across independent clusters)
    evidence_score = _compute_evidence_score(evidence_lines, cfg)

    # Compute quality dimensions (weakest-link product)
    dimensions = _compute_quality_dimensions(claim_id, claim, store)
    dimension_score = math.prod(d["score"] for d in dimensions) if dimensions else 1.0

    # Final composite
    final = evidence_score * dimension_score

    # Classify level
    if final >= 0.90:
        level = "very_high"
    elif final >= 0.75:
        level = "high"
    elif final >= 0.50:
        level = "medium"
    elif final >= 0.25:
        level = "low"
    else:
        level = "very_low"

    weakest = min(dimensions, key=lambda d: d["score"])["name"] if dimensions else None

    return ConfidenceResult(
        claim_id=claim_id,
        final_confidence=round(final, 3),
        level=level,
        evidence_score=round(evidence_score, 3),
        dimension_score=round(dimension_score, 3),
        cluster_count=len(_cluster_correlated(evidence_lines, cfg)) if evidence_lines else 0,
        weakest_dimension=weakest,
        bottleneck="evidence" if evidence_score < dimension_score else "quality",
    )


def _gather_evidence(claim_id: str, store: EpistemicStore, cfg) -> list[dict]:
    """Gather all evidence lines supporting a claim from graph edges.

    Within-source supports = logical argument structure (don't add independent corroboration
    but DO contribute to cascade paths for crux detection).
    Cross-source supports = potentially independent corroboration.
    """
    evidence = []
    assessment_weight = cfg.confidence.assessment_evidence_weight

    for edge in store.edges.values():
        if edge.get("status") != "active":
            continue
        if edge.get("target") != claim_id:
            continue
        if edge.get("edge_type") != "supports":
            continue

        source_claim = store.claims.get(edge["source"])
        if not source_claim or source_claim.get("status") != "active":
            continue

        strength = edge.get("strength", 0.5)

        # Assessment claims as evidence get reduced weight
        if source_claim.get("category") == "assessment":
            strength *= assessment_weight

        # Within-source supports are logical structure, not independent corroboration
        # They share provenance → will be clustered together by correlation detection
        source_url = source_claim.get("source_url", "")
        target_claim = store.claims.get(claim_id, {})
        target_url = target_claim.get("source_url", "")

        evidence.append({
            "claim_id": edge["source"],
            "strength": strength,
            "source_url": source_url,
            "source_title": source_claim.get("source_title", ""),
            "provenance_path": [source_url],
            "cross_source": edge.get("cross_source", source_url != target_url),
        })

    return evidence


def _compute_evidence_score(evidence_lines: list[dict], cfg) -> float:
    """Noisy-OR across independent evidence clusters."""
    if not evidence_lines:
        return 0.5  # No evidence = prior

    clusters = _cluster_correlated(evidence_lines, cfg)

    cluster_strengths = []
    for cluster in clusters:
        n = len(cluster)
        if n == 1:
            cluster_strengths.append(cluster[0]["strength"])
            continue

        # Within-cluster: effective sample size accounting for correlation
        total_corr = sum(
            _detect_correlation(cluster[i], cluster[j])
            for i in range(n) for j in range(i + 1, n)
        ) / max(1, n * (n - 1) // 2)

        effective_n = n / (1 + (n - 1) * total_corr)
        avg_strength = sum(e["strength"] for e in cluster) / n
        cluster_strengths.append(1.0 - (1.0 - avg_strength) ** effective_n)

    # Across clusters: noisy-OR (independent lines combine)
    if not cluster_strengths:
        return 0.5
    return 1.0 - math.prod(1.0 - s for s in cluster_strengths)


def _detect_correlation(ev_a: dict, ev_b: dict) -> float:
    """Provenance-path overlap → correlation (0=independent, 1=redundant)."""
    path_a = set(ev_a.get("provenance_path", []))
    path_b = set(ev_b.get("provenance_path", []))

    if not path_a or not path_b:
        return 0.0
    if not (path_a & path_b):
        return 0.0

    overlap = len(path_a & path_b)
    total = max(len(path_a), len(path_b))
    return overlap / total if total > 0 else 0.0


def _cluster_correlated(evidence: list[dict], cfg) -> list[list[dict]]:
    """Single-linkage clustering of correlated evidence. Conservative: over-clusters."""
    if not evidence:
        return []

    threshold = cfg.confidence.correlation_threshold
    n = len(evidence)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            if _detect_correlation(evidence[i], evidence[j]) > threshold:
                union(i, j)

    clusters: dict[int, list[dict]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(evidence[i])
    return list(clusters.values())


def _compute_quality_dimensions(
    claim_id: str,
    claim: dict,
    store: EpistemicStore,
) -> list[dict[str, Any]]:
    """Compute quality dimensions (any zero kills total)."""
    dimensions = []

    # Source quality
    from .scoring import score_source_quality
    source_signals = {}  # Would come from source registry
    source_score = score_source_quality(source_signals)
    dimensions.append({"name": "source_quality", "score": max(0.3, source_score)})

    # Quote verification (Layer 1 already passed if claim exists)
    quote_verified = claim.get("quote_verified", False)
    dimensions.append({"name": "quote_verified", "score": 1.0 if quote_verified else 0.3})

    # Logical consistency (no contradictions from verified claims)
    contradicted = False
    for edge in store.edges.values():
        if edge.get("edge_type") != "contradicts" or edge.get("status") != "active":
            continue
        if edge.get("target") == claim_id or edge.get("source") == claim_id:
            other_id = edge["source"] if edge["target"] == claim_id else edge["target"]
            other = store.claims.get(other_id, {})
            if other.get("confidence", 0) > 0.7:
                contradicted = True
                break
    dimensions.append({"name": "logical_consistency", "score": 0.3 if contradicted else 0.9})

    # Overclaiming penalty
    flags = claim.get("overclaiming_flags", [])
    overclaim_score = max(0.5, 1.0 - 0.15 * len(flags))
    dimensions.append({"name": "precision", "score": overclaim_score})

    return dimensions
