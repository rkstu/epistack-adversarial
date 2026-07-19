# Epistack-Adversarial

**Compliance-aware epistemic verification for AI-assisted knowledge bases.**

Takes existing debate materials (papers, transcripts, blog posts) and produces navigable static HTML discourse maps — showing positions, cruxes, empty chairs, and performed settling.

Submitted to the FLF Epistemic Case Study Competition, July 2026.

### Project Status

| Aspect | State |
|--------|-------|
| **Pipeline** | ✅ Complete — 15 modules, 4,000+ lines, 103 tests |
| **COVID case** | ✅ Complete — 230 claims, 1,242 edges, 3 positions, 10 cruxes, settling detected |
| **LHC case** | ✅ Complete — 53 claims, 232 edges, 5 positions (settled science) |
| **Eggs case** | ✅ Complete — 60 claims, 219 edges, 11 `frames_differently` edges |
| **HTML output** | ✅ 72 pages across 3 cases (pre-built, viewable immediately) |

**Total cost for all 3 cases: ~$1.** Total time: ~45 minutes of pipeline execution.

---

## Quick Start: View the Output

**No API keys needed.** Pre-built HTML sites are included:

```bash
# Open COVID-19 Origins discourse map (the flagship case)
open output/covid_origins/index.html

# Also available:
open output/lhc_black_holes/index.html   # Settled science case
open output/eggs_health/index.html        # Vague/open-ended case
```

Each site shows: positions, live cruxes (empirical claims whose resolution would most change the picture), performed settling detection, empty chairs (missing perspectives), and full claim provenance with source quotes.

---

## What This Does

Takes existing debate materials (papers, transcripts, judge decisions, blog posts) and produces a **structural map of disagreement** — not a summary, not a verdict, but a navigable picture of WHERE and WHY people disagree.

**COVID-19 Origins result** (5 sources, $0.30, 15 minutes):
- 3 positions: Zoonotic spillover (76 claims) vs Lab leak (62 claims) vs Methodology critique (6 claims)
- 10 empirical cruxes (top: "WIV gain-of-function in BSL-2 conditions")
- 9 verdicts detected as "performed settling" (declared winners without resolving underlying disputes)
- 5 empty chairs (perspectives absent from the evidence)

---

## Run It Yourself

Requires an OpenRouter API key (or Anthropic/OpenAI — config-driven, any provider works):

```bash
# Setup
git clone https://github.com/rkstu/epistack-adversarial
cd epistack-adversarial
uv sync

# Create .env with your API key
echo 'OPENROUTER_API_KEY=your-key-here' > .env

# Run the full pipeline (produces HTML site)
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
# → output/covid_origins/index.html

# Run other cases
uv run python run_pipeline.py lhc_black_holes --phase full --budget 1.0
uv run python run_pipeline.py eggs_health --phase full --budget 1.0
```

To change models/providers, edit `config.yaml`. The pipeline is provider-agnostic — one YAML change switches from OpenRouter to Anthropic to OpenAI.

---

## Add a Challenge (Collaboration Demo)

```bash
uv run python scripts/add_challenge.py covid_origins \
    --target clm_0037 \
    --body "NIH P3CO board classified WIV research as not gain-of-function" \
    --source-url "https://www.nih.gov/p3co" \
    --source-label "NIH P3CO Review Board"

# Re-run to see cascade effect
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
```

---

## Architecture

```
config.yaml → Sources → Fetch → Extraction (grounded quotes) → 4-Layer Verification
    → Event-Sourced Store → Relationship Detection → Confidence Model
    → Crux Detection → Discourse Mapping → Settling Detection → HTML Site
```

15 Python modules, 4,000+ lines, 103 tests. See [docs/PIPELINE.md](docs/PIPELINE.md) for full technical reference.

---

## Key Innovation

1. **Compliance-trap detection** (arXiv:2605.02398): Detects when AI is under pressure to fabricate, applies empirically-validated defenses
2. **`frames_differently` edge type**: Distinguishes "positions asking different questions" from "positions disagreeing on facts"
3. **Performed settling**: Detects when debates declared winners without resolving underlying cruxes
4. **Graph-based position detection**: Finds opposing positions via contradiction edges, not just embedding similarity

---

## Cost

| Case | Sources | Claims | Edges | Cost | Time |
|------|---------|--------|-------|------|------|
| COVID-19 | 5 | 230 | 1,242 | $0.30 | 15 min |
| LHC | 4 | 53 | 232 | $0.20 | 10 min |
| Eggs | 5 | 60 | 219 | $0.25 | 12 min |
| **Total** | **14** | **343** | **1,693** | **~$1** | **~37 min** |

---

## Documentation

| Document | What It Contains | When To Read |
|----------|-----------------|--------------|
| **This README** | Project status, quick start, how to run, cost table | First — orientation |
| **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)** | Epistemic approach (crux detection, settling, framework mismatches), research basis, design decisions, limitations. No code. | To understand WHY this approach |
| **[docs/PIPELINE.md](docs/PIPELINE.md)** | Every module explained, event schema, config reference, key design decisions table with rationale, acceptance criteria, edge progression debugging history, how to extend | To understand HOW it works technically |
| **[docs/SUBMISSION.md](docs/SUBMISSION.md)** | Competition entry: results → trust → architecture → scaling → generalization → unknowns | The formal submission |
| **[DEVELOPMENT.md](DEVELOPMENT.md)** | Complete build chronology (Day 0-16), every parameter decision with validation evidence, 13 changelog versions, review integration, debugging journey (14→1,242 edges) | To continue development or understand decision history |
| **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** | Original architecture plan with full schemas and algorithms — written before build, annotated with what changed | Historical reference |
| **[config.yaml](config.yaml)** | All runtime parameters with WHY comments | To tune or switch providers |

Every folder contains a `README.md` explaining its contents.

**Reading paths:**
- **Judge (see output)**: This README → `open output/covid_origins/index.html`
- **Understand approach**: docs/METHODOLOGY.md → docs/PIPELINE.md
- **Continue development**: DEVELOPMENT.md (full decision trail, Day 0-16) → docs/PIPELINE.md (current architecture) → `src/epistack/README.md` (module map) → source code
- **Run it yourself**: This README "Run It Yourself" section → config.yaml (model setup)
- **Add to this project**: docs/PIPELINE.md "How to Extend" section

---

**Author**: Rahul Kumar | **Paper**: arXiv:2605.02398 | **Competition**: FLF Epistemic Case Study
