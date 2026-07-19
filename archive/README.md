# archive — Historical Reference

Contains the v0.1 prototype code (pre-rewrite). Kept for reference only. This code is NOT used by the current pipeline.

## `v0_prototype/`

The original architecture used a different module structure: `models.py`, `oracle.py`, `ingestion.py`, `structure.py`, `assessment.py`, `pipeline.py`, `cli.py`. It was replaced during the June 27 rewrite with the current event-sourced architecture.

Key differences from current:
- No event sourcing (in-memory only)
- No provider abstraction (hardcoded Anthropic)
- No quote verification (claims extracted without grounding)
- No `frames_differently` edge type
- Different confidence model (purely multiplicative, no correlation detection)

For the current architecture, see [docs/PIPELINE.md](../docs/PIPELINE.md).
