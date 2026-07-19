# Epistack: Structural Illumination of Epistemic Disagreement

**FLF Epistemic Case Study Competition — Final Submission**
**Author**: Rahul Kumar
**Date**: July 2026
**Repo**: https://github.com/rkstu/epistack-adversarial

---

We processed 5 sources from the Rootclaim COVID origins debate ($100K bet, 15 hours of structured argument, 6 Bayesian analyses spanning 23 orders of magnitude) and found four things a careful reader wouldn't easily see on their own:

1. **The debate performed settling.** All 9 verdict claims declared winners while 46 dependency claims remain contested (confidence 0.3–0.7). The $100K bet format creates G3 compliance-forcing conditions (arXiv:2605.02398) — both debaters structurally cannot say "I don't know," meaning their expressed confidence is inflated regardless of argument quality.
2. **The 23-OOM Bayesian divergence traces to specific priors.** Weissman assigns P(lab leak) ≈ 1/200 (claim `clm_0168`, quote verified). Rootclaim evaluates 80% of Wuhan-origin pandemics as lab leaks (claim `clm_0159`, quote verified). That 100× gap in starting assumptions, before any evidence is weighed, is the largest single driver of their divergence — visible in the structured output but not in any existing narrative analysis.
3. **The top crux is empirical and traceable.** WIV conducting gain-of-function research in BSL-2 conditions (crux score 0.61) is the claim whose resolution would most cascade through the debate graph.
4. **Five perspectives are structurally absent.** Virological genomics, contact tracing, and lab safety whistleblowers — identified adversarially, not by assumption.

For comparison: a naive 23-minute Claude Code investigation on COVID origins produces a calibrated probability estimate and 192 source citations. Our system produces something structurally different — not "what's the answer?" but "where exactly do people diverge, why, and what would resolve it?" The output is a navigable map of disagreement structure, not a better summary.

The same pipeline diagnoses LHC black holes as settled (graph structure reveals why) and eggs & health as not a dispute at all (11 framework-mismatch edges show the sources are asking different questions). Three cases, three different epistemic structures, one pipeline. Total cost: **$1**. Total time: **45 minutes**.

---

## 1. See It

Open `output/covid_origins/index.html` in a browser — pre-built, no API key required.

**Representative slice — what a crux page shows:**

> **Claim**: "WIV was conducting gain-of-function research in BSL-2 conditions"
> **Crux score**: 0.61 (binary entropy 0.77 × cascade influence)
> **Confidence**: 0.23 (contested — exactly what makes it a crux)
> **Category**: empirical (not an assessment or verdict — the system excludes editorial judgments from crux scoring)
>
> **Source evidence** (quote verified ✓):
> - ACX: "WIV was irresponsibly doing it in BSL-2, ie medium security. The researchers weren't even required to wear masks."
> - Judge Will: "The major factors weighing against lab leak were the probability that WIV could carry out DEFUSE style research..."
> - Weissman: "P0(2019, LL) = ~1/200. This estimate is obviously very rough."
>
> **If resolved TRUE** → 12 downstream lab-leak claims strengthen
> **If resolved FALSE** → Lab-leak position loses strongest empirical anchor
>
> **Challenged by**: "NIH P3CO board classified WIV research as not gain-of-function"
> → After challenge: confidence drops, crux score stays high (more contested = more important to resolve)

The COVID site shows 3 positions (76 + 62 + 6 claims), 10 ranked cruxes, settling alerts on all 9 verdicts, 5 empty chairs, and full provenance for every claim.

---

## 2. Run It

```bash
# View output (no API key, 10 seconds):
git clone https://github.com/rkstu/epistack-adversarial
cd epistack-adversarial
open output/covid_origins/index.html

# Verify (no API key, 30 seconds):
uv sync --extra dev
uv run python scripts/verify.py   # 103 tests + output validation → exit 0

# Reproduce from scratch (~$0.30, ~15 min):
echo 'OPENROUTER_API_KEY=your-key' > .env
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
```

---

## 3. How It Works

```
sources.yaml → Fetch (web/PDF/YouTube/local)
    → Extraction (grounded quotes, 3-5 claims/chunk)
    → 4-Layer Verification (quote match → overclaiming → NLI → cross-provider)
    → events.jsonl (append-only, time-travel)
    → Relationship Detection (embed → cosine → batch classify → dedup)
    → Confidence Model (noisy-OR × quality product)
    → Crux Detection (binary entropy × cascade BFS)
    → Discourse Mapping (HDBSCAN + graph community detection)
    → Settling Detection (dependency chain + framework analysis)
    → Static HTML Site (Jinja2 + Mermaid)
```

