# scripts — Utility Scripts

## `verify.py` — Judge Verification (No API Key Required)

Runs all 103 unit tests and validates pre-built output against expected structural results. Single command to confirm the entire pipeline works correctly.

```bash
uv run python scripts/verify.py
```

Checks:
1. All 103 unit tests pass (LLM calls are mocked — no API key needed)
2. Pre-built HTML output present and complete for all 3 cases
3. Event store integrity — claim counts, edge counts, all quotes verified
4. Key structural findings — settling detection, position count, `frames_differently` edges

Exit code 0 = all pass. Exit code 1 = something failed with details.

---

## `smoke_test.py` — Live Integration Test (API Key Required)

End-to-end integration test against real APIs. Fetches a source, extracts claims, and reports results. Requires `OPENROUTER_API_KEY` in `.env`.

```bash
uv run python scripts/smoke_test.py
```

Use this to confirm the full pipeline works with your own API key before running a full case.

---

## `add_challenge.py` — Collaboration Protocol Demo

Demonstrates how new evidence enters the system and cascades through the knowledge base. Adds a counter-claim to an existing claim and shows how confidence and crux scores update.

```bash
uv run python scripts/add_challenge.py covid_origins \
    --target clm_0037 \
    --body "NIH P3CO board classified WIV research as not gain-of-function" \
    --source-url "https://www.nih.gov/p3co" \
    --source-label "NIH P3CO Review Board"

# Re-run pipeline to see cascade effect
uv run python run_pipeline.py covid_origins --phase full --budget 1.0
```
