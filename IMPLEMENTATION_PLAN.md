# Epistack — Implementation Plan v2.0

> **Status note:** This was the original architecture plan written before implementation. The system is now fully built. For the current technical reference, see [docs/PIPELINE.md](docs/PIPELINE.md). Key differences from this plan: models are GPT-4.1-mini/nano via OpenRouter (not Claude), cost is ~$0.30/case (not $14-18), and graph-based position detection supplements HDBSCAN.

**Author**: Rahul Kumar
**Completed**: July 2026

---

## 1. What This Is

A Python system that takes existing debate materials (papers, transcripts, blog posts) about contested questions and produces a **navigable static HTML site** showing:
- The distinct **positions** people hold on the question
- The **cruxes** — specific disagreements whose resolution would change the picture most
- The **confidence** of each claim, with correlation-aware evidence combination
- What's **missing** from the discourse (empty chairs)
- Whether the debate **performed settling** (declared a winner without resolving cruxes)

Three case studies: COVID-19 origins (contested), LHC black holes (settled), eggs & health (vague).

---

## 2. Architecture

```
SOURCE DOCS ──→ EXTRACTION (Sonnet 4.6) ──→ VERIFICATION (4 layers) ──→ events.jsonl
                                                                              │
                                                                              ▼
                                                                    ┌─────────────────┐
                                                                    │ EpistemicStore   │
                                                                    │ (Python dicts)   │
                                                                    └────────┬────────┘
                                                                             │
                          ┌──────────────────────────────────────────────────┼──────────┐
                          │                          │                       │          │
                          ▼                          ▼                       ▼          ▼
                   RELATIONSHIPS              DISCOURSE MAP           CONFIDENCE    CRUX SCORES
                   (Haiku batch)              (HDBSCAN + Sonnet)      (dual model)  (entropy×cascade)
                          │                          │                       │          │
                          └──────────────────────────┴───────────────────────┴──────────┘
                                                     │
                                                     ▼
                                            STATIC HTML SITE
                                            (Jinja2 + Mermaid)
```

**Constraints**: API-only (no local models). JSONL append-only storage. ~$14-18 per case study.

---

## 3. Schema (Event-Sourced)

Every action is an append-only event. Source of truth is `events.jsonl`. State is derived by replaying.

### Event Envelope

```json
{
  "event_id": "evt_000042",
  "event_type": "claim.asserted",
  "tx": 42,
  "timestamp": "2026-06-26T10:00:00Z",
  "actor": "pipeline:extraction",
  "method": "llm_extraction",
  "supersedes": null,
  "payload": { }
}
```

| Field | Type | Purpose |
|-------|------|---------|
| `event_id` | string | Globally unique, monotonic |
| `event_type` | enum | `claim.asserted`, `edge.asserted`, `position.stated`, `challenge.raised`, `claim.rank_changed`, `meta.flag` |
| `tx` | int | Transaction counter. Enables time-travel replay to any point. |
| `timestamp` | ISO 8601 | Wall-clock time (display/audit only; tx is ordering authority) |
| `actor` | string | `pipeline:extraction`, `pipeline:assessment`, `researcher:name` |
| `method` | enum | `llm_extraction`, `manual`, `inference`, `api_import` |
| `supersedes` | string/null | If set, this event replaces the referenced event_id |

### Claim Payload

```json
{
  "claim_id": "clm_covid_furin_natural",
  "statement": {
    "subject": "ent_sars_cov2_furin_cleavage_site",
    "predicate": "arose_via",
    "object": "ent_natural_evolution",
    "object_type": "entity_ref",
    "natural_language": "The furin cleavage site in SARS-CoV-2 arose through natural evolutionary processes"
  },
  "rank": "normal",
  "epistemic_status": "value",
  "confidence": 0.62,
  "qualifiers": {
    "temporal_validity": {"start": "2020-02-01", "end": null},
    "context": "Molecular virology analysis of spike protein",
    "strength_of_evidence": "comparative_genomics",
    "domain": "virology"
  },
  "references": [
    {
      "ref_id": "ref_andersen_2020",
      "type": "stated_in",
      "source": "https://doi.org/10.1038/s41591-020-0820-9",
      "source_label": "Andersen et al. 2020, Nature Medicine",
      "relevant_quote": "the genetic data irrefutably show that SARS-CoV-2 is not derived from any previously used virus backbone",
      "quote_verified": true
    }
  ],
  "extraction_metadata": {
    "source_document": "doc_andersen_2020",
    "extraction_model": "claude-sonnet-4-6",
    "quote_verification": "pass"
  },
  "tags": ["virology", "origins_debate"]
}
```

