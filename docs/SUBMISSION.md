# Epistack: Mapping Where Disagreements Come From

**FLF Epistemic Case Study Competition — Final Submission**
**Author**: Rahul Kumar
**Date**: July 2026
**Repo**: [github.com/rkstu/epistack-adversarial](https://github.com/rkstu/epistack-adversarial)

---

Epistack is a tool for mapping disagreements. Instead of asking an AI "who is right?", it asks a more useful question: where exactly do the arguments diverge, which unresolved claims matter most, and what evidence would change the picture?

I tested it on three cases. The system produced three different diagnoses:

- **COVID origins** is a real dispute with unresolved claims that matter a lot, and conclusions that went further than the evidence.
- **LHC black holes** is settled — the system identifies this from graph structure, not from a topic label.
- **Eggs and health** is mostly a framework mismatch — different studies are answering different questions, not disagreeing on facts.

Total cost for all three: **$1** (API calls via OpenRouter). Total compute time: **45 minutes** (wall-clock, after source selection). 103 tests, 72 HTML pages. The pipeline runs automatically once sources are chosen.

---

## What I Found (COVID Case)

The main finding is that the Rootclaim debate's verdicts look more settled than the underlying evidence warrants. Specifically:

1. **All 9 verdict claims pick winners, but their dependency claims remain contested** (confidence between 0.3 and 0.7). The most prominent verdict has 46 contested dependencies; the worst case has 92. The debate declared a resolution; the empirical disagreements underneath are still open. I call this "performed settling": the debate looks resolved on the surface, while the underlying factual questions are still open. It is detectable from graph structure: verdict exists + dependencies are contested + the verdict crosses framework boundaries.

2. **The largest driver of the divergence between analysts is a single starting assumption.** Weissman's Bayesian analysis assigns a prior of P(lab leak) ≈ 1/200. Rootclaim evaluates 80% of pandemics that first appear in Wuhan as lab leaks. That gap, roughly two orders of magnitude in the prior alone, propagates through everything downstream. Both claims are in the system with verified source quotes (inspectable in the HTML output).

3. **The most important unresolved claim is empirical.** "WIV was conducting gain-of-function research in BSL-2 conditions" has the highest crux score (0.61 on a 0-to-1 scale, where 1.0 would mean maximum uncertainty with maximum downstream impact). It scores high because it is genuinely contested (confidence 0.23) and many other claims depend on it. Resolving it would change the most conclusions.

4. **Several relevant perspectives are absent from all sources** — including virological genomics, epidemiological contact tracing, and laboratory safety whistleblowers. Identified by asking "what viewpoints are conspicuously missing?" rather than assuming.

One observation about the debate format: when $100K is on the line, both sides are rewarded for confident answers, not for saying "I don't know." I studied a structurally similar pressure in AI systems (arXiv:2605.02398, 67,221 evaluations): when a prompt format penalizes uncertainty, 8/11 models fabricate rather than admit ignorance. The human case is not identical, but the incentive shape is the same. Both debaters' expressed confidence should be read with that structural pressure in mind.

---

## See It While Reading

Optional but recommended: open `output/covid_origins/index.html` in a browser while reading this submission. The site is pre-built, so you do not need an API key. It lets you check the claims instead of taking my word for them. You can click through the COVID case, inspect the ranked cruxes, and see the source quote behind each extracted claim.

A good page to start with is the top crux:

> **Claim**: "WIV was conducting gain-of-function research in BSL-2 conditions"
> **Why it matters**: many downstream lab-leak claims depend on it
> **Current confidence**: 0.23, meaning the sources contest it heavily
> **What happens if it is resolved**:
> - If true, 12 downstream lab-leak claims strengthen
> - If false, the lab-leak position loses one of its strongest empirical anchors

The point of the page is not to tell you who is right. It shows why this claim matters, which sources discuss it, and what would change if the claim were resolved.

The full COVID site includes 3 positions, 10 ranked cruxes, settling alerts on all 9 verdicts, 5 missing perspectives, and source provenance for every claim.

---

## Three Cases Show It Generalizes

### COVID-19 Origins — contested dispute
230 claims, 1,242 edges, 3 positions, 10 cruxes. The system finds real unresolved disagreements and shows where the conclusions went further than the evidence.

### LHC Black Holes — settled science
53 claims, 232 edges, 5 positions. 215 of 232 edges are `supports`. The safety argument forms an unbroken dependency chain. No contested cruxes remain. The system identifies this as settled from graph structure, not from a topic label.

### Eggs & Health — framework mismatch
60 claims, 219 edges, 11 `frames_differently` edges. Observational studies ask "what correlates with mortality?" while RCTs ask "what causally drives LDL?" They aren't contradicting each other — they're asking different questions. No single load-bearing crux exists. The "dispute" dissolves once you separate the frames.

---

## Run It

```bash
# View output (no API key, 10 seconds):
git clone https://github.com/rkstu/epistack-adversarial
cd epistack-adversarial
open output/covid_origins/index.html

# Verify tests pass (no API key, 30 seconds):
uv sync --extra dev
uv run python scripts/verify.py   # 103 tests + output validation → exit 0

# Reproduce from scratch (~$0.30 per case, ~15 min):
echo 'OPENROUTER_API_KEY=your-key' > .env
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
```

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`). The `$1` figure in the intro is the total across all 3 cases. Each case costs about $0.20–0.30.

---

## How It Works

The pipeline extracts claims from sources, verifies each one against its source quote, detects relationships between claims, and then finds the claims whose resolution would change the most conclusions.

```
sources.yaml → Fetch (web/PDF/YouTube/local)
    → Extract claims (with mandatory source quotes)
    → Verify (4 layers: quote match → overclaiming → entailment → cross-provider)
    → Store (append-only event log)
    → Detect relationships (embed → cosine similarity → classify edge type)
    → Score confidence (independent evidence compounds; quality failures sharply reduce it)
    → Find cruxes (uncertainty × downstream impact)
    → Map positions (clustering + graph community detection)
    → Detect settling (verdict depends on contested claims?)
    → Generate HTML site
```

15 modules, 4,000+ lines, 103 tests. Provider-agnostic — one config change switches between OpenRouter, Anthropic, and OpenAI.

### Key Design Choices

| Decision | Choice | Why |
|----------|--------------|-----|
| How to find cruxes | Uncertainty × downstream impact (structural formula) | Reproducible. A claim that's uncertain AND consequential is more important than one that's just uncertain. Based on sensitivity analysis theory (Chan & Darwiche 2004). |
| How to handle "different questions" | Separate edge type (`frames_differently`) | The eggs case shows why this matters: calling a framework mismatch a "contradiction" misrepresents the debate. |
| How to count evidence | Independent lines compound; correlated evidence clusters first | Five citations of one paper shouldn't count five times. The system clusters by provenance overlap before combining. |
| How to prevent fabrication | Check prompt for compliance pressure before sending | My research (arXiv:2605.02398) shows models fabricate above a specific threshold. The system detects and defends before it happens. |

Full design rationale with all 7 decisions: [docs/PIPELINE.md](PIPELINE.md)

---

## Why Trust It

The main failure mode for any AI-assisted epistemic tool is hallucinated or overstated claims. The system prevents that in four ways:

1. **Every claim must have a source quote.** If the AI extracts a claim but can't point to where in the source text it comes from, the claim is rejected. 230/230 active COVID claims pass this check.

2. **Obvious overclaiming is caught cheaply before model-based verification.** Phrases like "proves conclusively" or "irrefutably demonstrates" trigger flags via regex. This is a fast, free ($0) first pass — not the core defense, but it catches the easy cases immediately.

3. **Entailment is verified by a second model.** "Does the quote actually support the claim?" catches cases where the AI overstates what the source says (e.g., upgrading "may contribute" to "causes").

4. **Cross-provider checks catch correlated blind spots.** A different model family verifies the highest-stakes claims. 121 verification flags fired across the COVID run (out of 238 initially extracted claims). Flagged claims were not deleted; their confidence was reduced to 0.1, keeping them visible but marked as unreliable. The 230 active claims that remain all passed the quote-verification check; the flags came from entailment and cross-provider layers catching overstatement.

---

## It Scales

| Sources | Claims | Edges | Cruxes | Cost | Time |
|---------|--------|-------|--------|------|------|
| 1 | 14 | 0 | 0 | $0.008 | 2 min |
| 2 | 88 | 14 | 0 | $0.05 | 12 min |
| 5 | 230 | 1,242 | 10 | $0.30 | 15 min |

More sources produce a denser disagreement map. More connections between claims means the crux scores become more stable and informative. I have not tested beyond 8 sources. I expect denser graphs continue to improve crux detection, but have not verified this at larger scale.

The main human judgment is source selection and metadata annotation (each source gets credibility signals in `sources.yaml`). Everything after that is automated. As extraction models improve, the pipeline gets better without code changes.

**New evidence can be added later**: `add_challenge.py` adds counter-evidence that cascades through confidence and crux scores. The store is an append-only event log. Multiple researchers can add claims independently; the system integrates them without manual restructuring. Another researcher could take the `events.jsonl` from this COVID analysis, add sources published in 2027, and the crux scores would update automatically without rerunning the full pipeline from scratch. (New evidence must be stronger than what it challenges to override it, so low-quality additions don't overwrite well-sourced claims.)

---

## What I Think Is Most Novel

1. **Performed settling as a detectable property.** Debates can declare winners without resolving underlying evidence. This is computable from graph structure: verdict exists + dependency claims remain contested + framework boundaries crossed. I think this is the most original part of the submission.

2. **Connecting compliance research to the specific debate.** The $100K bet creates a similar structural pressure to the conditions that cause AI fabrication in controlled experiments. This connects AI safety research to the debate being analyzed — it's not just about AI, it's about the debate format itself.

3. **Framework mismatches as a separate structural category.** What looks like disagreement can be two traditions asking different questions. The correct response is "which question are you asking?" not "who's right?"

4. **Correlated evidence detection from provenance.** "Independent evidence" requires independent provenance. This is computable from the graph and directly addresses the "correlated evidence treated as independent" failure mode.

---

## Honest Unknowns

1. **Whether confidence scores are calibrated** — I report relative rankings. When I say 0.23, that means "contested relative to this graph," not "23% chance of being true."
2. **Whether this beats manual analysis** — the system processes 5 sources in 15 minutes of compute. A domain expert working manually may catch things that automated extraction misses. The trade-off is speed and structure vs depth on any single source.
3. **Whether the discourse map changes minds** — no reader study data.
4. **Whether defenses transfer to evaluative prompts** — validated on "is this claim in the source?" questions, not "evaluate this argument."
5. **Whether findings survive domain expert scrutiny** — verified with 4 automated layers, not with virologists.

---

## References

1. Kumar, R. (2026). [The Compliance Trap: How Structural Constraints Degrade Frontier AI Metacognition Under Adversarial Pressure](https://arxiv.org/abs/2605.02398). 67,221 evaluations, 11 frontier models.
2. Chan & Darwiche (2004). Sensitivity Analysis in Bayesian Networks (UAI).
3. Howard (1966). Information Value Theory (IEEE).
4. Graphiti, [arXiv:2501.13956](https://arxiv.org/abs/2501.13956). Bi-temporal validity.
5. FPF, [arXiv:2601.21116](https://arxiv.org/abs/2601.21116). Confidence-gated supersession.
6. Wilson (1927). Probable Inference (JASA).

---

**Full documentation on GitHub**: [docs/METHODOLOGY.md](https://github.com/rkstu/epistack-adversarial/blob/main/docs/METHODOLOGY.md) (epistemic approach, no code) · [docs/PIPELINE.md](https://github.com/rkstu/epistack-adversarial/blob/main/docs/PIPELINE.md) (technical reference, all modules) · [DEVELOPMENT.md](https://github.com/rkstu/epistack-adversarial/blob/main/DEVELOPMENT.md) (full decision trail, Day 0–16)
