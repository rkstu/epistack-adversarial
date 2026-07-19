"""Crux detection — binary entropy × weighted cascade influence.

crux_score(v) = H(confidence(v)) × weighted_cascade_influence(v)

A crux is a claim that is:
1. Uncertain (high binary entropy — confidence near 0.5)
2. Influential (many downstream claims depend on it reaching a target)

Design sources:
- IMPLEMENTATION_PLAN.md §6.1
- Chan & Darwiche 2004 (sensitivity analysis in Bayesian networks)
- Howard 1966 (value of information theory)
- DEG temporal.py:cascade_impact() (BFS pattern)
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Any

import structlog

from .config import get_config
from .store import EpistemicStore

log = structlog.get_logger()

# Edge types that form vertical (causal/dependency) cascade relationships
CASCADE_EDGE_TYPES = ("supports", "depends_on", "is_crux_for")
# EXCLUDED: "frames_differently" (lateral, incommensurability — not vertical dependency)
# EXCLUDED: "contradicts" (opposes, not supports)


def binary_entropy(p: float) -> float:
    """H(p) — peaks at 0.5 (max uncertainty), zero at 0 and 1."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def compute_crux_scores(
    store: EpistemicStore,
    target_ids: list[str],
    decay: float | None = None,
    max_depth: int | None = None,
) -> dict[str, float]:
    """Compute crux scores for all active claims.

    crux_score(v) = H(confidence(v)) × weighted_cascade_influence(v)

    Args:
        store: EpistemicStore with claims and edges
        target_ids: Claim IDs of conclusion nodes (e.g., position core_commitments).
                    Day 7: hardcoded. Day 9+: from discourse mapping.
        decay: Exponential decay per hop (default from config)
        max_depth: BFS max traversal depth (default from config)

    Returns:
        Dict of claim_id → crux_score, sorted descending.
    """
    cfg = get_config()
    decay = decay if decay is not None else cfg.crux.decay
    max_depth = max_depth if max_depth is not None else cfg.crux.max_depth

    claims = store.claims
    edges = store.edges

    # Build adjacency from cascade-forming edges only
    adjacency: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)

    for edge in edges.values():
        if edge.get("status") != "active":
            continue
        if edge.get("edge_type") not in CASCADE_EDGE_TYPES:
            continue
        source = edge["source"]
        target = edge["target"]
        adjacency[source].append(target)
        in_degree[target] += 1

    # Reverse BFS: which nodes can reach any target?
    reverse_adj: dict[str, list[str]] = defaultdict(list)
    for src, targets in adjacency.items():
        for tgt in targets:
            reverse_adj[tgt].append(src)

    target_reachable = set(target_ids)
    queue = deque(target_ids)
    while queue:
        node = queue.popleft()
        for parent in reverse_adj.get(node, []):
            if parent not in target_reachable:
                target_reachable.add(parent)
                queue.append(parent)

    # Score each active claim
    # Exclude targets (conclusions) and assessment claims — cruxes should be
    # resolvable evidence disputes, not conclusions or editorial judgments.
    target_set = set(target_ids)
    scores: dict[str, float] = {}
    for claim_id, claim in claims.items():
        if claim.get("status") != "active":
            continue

        # Targets are what cruxes RESOLVE, not cruxes themselves
        if claim_id in target_set:
            scores[claim_id] = 0.0
            continue

        # Assessment claims are opinions about evidence quality, not empirical cruxes
        if claim.get("category") == "assessment":
            scores[claim_id] = 0.0
            continue

        confidence = claim.get("confidence", 0.5)
        uncertainty = binary_entropy(confidence)

        if uncertainty < 0.001:
            scores[claim_id] = 0.0
            continue

        # BFS cascade with corrections
        cascade = 0.0
        bfs_queue: deque[tuple[str, int]] = deque([(claim_id, 0)])
        visited = {claim_id}

        while bfs_queue:
            current, depth = bfs_queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in adjacency.get(current, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)

                depth_factor = decay ** (depth + 1)
                redundancy_factor = 1.0 / max(1, in_degree.get(neighbor, 1))
                target_factor = 1.0 if neighbor in target_reachable else 0.0

                cascade += depth_factor * redundancy_factor * target_factor
                bfs_queue.append((neighbor, depth + 1))

        scores[claim_id] = uncertainty * (cascade / max(1, len(target_ids)))

    # Sort descending
    sorted_scores = dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))

    # Log top cruxes
    top_5 = list(sorted_scores.items())[:5]
    if top_5:
        log.info("crux_detection_complete",
                 total_scored=len(sorted_scores),
                 top_crux=top_5[0][0],
                 top_score=round(top_5[0][1], 4))

    return sorted_scores


def get_top_cruxes(
    store: EpistemicStore,
    target_ids: list[str],
    n: int = 10,
) -> list[dict[str, Any]]:
    """Get top N cruxes with full context.

    Returns list of dicts with claim details + crux score.
    """
    scores = compute_crux_scores(store, target_ids)

    results = []
    for claim_id, score in list(scores.items())[:n]:
        if score <= 0:
            break
        claim = store.claims.get(claim_id, {})
        results.append({
            "claim_id": claim_id,
            "crux_score": round(score, 4),
            "text": claim.get("statement", {}).get("natural_language", ""),
            "confidence": claim.get("confidence", 0.5),
            "entropy": round(binary_entropy(claim.get("confidence", 0.5)), 4),
            "category": claim.get("category", "empirical"),
            "source_title": claim.get("source_title", ""),
        })

    return results
