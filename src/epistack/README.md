# src/epistack

Core library for Epistack-Adversarial.

## Modules

**models.py** defines the data structures everything else operates on. Claims, Sources, Edges, KnowledgeBases, DiscourseMap, VerificationTrials. A Claim carries its source provenance, extraction metadata, confidence scores, and evolution history. A KnowledgeBase holds claims, edges between them, discourse maps, and verification records.

**scoring.py** implements Pass-cubed statistical scoring. The key function is `wilson_ci(successes, trials)` which computes Wilson score confidence intervals for small-N binomial proportions. Also provides multi-dimensional epistemic scoring where dimensions are multiplied (any zero kills the composite) and cross-model agreement scoring that penalizes mono-family verification.

**compliance_detector.py** implements the G3 diagnostic from arXiv:2605.02398. Given any prompt, it detects compliance-forcing patterns at five levels (G1-G5). At G3 or above, the model is likely to fabricate. The module also provides `apply_m2_defense` (domain priming) and `apply_m3_defense` (metacognitive guard) which recovered +18.5pp and +19.3pp respectively in controlled testing.

**oracle.py** runs a 4-tier verification cascade on claims, adapted from Preseal's security oracle. Checks run most-reliable-first and short-circuit on definitive failure: (1) direct evidence check, (2) logical consistency against the knowledge base, (3) source credibility, (4) heuristic red flags.

**ingestion.py** handles Layer 1. Takes source documents, chunks them, extracts atomic claims via LLM, and attaches provenance metadata (content hash, extraction model, compliance pressure status).

**structure.py** handles Layer 2. Builds the claim relationship graph (typed edges) and discourse maps (positions, strongest cases, biggest holes, live cruxes, empty chairs).

**assessment.py** handles Layer 3. Orchestrates the full assessment pipeline: compliance detection, multi-trial verification with varied prompt framings, cross-model adversarial checking, and the oracle cascade. Produces per-claim ClaimConfidence objects with dimensional breakdowns.

**pipeline.py** is the orchestrator. The `EpistackPipeline` class runs ingest, structure, assess in sequence and provides export/reporting utilities.

**cli.py** is the command-line interface. Provides `epistack demo`, `epistack g3-test`, and the full pipeline commands (ingest, structure, assess, report).

## Design decisions

**Multiplicative scoring.** A claim with perfect source quality but zero logical consistency should not score 0.5. It should score 0. Any catastrophic failure in one dimension means the claim cannot be relied on.

**Compliance detection before verification.** If the verification prompt itself pushes the model past G3, the verifier fabricates confidence. Checking prompts first prevents this.

**Cross-model-family, not same-model.** Models from the same training family have correlated blind spots. Cross-family checking catches things same-family misses. Validated across 21 autonomous researcher runs.

**Wilson CIs over point estimates.** Passing 4/5 trials is not the same confidence as passing 8/10 even though both are 80%. Wilson intervals handle small-N properly.
