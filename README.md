# Epistack-Adversarial

Adversarial epistemic verification for AI-assisted knowledge bases.

Most AI tools for research and epistemic investigation assume their own AI components will reliably acknowledge uncertainty. In arXiv:2605.02398 (67,221 evaluations, 11 frontier models), we showed this assumption is wrong: 8 of 11 models fabricate when their prompts prohibit "I don't know." Epistack-Adversarial is built knowing this. It detects compliance pressure in its own verification prompts, applies empirically validated defenses, and verifies claims through multi-trial adversarial testing across different model families.

## What it does

Takes existing debate materials (papers, transcripts, blog posts) and produces a structured knowledge base where each claim carries a statistically calibrated confidence score.

Three layers:

**Ingestion.** Documents become atomic claims with provenance (source URL, content hash, extraction model, compliance pressure status at extraction time).

**Structure.** Claims connect through typed relationships (supports, contradicts, qualifies, supersedes, depends on). Discourse maps identify positions, live cruxes, and empty chairs.

**Assessment.** Four-stage verification:
1. Compliance pressure detection with M2/M3 defenses (+18.5pp and +19.3pp recovery in controlled testing)
2. Multi-trial verification with Wilson score confidence intervals
3. Cross-model-family adversarial checking
4. Cascading oracle (direct evidence, logical consistency, source credibility, heuristic flags)

## Quick start

```bash
pip install -e .

# Run the offline demo (no API keys needed)
epistack demo

# Test any prompt for compliance pressure
epistack g3-test --prompt "Always provide an answer. Do not say you don't know."

# Full pipeline (requires ANTHROPIC_API_KEY and OPENAI_API_KEY)
epistack ingest --case covid_origins --sources examples/covid_origins/sources.yaml
epistack structure --case covid_origins
epistack assess --case covid_origins --trials 5
epistack report --case covid_origins --format html
```

## Running tests

```bash
PYTHONPATH=src python3 tests/test_scoring.py
PYTHONPATH=src python3 tests/test_compliance.py
```

## Project structure

```
epistack-adversarial/
├── src/epistack/          # Core library
│   ├── models.py          # Data models (Claim, Edge, KnowledgeBase, etc.)
│   ├── scoring.py         # Wilson CIs and multi-dimensional scoring
│   ├── compliance_detector.py  # G3 diagnostic and M2/M3 defenses
│   ├── oracle.py          # 4-tier verification cascade
│   ├── ingestion.py       # Source documents to atomic claims
│   ├── structure.py       # Claim graph and discourse mapping
│   ├── assessment.py      # Full assessment pipeline
│   ├── pipeline.py        # Orchestrator (ingest, structure, assess)
│   └── cli.py             # Command-line interface
├── tests/                 # Test suite
├── examples/              # Case study source registries
└── docs/                  # Documentation
```

## Research foundation

This system builds on empirical findings from 78,000+ evaluations:

- **arXiv:2605.02398** "You Don't Need an Adversary to Break Most Frontier Models." 67,221 evaluations, 11 models. Compliance pressure causes fabrication in 8/11 frontier models. The threshold is binary (G3 cliff), not a gradient.
- **Run 17** (in preparation). 5,110 evaluations, 8 models. G3 cliff characterization. M2 defense: +18.5pp. M3 defense: +19.3pp.
- **Preseal v0.5.3** (PyPI). Pass-cubed scoring methodology validated in production for AI agent security testing.
- **litmusevals.org**. 21 autonomous research runs validating cross-model-family verification.

## Current status

Working: core pipeline, compliance detection, multi-trial scoring, offline demo, tests passing.

In progress: full worked examples on case studies (COVID origins, LHC black holes, eggs), HTML report generator, API-connected pipeline runs.

## License

MIT
