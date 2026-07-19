"""Discourse mapping — positions, cruxes, empty chairs.

Pipeline:
1. Load persisted embeddings (or compute fresh)
2. HDBSCAN clustering → candidate positions
3. Fallback: LLM-based position identification if clusters < 2 or > valid range
4. Label positions (stance, strongest case) via LLM
5. Identify live cruxes from crux_detection scores
6. Detect empty chairs (coverage gaps)
7. Classify disagreement type per position pair (factual vs framework)

Design sources:
- IMPLEMENTATION_PLAN.md §7
- PROJECT_CONTEXT.md §7 (discourse map is the hero)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import structlog

from .config import get_config
from .crux_detection import get_top_cruxes
from .store import EpistemicStore

log = structlog.get_logger()

POSITION_LABEL_PROMPT = """Given these claims that cluster together as a DISTINCT POSITION in a debate, identify what this position argues.

These claims were grouped because they form a coherent stance that OPPOSES or DIFFERS FROM other positions in the debate. What is this group's argument?

Claims:
{claims_text}

Output JSON:
{{
  "stance": "One-sentence description of this position's UNIQUE ARGUMENT (what distinguishes it from other positions?)",
  "core_commitment": "The single most fundamental claim this position rests on",
  "strongest_claims": ["claim_id of strongest supporting claim", "second strongest"],
  "summary": "2-3 sentence summary of what this position uniquely argues"
}}"""

EMPTY_CHAIRS_PROMPT = """Given the positions in this debate and the claims extracted, identify perspectives or evidence MISSING from the discourse.

Positions identified:
{positions_text}

Question being debated: {question}

What perspectives, evidence types, or stakeholder views are NOT represented?
Look for:
- Methodological approaches not applied
- Stakeholder groups not heard from
- Evidence types not considered
- Geographic/temporal gaps