15 modules, 4,000+ lines, 103 tests, provider-agnostic (one config change switches OpenRouter → Anthropic → OpenAI).

### Design Decisions (Why This Shape)

| Decision | Chose | Over | Because |
|----------|-------|------|---------|
| Crux scoring | Structural (entropy × cascade BFS) | LLM judgment | Deterministic, reproducible, grounded in sensitivity analysis (Chan & Darwiche 2004). LLM "what are the cruxes?" is non-reproducible and authority-dependent. |
| Position detection | HDBSCAN + graph community fallback | Pure LLM clustering | HDBSCAN finds semantic clusters; graph fallback catches what embedding similarity misses (lab-leak found via contradiction edges, not semantic proximity). |
| Framework mismatches | Separate edge type (`frames_differently`) | Forcing into `contradicts` | Eggs case proves this: observational mortality studies and mechanistic RCTs aren't disagreeing — they're asking different questions. Misclassifying this as contradiction misrepresents the structure. |
| Confidence model | Noisy-OR for evidence, product for quality | Single composite score | Independent evidence lines genuinely compound. But any quality failure (bad source, logical inconsistency) should kill confidence. Different aggregation for different meanings. |
| Assessment weighting | 0.3× as evidence | Full weight or excluded | "The judge found this argument weak" informs but isn't independent empirical evidence. One opinion ≠ one study. |
| Storage | Event-sourced JSONL | SQLite / in-memory | Time-travel debugging, trivial collaboration (merge JSONL files), append-only correctness. Anyone can inspect raw events. |
| Edge direction | Explicit "source=evidence, target=conclusion" | Free LLM choice | LLMs reverse direction ~30% of the time. Explicit convention + flip heuristic for verdicts corrects this measurably (14→344→916→1,242 edges as fixes accumulated). |

---

## 4. Why Trust It

### Fabrication Prevention

Every AI-assisted epistemic tool sends prompts to LLMs. If those prompts cross the G3 compliance threshold (arXiv:2605.02398, 67,221 evaluations, 11 models), the AI fabricates. Most production defaults do cross it.

Our defenses:
1. **Detect** compliance pressure in every prompt before sending (regex, $0)
2. **Defend** with M2 (+18.5pp) and M3 (+19.3pp) interventions validated on 5,110 evaluations
3. **Ground** every claim to a source quote — no quote, no entry. 230/230 active COVID claims have `quote_verified: true`
4. **Verify** in 4 layers — 121 verification flags fired across the COVID run, each dropping fabricated or overstated claims to 0.1 confidence

### What If a Source Deliberately Misleads?

Three structural defenses:
- **Mandatory quotes** — a claim not verbatim in the source text is rejected. Fabricated claims can't enter the store.
- **Cross-provider verification** — if the extraction model hallucinates a relationship, a different model family catches it (Layer 4).
- **Confidence-gated supersession** — a low-quality challenge cannot override a high-confidence established claim. Adversarial flooding doesn't work because new evidence must be *stronger* to override existing evidence (FPF, arXiv:2601.21116).

### Correlated Evidence

"15 claims supporting market origin" is not 15 independent evidence lines if they all reference Worobey 2022. The confidence model clusters evidence by provenance-path overlap (threshold 0.25) and applies noisy-OR across *clusters*, not individual claims. Correlated evidence gets counted once, not N times.

---

## 5. Three Cases, Three Diagnoses

### COVID-19 Origins (Contested) → Cruxes + Settling
- 230 claims, 1,242 edges, 3 positions, 10 cruxes, settling on all 9 verdicts
- **Structural diagnosis**: Clear positions exist. The verdict performed settling — declared a winner while 46 dependency claims remain contested and the verdict adjudicates between incompatible interpretive frameworks rather than resolving factual questions.
- **What makes this different from reading the sources**: The crux ranking shows WHICH specific claims matter most structurally. The settling detection shows WHERE verdicts outran evidence. Neither is visible from reading linearly.

### LHC Black Holes (Settled Science) → No Contested Cruxes
- 53 claims, 232 edges, 5 positions, 2 cruxes (both low-impact)
- **Structural diagnosis**: 215/232 edges are `supports`. The safety argument forms an unbroken dependency chain. No contested cruxes remain.
- **What makes this different**: The system correctly identifies "settled" from graph structure alone — without being told. The *absence* of contested cruxes IS the finding.