| Field | Values | Notes |
|-------|--------|-------|
| `rank` | `preferred` / `normal` / `deprecated` | Wikidata pattern |
| `epistemic_status` | `value` / `somevalue` / `novalue` | Wikidata pattern |
| `strength_of_evidence` | `anecdote` < `case_report` < `cohort` < `rct` < `meta_analysis` | Evidence hierarchy |
| `references[].type` | `stated_in` / `derived_from` / `imported_from` / `inferred_from` | Provenance type |

### Edge Payload

```json
{
  "edge_id": "edg_furin_supports_lab",
  "edge_type": "supports",
  "source": "clm_furin_not_in_close_relatives",
  "target": "clm_lab_engineering_hypothesis",
  "strength": 0.72,
  "qualifiers": {
    "mechanism": "Absence in closest relatives suggests insertion",
    "conditional_on": "clm_no_intermediate_host_found"
  },
  "references": [
    {
      "ref_id": "ref_edge_001",
      "type": "inferred_from",
      "source": "reasoning:pipeline:2026-06-26",
      "model_used": "claude-haiku-4-5",
      "confidence_of_inference": 0.78
    }
  ]
}
```

Edge types: `supports`, `contradicts`, `depends_on`, `is_crux_for`, `refines`, `supersedes`, `frames_differently`.