Output JSON array:
[
  {{"perspective": "description of what's missing", "why_it_matters": "why this gap is significant"}}
]"""


async def build_discourse_map(
    store: EpistemicStore,
    data_dir: Path,
    questions: list[str] | None = None,
) -> dict[str, Any]:
    """Build a complete discourse map from store claims.

    Returns dict with positions, cruxes, empty_chairs, disagreement_types.
    """
    from . import llm
    from .relationships import load_embeddings

    cfg = get_config()
    claims = {cid: c for cid, c in store.claims.items() if c.get("status") == "active"}

    if len(claims) < 5:
        log.warning("discourse_skipped", reason="fewer than 5 active claims")
        return {"positions": [], "cruxes": [], "empty_chairs": []}

    # Step 1: Load or compute embeddings
    loaded = load_embeddings(data_dir)
    if loaded:
        emb_ids, emb_matrix = loaded
        # Filter to active claims only
        active_mask = [i for i, cid in enumerate(emb_ids) if cid in claims]
        claim_ids = [emb_ids[i] for i in active_mask]
        vectors = emb_matrix[active_mask]
    else:
        claim_ids = list(claims.keys())
        texts = [claims[cid].get("statement", {}).get("natural_language", "") for cid in claim_ids]
        embeddings = await llm.embed(texts, role="embedding")
        vectors = np.array(embeddings)

    # Step 2: Cluster into positions
    positions = _cluster_positions(claim_ids, vectors, claims, cfg)

    # Step 2b: Merge positions with >50% mutual support edges (same stance, different semantics)
    if positions and len(positions) > 1:
        positions = _merge_related_positions(positions, store)

    # Step 2c: Find opposing position via contradiction edges (graph-based community detection)
    # If HDBSCAN only found one side, the other side's claims are scattered in noise.
    # Claims that CONTRADICT the largest position form the opposing position.
    positions = _find_opposing_positions(positions, claim_ids, store)

    # Step 3: If clustering failed, use LLM fallback
    if not positions or len(positions) < 2:
        positions = await _llm_position_fallback(claims, questions, cfg)

    # Step 4: Label positions via LLM
    labeled_positions = await _label_positions(positions, claims)

    # Step 5: Identify cruxes (use discourse-derived target_ids)
    target_ids = [p["core_claim_id"] for p in labeled_positions if p.get("core_claim_id")]
    if not target_ids:
        target_ids = [p["member_claims"][0] for p in labeled_positions if p.get("member_claims")]

    cruxes = get_top_cruxes(store, target_ids=target_ids, n=10) if target_ids else []

    # Step 6: Classify disagreement types between position pairs
    disagreement_types = _classify_disagreements(labeled_positions, store)

    # Store positions as events
    for pos in labeled_positions:
        store.append(
            event_type="position.stated",
            payload={
                "position_id": pos["position_id"],
                "label": pos.get("stance", ""),
                "summary": pos.get("summary", ""),
                "core_commitment": pos.get("core_commitment", ""),
                "member_claims": pos.get("member_claims", []),
                "strongest_claims": pos.get("strongest_claims", []),
            },
            actor="pipeline:discourse",
            method="hdbscan_clustering",
        )

    # Step 7: Empty chairs (perspectives missing from the discourse)
    empty_chairs = await _detect_empty_chairs(labeled_positions, cruxes, questions, cfg)

    result = {
        "positions": labeled_positions,
        "cruxes": cruxes,
        "empty_chairs": empty_chairs,
        "disagreement_types": disagreement_types,
        "questions": questions or [],
    }

    log.info("discourse_complete", positions=len(labeled_positions),
             cruxes=len(cruxes), target_ids=len(target_ids))
    return result


def _cluster_positions(
    claim_ids: list[str],
    vectors: np.ndarray,
    claims: dict,
    cfg,
) -> list[dict]:
    """HDBSCAN clustering on claim embeddings."""
    import hdbscan

    valid_range = cfg.discourse.valid_cluster_range
    min_sizes = cfg.discourse.min_cluster_size_values

    best_labels = None
    best_n_clusters = 0

    for min_size in min_sizes:
        clusterer = hdbscan.HDBSCAN(min_cluster_size=min_size, metric="euclidean")
        labels = clusterer.fit_predict(vectors)
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        if valid_range[0] <= n_clusters <= valid_range[1]:
            best_labels = labels
            best_n_clusters = n_clusters
            log.info("hdbscan_success", min_cluster_size=min_size, n_clusters=n_clusters)
            break

        if n_clusters > best_n_clusters and n_clusters <= valid_range[1]:
            best_labels = labels
            best_n_clusters = n_clusters

    if best_labels is None or best_n_clusters < valid_range[0]:
        log.warning("hdbscan_failed", best_clusters=best_n_clusters)
        return []

    # Group claims by cluster
    positions = []
    for cluster_id in range(best_n_clusters):
        member_indices = [i for i, l in enumerate(best_labels) if l == cluster_id]
        member_claim_ids = [claim_ids[i] for i in member_indices]

        positions.append({
            "position_id": f"pos_{cluster_id:02d}",
            "member_claims": member_claim_ids,
            "cluster_size": len(member_claim_ids),
        })

    return positions


def _find_opposing_positions(
    positions: list[dict],
    all_claim_ids: list[str],
    store: EpistemicStore,
) -> list[dict]:
    """Find opposing positions via contradiction edges (graph-based community detection).

    If HDBSCAN found positions but missed an opposing side (scattered in noise),
    identify claims that CONTRADICT the largest position's claims — they form the opposition.
    """
    if not positions:
        return positions

    # Find the largest position
    largest = max(positions, key=lambda p: len(p.get("member_claims", [])))
    largest_members = set(largest.get("member_claims", []))

    # Find claims that oppose the largest position (contradicts OR frames_differently OR qualifies)
    # These edge types all indicate the claim is on the OTHER SIDE of a disagreement
    opposing_edge_types = ("contradicts", "frames_differently", "qualifies")
    opposing_claims = set()
    for edge in store.edges.values():
        if edge.get("status") != "active":
            continue
        if edge.get("edge_type") not in opposing_edge_types:
            continue
        src, tgt = edge.get("source"), edge.get("target")
        if src in largest_members and tgt not in largest_members:
            opposing_claims.add(tgt)
        elif tgt in largest_members and src not in largest_members:
            opposing_claims.add(src)

    # Also add claims that SUPPORT the opposing claims (build out the position)
    expanded_opposing = set(opposing_claims)
    for edge in store.edges.values():
        if edge.get("status") != "active" or edge.get("edge_type") != "supports":
            continue
        if edge.get("target") in opposing_claims:
            expanded_opposing.add(edge["source"])
        if edge.get("source") in opposing_claims:
            expanded_opposing.add(edge["target"])

    # Remove claims already assigned to existing positions
    all_assigned = set()
    for p in positions:
        all_assigned.update(p.get("member_claims", []))
    opposing_final = expanded_opposing - all_assigned

    if len(opposing_final) >= 3:  # Minimum viable position
        new_pos = {
            "position_id": f"pos_{len(positions):02d}",
            "member_claims": list(opposing_final),
            "cluster_size": len(opposing_final),
        }
        positions.append(new_pos)
        log.info("opposing_position_found", claims=len(opposing_final),
                 method="contradiction_graph")

    return positions


def _merge_related_positions(positions: list[dict], store: EpistemicStore) -> list[dict]:
    """Merge positions that are the same stance expressed differently.

    If >50% of edges between two positions are `supports`, they're the same
    position (e.g., "zoonotic evidence" + "zoonotic conclusion" = one stance).
    """
    if len(positions) <= 2:
        return positions

    merged = list(positions)
    changed = True

    while changed and len(merged) > 1:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                members_i = set(merged[i].get("member_claims", []))
                members_j = set(merged[j].get("member_claims", []))

                # Count edges between positions
                support_count = 0
                total_edges = 0
                for edge in store.edges.values():
                    if edge.get("status") != "active":
                        continue
                    src, tgt = edge.get("source"), edge.get("target")
                    if (src in members_i and tgt in members_j) or (src in members_j and tgt in members_i):
                        total_edges += 1
                        if edge.get("edge_type") == "supports":
                            support_count += 1

                # Merge if >50% of inter-position edges are supports
                if total_edges >= 2 and support_count / total_edges > 0.5:
                    merged[i] = {
                        "position_id": merged[i]["position_id"],
                        "member_claims": list(members_i | members_j),
                        "cluster_size": len(members_i | members_j),
                    }
                    merged.pop(j)
                    changed = True
                    log.info("positions_merged", kept=merged[i]["position_id"],
                             merged_into=merged[i]["position_id"],
                             new_size=len(members_i | members_j))
                    break
            if changed:
                break

    return merged


async def _llm_position_fallback(
    claims: dict,
    questions: list[str] | None,
    cfg,
) -> list[dict]:
    """LLM-based position identification when HDBSCAN fails."""
    from . import llm

    claims_text = "\n".join(
        f"[{cid}] {c.get('statement', {}).get('natural_language', '')}"
        for cid, c in list(claims.items())[:50]
    )

    question = questions[0] if questions else "What are the main positions in this debate?"

    prompt = f"""Identify the 2-5 distinct POSITIONS in this debate about: {question}

