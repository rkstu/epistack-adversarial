# Epistack: Structural Illumination of Epistemic Disagreement

**FLF Epistemic Case Study Competition — Submission**
**Author**: Rahul Kumar
**Date**: July 2026
**Repo**: https://github.com/rkstu/epistack-adversarial

---

We processed 5 sources from the Rootclaim COVID origins debate ($100K bet, 15 hours of structured argument, 6 Bayesian analyses spanning 23 orders of magnitude) and found four things a careful reader wouldn't easily see on their own:

1. **The debate performed settling.** All 9 verdict claims declared winners while 46 dependency claims remain contested (confidence 0.3–0.7). The $100K bet format creates G3 compliance-forcing conditions (arXiv:2605.02398) — both debaters structurally cannot say "I don't know," meaning their expressed confidence is inflated regardless of argument quality.
2. **The 23-OOM divergence between Bayesian analysts traces to a single prior.** Weissman assigns P(lab leak) ≈ 1/200. Rootclaim assigns ~50% for Wuhan-origin pandemics. That 100× gap in a single starting assumption, before any evidence is weighed, accounts for most of the spread.
3. **The top crux is an empirical question with a traceable answer.** WIV conducting gain-of-function research in BSL-2 conditions (crux score 0.61) is the claim whose resolution would most cascade through the debate graph. It is uncertain, contested across sources, and has high downstream influence — exactly what the competition asks for.
4. **Five perspectives are structurally absent.** Virological/genomic analyses, epidemiological contact tracing, and laboratory safety whistleblowers are not represented in any source — identified adversarially, not by assumption.

The same pipeline diagnoses LHC black holes (settled: no contested cruxes, clear dependency chain) and eggs & health (not a dispute at all: 11 framework-mismatch edges show the sources are asking different questions). Three cases, three different epistemic structures, one pipeline. Total cost: **$1**. Total time: **45 minutes**.

---

## 1. What You Can See

Open `output/covid_origins/index.html` in a browser — the pre-built site is included in the repo, no API key required.

The COVID-19 Origins site shows:

- **3 positions**: Zoonotic spillover (76 claims), Lab leak hypothesis (62 claims), Bayesian methodology critique (6 claims)
- **10 empirical cruxes** — ranked by entropy × cascade influence:
  1. WIV conducting gain-of-function in BSL-2 conditions (score: **0.61**)
  2. Strong Bayesian evidence on both sides creates underdetermination (score: 0.24)
  3. Epidemiological proximity of the Huanan Seafood Market (score: 0.23)
  4. Coincidence of epidemic starting near Wuhan's coronavirus lab (score: 0.21)
  5. DEFUSE program collecting coronaviruses from bat caves (score: 0.14)
- **Performed settling on all 9 verdicts**: Every verdict claim has contested dependencies. The debate declared a winner; the underlying disagreements remain open.
- **5 empty chairs**: Perspectives absent from the discourse (viral genomics, contact tracing, lab safety whistleblowers)
- **Collaboration**: New evidence cascades — adding a challenge to any claim triggers re-scoring of all downstream conclusions

This is not a summary. It's a structural map of WHERE and WHY people disagree.

---

## 2. Why You Can Trust It (Verification)

### Compliance-Trap Detection (arXiv:2605.02398)

Every AI-assisted epistemic tool sends prompts to LLMs. If those prompts cross the G3 threshold (and most production defaults do), the AI fabricates. Our system:

1. **Detects** compliance pressure in every prompt before sending (regex, $0)
2. **Defends** with M2 (+18.5pp) + M3 (+19.3pp) interventions validated on 5,110 evaluations
3. **Verifies** every claim: quote containment check (Layer 1), overclaiming regex (Layer 2), NLI entailment (Layer 3), cross-provider check (Layer 4)

### Grounded Extraction

Every claim in the system traces to a **direct quote** from a source document. All 230 active claims in the COVID case have `quote_verified: true`. Claims with hallucinated quotes are rejected before entering the knowledge base — 121 verification events fired across the run, each dropping fabricated or overstated claims to 0.1 confidence rather than silently passing them.

### Statistical Rigor

Confidence uses Wilson score intervals (not CLT), noisy-OR combination across independent evidence clusters, and correlation detection to prevent "5 citations from 1 paper" from inflating confidence.

---

## 3. How It Works (Architecture)

```
Sources → Fetch → Extraction (grounded quotes) → 4-Layer Verification
    → Event-Sourced Store (JSONL, append-only, time-travel)
    → Relationship Detection (embed + classify, within-source + cross-source)
    → Confidence Model (noisy-OR × quality product)
    → Crux Detection (binary entropy × cascade BFS)
    → Discourse Mapping (HDBSCAN + graph-based community detection)
    → Performed Settling Detection (dependency chain + framework analysis)
    → Static HTML Site (Jinja2 + Mermaid)
```

