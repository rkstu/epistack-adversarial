# Methodology: Structural Illumination of Epistemic Disagreement

> For the technical implementation, see [PIPELINE.md](PIPELINE.md).
> For the competition submission, see [SUBMISSION.md](SUBMISSION.md).

---

## The Problem We Solve

Six independent Bayesian analysts looked at the same COVID origins evidence and produced estimates spanning 23 orders of magnitude — from "99.9% natural" to "99.9% lab leak." They aren't disagreeing about facts. They're weighting different considerations differently, making different independence assumptions, using different prior frameworks.

Existing tools fail at this:
- **AI deep research** (Claude, Perplexity): summarizes, flattens disagreement, hides uncertainty, can fabricate
- **Wikipedia**: good for settled questions, terrible for contested ones
- **Academic papers**: rigorous but siloed; don't compound across authors

We build something different: a system that maps the **structure** of disagreement — not who's right, but WHERE exactly they diverge and WHAT would resolve it.

---

## Core Principles

### 1. Structural Illumination, Not Verdicts

The system never says "lab leak is more likely." Instead it says: "These positions diverge on 3 specific claims. If claim X were resolved, 5 of 6 analysts would converge." The value is making the disagreement NAVIGABLE, not resolving it.

### 2. AI Connects Dots, Never Invents Them

Every claim in the system traces to a direct quote from a source document. The AI does structural labor (extract, cross-reference, detect contradictions). It never generates novel factual assertions. If a claim can't be grounded in a source quote, it is rejected.

### 3. Disagreement Is Preserved, Not Resolved

The system is append-only (like git). You add claims, add challenges — never edit others' work. Opposing positions coexist. "Forks" are a feature, not a bug.

---

## Key Epistemic Concepts

### Crux Detection

A **crux** is a claim that is both uncertain AND influential. Formally:

```
crux_score(v) = H(confidence(v)) × weighted_cascade_influence(v)
```

Where H is binary entropy (peaks at 0.5 — maximum uncertainty) and cascade influence measures how many downstream conclusions change if this claim flips. A foundational fact nobody disputes has high connectivity but LOW crux score (entropy ≈ 0). A contested claim that feeds into multiple conclusions has HIGH crux score.

**Basis**: Chan & Darwiche 2004 (sensitivity analysis in Bayesian networks), Howard 1966 (value of information theory).

### Performed Settling

A debate **performs settling** when it declares a winner without resolving the underlying disagreements. The Rootclaim debate judges ruled for zoonosis — but 92 of the dependency claims remain contested (confidence 0.3-0.7). The verdict didn't emerge from resolving cruxes; it emerged from the judges' overall impression.

We detect this via graph traversal: if a verdict claim's dependency chain contains unresolved cruxes OR crosses framework boundaries, performed settling is flagged.

### Framework Mismatches (`frames_differently`)

Not all disagreements are factual. When an observational study says "eggs correlate with mortality" and an RCT says "eggs raise LDL by 5mg/dL," they aren't contradicting each other — they're asking different questions about the same phenomenon.

Our `frames_differently` edge type captures this distinction. It prevents the system from misclassifying methodology mismatches as factual disputes. Resolution requires agreeing which question matters for your context, not finding more evidence.

### Empty Chairs

Perspectives absent from the discourse. If a debate about lab safety has no input from actual biosafety professionals, that's an empty chair. The system identifies these gaps adversarially: "Given these positions and evidence, what viewpoints or evidence types are conspicuously absent?"

---

## Verification Philosophy

### The Compliance Trap (arXiv:2605.02398)

In 78,000+ evaluations across 11 frontier models, we found that 8/11 fabricate when their system prompt prohibits "I don't know" (the G3 condition). This is a binary threshold — below G3, models admit uncertainty; above G3, they fabricate confidently.

**Why this matters for epistemic tools**: Every AI-assisted knowledge system sends prompts to language models. If those prompts cross the G3 threshold (and most production defaults do), the knowledge base contains confident-sounding fabrications indistinguishable from verified claims.

**Our defenses**:
- M2 (domain priming): +18.5pp resistance (5,110 evaluations, 8 models)
- M3 (metacognitive guard): +19.3pp resistance (same conditions)

These are applied automatically before every verification prompt.

### 4-Layer Verification

| Layer | Method | Cost | What It Catches |
|-------|--------|------|-----------------|
| 1 | Quote containment | $0 | Hallucinated quotes |
| 2 | Overclaiming regex | $0 | "Proves conclusively," absolute language |
| 3 | NLI entailment | ~$0.01 | Claims stretching beyond source |
| 4 | Cross-provider check | ~$0.01 | Correlated blind spots |

Claims failing Layer 1-2 are rejected immediately (free). Layers 3-4 only run on survivors.

---

## Confidence Model

**Dual model**: Evidence combination × Quality dimensions.

**Evidence combination** (noisy-OR):
- Multiple independent lines of evidence strengthen a claim
- BUT correlated evidence (same source cited multiple ways) is detected via provenance-path overlap and clustered — it counts as ~1 effective line, not N

**Quality dimensions** (weakest-link product):
- Source quality (peer-reviewed > blog > anonymous)
- Quote verification (Layer 1 passed)
- Logical consistency (no contradictions from verified claims)
- Precision (no overclaiming flags)

Any quality dimension at zero kills the total confidence. This prevents a well-sourced but logically incoherent claim from scoring high.

**Assessment claims** (editorial judgments like "the judge found this argument weak") are weighted at 0.3× as evidence — one person's opinion is useful context but not independent empirical evidence.

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Event-sourced JSONL store | Time-travel, trivial debugging, append-only collaboration |
| Provider-agnostic (config.yaml) | Switch models with zero code changes |
| Static HTML over interactive D3 | Force graphs become hairballs at 200+ nodes; hyperlinks are zero-training |
| Selective extraction (3-5 claims/chunk) | Cost control + quality (not ALL claims, just the most important) |
| Within-source + cross-source edges | Within-source captures argument chains; cross-source captures debate structure |
| Lower cosine threshold for cross-source (0.4 vs 0.6) | Opposing claims use different vocabulary but address the same topic |

---

## Limitations (Honest Unknowns)

1. **Confidence is not calibrated** — relative rankings, not calibrated probabilities
2. **Position extraction depends on source balance** — if all sources argue one side, that position dominates
3. **Assessment claims as evidence** — the 0.3× weight is a chosen parameter, not empirically validated
4. **No ground truth for crux detection** — we can't prove our crux list matches expert judgment
5. **The system cannot resolve debates** — it only makes disagreement structure visible

---

## References

| Paper | Finding | How We Use It |
|-------|---------|---------------|
| Kumar 2026 (arXiv:2605.02398) | 8/11 models fabricate at G3 threshold | Compliance detection guards all LLM calls |
| Chan & Darwiche 2004 (UAI) | Sensitivity ≈ variance × downstream influence | Crux formula: entropy × cascade |
| Howard 1966 (IEEE) | Value of resolving unknown = decision impact | Crux detection theoretical basis |
| Graphiti (arXiv:2501.13956) | Bi-temporal validity achieves 94.8% recall | Temporal model for claim validity |
| FPF (arXiv:2601.21116) | Confidence-gated supersession | Low-conf can't override high-conf |
| Wilson 1927 (JASA) | Score interval for binomial proportion | Proper small-N statistics |
| arXiv:2503.01747 | Don't use CLT for LLM evals | Why Wilson CI, not normal approximation |
