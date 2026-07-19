"""Performed settling detection — detects when a debate declared a winner without resolving cruxes.

Two types:
- Type 1: Verdict exists but dependency cruxes remain contested (unresolved factual disputes)
- Type 2: Verdict adjudicates a framework choice rather than resolving a fact
         (detected via frames_differently edges in the verdict's dependency chain)

Design sources:
- IMPLEMENTATION_PLAN.md §6.3
- PROJECT_CONTEXT.md §7 (performed settling = unique contribution)
"""

from __future__ import annotations

from collections import deque
from typing import Any

import structlog

from .store import EpistemicStore

log = structlog.get_logger()


def detect_performed_settling(
    store: EpistemicStore,
    verdict_claim_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Detect performed settling for all verdict claims.

    Args:
        store: EpistemicStore with claims and edges
        verdict_claim_ids: Explicit verdict claim IDs. If None, auto-detects
                          claims marked with contains_verdict metadata.

    Returns list of settling detection results (one per verdict).
    """
    if verdict_claim_ids is None:
        verdict_claim_ids = _find_verdict_claims(store)

    # Edge direction heuristic: if verdicts have OUTGOING supports but no INCOMING,
    # the relationship classifier got direction wrong. Use outgoing targets as dependencies.
    _fix_verdict_edge_direction(store, verdict_claim_ids)

    if not verdict_claim_ids:
        return [{"detected": False, "reason": "No verdict claims found"}]

    results = []
    for verdict_id in verdict_claim_ids:
        result = _check_settling(store, verdict_id)
        results.append(result)

        if result["detected"]:
            store.append(
                event_type="meta.flag",
                payload={
                    "flag_type": "performed_settling",
                    "verdict_claim_id": verdict_id,
                    "settling_type": result["settling_type"],
                    "contested_cruxes": result.get("contested_cruxes", []),
                    "severity": result["severity"],
                    "explanation": result["explanation"],
                },
                actor="pipeline:settling",
                method="graph_traversal",
            )

    detected_count = sum(1 for r in results if r["detected"])
    log.info("settling_detection_complete", verdicts_checked=len(verdict_claim_ids),
             settling_detected=detected_count)
    return results


def _find_verdict_claims(store: EpistemicStore) -> list[str]:
    """Auto-detect verdict claims from metadata or content patterns."""
    verdict_ids = []

    for claim_id, claim in store.claims.items():
        if claim.get("status") != "active":
            continue

        text = claim.get("statement", {}).get("natural_language", "").lower()

        # Check for verdict-indicating language (broadened from Day 7 real claims)
        verdict_markers = [
            "judges ruled", "judge ruled", "judges decided", "judge decided",
            "found in favor", "ruled in favor", "verdict",
            "concluded that", "judges found", "judge finds",
            "decided in favor", "found for",
            "more probable", "more likely",
            "ruled for", "judged in favor",
        ]
        if any(marker in text for marker in verdict_markers):
            verdict_ids.append(claim_id)

    return verdict_ids


def _check_settling(store: EpistemicStore, verdict_claim_id: str) -> dict[str, Any]:
    """Check if a specific verdict exhibits performed settling."""
    verdict = store.claims.get(verdict_claim_id)
    if not verdict:
        return {"detected": False, "reason": "Verdict claim not found", "verdict_id": verdict_claim_id}

    # BFS upstream: what does this verdict depend on?
    dependencies = _get_dependencies(store, verdict_claim_id)

    # Find crux claims in the dependency chain
    crux_edges = [
        e for e in store.edges.values()
        if e.get("edge_type") == "is_crux_for" and e.get("status") == "active"
    ]
    relevant_cruxes = [
        e["source"] for e in crux_edges
        if e["source"] in dependencies or e["target"] in dependencies
    ]

    # Also check: any claims in dependency chain that have high uncertainty (conf 0.3-0.7)
    contested_deps = [
        dep_id for dep_id in dependencies
        if 0.3 <= store.claims.get(dep_id, {}).get("confidence", 0.5) <= 0.7
    ]

    # Which cruxes remain unresolved?
    contested_cruxes = [
        c for c in relevant_cruxes
        if store.claims.get(c, {}).get("confidence", 0.5) < 0.85
    ]

    # Type 2: Check if verdict crosses a framework boundary
    framework_adjudication = False
    frame_edges_found = []
    for dep_id in dependencies:
        for edge in store.edges.values():
            if edge.get("status") != "active":
                continue
            if edge.get("edge_type") != "frames_differently":
                continue
            if edge.get("source") == dep_id or edge.get("target") == dep_id:
                framework_adjudication = True
                frame_edges_found.append(edge.get("edge_id", ""))

    # Determine if settling detected
    if not contested_cruxes and not contested_deps and not framework_adjudication:
        return {
            "detected": False,
            "verdict_id": verdict_claim_id,
            "reason": "Cruxes resolved, dependencies high-confidence, no framework issues",
        }

    settling_type = []
    if contested_cruxes or contested_deps:
        settling_type.append("unresolved_cruxes")
    if framework_adjudication:
        settling_type.append("framework_adjudication")

    # Severity = proportion of contested dependencies
    total_deps = len(dependencies) if dependencies else 1
    contested_count = len(set(contested_cruxes + contested_deps))
    severity = min(1.0, contested_count / total_deps)
    if framework_adjudication:
        severity = max(severity, 0.5)

    explanation_parts = []
    if contested_cruxes:
        explanation_parts.append(f"Verdict rests on {len(contested_cruxes)} unresolved cruxes")
    if contested_deps:
        explanation_parts.append(f"{len(contested_deps)} contested dependencies (confidence 0.3-0.7)")
    if framework_adjudication:
        explanation_parts.append("Adjudicates between incompatible frameworks")

    return {
        "detected": True,
        "verdict_id": verdict_claim_id,
        "settling_type": settling_type,
        "contested_cruxes": contested_cruxes,
        "contested_dependencies": contested_deps[:10],
        "framework_adjudication": framework_adjudication,
        "framework_edges": frame_edges_found,
        "severity": round(severity, 3),
        "explanation": "; ".join(explanation_parts),
        "dependency_count": len(dependencies),
    }


def _fix_verdict_edge_direction(store: EpistemicStore, verdict_ids: list[str]):
    """Heuristic: if verdict has outgoing `supports` but no incoming, flip those edges.

    The LLM sometimes classifies "verdict supports evidence" instead of "evidence supports verdict."
    This flips them in-memory (doesn't modify events.jsonl) so BFS traversal works correctly.
    """
    for vid in verdict_ids:
        incoming = [e for e in store.edges.values()
                    if e.get("target") == vid and e.get("edge_type") == "supports" and e.get("status") == "active"]
        outgoing = [e for e in store.edges.values()
                    if e.get("source") == vid and e.get("edge_type") == "supports" and e.get("status") == "active"]

        if not incoming and outgoing:
            # Flip: verdict→X becomes X→verdict
            for edge in outgoing:
                edge["source"], edge["target"] = edge["target"], edge["source"]
            log.info("verdict_edges_flipped", verdict=vid, flipped=len(outgoing))


def _get_dependencies(store: EpistemicStore, claim_id: str) -> set[str]:
    """BFS upstream: find all claims this verdict depends on."""
    dependencies = set()
    queue = deque([claim_id])
    visited = {claim_id}

    while queue:
        current = queue.popleft()
        for edge in store.edges.values():
            if edge.get("status") != "active":
                continue
            if edge.get("target") != current:
                continue
            if edge.get("edge_type") not in ("supports", "depends_on"):
                continue

            source = edge["source"]
            if source not in visited:
                visited.add(source)
                dependencies.add(source)
                queue.append(source)

    return dependencies
