# Epistack

**FLF Epistemic Case Study Competition, Feedback Request**
Rahul Kumar | July 2026

---

## How I'm Thinking About This

The core problem as I see it: when people disagree about something complex, the disagreement has structure that's invisible in the source materials. You can read all six Bayesian analyses of COVID origins and still not see clearly which specific assumptions account for the 23-order-of-magnitude spread between them. The structure exists but nobody has made it navigable.

So I built a system that takes debate materials (papers, transcripts, blog posts) and produces a static HTML site showing that structure. Not a summary, not a verdict. A picture of: what positions exist, what the strongest case for each is, where they actually disagree (the cruxes), what's missing from the discourse, and whether the debate declared a winner without resolving the underlying disagreements.

The idea is that someone looking at this output understands the shape of a debate faster and more accurately than reading the source materials themselves.

---

## What I've Done So Far

The system runs end-to-end on all 3 case studies. One command produces the full HTML output.

| Case | Claims | Positions | Cruxes | Framework mismatches | HTML pages |
|------|--------|-----------|--------|---------------------|------------|
| COVID origins | 230 | 3 | 10 | 78 | 29 |
| LHC black holes | 53 | 5 | 2 | 4 | 21 |
| Eggs & health | 60 | 5 | 4 | 11 | 22 |

Total cost for all 3: about $1. Each run takes about 15 minutes.

Every claim in the system traces to a direct quote from its source document. All 230 active COVID claims have `quote_verified: true`. If the AI can't point to where in the source a claim comes from, the claim is rejected.

Some specific things the system found on COVID:

The top crux (the claim whose resolution would most change downstream conclusions) is "WIV was conducting gain-of-function research in BSL-2 conditions." The score combines how uncertain the claim is with how many other conclusions depend on it. A foundational fact nobody disputes scores low (nothing to resolve), and a contested claim nothing depends on also scores low (resolving it changes nothing). Only claims that are both uncertain AND consequential score high.

The system detected "performed settling" on all 9 verdict claims: the debate declared winners but 92 supporting claims remain contested, and the verdict adjudicates between incompatible interpretive frameworks rather than resolving factual questions. The Rootclaim debate is the clearest example: judges ruled for zoonosis, $100K changed hands, but the empirical cruxes remain open.

On eggs: the system found 11 instances where research traditions aren't actually contradicting each other but are asking different questions about the same phenomenon (observational mortality studies vs mechanistic RCTs). The output shows this as a framework mismatch rather than forcing it into a "who's right" frame. The finding is that no single load-bearing crux exists for eggs because the apparent disagreement dissolves once you separate the methodological frames.

---

## How It Works

The pipeline has layers:

First, it extracts claims from source documents with mandatory source quotes. No quote, no claim enters the system. This prevents the AI from generating assertions not present in the original data.

Second, it maps relationships between claims (supports, contradicts, depends on, and a distinct type for framework mismatches where two claims address the same topic through different methodological lenses).

Third, it computes which claims matter most. The crux score is structural: binary entropy (how split the evidence is) times cascade impact (how many downstream conclusions depend on this claim, decaying with distance and correcting for redundancy). This is grounded in sensitivity analysis from Bayesian networks (Chan & Darwiche 2004) and value of information theory (Howard 1966).

Fourth, it detects correlated evidence. When multiple claims appear to independently support a conclusion but trace back to the same underlying source in the provenance graph, the confidence model doesn't count them as independent. Five articles citing the same dataset counts as roughly 1.2 independent lines, not 5.

Fifth, it checks for compliance pressure before every AI call. My research (arXiv:2605.02398, "Compliance-Induced Epistemic Collapse," 78K evaluations across 11 models) found that 8 of 11 frontier models fabricate when their prompt prohibits "I don't know." The system detects when prompts cross this threshold and applies defenses that recover 18-19 percentage points in controlled testing.

The system is provider-agnostic (one config file change switches between models). Storage is event-sourced and append-only, which means someone else can add claims or challenges without modifying existing structure.

---

## What I Genuinely Don't Know

Whether the output helps someone reason better than a careful 30-minute Claude Deep Research run on the same topic. The system produces structural illumination, not a summary — these are different trade-offs.

Whether confidence scores are calibrated. Currently they're relative rankings, not probabilities.

Whether M2/M3 defenses transfer from factual verification prompts to evaluative/argumentative prompts — validated in controlled experiments, not yet for this specific context.

---

## Feedback I'd Find Useful

1. The Bayesian divergence decomposition (showing which specific assumptions account for the 23-OOM spread): is this the direction that would be most valuable? Or is the current position/crux/settling structure already the right level of output?

2. Depth vs breadth: COVID is much richer than LHC or Eggs. Should I go deeper on COVID (more sources, the Bayesian decomposition) or is the current three-case breadth the right balance?

3. The framework mismatch distinction (eggs case: "these aren't contradicting, they're asking different questions"): is identifying and surfacing that distinction useful? Or is it too fine-grained?

4. Is the collaboration protocol (append claims/challenges, system re-evaluates) sufficient to demonstrate compounding? Or would you want to see something more elaborate?

5. What's the gap between what I've described here and something that would genuinely change how you think about the problem? I'd rather hear that directly than guess.

---

**References**

arXiv:2605.02398. "Compliance-Induced Epistemic Collapse." 78K evaluations, 11 models. May 2026.

Chan & Darwiche 2004. "Sensitivity Analysis in Bayesian Networks." UAI.

Howard 1966. "Information Value Theory." IEEE.

GitHub: https://github.com/rkstu/epistack-adversarial — Full source, 103 tests, pre-built output included.
