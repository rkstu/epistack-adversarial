<!-- FOR AI AGENTS/DEVELOPERS: This is the complete decision trail.
     Read this to understand WHY the system is built this way, not just WHAT it does.
     Contains: parameter tuning rationale, debugging history (14→916 edges), 
     model selection benchmarks, 7 integrated review rounds, acceptance criteria validation,
     and the full build chronology (Day 0 through Day 16).
     For the public technical reference, see docs/PIPELINE.md.
     For non-technical understanding, see docs/METHODOLOGY.md. -->

# Epistack — Development Log

**Competition**: FLF Epistemic Case Study Competition ($200K pool)
**Deadline**: July 19, 2026
**Builder**: Rahul Kumar (solo)
**Started**: June 27, 2026
**Days remaining**: 10 (as of July 9)
**Current status**: Day 14 — **ALL 3 CASE STUDIES PRODUCE OUTPUT.** COVID (222 claims, 30 files), LHC (47 claims, 22 files), Eggs (55 claims, 23 files). 75 HTML pages total across 3 cases. Professional CSS + Mermaid. 103 tests. ~$1 total cost. SUBMISSION.md skeleton written.

> This file tracks all implementation progress. Updated after every significant change.
> For architecture/algorithms, see `IMPLEMENTATION_PLAN.md`.
> For project context/strategy, see `PROJECT_CONTEXT.md`.

---

## Architecture Overview

```
config.yaml (single source of truth — models, thresholds, budget)
     │
     ▼
SOURCE URLs ──→ FETCH (trafilatura/pymupdf/yt-api)
                    │
                    ▼
              SOURCE TEXT ──→ EXTRACTION (GPT-4.1-mini via OpenRouter)
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
                         (HDBSCAN + positions + empty chairs + settling)
                                 │
                                 ▼
                        STATIC HTML SITE
                        (Jinja2 + Mermaid)
```

**Provider-agnostic**: All LLM calls route through `config.py` → `llm.py`. To switch providers, edit `config.yaml` only. Zero code changes needed.

**Model decision**: GPT-4.1-mini (extraction/confirmation) + GPT-4.1-nano (batch tasks). 2.3× faster than DeepSeek V4 Pro with better edge direction compliance. $0.23/case for 5 sources. Config-driven — one YAML change to switch.

---

## Current State (What's Built & Working)

```
src/epistack/
├── __init__.py              ✅ v0.3.3
├── config.py                ✅ Single source of truth — providers, models, all params
├── compliance_detector.py   ✅ G3 diagnostic + M2/M3 defenses (from research)
├── scoring.py               ✅ Wilson CI + cross-model + source quality (stripped)
├── llm.py                   ✅ Provider-agnostic client (OpenRouter/Anthropic/OpenAI/Nebius)
├── store.py                 ✅ Event-sourced JSONL (append, replay, time-travel, supersession)
├── fetch.py                 ✅ URL → text (blogs, PDFs, YouTube, local files)
├── extraction.py            ✅ Grounded claims with mandatory quotes + Layer 1-2 verification
├── verification.py          ✅ Layers 3-4 (NLI entailment + cross-provider)
├── relationships.py         ✅ Embed → cosine → dedup → classify → confirm contradictions
├── confidence.py            ✅ Dual model (noisy-OR × quality product) + assessment weighting
├── crux_detection.py        ✅ Binary entropy × cascade BFS
├── discourse.py             ✅ HDBSCAN + LLM fallback + position labeling + disagreement classification
├── settling.py              ✅ Performed settling (Type 1: unresolved cruxes + Type 2: framework adjudication)
├── generate_site.py         ✅ Jinja2 + inline templates (index + positions + cruxes)
└── cli.py                   — Removed (use run_pipeline.py directly)

config.yaml                  ✅ Model assignments, thresholds, budget caps (with WHY comments)
run_pipeline.py              ✅ Full orchestrator: --phase full produces complete HTML site
scripts/smoke_test.py        ✅ Integration test (real data, real API)
```

**Tests**: 103 passing, 1.89s
**Latest output (v0.3.4)**: 5 sources → 222 claims, 916+ edges, 3 positions, 10 cruxes, 5 empty chairs, settling on 5 verdicts. **15-file HTML site** with external CSS + Mermaid diagram. `run_pipeline.py --phase full` produces everything end-to-end in ~15 min for $0.30.

---

## Provider & Model Setup

**Active provider**: OpenRouter (using `OPENROUTER_API_KEY` from `.env`)
**Speed-optimized**: GPT-4.1-mini (3s/call, quality) + GPT-4.1-nano (3s/call, cheapest)
**Previous**: DeepSeek V4 Pro (7s/call) — switched Day 10 for 2.3× speed improvement

| Pipeline Stage | Model | Provider | Cost |
|---|---|---|---|
| Extraction | `openai/gpt-4.1-mini` | OpenRouter | $0.40/$1.60 per M tokens |
| Verification NLI | `openai/gpt-4.1-nano` | OpenRouter | $0.10/$0.40 per M tokens |
| Verification Cross | `openai/gpt-4.1-nano` | OpenRouter | $0.10/$0.40 per M tokens |
| Relationship Batch | `openai/gpt-4.1-nano` | OpenRouter | $0.10/$0.40 per M tokens |
| Relationship Confirm | `openai/gpt-4.1-mini` | OpenRouter | $0.40/$1.60 per M tokens |
| Discourse Crux | `openai/gpt-4.1-mini` | OpenRouter | $0.40/$1.60 per M tokens |
| Discourse Empty | `openai/gpt-4.1-mini` | OpenRouter | $0.40/$1.60 per M tokens |
| Embedding | `text-embedding-3-small` | OpenAI | $0.02/$0 per M tokens |

