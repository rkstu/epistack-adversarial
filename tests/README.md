# tests — Test Suite

103 tests covering all pipeline modules. No API keys required (LLM calls are mocked).

## Running

```bash
uv run pytest tests/           # All tests
uv run pytest tests/ -v        # Verbose
uv run pytest tests/ -q        # Quiet (just pass/fail count)
```

## Test Files

| File | Module | Tests | What's Covered |
|------|--------|-------|----------------|
| `test_scoring.py` | scoring.py | 8 | Wilson CI, cross-model agreement, source quality |
| `test_compliance.py` | compliance_detector.py | 9 | G1-G5 detection, M2/M3 defenses, safe prompts |
| `test_extraction.py` | extraction.py | 17 | Quote containment, overclaiming, chunking, full extraction with mock |
| `test_fetch.py` | fetch.py | 8 | Type detection, YouTube ID parsing, local file reading |
| `test_llm.py` | llm.py + config.py | 8 | Provider config, model resolution, cost tracking |
| `test_store.py` | store.py | 9 | Append/replay, time-travel, supersession, bi-temporal, snapshots |
| `test_relationships.py` | relationships.py | 8 | Candidate pairs, JSON parsing, embedding roundtrip |
| `test_confidence.py` | confidence.py | 9 | Noisy-OR, correlation, clustering, assessment weighting |
| `test_crux.py` | crux_detection.py | 10 | Entropy, cascade BFS, target exclusion, frames_differently excluded |
| `test_discourse.py` | discourse.py | 4 | HDBSCAN clustering, disagreement classification |
| `test_settling.py` | settling.py | 6 | Type 1/2 detection, verdict auto-detection, no-settling case |
| `test_verification.py` | verification.py | 6 | Layer 3 NLI, Layer 4 cross-provider, subset selection |
| `test_integration.py` | Full pipeline | 1 | Fixture → discourse → site → HTML assertions |

## Adding Tests

Tests run without API keys. Mock `llm.call` with fixed responses:
```python
async def mock_call(prompt, **kwargs):
    return '{"result": "mocked"}'
monkeypatch.setattr("epistack.llm.call", mock_call)
```
