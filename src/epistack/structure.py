"""Layer 2: Structure — Claim Dependency DAG with discourse mapping.

Builds a directed graph of claims with typed edges (supports, contradicts,
qualifies, supersedes, depends_on) and produces discourse maps showing
positions, strongest cases, and biggest holes per question.

Adapted from: DEG (Decision Evidence Graph) architecture in DAST/Preseal.
"""

import json
from typing import Optional

from .models import Claim, Edge, EdgeType, KnowledgeBase, Position, DiscourseMap


STRUCTURE_PROMPT = """You are a claim relationship analyzer. Given a set of claims, identify relationships between them.

For each pair of related claims, output:
{
  "source_id": "claim that makes the assertion",
  "target_id": "claim being referenced",
  "type": "supports|contradicts|qualifies|supersedes|depends_on",
  "evidence": "Brief explanation of WHY this relationship holds"
}

Relationship definitions:
- supports: source provides evidence or reasoning that strengthens target
- contradicts: source presents evidence/logic that undermines target
- qualifies: source adds a condition, exception, or nuance to target
- supersedes: source replaces target with updated/corrected information
- depends_on: source's truth requires target to be true

Rules:
- Only identify relationships where the connection is clear and defensible
- Contradictions must be genuine logical conflicts, not mere differences in framing
- A claim qualifies another when it adds boundary conditions, not when it merely adds detail
- Supersession requires the later claim to explicitly update or correct the earlier one

Output as JSON array of relationship objects."""


DISCOURSE_PROMPT = """You are a discourse mapper. Given a set of claims about a question, identify:

1. POSITIONS: Distinct stances held on this question
2. STRONGEST CASES: For each position, which claims form its best argument?
3. BIGGEST HOLES: For each position, what is missing or weakest?
4. LIVE CRUXES: The specific factual or logical disagreements that, if resolved, would settle the question
5. EMPTY CHAIRS: Perspectives or evidence that should exist but are absent from the discourse

Output as JSON:
{
  "question": "The question being mapped",
  "positions": [
    {
      "stance": "Brief description of this position",
      "strongest_claims": ["claim_id1", "claim_id2"],
      "biggest_holes": ["Description of weakness 1", "Description of weakness 2"]
    }
  ],
  "live_cruxes": ["Crux 1: the specific disagreement", "Crux 2: ..."],
  "empty_chairs": ["Missing perspective 1", "Missing evidence 2"]
}"""


async def build_claim_graph(
    claims: list,
    llm_call,
    model: str = "claude-sonnet-4-20250514",
    batch_size: int = 20,
) -> list:
    """Identify relationships between claims and build edges.

    Processes claims in batches to handle large knowledge bases.
    Returns list of Edge objects.
    """
    edges = []

    # Process in batches
    for i in range(0, len(claims), batch_size):
        batch = claims[i:i + batch_size]
        claims_text = "\n".join(
            f"[{c.id}] {c.text}" for c in batch
        )

        # Also include prior claims for cross-batch relationships
        context_claims = claims[max(0, i - 5):i]
        if context_claims:
            claims_text = "PRIOR CLAIMS (for reference):\n" + "\n".join(
                f"[{c.id}] {c.text}" for c in context_claims
            ) + "\n\nCURRENT BATCH:\n" + claims_text

        prompt = f"{STRUCTURE_PROMPT}\n\n---\nCLAIMS:\n{claims_text}"
        response = await llm_call(prompt, model)

        batch_edges = _parse_edges_response(response)
        edges.extend(batch_edges)

    return edges


def _parse_edges_response(response_text: str) -> list:
    """Parse LLM response into Edge objects."""
    try:
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            start = response_text.find("[")
            end = response_text.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
            else:
                return []

        raw_edges = json.loads(json_str)
        edges = []
        for raw in raw_edges:
            try:
                edge_type = EdgeType(raw["type"])
                edges.append(Edge(
                    source_claim_id=raw["source_id"],
                    target_claim_id=raw["target_id"],
                    edge_type=edge_type,
                    evidence=raw.get("evidence", ""),
                ))
            except (KeyError, ValueError):
                continue
        return edges
    except (json.JSONDecodeError, IndexError):
        return []


async def build_discourse_map(
    claims: list,
    question: str,
    llm_call,
    model: str = "claude-sonnet-4-20250514",
) -> DiscourseMap:
    """Build a discourse map for a specific question.

    Identifies positions, strongest cases, biggest holes, live cruxes,
    and empty chairs (perspectives not represented).
    """
    claims_text = "\n".join(f"[{c.id}] {c.text}" for c in claims)

    prompt = f"""{DISCOURSE_PROMPT}

---
QUESTION: {question}

CLAIMS:
{claims_text}"""

    response = await llm_call(prompt, model)
    return _parse_discourse_response(response, question)


def _parse_discourse_response(response_text: str, question: str) -> DiscourseMap:
    """Parse LLM discourse mapping response."""
    try:
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
            else:
                return DiscourseMap(question=question)

        raw = json.loads(json_str)

        positions = []
        for p in raw.get("positions", []):
            positions.append(Position(
                id=f"pos_{len(positions)}",
                question=question,
                stance=p.get("stance", ""),
                strongest_cases=p.get("strongest_claims", []),
                biggest_holes=p.get("biggest_holes", []),
            ))

        return DiscourseMap(
            question=question,
            positions=positions,
            live_cruxes=raw.get("live_cruxes", []),
            empty_chairs=raw.get("empty_chairs", []),
        )
    except (json.JSONDecodeError, IndexError):
        return DiscourseMap(question=question)


def detect_contradictions(kb: KnowledgeBase) -> list:
    """Find contradictions in the knowledge base.

    Returns list of (claim_a, claim_b, edge) tuples where both claims
    are active/verified but contradict each other.
    """
    contradictions = []
    for edge in kb.edges:
        if edge.edge_type == EdgeType.CONTRADICTS:
            a = kb.claims.get(edge.source_claim_id)
            b = kb.claims.get(edge.target_claim_id)
            if a and b:
                active_statuses = {"active", "verified"}
                if a.status.value in active_statuses and b.status.value in active_statuses:
                    contradictions.append((a, b, edge))
    return contradictions


def find_unsupported_claims(kb: KnowledgeBase) -> list:
    """Find claims that have no supporting evidence edges."""
    supported_ids = set()
    for edge in kb.edges:
        if edge.edge_type == EdgeType.SUPPORTS:
            supported_ids.add(edge.target_claim_id)

    unsupported = []
    for cid, claim in kb.claims.items():
        if cid not in supported_ids and claim.status.value == "active":
            unsupported.append(claim)
    return unsupported