Claims:
{claims_text}

For each position, list which claim_ids belong to it.

Output JSON:
[{{"stance": "description", "member_claims": ["clm_xxxx", ...]}}]"""

    response = await llm.call(prompt, role="discourse_crux")
    results = _parse_json_array(response)

    positions = []
    for i, r in enumerate(results):
        positions.append({
            "position_id": f"pos_{i:02d}",
            "member_claims": r.get("member_claims", []),
            "stance": r.get("stance", ""),
            "cluster_size": len(r.get("member_claims", [])),
        })

    log.info("llm_fallback_positions", count=len(positions))
    return positions


async def _label_positions(positions: list[dict], claims: dict) -> list[dict]:
    """Label each position with stance, core commitment, strongest claims."""
    from . import llm

    labeled = []
    for pos in positions:
        member_claims = pos.get("member_claims", [])
        if not member_claims:
            continue

        claims_text = "\n".join(
            f"[{cid}] {claims.get(cid, {}).get('statement', {}).get('natural_language', '')}"
            for cid in member_claims[:20]
        )

        prompt = POSITION_LABEL_PROMPT.format(claims_text=claims_text)
        response = await llm.call(prompt, role="discourse_label")
        result = _parse_json_response(response)

        if result:
            # Find the core claim ID (closest to core_commitment text)
            core_claim_id = member_claims[0] if member_claims else None

            labeled.append({
                **pos,
                "stance": result.get("stance", pos.get("stance", "")),
                "core_commitment": result.get("core_commitment", ""),
                "core_claim_id": core_claim_id,
                "strongest_claims": result.get("strongest_claims", member_claims[:3]),
                "summary": result.get("summary", ""),
            })
        else:
            labeled.append(pos)

    return labeled


def _classify_disagreements(positions: list[dict], store: EpistemicStore) -> list[dict]:
    """Classify disagreement type between each position pair.

    Count contradicts vs frames_differently edges between positions.
    """
    disagreements = []

    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            pos_a = positions[i]
            pos_b = positions[j]
            members_a = set(pos_a.get("member_claims", []))
            members_b = set(pos_b.get("member_claims", []))

            contradicts_count = 0
            frames_count = 0

            for edge in store.edges.values():
                if edge.get("status") != "active":
                    continue
                src, tgt = edge.get("source"), edge.get("target")
                if (src in members_a and tgt in members_b) or (src in members_b and tgt in members_a):
                    if edge.get("edge_type") == "contradicts":
                        contradicts_count += 1
                    elif edge.get("edge_type") == "frames_differently":
                        frames_count += 1

            total = contradicts_count + frames_count
            if total == 0:
                dtype = "unknown"
            elif frames_count > contradicts_count:
                dtype = "framework_mismatch"
            else:
                dtype = "factual_dispute"

            disagreements.append({
                "position_a": pos_a["position_id"],
                "position_b": pos_b["position_id"],
                "type": dtype,
                "contradicts": contradicts_count,
                "frames_differently": frames_count,
            })

    return disagreements


async def _detect_empty_chairs(
    positions: list[dict],
    cruxes: list[dict],
    questions: list[str] | None,
    cfg,
) -> list[dict]:
    """Detect perspectives/evidence missing from the discourse."""
    from . import llm

    positions_text = "\n".join(
        f"- {p.get('stance', p.get('position_id', '?'))}: {p.get('summary', '')[:100]}"
        for p in positions
    )

    cruxes_text = "\n".join(
        f"- {c.get('text', '')[:100]}" for c in cruxes[:5]
    )

    question = questions[0] if questions else "the main question under debate"

    prompt = EMPTY_CHAIRS_PROMPT.format(
        positions_text=positions_text,
        question=question,
    )

    # Add cruxes context
    prompt += f"\n\nKey cruxes identified:\n{cruxes_text}"

    response = await llm.call(prompt, role="discourse_empty")
    results = _parse_json_array(response)

    empty_chairs = []
    for r in results[:5]:  # Cap at 5
        if r.get("perspective"):
            empty_chairs.append({
                "perspective": r["perspective"],
                "why_it_matters": r.get("why_it_matters", ""),
            })

    log.info("empty_chairs_detected", count=len(empty_chairs))
    return empty_chairs


def _parse_json_response(text: str) -> dict | None:
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
