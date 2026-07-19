# src/epistack — Core Library

The 15-module Python library implementing the Epistack pipeline.

## Module Map

| Module | Role | Key Function |
|--------|------|--------------|
| `config.py` | Configuration & provider abstraction | `get_config()` |
| `llm.py` | Provider-agnostic LLM calls + cost tracking | `call(prompt, role=...)` |
| `fetch.py` | Source fetching (web, PDF, YouTube, local) | `fetch_source(url)` |
| `extraction.py` | Grounded claim extraction + Layers 1-2 | `extract_claims(text, store)` |
| `verification.py` | Verification Layers 3-4 (NLI + cross-provider) | `verify_claims(store)` |
| `store.py` | Event-sourced JSONL state management | `EpistemicStore` |
| `relationships.py` | Edge detection (embed + classify + dedup) | `detect_relationships(store)` |
| `confidence.py` | Dual confidence model (noisy-OR × quality) | `compute_all_confidences(store)` |
| `crux_detection.py` | Binary entropy × cascade BFS | `compute_crux_scores(store, targets)` |
| `discourse.py` | Position detection + empty chairs | `build_discourse_map(store)` |
| `settling.py` | Performed settling detection | `detect_performed_settling(store)` |
| `generate_site.py` | Jinja2 HTML site generation | `generate_site(store, discourse)` |
| `compliance_detector.py` | G3 compliance-trap detection + M2/M3 | `detect_compliance_pressure(prompt)` |
| `scoring.py` | Wilson CI + source quality scoring | `wilson_ci(successes, trials)` |

## Design Principles

- **Provider-agnostic**: All LLM calls via `config.yaml` role assignments
- **Event-sourced**: Append-only JSONL — never mutate, only supersede
- **Grounded**: Every claim has a verified source quote
- **Compliance-aware**: G3 check before every LLM verification call

## Full Documentation

See [docs/PIPELINE.md](../../docs/PIPELINE.md) for complete technical reference.
