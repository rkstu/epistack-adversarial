# Epistack-Adversarial

**Compliance-aware epistemic verification for AI-assisted knowledge bases.**

Takes existing debate materials (papers, transcripts, blog posts) and produces navigable static HTML discourse maps — showing positions, cruxes, empty chairs, and performed settling.

Submitted to the FLF Epistemic Case Study Competition, July 2026.

---

## What It Found

Applied to the Rootclaim COVID origins debate ($100K bet, 5 sources, 15 minutes):

1. **The debate performed settling.** All 9 verdict claims declared winners while 46 dependency claims remain contested (confidence 0.3–0.7). The $100K bet format structurally prohibits "I don't know" — both debaters' expressed confidence is inflated regardless of argument quality (arXiv:2605.02398).
2. **The 23-OOM Bayesian divergence traces to a single prior.** Weissman assigns P(lab leak) ≈ 1/200. Rootclaim assigns ~50% for Wuhan-origin pandemics. That 100× gap before any evidence is weighed accounts for most of the spread.
3. **The top crux is empirical and traceable.** WIV conducting gain-of-function in BSL-2 conditions (crux score 0.61) is the claim whose resolution would most change downstream conclusions.
4. **Five perspectives are structurally absent.** Virological genomics, contact tracing, and lab safety whistleblowers — identified adversarially, not by assumption.

The same pipeline identifies LHC black holes as settled (graph structure shows why) and eggs & health as a framework mismatch, not a dispute (11 `frames_differently` edges).

---

## Verify Without an API Key

```bash
git clone https://github.com/rkstu/epistack-adversarial
cd epistack-adversarial
uv sync
uv run python scripts/verify.py
```

This runs all 103 unit tests and validates the pre-built output. No API key needed. Exit 0 = everything passes.

---

## View the Output

Pre-built HTML sites are included — open directly in a browser:

```bash
open output/covid_origins/index.html    # Flagship: contested case
open output/lhc_black_holes/index.html  # Settled science case
open output/eggs_health/index.html      # Framework mismatch case
```

Each site shows positions, cruxes ranked by entropy × cascade influence, performed settling alerts, empty chairs, and full claim provenance with source quotes.

---

## Run It Yourself

Requires an API key from any provider (OpenRouter, Anthropic, or OpenAI — config-driven):

```bash
# Add your API key
echo 'OPENROUTER_API_KEY=your-key-here' > .env

# Run full pipeline → produces HTML site
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
# → output/covid_origins/index.html

# Other cases
uv run python run_pipeline.py lhc_black_holes --phase full --budget 1.0
uv run python run_pipeline.py eggs_health --phase full --budget 1.0
```

To change models or providers: edit `config.yaml`. One YAML change switches from OpenRouter to Anthropic to OpenAI — no code changes.

---

## Add a Challenge (Collaboration Demo)

```bash
uv run python scripts/add_challenge.py covid_origins \
    --target clm_0037 \
    --body "NIH P3CO board classified WIV research as not gain-of-function" \
    --source-url "https://www.nih.gov/p3co" \
    --source-label "NIH P3CO Review Board"

# Re-run to see cascade
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
```

New evidence enters the append-only store and cascades through all downstream confidence and crux scores — without modifying any existing claims.

---

## Results

| Case | Sources | Claims | Edges | Cost | Time | Pages |
|------|---------|--------|-------|------|------|-------|
| COVID-19 Origins | 5 | 230 | 1,242 | $0.30 | 15 min | 29 |
| LHC Black Holes | 4 | 53 | 232 | $0.20 | 10 min | 21 |
| Eggs & Health | 5 | 60 | 219 | $0.25 | 12 min | 22 |
| **Total** | **14** | **343** | **1,693** | **~$1** | **~37 min** | **72** |

---

## Architecture

```
config.yaml (single source of truth — models, thresholds, budget)
     │
sources.yaml → Fetch (web/PDF/YouTube/local)
     │
     ▼
Extraction (grounded quotes, 3-5 claims/chunk)
     │
4-Layer Verification:
  L1: Quote containment (free)
  L2: Overclaiming regex (free)
  L3: NLI entailment (~$0.01)
  L4: Cross-provider check (~$0.01, top 10% only)
     │
     ▼
events.jsonl (append-only, time-travel, supersession)
     │
     ├── Relationship Detection (embed → cosine → classify → dedup)
     ├── Confidence Model (noisy-OR × quality product)
     ├── Crux Detection (entropy × cascade BFS)
     ├── Discourse Mapping (HDBSCAN + graph community detection)
     ├── Settling Detection (dependency chain + framework analysis)
     └── HTML Site (Jinja2 + Mermaid CDN)
```

15 Python modules, 4,000+ lines, 103 tests. See full rendered diagrams: [Architecture](docs/diagrams/architecture.md) | [COVID Discourse](docs/diagrams/covid_discourse.md) | [Three Cases Compared](docs/diagrams/three_cases.md)

**Key innovations:**
- **Compliance-trap detection** (arXiv:2605.02398): Detects G3 pressure before every LLM call, applies M2/M3 defenses validated on 5,110 evaluations
- **`frames_differently` edge type**: Distinguishes framework mismatches from factual contradictions
- **Performed settling detection**: Detects debates that declared winners without resolving cruxes
- **Correlated evidence detection**: Prevents N citations of the same paper from counting as N independent lines

**Raw pipeline output**: See [data/sample/](data/sample/) for a committed trace showing the full input→output chain for one claim through all pipeline stages.

---

## Documentation

| Document | Contents | Read When |
|----------|----------|-----------|
| **This README** | What it found, how to run, verify, architecture | Start here |
| **[docs/SUBMISSION.md](docs/SUBMISSION.md)** | Formal competition entry — findings, trust, architecture, scaling, limitations | Full picture |
| **[docs/METHODOLOGY.md](docs/METHODOLOGY.md)** | Epistemic approach: crux formula, settling, framework mismatches, research basis. No code. | Why this approach |
| **[docs/PIPELINE.md](docs/PIPELINE.md)** | Every module, config reference, design decision rationale, how to extend | How it works |
| **[DEVELOPMENT.md](DEVELOPMENT.md)** | Full build chronology, parameter tuning decisions, debugging history (14→1,242 edges) | Continue development |
| **[config.yaml](config.yaml)** | All runtime parameters with WHY comments | Tune or switch providers |

Every folder has a `README.md` explaining its purpose.

---

## Folder Structure

```
epistack-adversarial/
├── README.md                  # This file — start here
├── run_pipeline.py            # Main orchestrator — one command produces full HTML site
├── config.yaml                # All parameters (models, thresholds, budget)
├── pyproject.toml             # Dependencies (managed with uv)
│
├── src/epistack/              # 15-module Python library (each has docstring)
├── examples/                  # Source registries (sources.yaml per case)
├── output/                    # Pre-built HTML output (no API key to view)
├── data/sample/               # Committed pipeline trace — full input→output chain
├── tests/                     # 103 tests — all pass without API keys
├── scripts/                   # verify.py, smoke_test.py, add_challenge.py
├── docs/                      # SUBMISSION.md, METHODOLOGY.md, PIPELINE.md
│   └── diagrams/             # Mermaid diagrams (rendered by GitHub)
├── static/                    # Shared CSS for HTML output
├── templates/                 # Reserved for future template extraction
└── archive/                   # v0 prototype (historical reference only)
```

---

**Author**: Rahul Kumar | **Paper**: arXiv:2605.02398 | **Competition**: FLF Epistemic Case Study
