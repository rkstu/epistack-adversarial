# tests

Test suite for Epistack-Adversarial.

## Running

```bash
PYTHONPATH=src python3 tests/test_scoring.py
PYTHONPATH=src python3 tests/test_compliance.py
```

## What's tested

**test_scoring.py** validates the statistical scoring layer:
- Wilson CI computation (basic, perfect, zero, no-trials cases)
- Cross-model agreement scoring (multi-family vs mono-family penalty)
- Source quality scoring (retracted sources, high-quality sources)
- Multiplicative composite scoring (zero propagation)
- Confidence level classification

**test_compliance.py** validates the G3 compliance-trap detector:
- G1 baseline (no pressure detected)
- G2 mild pressure (detected but below threshold)
- G3 threshold detection (the critical cliff)
- G4/G5 strong and extreme pressure
- Bedrock-style production prompts correctly flagged
- M2 domain priming defense application
- M3 metacognitive guard application
- Safe prompts pass through without modification

## Adding tests

Tests run without API keys. If you're adding tests for the assessment pipeline that require LLM calls, mock the `llm_call` function with fixed responses.