**To switch to production (Anthropic direct)**: Change `config.yaml` model assignments to `claude-sonnet`, `claude-haiku`. No code changes.

**Budget cap**: $5.00 per dev session (raises `BudgetExceeded`). Set `budget.dev_budget: 20.0` for production.

---

## Validated Results (Latest Full Run — Day 10, All Fixes Applied)

```
Sources: ACX post + Judge Will + Judge Eric + Bayesian Analysis + Rootclaim Response (5)
Model:   openai/gpt-4.1-mini (extraction/confirm) + openai/gpt-4.1-nano (batch)
Claims:  222 extracted (113 empirical, 75 assessment, 36 methodological — assessments excluded from crux scoring)
Edges:   916 (685 supports, 183 contradicts, 23 qualifies, 18 depends_on, 6 frames_differently, 1 supersedes)
Ratio:   4.13 edges/claim (very dense graph)
Cruxes:  Top score 1.128 — EMPIRICAL claims only (verdicts/assessments excluded)
Settling: DETECTED on 5 of 9 verdicts (92 contested deps + framework adjudication)
Empty Chairs: 5 perspectives identified as missing
Positions: 3 (Bayesian methodology + Zoonotic spillover + Lab leak hypothesis)
Cost:    ~$0.30 total (~15 min wall-clock)

Top Cruxes (empirical evidence that would resolve the debate):
  1.128 | WIV was conducting gain-of-function research in BSL-2 conditions
  0.434 | Strong Bayesian evidence on BOTH sides creates underdetermination
  0.350 | Epidemiological proximity of the Huanan Seafood Market
  0.332 | DEFUSE program involved collecting coronaviruses from bat caves + GoF
  0.327 | Earliest 40 cases included ~half with wet market connection

Settling Detection:
  ⚠️ 5 verdicts have performed settling
  ⚠️ 92 contested dependencies (confidence 0.3-0.7)
  ⚠️ Adjudicates between incompatible frameworks
  → Type: [unresolved_cruxes, framework_adjudication] | Severity: 0.50

Empty Chairs:
  - Virological/genomic analyses (viral evolution, mutation patterns)
  - Epidemiological contact tracing and early case cluster analysis
  - Laboratory safety experts and whistleblowers from WIV
```

**All 5 acceptance criteria PASS.**
This proves the core thesis: the debate declared a winner but cruxes remain open,
AND the system identifies what evidence would actually resolve the disagreement.

---

## Build Plan

### Day 0-1 (June 27): Foundation ✅

- [x] `uv` setup + lockfile (70 packages, deterministic)
- [x] All deps verified (hdbscan, jinja2, trafilatura, anthropic, structlog)
- [x] YouTube transcript API verified (2855 segments from Rootclaim debate)
- [x] Archive v0.1 prototype → `archive/v0_prototype/`
- [x] `config.py` — single source of truth for all configuration
- [x] `llm.py` — provider-agnostic client with retry, cost tracking, budget cap
- [x] `store.py` — event-sourced JSONL (append, replay, time-travel, supersession, bi-temporal)
- [x] `extraction.py` — grounded extraction with quotes, Layer 1-2, claim categories
- [x] Tests: 59 passing in 0.10s

### Day 2 (June 28): Fetch + Real Data ✅

- [x] `fetch.py` — multi-format fetcher (blog/PDF/YouTube/local)
- [x] `run_pipeline.py` — incremental orchestrator with `--phase`, `--budget`, `--max-sources`
- [x] `config.yaml` — user-editable config (models, thresholds, budget)
- [x] OpenRouter integration (DeepSeek V4 Pro as Sonnet-equivalent)
- [x] End-to-end smoke test: ACX post → 14 claims → events.jsonl ($0.008)
- [x] Budget cap, .env loading, selective prompts, claim categories all working

### Day 3-4 (June 29-30): Relationships + Confidence ✅

- [x] **`relationships.py`**
  - Batch embed all claims (OpenAI text-embedding-3-small)
  - **Persist embeddings** as `data/{case}/embeddings.npz` — reused by discourse.py
  - Cosine similarity filter (>0.6, different positions only)
  - Batch classification via `relationship_batch` model (15 pairs/call)
  - Edge types: supports, contradicts, depends_on, qualifies, supersedes, frames_differently
  - Confirm `contradicts` edges via `relationship_confirm` model
  - **Prompt design session** (1-2 hrs): explicit `frames_differently` examples + synthetic test pairs
  - **Two-stage deduplication**:
    - >0.92 similarity → auto-merge (emit `claim.reference_added`)
    - 0.80-0.92 → LLM check "Are these the same claim?"
    - <0.80 → keep both
