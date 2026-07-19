"""Relationship detection — embed claims, find pairs, classify edges.

Pipeline:
1. Batch embed all claims (OpenAI text-embedding-3-small)
2. Persist embeddings as data/{case}/embeddings.npz
3. Cosine similarity filter (>threshold from DIFFERENT sources)
4. Batch LLM classification (edge type per pair)
5. Confirm contradictions with stronger model
6. Two-stage deduplication (>0.92 auto-merge, 0.80-0.92 LLM check)

Design sources:
- IMPLEMENTATION_PLAN.md §5.3
- DEG retrieval.py (hybrid search pattern)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from .config import get_config
from .store import EpistemicStore

log = structlog.get_logger()

CLASSIFY_PROMPT = """You are a claim relationship analyzer. Given two claims, determine their relationship.

IMPORTANT — Edge direction convention:
- The claim that PROVIDES evidence/reasoning goes first (source = Claim A)
- The claim that is SUPPORTED/AFFECTED goes second (target = Claim B)
- "A supports B" means A is evidence FOR B (A is more specific/foundational, B is a conclusion)

Relationship types:
- supports: Claim A provides evidence or reasoning that strengthens Claim B (A=evidence, B=conclusion)
- contradicts: Claim A and Claim B cannot both be true (genuine logical conflict)
- depends_on: Claim A's truth requires Claim B to be true (A needs B as a premise)
- qualifies: Claim A adds conditions, exceptions, or nuance to Claim B
- frames_differently: Claim A and Claim B address the same phenomenon through INCOMPATIBLE interpretive frames. They agree on facts but ask different questions or apply different methodological lenses.
- supersedes: Claim A explicitly updates or corrects Claim B with newer information
- none: No meaningful relationship

CRITICAL DISTINCTION — contradicts vs frames_differently:
- contradicts = "If A is true, B must be false" (factual dispute, resolvable by evidence)
- frames_differently = "A and B ask different questions about the same thing" (framework mismatch, resolvable only by agreeing which question matters)

For each pair, output JSON:
{{"type": "supports|contradicts|depends_on|qualifies|frames_differently|supersedes|none", "evidence": "Brief explanation of WHY this relationship holds", "strength": 0.0-1.0}}

PAIRS:
{pairs_text}

Output a JSON array with one object per pair, in order."""

CONFIRM_CONTRADICTION_PROMPT = """You are verifying a potential contradiction between two claims.

Claim A: {claim_a}
Claim B: {claim_b}
Initial assessment: These claims contradict each other because: {evidence}

