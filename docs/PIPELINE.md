# Pipeline: Complete Technical Reference

> For the non-technical explanation, see [METHODOLOGY.md](METHODOLOGY.md).
> For the competition submission, see [SUBMISSION.md](SUBMISSION.md).

---

## Overview

```
config.yaml (single source of truth — models, thresholds, budget)
     │
     ▼
SOURCE URLs ──→ FETCH (trafilatura/pymupdf/yt-api)
                    │
                    ▼
              SOURCE TEXT ──→ EXTRACTION (GPT-4.1-mini, grounded quotes)
                                  │
                                  ▼
                        VERIFICATION (4 layers: quote match → regex → NLI → cross-provider)
                                  │
                                  ▼
                            events.jsonl (append-only, event-sourced)
                                  │
                                  ▼
                        ┌─────────────────┐
                        │ EpistemicStore   │
                        │ (replay → dicts)│
                        └────────┬────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
              ▼                  ▼                   ▼
        RELATIONSHIPS      CONFIDENCE          CRUX SCORES
        (embed+cosine+     (noisy-OR ×         (entropy ×
         batch classify)    quality product)     cascade BFS)
              │                  │                   │
              └──────────────────┼──────────────────┘
                                 │
                                 ▼
                         DISCOURSE MAP
                         (HDBSCAN + graph community + empty chairs + settling)
                                 │
                                 ▼
                        STATIC HTML SITE
                        (Jinja2 + Mermaid + external CSS)
```

---

## Running the Pipeline

```bash
# Full pipeline (produces HTML site)
uv run python run_pipeline.py <case_name> --phase full --budget 5.0

# Individual phases
uv run python run_pipeline.py <case_name> --phase extract
uv run python run_pipeline.py <case_name> --phase relationships

# Options
--max-sources N    # Limit sources processed (for testing)
--budget X.XX      # API cost cap in dollars
```

---

## Module Reference

### `config.py` — Single Source of Truth

All parameters, model assignments, provider credentials, and thresholds. Loads from `config.yaml` with environment variable overrides.

```python
from epistack.config import get_config
cfg = get_config()
model = cfg.resolve_model("extraction")  # → ModelConfig with id, provider, costs
```

Key config sections: `models` (pipeline role → model key), `extraction`, `verification`, `relationships`, `confidence`, `crux`, `discourse`, `budget`.

### `llm.py` — Provider-Agnostic LLM Client

Routes calls to OpenRouter, Anthropic, OpenAI, or Nebius based on config. Handles retry (tenacity, 3 attempts, exponential backoff), structured logging, and cost tracking.

```python
from epistack import llm
response = await llm.call(prompt, role="extraction")  # Resolves model via config
embeddings = await llm.embed(texts, role="embedding")
```

Cost tracked per call. `BudgetExceeded` raised when limit hit. `llm.get_cost_summary()` for totals.

### `fetch.py` — Source Fetching

Downloads and extracts text from URLs. Supports:
- **Blog/article**: httpx + trafilatura (HTML → clean text)
- **PDF**: pymupdf (text by page)
- **YouTube**: youtube-transcript-api (segments → full text)
- **Local files**: Path.read_text()

`manual_fallback` field in sources.yaml checked first (for paywalled/unavailable URLs).

### `extraction.py` — Grounded Claim Extraction

Extracts 3-5 most important claims per chunk. Every claim MUST have:
- `natural_language`: Atomic, falsifiable sentence
- `relevant_quote`: Exact text from source (verified Layer 1)
- `category`: empirical | assessment | methodological

**Layer 1** (quote containment, $0): Fuzzy 80% word-order match against source text. Hallucinated quotes rejected.
**Layer 2** (overclaiming regex, $0): 10 patterns ("proves conclusively", "irrefutably", etc.). Flagged but not rejected.

### `verification.py` — Layers 3-4

**Layer 3** (NLI entailment): "Does the quote actually ENTAIL the claim?" Catches overstatement (upgrading "may" to "does") and fabrication.
**Layer 4** (cross-provider): Independent model verifies claim is supported by quote. Only runs on top N% medium-confidence claims (cost optimization).

Fabrication detected → confidence dropped to 0.1. Both layers emit `meta.flag` events for audit trail.

### `store.py` — Event-Sourced JSONL Store

All state derived by replaying `events.jsonl`. Never mutates events — only appends.

**Event envelope**:
```json
{
  "event_id": "evt_000042",
  "event_type": "claim.asserted",
  "tx": 42,
  "timestamp": "2026-07-05T10:00:00Z",
  "actor": "pipeline:extraction",
  "method": "llm_extraction",
  "supersedes": null,
  "payload": { ... }
}
```