- [x] **`confidence.py`**
  - Provenance-path LCA → detect correlated evidence
  - Single-linkage clustering (conservative over-clusters)
  - Noisy-OR across independent clusters (evidence combination)
  - Quality dimensions: weakest-link product (source_quality, quote_verified, logical_consistency, precision)
  - Final = evidence_score × dimension_score
  - Assessment claims as evidence get strength × 0.3 (`assessment_evidence_weight` from config)
  - Updates store via `claim.rank_changed` events when confidence shifts >0.05
- [x] Tests: 76 passing (8 relationship + 9 confidence + existing 59)
- [x] **`frames_differently` prompt validated**: Synthetic pair test (5 pairs) → correctly fires on observational vs RCT pattern (Pair 2) and correctly identifies contradicts on factual conflicts (Pair 1). 3/5 exact match, 2 defensible alternate classifications.
- [x] **Google Drive PDFs downloaded**: Judge Will (57K chars) + Judge Eric (210K chars) extracted to `data/covid_origins/sources/`
- [x] **Exit criterion met**: Relationships detect edges via cosine + LLM classify; confidence model computes dual scores; dedup and contradiction confirmation built in; frames_differently works

### Day 5-6 (July 1-2): Crux Detection + Verification Layers 3-4 ✅

- [x] **`crux_detection.py`**
  - `binary_entropy(p)` — peaks at 0.5, zero at 0/1
  - Cascade BFS: exponential decay, redundancy factor, target relevance
  - CASCADE_EDGE_TYPES: supports, depends_on, is_crux_for
  - EXCLUDED: frames_differently (lateral), contradicts (opposes)
  - `compute_crux_scores(claims, edges, target_ids)` → sorted dict
  - `get_top_cruxes()` → returns full context (text, confidence, entropy, category)
  - Day 7 uses hardcoded targets; Day 9 re-runs with discourse-derived targets
- [x] **`verification.py`** — Layers 3-4
  - Layer 3: NLI entailment ("Does quote entail claim?") — flags overstatement/fabrication
  - Layer 4: Cross-provider ("Is claim in source?") — runs on top N% medium-confidence only
  - Fabrication detected → confidence dropped to 0.1
  - Both layers emit meta.flag events for audit trail
- [x] **`run_pipeline.py`** updated: full pipeline wired (extract → verify → relationships → confidence → crux)
  - `--phase full` runs everything end-to-end
  - Hardcoded target_ids for crux (auto-selects claims mentioning origin/zoonotic/lab leak)
- [x] Tests: 92 passing (10 crux + 6 verification + existing 76)
- [x] **Exit criterion met**: Crux detection validated on synthetic graph (foundation=top crux, certain=lower, irrelevant=zero, frames_differently=excluded). Verification layers callable with proper mocking.

### Day 7 (July 3): End-to-End Integration ✅

**Ran `--max-sources 2 --phase full` (ACX + Judge Will).**

Results:
- **88 claims** extracted (50 ACX + 39 Judge Will, 3 deduped → 85 active)
- **Categories**: 54 empirical, 29 assessment, 5 methodological
- **14 edges** detected (5 frames_differently, 4 supports, 2 qualifies, 3 other)
- **85 claims scored** confidence (avg 0.226 — expected low with sparse edges)
- **Crux scores = 0** — too few edges for cascade paths (need more sources)
- **Cost: $0.048** (125 API calls, 4 models)
- **Wall-clock: ~12 minutes**
- **`frames_differently` working correctly** in real data (23-OOM Bayesian divergence framed differently from 1-in-300 probability = correct classification)

Key observations:
- Layer 3 NLI caught real overstatements (e.g., "I think" opinion stated as fact)
- Dedup caught 3 near-duplicates and superseded them
- Relationship detection limited by different-source requirement (only 2 sources → few cross-source pairs)
- Good crux targets identified: `clm_0051` (zoonotic origin likely), `clm_0060` (judge verdict), `clm_0001` (Rootclaim lab leak)

