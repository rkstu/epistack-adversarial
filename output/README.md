# output — Pre-Built HTML Sites

Pre-generated discourse maps for all three case studies.
Committed to the repository so judges can view results immediately without running the pipeline or needing API keys.

## Viewing

```bash
open output/covid_origins/index.html       # Contested case (flagship)
open output/lhc_black_holes/index.html     # Settled science case
open output/eggs_health/index.html         # Vague/open-ended case
```

## Structure (per case)

```
<case>/
├── index.html          # Overview: positions, cruxes, settling, Mermaid diagram
├── positions/          # One page per detected position (stance, claims, cross-links)
├── cruxes/             # One page per empirical crux (score, entropy, provenance)
├── claims/             # One page per important claim (provenance, confidence, edges)
└── static/style.css    # Stylesheet (copied from /static/)
```

## Regenerating

```bash
uv run python run_pipeline.py <case> --phase full --budget 1.0
```

Requires `OPENROUTER_API_KEY` in `.env`. Cost: ~$0.25-$0.30 per case.

## Results Summary

| Case | Claims | Edges | Positions | Cruxes | Pages |
|------|--------|-------|-----------|--------|-------|
| COVID-19 Origins | 222 | 916 | 3 | 10 | 29 |
| LHC Black Holes | 47 | 225 | 5 | 2 | 21 |
| Eggs & Health | 55 | 193 | 5 | 4 | 22 |