**Event types**: `claim.asserted`, `edge.asserted`, `position.stated`, `challenge.raised`, `claim.rank_changed`, `claim.superseded`, `meta.flag`

**Key operations**: `append()`, `replay()`, `replay_to(tx)`, `snapshot()`, `can_supersede()`, `is_valid()`

### `relationships.py` — Edge Detection

1. Batch embed all claims (OpenAI text-embedding-3-small)
2. Persist to `data/{case}/embeddings.npz`
3. Two-stage deduplication (>0.92 auto-merge, 0.80-0.92 LLM check)
4. Cosine candidate pairs (0.6 within-source, 0.4 cross-source)
5. Batch LLM classification (15 pairs per call)
6. Contradiction confirmation (reclassifies false contradicts → frames_differently)

**Edge types**: `supports`, `contradicts`, `depends_on`, `qualifies`, `supersedes`, `frames_differently`

### `confidence.py` — Dual Confidence Model

**Evidence score** (noisy-OR across independent clusters):
- Cluster correlated evidence (provenance-path overlap > 0.25)
- Within-cluster: effective sample size accounting for correlation
- Across clusters: noisy-OR (independent lines combine)

**Quality score** (weakest-link product):
- source_quality, quote_verified, logical_consistency, precision
- Any zero kills total

**Final** = evidence_score × quality_score

Assessment claims as evidence get strength × 0.3 (config-driven).

### `crux_detection.py` — Binary Entropy × Cascade BFS

```python
crux_score(v) = H(confidence(v)) × weighted_cascade_influence(v)
```

- CASCADE_EDGE_TYPES: `supports`, `depends_on`, `is_crux_for`
- EXCLUDED: `frames_differently` (lateral), `contradicts` (opposes)
- Target claims (conclusions) and assessment claims excluded from scoring
- Corrections: exponential decay per hop (0.7), redundancy factor (1/in_degree), target relevance

### `discourse.py` — Position Detection

1. HDBSCAN clustering on embeddings (tries min_cluster_size [5, 10, 15, 20])
2. Position merge: >50% mutual support edges → same position
3. **Graph-based opposing detection**: Claims contradicting/qualifying the largest position form the opposition
4. LLM fallback if HDBSCAN fails (< 2 positions)
5. Position labeling via LLM (stance, core_commitment, strongest_claims)
6. Empty chairs: LLM adversarial generation ("what perspectives are missing?")
7. Disagreement classification per position pair (factual_dispute vs framework_mismatch)

### `settling.py` — Performed Settling Detection

- Auto-detects verdict claims from language patterns
- Type 1: Verdict depends on unresolved cruxes (confidence 0.3-0.7)
- Type 2: Verdict adjudicates between frameworks (`frames_differently` in dependency chain)
- Edge-flip heuristic: if verdict has outgoing but no incoming supports, flips direction

### `generate_site.py` — HTML Site Generation

Jinja2 inline templates + external CSS (`static/style.css`) + Mermaid CDN.

**Page types**: index.html, positions/{id}.html, cruxes/{id}.html, claims/{id}.html
**Features**: color-coded positions, confidence bars, settling alerts, Mermaid overview diagram, "show all" toggle on position pages, bidirectional cross-linking

### `compliance_detector.py` — G3 Diagnostic

Regex-based detection of compliance-forcing patterns in prompts. 5 G-levels (G1 baseline → G5 extreme). G3 = threshold where fabrication begins.

Defenses: M2 (domain priming prefix) + M3 (metacognitive guard suffix). Applied automatically when above G3.

### `scoring.py` — Statistical Primitives

- `wilson_ci(successes, trials)`: Wilson score confidence interval
- `score_cross_model(results)`: Cross-model agreement with family penalty
- `score_source_quality(signals)`: Source credibility from metadata

---

## Configuration Reference (`config.yaml`)

```yaml
models:
  extraction: "gpt-4.1-mini"        # Fast + quality
  verification_nli: "gpt-4.1-nano"  # Batch, cheapest
  relationship_batch: "gpt-4.1-nano"
  relationship_confirm: "gpt-4.1-mini"
  discourse_crux: "gpt-4.1-mini"
  embedding: "embedding-small"

relationships:
  cosine_threshold: 0.6              # Within-source
  cross_source_cosine_threshold: 0.4 # Opposing claims use different vocabulary
  dedup_merge_threshold: 0.92
  dedup_check_threshold: 0.80

confidence:
  assessment_evidence_weight: 0.3    # Editorial judgments ≠ independent evidence
  correlation_threshold: 0.25        # Provenance overlap for clustering

crux:
  decay: 0.7                         # Exponential per BFS hop
  max_depth: 20

budget:
  dev_budget: 5.0                    # Raises BudgetExceeded when hit
```

---