**Critical fix applied (from review):**
- [x] **Removed different-source filter** — within-source edges now detected (captures argument structure: premise→conclusion chains). Edges tagged with `cross_source: true/false`.
- [x] **Filtered `none` edge types** — no longer stored (was polluting graph)
- [x] **Saved Day 7 baseline** → `data/covid_origins/baselines/day7_2sources/` for regression comparison
- [x] Confidence model updated to track within-source vs cross-source provenance (within-source shares provenance → gets clustered as correlated, doesn't inflate independent corroboration)

**Expected impact**: With within-source edges enabled, 88 claims should produce 50-100+ edges instead of 14. This unlocks crux detection cascades.

**Day 8 re-run results (within-source edges enabled):**
- Edges: 14 → **39** (+178%) — within-source edges working
- Edge types: 21 supports, 8 qualifies, 7 frames_differently, 3 depends_on
- Crux detection: **scores > 0** (top: 0.233) — cascades now traversable
- HDBSCAN: **2 positions found** (28 market/epi claims + 7 FCS/lab claims)
- Settling: verdicts auto-detected (4) but not firing (edge direction issue — verdict claims lack incoming `supports` edges)
- Cost: still under $0.10 total

**Known tuning issues for Day 10-12:**
- Edge direction: relationship classifier sometimes puts conclusion→evidence instead of evidence→conclusion. Need prompt refinement or post-processing flip.
- Settling depends on dense incoming edges to verdict claims — will improve with 8 sources.
- HDBSCAN produced 2 positions + 51 noise claims — may need min_cluster_size tuning or more data.

**Day 9 results (5 sources, full pipeline):**
- **224 claims** from 5 sources (113 empirical, 75 assessment, 36 methodological)
- **151 edges** (89 supports, 21 frames_differently, 20 qualifies, 13 depends_on, 3 contradicts)
- **3 positions** via HDBSCAN: zoonotic evidence (9), zoonotic conclusion (66), Bayesian methodology critique (6)
- **Crux detection working**: top crux = market evidence claim (score 0.172), FCS molecular evidence, Bayesian methodology
- **Site generated**: 4 HTML pages (index + 3 positions), clean layout
- **Cost: $0.23 total** for 5 sources end-to-end (355 API calls)
- **Settling**: not firing (edge direction issue — verdicts lack incoming `supports` edges)

**Edge direction prompt fix applied** (explicit "source=evidence, target=conclusion" instruction). Will take effect on next full re-run.

**Baseline saved**: `data/covid_origins/baselines/day9_5sources/`

**Remaining for quality pass (Day 10-12):**
- Re-run with edge direction fix → settling should fire
- Add 3 more sources (YouTube debates) for fuller coverage
- Tune HDBSCAN (currently 3 positions with 149/224 claims as noise)
- Empty chairs generation
- Claim.html + evidence.html page types

### Day 8-9 (July 4-5): Discourse + Settling + Site ✅

**Priority order** (don't try to do everything equally):

**Day 8 (July 4)** ✅:
- [x] **`discourse.py`** (270 lines)
  - HDBSCAN on persisted embeddings (tries min_cluster_size [5, 10, 15, 20])
  - LLM fallback if clusters <2 or >8
  - Position labeling via LLM (stance, core_commitment, strongest_claims, summary)
  - Disagreement classification per position pair (factual_dispute vs framework_mismatch)
  - Re-runs crux detection with discourse-derived target_ids
  - Stores positions as events
- [x] **`settling.py`** (165 lines)
  - Type 1: BFS upstream finds contested cruxes (conf 0.3-0.7) in verdict's dependency chain
  - Type 2: Detects `frames_differently` edges in dependency chain = framework adjudication
  - Auto-detects verdict claims from language patterns ("judges ruled", "found in favor")
  - Severity = proportion of contested deps + framework bonus
  - Emits meta.flag events for detected settling
- [x] Tests: 102 passing (4 discourse + 6 settling + existing 92)

**Day 9 (July 5)** ✅:
- [x] **`generate_site.py`** — index.html + position pages + crux pages (inline styles)
- [x] Verified site renders (12 pages generated)
- [x] **Exit**: Navigable HTML site for COVID case

### Day 10 (July 5): Critical Fixes + All Criteria Pass ✅

**Fixes applied:**
- [x] Crux detection: exclude verdict/target claims + assessment claims from scoring → top cruxes are now empirical evidence
- [x] Relationship detection: lower cross-source cosine threshold (0.4) → 183 contradicts (from 3)
- [x] Empty chairs: built `_detect_empty_chairs()` in discourse.py → 5 perspectives identified
- [x] Model switch: GPT-4.1-mini/nano (2.3× faster than DeepSeek V4 Pro)
- [x] Position merge logic validated
- [x] Edge direction fix + flip heuristic working
- [x] Full re-run: 222 claims, 916 edges, 4.13 edges/claim
- [x] **ALL 5 ACCEPTANCE CRITERIA PASS**
- [x] Baseline saved: `data/covid_origins/baselines/day10_final/`

### Day 11 (July 6-7): Pipeline Wiring + Integration + Source Prep ✅

**Pipeline completeness fixes (from code review):**
- [x] Wired discourse + settling + site generation into `run_pipeline.py --phase full`
- [x] Judges can now run ONE command and get full HTML output
- [x] Removed broken `cli.py` entry point from pyproject.toml
- [x] Added integration test (fixture store → discourse → HTML site → assertions)
- [x] Added WHY comments to all magic numbers in config.yaml
- [x] Fixed position labeling prompt (emphasize UNIQUE argument of each position)
- [x] Graph-based opposing position detection (lab-leak found via contradiction edges)

**Source preparation:**
- [x] Created `examples/lhc_black_holes/sources.yaml` (5 sources: CERN FAQ, LSAG report, Wilczek paper, Wikipedia, SciAm)
- [x] Created `examples/eggs_health/sources.yaml` (5 sources: Zhong BMJ, Xu meta-analysis, Zhong JAMA, Soliman review, Harvard)
- [x] Tests: 103 passing

### Day 12 (July 7-8): COVID Visual Polish ✅

**Done:**
- [x] Extracted CSS to `static/style.css` (150 lines — position colors, confidence bars, badges, settling alerts, cards, responsive)
- [x] Updated all Jinja2 templates: external CSS `<link>`, Mermaid via CDN `<script type="module">`
- [x] Mermaid discourse structure diagram on index (positions as nodes, edge counts as labels)
- [x] Site regenerated: **15 files** (index + 3 positions + 10 cruxes + style.css)
- [x] CUT: evidence.html (claim.html will include source reference — sufficient)
- [x] CUT: Rootclaim 6th source (lab-leak already found via graph detection)

**Also completed:**
- [x] `claim.html` page type: 15 important claims get individual pages (cruxes + strongest_case). Shows provenance, confidence, "supported by"/"contradicted by" with cross-links.
- [x] Cross-linking: position pages link to claim pages, claims link back to positions. Max 2 clicks to index from anywhere.
- [x] Position pages: top 15 claims shown, rest in `<details>` toggle ("Show all N remaining claims")
- [x] **SUBMISSION.md skeleton written** (6 sections: SHOW→TRUST→HOW→SCALES→GENERALIZE→UNKNOWNS). Real numbers from output. Ready for Day 18 full rewrite with screenshots.
- [x] **29 pages total**: index + 3 positions + 10 cruxes + 15 claims + style.css
- [ ] Visual review in browser (judge test) — deferred to Day 13

**Status**: Day 12 COMPLETE. Site is professional, navigable, cross-linked. Submission skeleton ready.

### Day 13-14 (July 8): LHC + Eggs Initial Runs + Source Issues ✅

**LHC ran successfully (2/3 sources):**
- 10 claims, 8 edges, 2 positions, 2 cruxes — site generated (11 files)
- LSAG PDF URL 404'd — needs corrected URL or manual download
- "Settled by" template logic added but didn't trigger (need more sources for all-high confidence)

**Eggs partially ran (1/3 sources):**
- BMJ and AHA journals returned 403 (paywall) — need manual PDF downloads
- Only PubMed meta-analysis worked → 5 claims, 5 edges
- Too thin for discourse mapping

**Action needed:** Download paywall PDFs manually to `data/{case}/sources/` fallback paths. Then re-run.

**Also done:**
- [x] Site visual audit: 11/11 checks pass (Mermaid, stats, positions, cruxes, confidence bars, settling, empty chairs, CSS, cross-links, footer)
- [x] SUBMISSION.md skeleton written with real numbers from COVID output

### Day 13 (July 8): Final COVID Quality + SUBMISSION.md Skeleton ✅

**ALL 5 ACCEPTANCE CRITERIA PASS (confirmed Day 10):**

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | ≥2 positions | ✅ PASS | 3 positions (methodology + zoonotic spillover + lab leak) |
| 2 | Market crux in top-5 | ✅ PASS | #3: HSM proximity (0.350) + #5: earliest 40 cases (0.327) |
| 3 | ≥1 empty chair | ✅ PASS | 5 found (virological, epi, lab safety experts) |
| 4 | Settling fires | ✅ PASS | 5/9 verdicts, 92 contested deps + framework adjudication |
| 5 | All claims have quotes | ✅ PASS | 222/222 verified |

**Day 13 focus:** SUBMISSION.md skeleton + final quality review of output.

### Day 14-15 (July 9): LHC + Eggs Cases ✅

**Both cases ran successfully with free alternative sources:**
- [x] Downloaded free sources: Wikipedia LHC Safety (40K), Harvard Eggs (8K), Soliman 2018 PMC (57K)
- [x] Updated sources.yaml to use manual_fallback paths for paywalled URLs
- [x] LHC pipeline: **47 claims, 225 edges, 5 positions, 2 cruxes, 5 empty chairs** (22 files)
  - Edge types: 215 supports, 4 qualifies, 4 frames_differently, 1 depends_on
  - "Settled by" template logic added (conditional: if no cruxes + 1 position → shows dependency chain)
- [x] Eggs pipeline: **55 claims, 193 edges, 5 positions, 4 cruxes, 5 empty chairs** (23 files)
  - Edge types: 161 supports, 11 frames_differently, 7 qualifies, 8 "difference in scope", 2 depends_on
  - **11 `frames_differently` edges** — observational vs RCT methodology correctly identified
- [x] Both sites generated with CSS + Mermaid

**Results summary (all 3 cases):**

| Case | Claims | Edges | Positions | Cruxes | frames_differently | Files |
|------|--------|-------|-----------|--------|-------------------|-------|
| COVID | 222 | 916 | 3 | 10 | 6 | 30 |
| LHC | 47 | 225 | 5 | 2 | 4 | 22 |
| Eggs | 55 | 193 | 5 | 4 | **11** | 23 |
| **Total** | **324** | **1,334** | **13** | **16** | **21** | **75** |

**Total cost for all 3 cases: ~$1.00**

### Day 16 (July 10): Quality Pass + Collaboration Demo ✅

- [x] Quality pass: all 3 sites verified (72 pages, 0 broken links, CSS + Mermaid working)
- [x] Built `scripts/add_challenge.py` — collaboration protocol demo
- [x] Ran collaboration demo: WIV GoF + NIH P3CO challenge → cascade documented
- [x] Browser link test: 0 broken links across all 3 cases
- [x] Full documentation restructure (11 READMEs, METHODOLOGY.md, PIPELINE.md)
- [x] SUBMISSION.md written (1,200 words, 6 sections, result-first opening)

### Day 17+ (Remaining): Final Polish + Ship

**What's actually left (everything else is done):**
- [ ] Visual browser review + capture screenshots for SUBMISSION.md
- [ ] Add "How to Navigate" brief guide on each site's index page
- [ ] Reproducibility check: fresh `uv sync && uv run python run_pipeline.py covid_origins --phase full`
- [ ] GitHub repo push (all files, .env excluded, output/ included)
- [ ] **Submit by July 14** (5 days before deadline)

### Buffer (July 14-18): Available for fixes

5 days buffer before July 19 deadline.

---

## Config Architecture

**Principle**: Change behavior by editing `config.yaml`, never code. Pipeline is provider-agnostic.

```yaml
# config.yaml — the ONLY file to edit for model/provider/threshold changes
models:
  extraction: "gpt-4.1-mini"           # Fast + quality ($0.40/$1.60 per M)
  verification_nli: "gpt-4.1-nano"     # Batch, cheapest ($0.10/$0.40 per M)
  relationship_batch: "gpt-4.1-nano"
  relationship_confirm: "gpt-4.1-mini"
  discourse_crux: "gpt-4.1-mini"
  discourse_empty: "gpt-4.1-mini"
  embedding: "embedding-small"
relationships:
  cosine_threshold: 0.6               # Within-source
  cross_source_cosine_threshold: 0.4  # Lower for opposing claims (different vocabulary)
budget:
  dev_budget: 5.0                     # Raises BudgetExceeded when hit
```

**Defined in `config.py`**:
- `PROVIDERS` dict: name → (base_url, api_key_env)
- `MODELS` dict: key → (id, provider, costs, max_tokens)
- `PipelineModels`: which model handles each pipeline stage
- `EpistackConfig`: master config with all parameter dataclasses
- `load_config()`: YAML file → env overrides → defaults (12-factor pattern)
- `get_config()`: singleton access from any module

**Adding a new provider**: Add entry to `PROVIDERS` in `config.py`, add model entries to `MODELS`, reference in `config.yaml`. All routing handled by `llm.py` automatically.

---

## Cost Tracking

**Actual costs (validated runs):**

| Run | Sources | Claims | Edges | Cost | Time |
|-----|---------|--------|-------|------|------|
| Smoke test (Day 2) | 1 partial | 14 | 0 | $0.008 | 2 min |
| Day 7 (DeepSeek, cross-only) | 2 | 88 | 14 | $0.048 | 12 min |
| Day 9 (DeepSeek, within-source) | 5 | 224 | 151 | $0.230 | 35 min |
| Day 10a (GPT-4.1, within-source) | 5 | 222 | 344 | $0.23 | ~15 min |
| **Day 10b (GPT-4.1, +cross 0.4)** | **5** | **222** | **916** | **$0.30** | **~15 min** |

**Projected for full submission (3 cases):**
- COVID (8 sources): ~$0.40
- LHC (4-5 sources): ~$0.20
- Eggs (4-5 sources): ~$0.20
- **Total: ~$0.80** (vs original $40-54 estimate with Claude direct)

50× cheaper than planned. Unlimited iteration budget.

Tracked by `llm.py`, printed at pipeline end.

---

## Key Design Decisions (Tracing to Sources)

| Decision | Rationale | Source |
|----------|-----------|--------|
| Config-driven, provider-agnostic | Switch providers in 1 line; enterprise-standard | 12-factor app, Apollo Research pattern |
| Event-sourced JSONL | Time-travel, debugging, append-only collaboration | DEG (`Internal-context/memory_challange/`) |
| Confidence-gated supersession | Low-conf can't override high-conf claims | DEG `trust.py`, FPF arXiv:2601.21116 |
| Bi-temporal validity | When claim was true vs when we learned it | DEG `temporal.py`, Graphiti arXiv:2501.13956 |
| Cascade BFS for crux detection | Downstream impact with decay + redundancy | DEG `temporal.py:cascade_impact()`, Chan & Darwiche 2004 |
| G3 compliance detection | 8/11 models fabricate at G3 threshold | arXiv:2605.02398, `bluedot-proj/schema-compliance-trap/` |
| M2/M3 defenses | +18.5pp, +19.3pp recovery in controlled testing | Run 17 (5,110 evals, 8 models) |
| Wilson CI for trials | Proper small-N statistics, not CLT | arXiv:2503.01747, Preseal `scorer.py` |
| `frames_differently` edge type | Framework mismatch ≠ contradiction | Novel (Tony Sale's CONTEXT_MUTATION) |
| Noisy-OR evidence combination | Independent lines strengthen; correlated don't | Bayesian networks standard |
| Product for quality dimensions | Any zero kills total | Preseal multiplicative scoring |
| Selective extraction (3-5/chunk) | Cost control + quality (not ALL claims) | Review feedback |
| Claim categories | Assessments ≠ empirical claims (different weights) | Review feedback |
| `uv` for deps | Deterministic lockfile, fast, enterprise-standard | Industry best practice |
| GPT-4.1-mini/nano for dev | 2.3× faster than DeepSeek, better edge direction, $0.23/case | Benchmarked Day 10 |

---

## References Cross-Map

| In IMPLEMENTATION_PLAN.md | Verified Source | Status |
|---|---|---|
| §3 Event schema | `src/epistack/store.py` | ✅ Implemented |
| §5.1 Grounded extraction | `src/epistack/extraction.py` | ✅ Implemented |
| §5.2 Verification Layer 1-2 | `src/epistack/extraction.py` (quote + regex) | ✅ Implemented |
| §5.2 Verification Layer 3-4 | `src/epistack/verification.py` | ✅ Implemented |
| §5.3 Relationship detection | `src/epistack/relationships.py` | ✅ Implemented |
| §5.6 Compliance detection | `src/epistack/compliance_detector.py` | ✅ Ported from research |
| §6.1 Crux formula | `src/epistack/crux_detection.py` | ✅ Implemented |
| §6.2 Confidence model | `src/epistack/confidence.py` | ✅ Implemented |
| §6.3 Settling detection | `src/epistack/settling.py` | ✅ Implemented + edge-flip heuristic |
| §7 Discourse mapping | `src/epistack/discourse.py` | ✅ Implemented + position merge |
| §9 Static HTML | `src/epistack/generate_site.py` | ✅ Implemented (inline templates) |
| Wilson CI | `src/epistack/scoring.py` | ✅ Ported from Preseal |
| G-level patterns | `src/epistack/compliance_detector.py` | ✅ Ported from paper |
| `frames_differently` | `src/epistack/store.py` (edge type supported) | ✅ Schema ready |

---

## Changelog

### v0.3.5 (July 9, 2026) — All 3 Case Studies Complete

- **LHC case**: 47 claims, 225 edges, 5 positions, 2 cruxes, 22-file site. Settled-by template logic added.
- **Eggs case**: 55 claims, 193 edges, 5 positions, 4 cruxes, 23-file site. **11 `frames_differently` edges** — observational vs RCT methodology correctly identified as framework mismatches.
- **Source workaround**: Paywalled PDFs (BMJ 403, CERN 404) replaced with free alternatives (Harvard Nutrition Source, Soliman 2018 PMC, Wikipedia LHC Safety). Pipeline uses `manual_fallback` paths.
- **75 HTML pages total** across 3 cases for ~$1 total API cost.
- All 3 cases demonstrate different epistemic structures: contested (COVID), consensus-heavy (LHC), framework-mismatch (Eggs).

### v0.3.4 (July 8, 2026) — Professional CSS + Mermaid + Visual Polish

- **`static/style.css`** (150 lines): Position color-coding (blue=zoonotic, red=lab-leak, purple=methodology), confidence bars, edge-type badges, settling alerts, responsive layout. Inspired by daisyUI/Tabler patterns, zero framework dependencies.
- **Mermaid via CDN**: Overview diagram on index.html showing positions as nodes with edge counts (contradictions, framework mismatches). Zero build step — single `<script type="module">` import.
- **Templates rewritten**: External CSS via `<link>`, viewport meta, proper semantic HTML. Inline styles removed.
- **15-file output**: index + 3 positions + 10 cruxes + style.css
- **Decision**: No MkDocs/Hugo/Pelican — custom Jinja2 approach is correct for this use case (direct Python integration, no intermediate build step, full control)
- Tests: 103 passing

### v0.3.3 (July 7, 2026) — Pipeline Complete + Submission-Ready Fixes

- **`run_pipeline.py --phase full` now end-to-end**: extract → verify → relationships → confidence → discourse → settling → HTML site. One command produces the complete artifact.
- **Removed broken `cli.py` entry point** from pyproject.toml (prevents ImportError).
- **Integration test** added: fixture store → discourse → site → HTML assertions (103 tests total).
- **Config.yaml comments**: All magic numbers have WHY rationale (e.g., "0.4 cross-source: validated Day 10, produces 183 contradictions vs 3 at 0.6").
- **Position labeling prompt improved**: Emphasizes "unique argument that distinguishes from other positions."
- **LHC + Eggs sources.yaml curated**: 5 sources each, ready for pipeline runs Day 14-15.
- **Hard decision**: Skip Rootclaim 6th source (lab-leak already found via graph detection — saves time).

### v0.3.2 (July 6, 2026) — Lab-Leak Position Found + 12-Page Site

- **Graph-based position detection**: `_find_opposing_positions()` uses contradiction/qualification/framing edges to identify opposing claims. Found 62 lab-leak claims that HDBSCAN missed as noise.
- **3 positions**: Bayesian methodology (6), Zoonotic spillover (76), Lab leak (62)
- **12-page HTML site**: index + 3 positions + 8 crux pages
- **Edge quality validated**: 10 random supports edges spot-checked, all genuinely valid
- Edges/claim ratio 4.13 is legitimate (not over-connected — edges are real debate connections)

### v0.3.1 (July 5, 2026) — All Acceptance Criteria Pass

- **Crux fix**: Exclude verdict/target claims + assessment claims from scoring. Top cruxes now empirical evidence (WIV GoF, HSM proximity, DEFUSE program) instead of debate outcomes.
- **Contradiction fix**: Lower cross-source cosine threshold (0.4 vs 0.6). Opposing claims now get paired despite different vocabulary.
- **Empty chairs**: Built `_detect_empty_chairs()` in discourse.py. 5 perspectives found (virological, epidemiological, lab safety).
- **Results**: 222 claims, 916 edges (4.13/claim), crux top 1.128, settling on 5 verdicts, 5 empty chairs.
- **All 5 acceptance criteria PASS.**
- Baseline saved: `data/covid_origins/baselines/day10_final/`

### v0.3.0 (July 5, 2026) — Full Pipeline Working + Speed Optimization

- **Model switch**: DeepSeek V4 Pro → GPT-4.1-mini/nano. 2.3× faster (3s vs 7s/call), better edge direction compliance, same quality.
- **5-source run validated**: 222 claims, 344 edges (1.55/claim), crux top 0.82, settling fires on 3 verdicts.
- **`generate_site.py`**: Jinja2 with inline templates. Generates index + position + crux pages.
- **`discourse.py` + position merge**: Merges positions with >50% mutual support edges (fixes "zoonotic evidence" vs "zoonotic conclusion" as separate positions).
- **`settling.py` + edge-flip heuristic**: Auto-flips verdict edges if direction is wrong. Settling now fires correctly.
- **Edge direction prompt fix**: Explicit "source=evidence, target=conclusion" convention in classification prompt.
- **Within-source edges**: 14 → 344 edges. Unlocked crux detection and settling.
- **Acceptance criteria**: 4/5 passing (positions, cruxes, settling, provenance). Missing: empty chairs.
- Tests: 102 passing, 0.71s

### v0.2.6 (June 30, 2026) — Crux Detection + Verification

- **`crux_detection.py`**: Binary entropy × weighted cascade BFS. Excludes `frames_differently` from cascade. `get_top_cruxes()` returns full context. Validated on synthetic graph (10 tests).
- **`verification.py`**: Layer 3 NLI entailment + Layer 4 cross-provider. Fabrication → confidence 0.1. L4 cost-optimized (top N% only). Emits meta.flag events.
- **`run_pipeline.py`** wired: `--phase full` runs extract → verify → relationships → confidence → crux end-to-end.
- Tests: 92 passing, 0.16s

### v0.2.5 (June 30, 2026) — Relationships + Confidence

- **`relationships.py`** (395 lines): Embed all claims → persist embeddings.npz → two-stage dedup (>0.92 auto-merge, 0.80-0.92 LLM check) → cosine candidate pairs → batch classification (15/call) → contradiction confirmation with reclassification to `frames_differently`
- **`confidence.py`** (280 lines): Dual model (noisy-OR corroboration × quality product). Correlation detection via provenance-path overlap. Single-linkage clustering. Assessment evidence weighted 0.3×. Quality dimensions: source_quality, quote_verified, logical_consistency, precision.
- Tests: 76 passing (added 8 relationship + 9 confidence)
- Status sync: updated current state, references, test counts in DEVELOPMENT.md

### v0.2.4 (June 28, 2026) — Review Fixes + Production Decisions

- **Decision**: Stay on DeepSeek V4 Pro for submission (quality validated, 5-10x cheaper than Claude)
- **Extraction idempotency**: Running extract twice on same source skips (checks existing source_urls)
- **Manual fallback**: `fetch.py` checks `manual_fallback` path before attempting URL fetch (for Google Drive PDFs, failed URLs)
- **Verdict tagging**: `sources.yaml` now has `contains_verdict` + `verdict_position` fields for settling.py
- **Assessment evidence weight**: Added `assessment_evidence_weight: 0.3` to config (when assessment claims support empirical claims, their strength is multiplied by 0.3)
- Tests: 59 passing

### v0.2.3 (June 28, 2026) — Config-Driven Architecture

- **`config.py`**: Single source of truth. Providers (OpenRouter, Anthropic, OpenAI, Nebius), models with costs, pipeline role assignments, all parameter dataclasses. YAML loading with env overrides.
- **`config.yaml`**: User-editable config file. Change models/providers/budget here only.
- **`llm.py` rewritten**: Provider-agnostic. Routes via config. Supports role-based calls (`role="extraction"`) and direct calls (`model_key="deepseek-v4-pro"`).
- **OpenRouter integration**: DeepSeek V4 Pro ($0.43/M) as Sonnet-equivalent for dev.
- **Smoke test validated**: 14 claims from ACX post, $0.008 total cost, all quotes verified.
- Tests: 59 passing, 0.10s

### v0.2.2 (June 28, 2026) — Fetch + Pipeline Wiring

- **`fetch.py`**: Blog (trafilatura), PDF (pymupdf), YouTube (transcript API), local files.
- **`run_pipeline.py`**: Orchestrator with --phase, --budget, --max-sources.
- **`scripts/smoke_test.py`**: End-to-end integration test.
- Budget cap ($5 dev), .env loading, selective extraction prompt, claim categories.

### v0.2.1 (June 27, 2026) — Core Foundation

- **`llm.py`**: Async wrapper with retry, cost tracking, model routing.
- **`store.py`**: Event-sourced JSONL (append, replay, time-travel, snapshot, supersession, bi-temporal).
- **`extraction.py`**: Grounded extraction with quotes, Layer 1-2, compliance defense.
- Tests: 51 passing in 0.08s.

### v0.2.0 (June 27, 2026) — Clean Slate

- Migrated to `uv` (from pip/setuptools). Lockfile: 70 packages.
- Archived v0.1 prototype. Fresh `src/epistack/` with 3 keeper files.
- YouTube transcript API verified on Rootclaim debate (2855 segments).
- 17 tests passing.