### Eggs & Health (Vague/Open-ended) → Framework Mismatch
- 60 claims, 219 edges, 5 positions, 4 cruxes, **11 `frames_differently` edges**
- **Structural diagnosis**: The disagreement isn't factual. Observational studies ask "what correlates with mortality?" RCTs ask "what causally drives LDL?" These aren't contradicting each other — they're asking different questions about the same phenomenon.
- **What makes this different**: No single load-bearing crux exists. The "dispute" dissolves once you separate the methodological frames. The correct resolution is agreeing which question matters for your context, not finding more evidence.

---

## 6. It Scales and Compounds

### More compute = better structural illumination

| Sources | Claims | Edges | Cruxes | Cost | Time |
|---------|--------|-------|--------|------|------|
| 1 | 14 | 0 | 0 | $0.008 | 2 min |
| 2 | 88 | 14 | 0 | $0.048 | 12 min |
| 5 | 230 | 1,242 | 10 | $0.30 | 15 min |
| 8 (projected) | ~350 | ~1,500 | ~15 | $0.50 | 25 min |

Denser graph = more cascade paths = better crux identification. Not a fixed-quality summary that hits a ceiling.

Not bottlenecked on any hand-designed human step. The only human input is selecting sources. Everything from extraction through HTML generation is automated. As base models improve, extraction quality and edge classification improve — the pipeline inherits model progress without code changes.

### Knowledge compounds

New evidence enters via `add_challenge.py` and cascades:
```
BEFORE: "WIV GoF in BSL-2" — crux score 0.61, confidence 0.23
CHALLENGE: "NIH P3CO board classified WIV research as not gain-of-function"
AFTER:  Confidence drops. Crux score stays HIGH — correctly, because a
        more-contested claim is MORE important to resolve.
```

The store is append-only (like git). Multiple researchers add claims independently; the system integrates them. Outputs are structured JSON events — another team can pick up `events.jsonl`, replay it, and build on it with different analysis tools.

---

## 7. What This Surfaces That's New

1. **Performed settling is detectable from graph structure.** A verdict exists + dependency claims remain contested + framework boundaries are crossed. This is computable, not a value judgment. Nobody else in the competition is detecting this.

2. **The debate format is itself compliance-forcing.** The $100K bet structurally prohibits "I don't know" — the same condition that causes 8/11 AI models to fabricate (arXiv:2605.02398). Both debaters' expressed confidence is structurally inflated regardless of argument quality. This connects AI safety research to the specific debate being analyzed.

3. **Framework mismatches are structurally distinct from factual disputes.** The eggs case demonstrates this: what looks like disagreement is two research traditions asking different questions. The correct response is "which question are you asking?" not "who's right?" This changes how we design systems for vague/open-ended topics.

4. **Correlated evidence is measurable from provenance structure.** "Independent evidence" requires independent provenance — not just different documents but different underlying data. This is computable from the graph without domain expertise. It directly addresses the "correlated evidence treated as independent" failure mode the competition identifies.

---

## 8. Honest Unknowns

1. **Whether confidence scores are calibrated** — we report relative rankings, not probabilities. When we say 0.23, that means "contested relative to this graph," not "23% chance of being true."
2. **Whether this beats a skilled human** — Scott Alexander spent months writing 20K words on COVID origins. Our system processes 5 sources in 15 minutes. Different trade-off: we're faster and more structured, but a domain expert reading the same sources may catch things the extraction misses.
3. **Whether the discourse map changes minds** — we have no reader study data.
4. **Whether M2/M3 defenses transfer to evaluative prompts** — validated on factual questions ("is this claim in the source?"), not on "evaluate this argument."
5. **Whether the findings would survive domain expert scrutiny** — verified with 4 automated layers, not with virologists.

---

## References

1. Kumar, R. (2026). arXiv:2605.02398 — Compliance-Induced Epistemic Collapse. 67,221 evaluations, 11 frontier models.
2. Chan & Darwiche (2004). Sensitivity Analysis in Bayesian Networks (UAI) — crux formula theoretical basis.
3. Howard (1966). Information Value Theory (IEEE) — value of resolving unknowns.
4. Graphiti, arXiv:2501.13956 — bi-temporal validity (94.8% DMR).
5. FPF, arXiv:2601.21116 — confidence-gated supersession.
6. Wilson (1927). Probable Inference (JASA) — CI methodology for small-N.

---

**Full documentation**: [docs/METHODOLOGY.md](METHODOLOGY.md) (non-technical approach) · [docs/PIPELINE.md](PIPELINE.md) (technical reference) · [DEVELOPMENT.md](../DEVELOPMENT.md) (full decision trail)