## Cost Model (Actual, Validated)

| Stage | Model | Cost/case (5 sources) |
|-------|-------|----------------------|
| Extraction | gpt-4.1-mini | ~$0.10 |
| Verification L3-4 | gpt-4.1-nano | ~$0.04 |
| Embedding | text-embedding-3-small | <$0.01 |
| Relationships | gpt-4.1-nano + mini | ~$0.08 |
| Discourse | gpt-4.1-mini + nano | ~$0.05 |
| **Total per case** | | **~$0.25-0.30** |

Total for 3 case studies: ~$1.00. Wall-clock: ~15 min per case.

---

## Key Design Decisions (Why These Values)

| Parameter | Value | Why |
|-----------|-------|-----|
| Cross-source cosine threshold | 0.4 | Opposing claims use different vocabulary. Validated: 183 contradictions at 0.4 vs only 3 at 0.6 |
| Within-source cosine threshold | 0.6 | Same author = same vocabulary = high similarity. 0.6 filters noise. |
| Assessment evidence weight | 0.3 | One person's editorial judgment ("this argument is weak") ≠ independent empirical evidence. Tuned to prevent Alexander's assessments from dominating confidence. |
| Crux BFS decay | 0.7 | 0.7³ = 0.34 at depth 3. Distant claims matter less. Prevents all claims from scoring high in dense graphs. |
| Exclude assessments from crux scoring | — | Assessment claims ("judges found zoonosis more likely") are conclusions, not resolvable evidence. Without this, top cruxes were verdicts instead of empirical claims. |
| Exclude targets from crux scoring | — | Target claims (conclusions) are what cruxes RESOLVE, not cruxes themselves. Without this, the formula scored conclusions highest (circular). |
| Position merge threshold | >50% mutual supports | HDBSCAN separates "zoonotic evidence" from "zoonotic conclusion" (semantically different). But they're the same position (one supports the other). Merge fixes this. |
| Graph-based opposing position | Via contradicts/qualifies/frames edges | HDBSCAN misses lab-leak position because lab-leak claims are scattered across sources with diverse vocabulary. But they all CONTRADICT the zoonotic position. Graph community detection finds them. |
| GPT-4.1-mini for extraction | — | Benchmarked: 3s/call vs DeepSeek V4 Pro 7s/call. Same quality, 2.3× faster. Better edge direction compliance (follows "source=evidence, target=conclusion" convention). |
| Edge-flip heuristic for verdicts | — | LLMs sometimes classify "verdict supports evidence" instead of "evidence supports verdict." If a verdict claim has outgoing but no incoming supports, flip those edges. |
| Manual fallback for paywalled sources | — | BMJ, AHA journals return 403. Pipeline checks `manual_fallback` path in sources.yaml first, falls back to URL fetch only if no local file exists. |

## Acceptance Criteria (COVID Case — All Pass)

| # | Criterion | Evidence |
|---|---|---|
| 1 | ≥2 distinct positions | 3 found: zoonotic (76), lab-leak (62), methodology (6) |
| 2 | Market origin/amplification in top-5 cruxes | #3: HSM proximity, #5: earliest 40 cases |
| 3 | ≥1 genuine empty chair | 5 found (viral genomics, contact tracing, lab safety experts) |
| 4 | Performed settling fires on Rootclaim verdict | 5/9 verdicts, 92 contested deps + framework adjudication |
| 5 | All claims traceable to source quotes | 230/230 active claims with `quote_verified: true` |

## Edge Progression (Debugging History)

Understanding how the edge count evolved helps diagnose future issues:

| Change | Edges | What Fixed It |
|--------|-------|---------------|
| Cross-source only | 14 | Initial design — too restrictive |
| + Within-source edges | 39 | Removed source filter — captures argument chains |
| + GPT-4.1-mini (edge direction fix) | 344 | Better prompt compliance (source=evidence, target=conclusion) |
| + Lower cross-source threshold (0.4) | 916 | Opposing claims in different vocabulary now get paired |

If you see low edge counts on a new case, check: within-source enabled? Cross-source threshold appropriate for the vocabulary diversity?

## How to Extend

**Add a new case study:**
1. Create `examples/<case_name>/sources.yaml` (URLs + metadata)
2. Run `uv run python run_pipeline.py <case_name> --phase full`
3. Open `output/<case_name>/index.html`

**Add a new provider:**
1. Add entry to `PROVIDERS` in `src/epistack/config.py`
2. Add model entries to `MODELS`
3. Reference in `config.yaml`

**Add a challenge (collaboration):**
```bash
uv run python scripts/add_challenge.py <case> --target <claim_id> --body "..." --source-label "..."
```

**Change models:** Edit `config.yaml` models section. Zero code changes.