**The `frames_differently` edge** (inspired by Tony Sale's CONTEXT_MUTATION concept): Two claims address the same phenomenon through incompatible interpretive frames. They agree on facts but ask different questions or apply different methodological lenses. Example: an egg-mortality observational study and an egg-LDL RCT aren't contradicting each other — one asks "what correlates with death" and the other asks "what causally drives cholesterol." Marking this as `contradicts` would misrepresent the debate structure.

```json
{
  "edge_id": "edg_eggs_frame_mismatch",
  "edge_type": "frames_differently",
  "source": "clm_eggs_ldl_rct",
  "target": "clm_eggs_mortality_observational",
  "strength": 0.85,
  "qualifiers": {
    "mechanism": "Different question asked of same phenomenon",
    "source_frame": "Causal mechanism (LDL under controlled conditions)",
    "target_frame": "Population outcome (mortality in free-living cohorts)",
    "shared_facts": ["ent_egg_consumption", "ent_cholesterol_pathway"],
    "divergence_type": "methodological_frame"
  }
}
```

**System-wide implications of `frames_differently`:**
- Crux detection: EXCLUDED from cascade BFS (lateral, not vertical dependency)
- Confidence model: does NOT count as contradicting evidence (different question ≠ counter-evidence)
- Discourse mapping: signals framework mismatch vs factual dispute (changes crux page display)
- Performed settling: Type 2 detection — verdict adjudicates a framework choice rather than resolving a fact
- Empty chairs: framework boundaries signal missing "bridging" positions
- Visualization: different crux template for framework mismatches ("resolution requires agreeing on which question matters, not finding more evidence")

### Position Payload

```json
{
  "position_id": "pos_lab_leak",
  "label": "Lab leak from gain-of-function research",
  "summary": "SARS-CoV-2 originated from a laboratory incident at WIV",
  "core_commitment": "The virus was being studied or engineered before release",
  "member_claims": ["clm_wiv_research", "clm_furin_site", "clm_database_removal"],
  "strongest_case": ["clm_wiv_research", "clm_furin_site", "clm_early_cases"],
  "credence": 0.55,
  "confidence_trajectory": [
    {"date": "2020-03", "credence": 0.15, "event": "Initial outbreak"},
    {"date": "2023-03", "credence": 0.55, "event": "US agency assessments"}
  ]
}
```

### Challenge Payload (minimum viable — 6 fields from user)

```json
{
  "type": "Challenge",
  "target": "clm_early_cases_no_market_link",
  "challenge_type": "evidential",
  "body": "Worobey et al. 2022 shows earliest cases DID cluster at market",
  "source_url": "https://doi.org/10.1126/science.abp8715",
  "source_label": "Worobey et al. 2022, Science"
}
```

System expands this into full challenge event with: challenge_id, severity assessment, argument extraction, graph integration.

---

## 4. Storage

**JSONL append-only event log + in-memory Python dicts.**

Why not SQLite: At 500-2000 claims (5K-20K total events), everything fits in ~20-50MB RAM. SQLite's value (ACID, concurrent access) doesn't apply to single-developer, single-process. JSONL gives trivial time-travel (`replay to tx N`), trivial debugging (`grep`), trivial backup (`cp`).

```
data/
  covid_origins/
    events.jsonl          # Source of truth, append-only
    sources/              # Raw source documents
    snapshots/            # Periodic full-state dumps for fast reload
  lhc_black_holes/
    events.jsonl
    sources/
  eggs_health/
    events.jsonl
    sources/
```

---

## 5. AI Pipeline

### 5.1 Extraction (Claude Sonnet 4.6)

Prompt pattern enforcing grounded extraction:

```
You are extracting claims from a source document. RULES:
1. Only extract claims EXPLICITLY stated in the text
2. Every claim MUST include a direct quote from the source
3. Never infer, synthesize, or generate claims not present in the source
4. If ambiguous, extract with qualifier "ambiguous"
5. Preserve assertion strength (don't upgrade "may" to "does")

For each claim output:
- natural_language: the claim as one atomic sentence
- relevant_quote: exact quote from source (for verification)
- strength_of_evidence: anecdote/case_report/cohort/rct/meta_analysis
- tags: [domain keywords]
```

### 5.2 Verification (4 layers)

| Layer | Method | Cost | What it catches |
|-------|--------|------|-----------------|
| 1. Quote Match | String containment | $0 | Hallucinated quotes |
| 2. Structural Rules | Regex for overclaiming | $0 | "proves conclusively", "beyond doubt" |
| 3. NLI Entailment | Haiku: "Does quote support claim?" | $0.20/1K | Claims stretching beyond source |
| 4. Cross-Provider | GPT-4o: "Is claim in source?" | $1.50/1K | Correlated blind spots |

Claims failing Layer 1-2 rejected immediately (free). Layer 3-4 only on survivors.

### 5.3 Relationship Detection

1. Embed all claims (OpenAI `text-embedding-3-small`, $0.01/1K)
2. Cosine filter: similarity > 0.6 from DIFFERENT positions → candidates
3. Batch LLM (Haiku): 15 pairs per call → classify edge type
4. Contradiction confirmation (Sonnet): only for "contradicts" — higher stakes

### 5.4 Multi-Trial Assessment

Two trials per claim with different framings:
- Neutral: "Evaluate whether this claim is supported"
- Adversarial: "Find the weakest assumption. Attack it."

### 5.5 Cross-Model Adversarial (top 10% only)

GPT-4o skeptic attacks → Claude Sonnet judge evaluates. Only on medium-confidence claims (0.3-0.7).

### 5.6 Compliance-Trap Detection

Before ANY verification prompt: run G3 diagnostic (regex, $0). If compliance pressure detected, apply M2 (domain priming) + M3 (metacognitive guard). Reference: arXiv:2605.02398.

---

## 6. Algorithms

### 6.1 Crux Detection

```python
import math
from collections import defaultdict

def binary_entropy(p: float) -> float:
    """H(p) peaks at 0.5 (max uncertainty), zero at 0 and 1."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)

# Edge types that create vertical (causal/dependency) relationships for cascade
CASCADE_EDGE_TYPES = ("supports", "depends_on", "is_crux_for")
# NOTE: "frames_differently" is EXCLUDED — it's lateral (incommensurability),
# not vertical (dependency). "contradicts" is also excluded — it opposes, not supports.

def compute_crux_scores(claims, edges, target_ids, decay=0.7, max_depth=20):
    """
    crux_score(v) = H(confidence(v)) × weighted_cascade_influence(v)

    Based on: Chan & Darwiche 2004 (sensitivity analysis in Bayesian networks),
    Howard 1966 (value of information theory).

    Corrections applied:
    - Exponential decay per hop (distant claims matter less)
    - Redundancy: if node has many supporters, losing one matters less
    - Target relevance: only count nodes that can reach a conclusion node
    """
    # Build adjacency (only cascade-forming edge types)
    adjacency = defaultdict(list)
    in_degree = defaultdict(int)
    for edge in edges.values():
        if edge["edge_type"] in CASCADE_EDGE_TYPES:
            adjacency[edge["source"]].append(edge["target"])
            in_degree[edge["target"]] += 1

    # Reverse BFS: which nodes can reach targets?
    reverse_adj = defaultdict(list)
    for src, targets in adjacency.items():
        for tgt in targets:
            reverse_adj[tgt].append(src)
    target_reachable = set(target_ids)
    queue = list(target_ids)
    while queue:
        node = queue.pop(0)
        for parent in reverse_adj[node]:
            if parent not in target_reachable:
                target_reachable.add(parent)
                queue.append(parent)

    # Score each claim
    scores = {}
    for claim_id, claim in claims.items():
        confidence = claim.get("confidence", 0.5)
        uncertainty = binary_entropy(confidence)
        if uncertainty < 0.001:
            scores[claim_id] = 0.0
            continue

        # BFS cascade with corrections
        cascade = 0.0
        bfs_queue = [(claim_id, 0)]
        visited = {claim_id}
        while bfs_queue:
            current, depth = bfs_queue.pop(0)
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

    return dict(sorted(scores.items(), key=lambda x: x[1], reverse=True))
```

**Complexity**: O(n × (n + m)). ~0.3s at 2000 nodes.

### 6.2 Confidence Model (Dual: Corroboration × Quality)

```python
import math

def detect_correlation(ev_a, ev_b, k_max=4):
    """Provenance-path overlap → correlation (0=independent, 1=redundant)."""
    path_a = set(ev_a["provenance_path"])
    path_b = set(ev_b["provenance_path"])
    if not (path_a & path_b):
        return 0.0
    # LCA depth as fraction of path length
    lca_depth = 0
    for i in range(min(len(ev_a["provenance_path"]), len(ev_b["provenance_path"]))):
        if ev_a["provenance_path"][i] == ev_b["provenance_path"][i]:
            lca_depth = i + 1
        else:
            break
    return lca_depth / max(len(ev_a["provenance_path"]), len(ev_b["provenance_path"]), 1)

def cluster_correlated(evidence, threshold=0.25):
    """Single-linkage clustering. Conservative: over-clusters."""
    n = len(evidence)
    parent = list(range(n))
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(x, y):
        px, py = find(x), find(y)
        if px != py: parent[px] = py
    for i in range(n):
        for j in range(i + 1, n):
            if detect_correlation(evidence[i], evidence[j]) > threshold:
                union(i, j)
    clusters = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(evidence[i])
    return list(clusters.values())

def compute_confidence(evidence_lines, quality_dimensions):
    """
    DUAL MODEL:
    - Evidence lines: independent corroboration (noisy-OR across clusters)
    - Quality dimensions: weakest-link (product — any zero kills total)
    - Final = evidence_score × dimension_score
    """
    # Cluster correlated evidence
    clusters = cluster_correlated(evidence_lines)
    # Within-cluster: effective sample size + noisy-OR
    cluster_strengths = []
    for cluster in clusters:
        n = len(cluster)
        if n == 1:
            cluster_strengths.append(cluster[0]["strength"])
            continue
        total_corr = sum(
            detect_correlation(cluster[i], cluster[j])
            for i in range(n) for j in range(i+1, n)
        ) / max(1, n*(n-1)//2)
        effective_n = n / (1 + (n-1) * total_corr)
        avg_strength = sum(e["strength"] for e in cluster) / n
        cluster_strengths.append(1.0 - (1.0 - avg_strength) ** effective_n)

    # Across clusters: noisy-OR
    evidence_score = 1.0 - math.prod(1.0 - s for s in cluster_strengths) if cluster_strengths else 0.0
    # Quality dimensions: product (conjunctive)
    dimension_score = math.prod(d["score"] for d in quality_dimensions) if quality_dimensions else 1.0
    final = evidence_score * dimension_score

    if final >= 0.90: level = "very_high"
    elif final >= 0.75: level = "high"
    elif final >= 0.50: level = "medium"
    elif final >= 0.25: level = "low"
    else: level = "very_low"

    return {
        "final_confidence": round(final, 3), "level": level,
        "evidence_score": round(evidence_score, 3),
        "dimension_score": round(dimension_score, 3),
        "cluster_count": len(clusters),
        "weakest_dimension": min(quality_dimensions, key=lambda d: d["score"])["name"] if quality_dimensions else None,
        "bottleneck": "evidence" if evidence_score < dimension_score else "quality"
    }
```

### 6.3 Performed Settling Detection

```python
def detect_performed_settling(store, verdict_claim_id):
    """
    performed_settling = verdict_exists AND (
        Type 1: dependency cruxes remain contested, OR
        Type 2: verdict adjudicates a framework choice rather than resolving a fact
    )
    """
    verdict = store.claims.get(verdict_claim_id)
    if not verdict:
        return {"detected": False}

    # BFS upstream: what does this verdict depend on?
    dependencies = set()
    queue = [verdict_claim_id]
    visited = {verdict_claim_id}
    while queue:
        current = queue.pop(0)
        for edge in store.edges.values():
            if edge["target"] == current and edge["edge_type"] in ("supports", "depends_on"):
                if edge["source"] not in visited:
                    visited.add(edge["source"])
                    dependencies.add(edge["source"])
                    queue.append(edge["source"])

    # Which cruxes are in the dependency chain?
    crux_edges = [e for e in store.edges.values() if e["edge_type"] == "is_crux_for"]
    relevant_cruxes = [
        e["source"] for e in crux_edges
        if e["source"] in dependencies or e["target"] in dependencies
    ]

    # Which remain unresolved?
    contested = [c for c in relevant_cruxes if store.claims.get(c, {}).get("confidence", 0.5) < 0.85]

    # Type 2: Check if verdict crosses a framework boundary
    framework_adjudication = False
    for dep_id in dependencies:
        frame_edges = [
            e for e in store.edges.values()
            if e["edge_type"] == "frames_differently"
            and (e["source"] == dep_id or e["target"] == dep_id)
        ]
        if frame_edges:
            framework_adjudication = True
            break

    if not contested and not framework_adjudication:
        return {"detected": False, "reason": "Cruxes resolved, no framework issues"}

    settling_type = []
    if contested:
        settling_type.append("unresolved_cruxes")
    if framework_adjudication:
        settling_type.append("framework_adjudication")

    return {
        "detected": True,
        "settling_type": settling_type,
        "contested_cruxes": contested,
        "framework_adjudication": framework_adjudication,
        "severity": len(contested) / max(1, len(relevant_cruxes)) if relevant_cruxes else (0.5 if framework_adjudication else 0.0),
        "explanation": f"Verdict rests on {len(contested)} unresolved cruxes" + 
                       (" and adjudicates between incompatible frameworks" if framework_adjudication else "")
    }
```

---

## 7. Discourse Mapping Pipeline

| Step | Algorithm | LLM Cost | Output |
|------|-----------|----------|--------|
| 1. Embed claims | OpenAI text-embedding-3-small | $0.01 | Vectors |
| 2. Extract positions | HDBSCAN (min_cluster=10) + Haiku labeling | $0.05 | 3-8 Positions |
| 2b. Classify disagreements | Count `contradicts` vs `frames_differently` edges between position pairs → `factual_dispute` or `framework_mismatch` | $0 (graph) | Disagreement type per pair |
| 3. Identify cruxes | Sonnet (different prompts for factual vs framework disputes) | $0.20 | 5-15 Cruxes |
| 4. Detect empty chairs | Coverage asymmetry + Sonnet adversarial | $0.25 | 0-5 Gaps |
| 5. Select strongest case | PageRank within subgraph + coherence | $0.25 | Top 3-5 claims/position |
| 6. Check settling | Pure graph traversal (6.3 above) | $0 | Boolean per verdict |

**Total: ~$0.75/case, ~2 minutes.**

---

## 8. Collaboration Protocol

**Challenge triggers re-assessment when ALL hold**:
1. Challenge has a cited source
2. Target claim confidence > 0.3
3. No duplicate challenge for same source

**Process**: New contradicting edge → confidence recomputed → cascade propagation if drop is significant → discourse map flags updated.

---

## 9. Visualization (Static HTML)

### Page Types

| Page | Content |
|------|---------|
| `index.html` | Mermaid overview, positions, cruxes, stats, settling status |
| `positions/{id}.html` | Strongest case, challenges, trajectory, member claims |
| `cruxes/{id}.html` | Both sides, evidence, what would resolve it |
| `claims/{id}.html` | Provenance, confidence breakdown, cascade impact |
| `evidence/{id}.html` | Source detail, extracted claims |

### Generated Output

```
output/covid_origins/
  index.html
  positions/pos_zoonotic.html, pos_lab_leak.html
  cruxes/crx_host_found.html, crx_furin.html
  claims/clm_001.html ... clm_500.html
  evidence/ref_andersen.html, ref_worobey.html
  static/style.css
```

**Build time**: ~36 hours total.

---

## 10. 20-Day Build Plan

### Week 1 (Days 1-7): Core Engine

| Day | Deliverable |
|-----|-------------|
| 1 | `store.py`: JSONL append, replay, event types. Tests. |
| 2 | `extraction.py`: Grounded prompt, Sonnet calls, 1 doc e2e. |
| 3 | `verification.py`: 4-layer pipeline. Measure fabrication rate. |
| 4 | `relationships.py`: Embed → cosine → Haiku batch → edges. |
| 5 | `confidence.py`: Dual model + correlation detection. Tests. |
| 6 | `crux_detection.py`: Entropy × cascade. Synthetic graph test. |
| 7 | Integration: Full pipeline on 5 docs. Fix bugs. |

**Exit**: 5 docs → populated events.jsonl with claims, edges, scores.

### Week 2 (Days 8-14): Discourse + Viz

| Day | Deliverable |
|-----|-------------|
| 8 | `discourse.py`: HDBSCAN + crux identification |
| 9 | `settling.py` + empty chairs |
| 10 | `generate_site.py` + Jinja2 templates (functional, ugly) |
| 11 | CSS + Mermaid (styled) |
| 12 | Cross-linking, breadcrumbs, "if wrong what changes" |
| 13 | Case 1 (COVID): full pipeline, all sources |
| 14 | Iterate: fix quality, tune params |

**Exit**: Navigable HTML site for COVID case.

### Week 3 (Days 15-20): Ship

| Day | Deliverable |
|-----|-------------|
| 15 | Case 2 (LHC): settled-science handling |
| 16 | Case 3 (Eggs): question-decomposition handling |
| 17 | Quality pass across all three |
| 18 | Collaboration demo: manual challenges showing evolution |
| 19 | Polish: browser test, links, "How to Navigate" |
| 20 | Submission: package, reproducibility check |

### What to SKIP

Real-time collab UI, D3 force graph, NetworkX, SQLite, prompt caching, LiteLLM, temporal charts, local models (DeBERTa/ONNX).

---

## 11. Cost Estimates

| Call Type | Model | Cost / 1000 claims |
|-----------|-------|--------------------|
| Extraction | Claude Sonnet 4.6 | $2.60 |
| Quote Verification | String match | $0.00 |
| NLI Entailment | Claude Haiku 4.5 | $0.20 |
| Cross-Provider | GPT-4o | $1.50 |
| Embedding | text-embedding-3-small | $0.01 |
| Relationship Detection | Claude Haiku 4.5 | $2.50 |
| Contradiction Confirm | Claude Sonnet 4.6 | $0.80 |
| Multi-Trial Assessment | Claude Sonnet 4.6 | $6.10 |
| Adversarial (top 10%) | Claude Opus 4 | $3.30 |
| Position Labeling | Claude Haiku 4.5 | $0.05 |
| Crux Identification | Claude Sonnet 4.6 | $0.20 |
| Empty Chairs | Claude Sonnet 4.6 | $0.15 |
| **Total per case** | | **$14-18** |
| **Total (3 cases)** | | **$40-54** |

---

## 12. Edge Cases & Mitigations

Scenarios tested hypothetically against the architecture:

| Scenario | What breaks | Mitigation |
|----------|-------------|------------|
| YouTube debate transcripts (COVID case) | Extraction assumes text input | Need transcript fetcher or manual transcript prep before ingestion |
| Eggs: all framework mismatches, no factual disputes | Crux detector returns zero scores (no cascade through `frames_differently` edges) | Fallback: surface framework mismatches as "meta-cruxes" — the crux is which question to ask |
| LHC: all claims high confidence | No cruxes identified (entropy ≈ 0 for everything) | Show "settled by" page instead of empty crux list — map dependency chain + identify weakest speculative link |
| Challenge with stronger source than original | Fixed `-0.1 * contra_score` doesn't capture relative strength | Adjustment proportional to quality ratio: `challenge_quality / original_quality` |
| Circular reasoning (A supports B supports C supports A) | BFS stops at visited nodes, cycle goes semantically undetected | Detect cycles via DFS back-edges, flag as "potential circular reasoning" |
| 5 claims from same paper look like 5 independent lines | Without provenance tracking, correlation undetectable | Make `extraction_metadata.source_document` mandatory; conservative assumption if missing |
| Haiku fabricates a relationship between unrelated claims | Bad edge enters the graph | Confidence threshold on edge creation (>0.6); Sonnet confirmation for `contradicts` |
| HDBSCAN produces 0 or 15 clusters (eggs case) | Positions nonsensical | Fallback to LLM-based sub-question identification when cluster count < 2 or > 10 |
| Same claim extracted from two sources | Duplicate nodes, inflated confidence | Content-based dedup via embedding similarity (>0.92 threshold → merge as additional reference) |
| Event replay to past transaction | Challenge exists but confidence update doesn't yet | Strict monotonic replay: only apply events where `tx <= target_tx` |
| Relationship prompt missing `frames_differently` option | LLM forces framework mismatches into `contradicts` | Explicitly include `frames_differently` with clear usage criteria in classification prompt |

---

## 13. Known Limitations

1. **Confidence uncalibrated** (mitigation: verbal labels + explicit disclaimer on output) — relative rankings, not calibrated probabilities
2. **Source quality dependent** — faithfully reproduces claims from unreliable sources
3. **Position extraction fragile** — HDBSCAN may fail without clear polarization
4. **Single-user collaboration** — protocol demonstrated, not proven multi-user
5. **DAG assumption** — cycles handled mechanically (visited set) not semantically
6. **Empty chair false positives** — only top 2-3 presented
7. **Non-empirical claims** — values/definitions forced into claim format
8. **Source coverage** — 20 docs per case may not suffice for exhaustive coverage
9. **No ground truth** — can't prove crux detection matches expert judgment

---

## 14. References

| Paper | Relevance |
|-------|-----------|
| Chan & Darwiche 2004, "Sensitivity Analysis in Bayesian Networks" (UAI) | Crux formula basis |
| Howard 1966, "Information Value Theory" (IEEE) | Value of information = entropy × cascade |
| Kumar 2026, arXiv:2605.02398, "Compliance-Induced Epistemic Collapse" | G3 threshold, M2/M3 defenses |
| Graphiti, arXiv:2501.13956 (2025) | Bi-temporal validity (94.8% DMR) |
| FPF, arXiv:2601.21116 (2026) | Confidence-gated supersession |
| GAAMA, arXiv:2603.27910 (2026) | Hybrid retrieval |
| EditPropBench, arXiv:2605.02083 (2026) | Cascade propagation |
| Fat-Cat, arXiv:2602.02206 (2026) | Markdown > JSON for LLM reasoning |
| Piraveenan et al. 2013, "Percolation Centrality" | Structure + state importance |
| Dung 1995, "On the Acceptability of Arguments" (AIJ) | Argumentation frameworks |

---

## File Structure

```
src/
  store.py              # EpistemicStore: JSONL append, replay, state dicts
  extraction.py         # Grounded claim extraction (Sonnet)
  verification.py       # 4-layer fabrication prevention
  relationships.py      # Edge detection (embed + cosine + Haiku)
  confidence.py         # Dual model: corroboration × quality
  crux_detection.py     # Binary entropy × weighted cascade
  discourse.py          # Positions (HDBSCAN) + cruxes + empty chairs
  settling.py           # Performed settling detection
  generate_site.py      # Static HTML generator (Jinja2 + Mermaid)
  compliance.py         # G3 diagnostic + M2/M3 defenses
templates/
  base.html             # Shared layout, nav, CSS link
  index.html            # Landing: overview + Mermaid + stats
  position.html         # Position detail
  crux.html             # Crux detail (both sides)
  claim.html            # Claim detail (provenance, confidence)
  evidence.html         # Source detail
static/
  style.css             # ~250 lines, Kialo-inspired
data/
  covid_origins/events.jsonl, sources/
  lhc_black_holes/events.jsonl, sources/
  eggs_health/events.jsonl, sources/
output/
  covid_origins/index.html, positions/, cruxes/, claims/, evidence/
  lhc_black_holes/...
  eggs_health/...
tests/
  test_store.py
  test_confidence.py
  test_crux.py
  test_settling.py
run_pipeline.py         # Main entry: sources → events → site
requirements.txt        # jinja2, hdbscan, numpy, anthropic, openai, httpx
```