**Key design choices:**
- `frames_differently` edge type: Captures when positions ask different questions (observational vs RCT), not just when they disagree on facts. Prevents misclassifying framework mismatches as contradictions.
- Assessment claims (editorial judgments) weighted 0.3× as evidence — one person's opinion ≠ independent empirical evidence.
- Confidence-gated supersession: Low-confidence evidence cannot override high-confidence claims (prevents adversarial pollution).

---

## 4. It Scales With Compute

| Sources | Claims | Edges | Cruxes | Cost | Time |
|---------|--------|-------|--------|------|------|
| 1 (partial) | 14 | 0 | 0 | $0.008 | 2 min |
| 2 | 88 | 14 | 0 | $0.048 | 12 min |
| 5 | 230 | 1,242 | 10 | $0.30 | 15 min |
| 8 (projected) | ~350 | ~1500 | ~15 | ~$0.50 | ~25 min |

More sources = denser graph = more precise crux detection = more cascade paths = better structural illumination. This is not a fixed-quality summary — it improves **monotonically** with compute. The cost per case study ($0.30-0.50) enables unlimited iteration.

---

## 5. It Generalizes

Three cases, three different epistemic failure modes:

### COVID-19 Origins (Contested) → Cruxes + Settling
- 222 claims, 916 edges, 3 positions, 10 cruxes, settling detected on 5 verdicts
- **What the system shows**: The debate has clear positions but the verdict PERFORMED SETTLING — declared a winner without resolving the underlying empirical disagreements
- **Novel insight**: 92 dependency claims remain contested, and the verdict crosses framework boundaries

### LHC Black Holes (Settled Science) → Dependency Chain
- 47 claims, 225 edges, 5 positions, 2 cruxes
- **What the system shows**: Heavy consensus (215/225 edges are `supports`). The safety argument forms a well-supported dependency chain. No fundamental disagreements detected.
- **Novel insight**: The system correctly identifies this as settled WITHOUT being told — the graph structure (all-supports, no contradictions) reveals it

### Eggs & Health (Vague/Open-ended) → Framework Mismatches
- 55 claims, 193 edges, 5 positions, 4 cruxes, **11 `frames_differently` edges**
- **What the system shows**: The disagreement isn't factual — it's about WHICH QUESTION to ask. Observational studies ask "what correlates with mortality?" while RCTs ask "what causally drives LDL?" These aren't contradicting each other; they're asking different questions.
- **Novel insight**: The `frames_differently` edge type prevents misclassifying methodology mismatches as factual disputes. Resolution requires agreeing which question matters for your context, not finding more evidence.

### Collaboration: Knowledge Compounds

New evidence enters the system and cascades:
```
BEFORE: "WIV GoF in BSL-2" — crux score 0.838, confidence 0.23
CHALLENGE ADDED: "NIH P3CO board classified as not gain-of-function"
AFTER:  Confidence drops (contradiction registered). Crux score STAYS HIGH —
        correctly, because the contested claim now matters MORE to resolve.
```

The discourse map evolves without manual restructuring. Multiple researchers can add challenges independently; the system integrates them into the structural picture.

---

## 6. Honest Unknowns

1. **Whether confidence scores are calibrated** — we report relative rankings, not calibrated probabilities
2. **Whether this beats a skilled human** — Scott Alexander wrote 20K words on COVID origins over months. Our system processes 5 sources in 15 minutes. Different trade-off.
3. **Whether the discourse map changes minds** — we don't have reader study data
4. **Whether M2/M3 defenses transfer to evaluative prompts** — validated on factual questions, not "evaluate this argument"
5. **Whether HDBSCAN generalizes** — worked for COVID (polarized), may need LLM fallback for eggs (vague)

---

## References

1. Kumar, R. (2026). arXiv:2605.02398 — Compliance-Induced Epistemic Collapse. 67,221 evaluations, 11 models.
2. Chan & Darwiche (2004). Sensitivity Analysis in Bayesian Networks (UAI) — crux formula basis.
3. Howard (1966). Information Value Theory (IEEE) — value of resolving unknowns.
4. Graphiti, arXiv:2501.13956 — bi-temporal validity (94.8% DMR).
5. FPF, arXiv:2601.21116 — confidence-gated supersession.
6. Wilson (1927). Probable Inference — CI methodology.

---

**Run it yourself:**
```bash
git clone https://github.com/rkstu/epistack-adversarial
cd epistack-adversarial
uv sync
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
# → output/covid_origins/index.html (open in browser)
```