Verify: Is this a GENUINE logical contradiction (both cannot be true), or is it actually:
- A framework mismatch (different questions about the same phenomenon)?
- A difference in scope or context (both could be true in different circumstances)?
- A difference in certainty/strength (one is stronger but doesn't negate the other)?

Output JSON:
{{"confirmed": true/false, "revised_type": "contradicts|frames_differently|qualifies|none", "reason": "explanation"}}"""

DEDUP_CHECK_PROMPT = """Are these two claims making the SAME factual assertion (just worded differently)?

Claim A: {claim_a}
Source A: {source_a}

Claim B: {claim_b}
Source B: {source_b}

Answer JSON: {{"same_claim": true/false, "reason": "brief explanation"}}"""


async def detect_relationships(
    store: EpistemicStore,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Run full relationship detection pipeline on store claims.

    Returns summary dict with edge counts, dedup stats.
    """
    from . import llm

    cfg = get_config()
    claims = store.claims
    if len(claims) < 2:
        log.info("relationships_skipped", reason="fewer than 2 claims")
        return {"edges_created": 0, "deduped": 0}

    claim_ids = list(claims.keys())
    claim_texts = [claims[cid].get("statement", {}).get("natural_language", "") for cid in claim_ids]

    # Step 1: Embed all claims
    log.info("embedding_claims", count=len(claim_texts))
    embeddings = await llm.embed(claim_texts, role="embedding")
    emb_matrix = np.array(embeddings)

    # Persist embeddings
    if data_dir and cfg.relationships.embedding_persist:
        emb_path = data_dir / "embeddings.npz"
        np.savez_compressed(emb_path, ids=claim_ids, vectors=emb_matrix)
        log.info("embeddings_persisted", path=str(emb_path), shape=emb_matrix.shape)

    # Step 2: Deduplication
    dedup_count = await _deduplicate(store, claim_ids, emb_matrix, cfg)

    # Step 3: Find candidate pairs (cosine > threshold, different sources)
    pairs = _find_candidate_pairs(store, claim_ids, emb_matrix, cfg)
    log.info("candidate_pairs", count=len(pairs))

    if not pairs:
        return {"edges_created": 0, "deduped": dedup_count}

    # Step 4: Batch classify
    edges_created = await _classify_pairs(store, pairs, cfg)

    # Step 5: Confirm contradictions
    confirmed = await _confirm_contradictions(store, cfg)

    summary = {
        "edges_created": edges_created,
        "deduped": dedup_count,
        "contradictions_confirmed": confirmed,
        "candidate_pairs": len(pairs),
    }
    log.info("relationships_complete", **summary)
    return summary


async def _deduplicate(
    store: EpistemicStore,
    claim_ids: list[str],
    emb_matrix: np.ndarray,
    cfg,
) -> int:
    """Two-stage deduplication: embedding similarity + LLM check for gray zone."""
    from . import llm

    merge_threshold = cfg.relationships.dedup_merge_threshold
    check_threshold = cfg.relationships.dedup_check_threshold
    dedup_count = 0

    # Compute pairwise cosine similarity
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = emb_matrix / norms
    sim_matrix = normed @ normed.T

    merged_ids = set()

    for i in range(len(claim_ids)):
        if claim_ids[i] in merged_ids:
            continue
        for j in range(i + 1, len(claim_ids)):
            if claim_ids[j] in merged_ids:
                continue

            sim = sim_matrix[i, j]

            if sim >= merge_threshold:
                # Auto-merge
                _merge_claims(store, claim_ids[i], claim_ids[j])
                merged_ids.add(claim_ids[j])
                dedup_count += 1

            elif sim >= check_threshold:
                # Gray zone — ask LLM
                claim_a = store.claims[claim_ids[i]]
                claim_b = store.claims[claim_ids[j]]
                prompt = DEDUP_CHECK_PROMPT.format(
                    claim_a=claim_a.get("statement", {}).get("natural_language", ""),
                    source_a=claim_a.get("source_title", ""),
                    claim_b=claim_b.get("statement", {}).get("natural_language", ""),
                    source_b=claim_b.get("source_title", ""),
                )
                response = await llm.call(prompt, role="relationship_batch")
                result = _parse_json_response(response)
                if result and result.get("same_claim"):
                    _merge_claims(store, claim_ids[i], claim_ids[j])
                    merged_ids.add(claim_ids[j])
                    dedup_count += 1

    if dedup_count:
        log.info("deduplication_complete", merged=dedup_count)
    return dedup_count


def _merge_claims(store: EpistemicStore, keep_id: str, merge_id: str):
    """Merge duplicate: mark merge_id as superseded, add reference to keep_id."""
    store.append(
        event_type="claim.superseded",
        payload={
            "old_claim_id": merge_id,
            "merged_into": keep_id,
            "reason": "duplicate_detected",
        },
        actor="pipeline:relationships",
        method="embedding_dedup",
    )


def _find_candidate_pairs(
    store: EpistemicStore,
    claim_ids: list[str],
    emb_matrix: np.ndarray,
    cfg,
) -> list[tuple[str, str, float, bool]]:
    """Find claim pairs above cosine threshold.

    Returns (cid_a, cid_b, similarity, cross_source).
    Both within-source and cross-source pairs are included:
    - Within-source edges capture argument structure (premise→conclusion chains)
    - Cross-source edges capture debate structure (agreements/disagreements between sources)
    The confidence model handles correlation differently for each.

    Cross-source pairs use a LOWER cosine threshold (0.4 vs 0.6) because opposing
    claims often use different vocabulary but address the same topic.
    """
    within_threshold = cfg.relationships.cosine_threshold
    cross_threshold = cfg.relationships.cross_source_cosine_threshold
    claims = store.claims

    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normed = emb_matrix / norms
    sim_matrix = normed @ normed.T

    pairs = []
    for i in range(len(claim_ids)):
        cid_i = claim_ids[i]
        if claims.get(cid_i, {}).get("status") == "superseded":
            continue
        for j in range(i + 1, len(claim_ids)):
            cid_j = claim_ids[j]
            if claims.get(cid_j, {}).get("status") == "superseded":
                continue

            source_i = claims[cid_i].get("source_url", "")
            source_j = claims[cid_j].get("source_url", "")
            cross_source = source_i != source_j

            # Use lower threshold for cross-source (opposing claims use different vocabulary)
            effective_threshold = cross_threshold if cross_source else within_threshold

            sim = sim_matrix[i, j]
            if sim < effective_threshold:
                continue

            pairs.append((cid_i, cid_j, float(sim), cross_source))

    # Sort: cross-source first (higher value for debate structure), then by similarity
    pairs.sort(key=lambda x: (-int(x[3]), -x[2]))
    max_pairs = min(len(pairs), len(claim_ids) * 5)  # Cap at 5× claim count
    return pairs[:max_pairs]


async def _classify_pairs(
    store: EpistemicStore,
    pairs: list[tuple[str, str, float, bool]],
    cfg,
) -> int:
    """Batch classify pairs into edge types."""
    from . import llm

    batch_size = cfg.relationships.batch_size
    edges_created = 0
    claims = store.claims

    for batch_start in range(0, len(pairs), batch_size):
        batch = pairs[batch_start:batch_start + batch_size]

        pairs_text = ""
        for idx, (cid_a, cid_b, sim, cross) in enumerate(batch):
            text_a = claims[cid_a].get("statement", {}).get("natural_language", "")
            text_b = claims[cid_b].get("statement", {}).get("natural_language", "")
            pairs_text += f"\nPair {idx + 1}:\n  A [{cid_a}]: {text_a}\n  B [{cid_b}]: {text_b}\n"

        prompt = CLASSIFY_PROMPT.format(pairs_text=pairs_text)
        response = await llm.call(prompt, role="relationship_batch")

        results = _parse_json_array(response)
        for idx, result in enumerate(results):
            if idx >= len(batch):
                break
            cid_a, cid_b, sim, cross_source = batch[idx]
            edge_type = result.get("type", "none")
            if edge_type == "none":
                continue

            edge_id = f"edg_{store.edge_count + edges_created + 1:04d}"
            store.append(
                event_type="edge.asserted",
                payload={
                    "edge_id": edge_id,
                    "edge_type": edge_type,
                    "source": cid_a,
                    "target": cid_b,
                    "strength": result.get("strength", 0.5),
                    "evidence": result.get("evidence", ""),
                    "cosine_similarity": sim,
                    "cross_source": cross_source,
                },
                actor="pipeline:relationships",
                method="llm_classification",
            )
            edges_created += 1

    return edges_created


async def _confirm_contradictions(store: EpistemicStore, cfg) -> int:
    """Confirm contradiction edges with a stronger model."""
    from . import llm

    confirmed = 0
    contradiction_edges = [
        (eid, e) for eid, e in store.edges.items()
        if e.get("edge_type") == "contradicts" and e.get("status") == "active"
    ]

    for edge_id, edge in contradiction_edges:
        claim_a = store.claims.get(edge["source"], {})
        claim_b = store.claims.get(edge["target"], {})

        text_a = claim_a.get("statement", {}).get("natural_language", "")
        text_b = claim_b.get("statement", {}).get("natural_language", "")

        prompt = CONFIRM_CONTRADICTION_PROMPT.format(
            claim_a=text_a,
            claim_b=text_b,
            evidence=edge.get("evidence", ""),
        )

        response = await llm.call(prompt, role="relationship_confirm")
        result = _parse_json_response(response)

        if not result:
            continue

        if result.get("confirmed"):
            confirmed += 1
        else:
            # Reclassify — might be frames_differently
            revised = result.get("revised_type", "none")
            if revised and revised != "contradicts":
                store.append(
                    event_type="edge.asserted",
                    payload={
                        "edge_id": edge_id,
                        "edge_type": revised,
                        "source": edge["source"],
                        "target": edge["target"],
                        "strength": edge.get("strength", 0.5),
                        "evidence": result.get("reason", ""),
                        "revised_from": "contradicts",
                    },
                    actor="pipeline:relationships",
                    method="llm_confirmation",
                    supersedes=edge.get("event_id"),
                )

    return confirmed


def _parse_json_response(text: str) -> dict | None:
    """Parse a single JSON object from LLM response."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, IndexError):
        pass
    return None


def _parse_json_array(text: str) -> list[dict]:
    """Parse a JSON array from LLM response."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            return result if isinstance(result, list) else []
    except (json.JSONDecodeError, IndexError):
        pass
    return []


def load_embeddings(data_dir: Path) -> tuple[list[str], np.ndarray] | None:
    """Load persisted embeddings (used by discourse.py)."""
    emb_path = data_dir / "embeddings.npz"
    if not emb_path.exists():
        return None
    data = np.load(emb_path, allow_pickle=True)
    return list(data["ids"]), data["vectors"]
