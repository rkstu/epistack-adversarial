# scripts — Utility Scripts

## `smoke_test.py`

End-to-end integration test. Fetches a real source (ACX blog post), extracts claims via the full pipeline, and reports results. Requires `OPENROUTER_API_KEY` in `.env`.

```bash
uv run python scripts/smoke_test.py
```

## `add_challenge.py`

Demonstrates the collaboration protocol. Adds counter-evidence to an existing claim, showing how new information cascades through the knowledge base.

```bash
uv run python scripts/add_challenge.py covid_origins \
    --target clm_0037 \
    --body "NIH P3CO board classified WIV research as not gain-of-function" \
    --source-url "https://www.nih.gov/p3co" \
    --source-label "NIH P3CO Review Board"
```

After adding a challenge, re-run the pipeline to see the cascade effect:
```bash
uv run python run_pipeline.py covid_origins --phase full
```
