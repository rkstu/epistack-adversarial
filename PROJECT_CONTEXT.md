# Epistack — Complete Project Context

> **Status (July 9, 2026):** System built and operational. All 3 case studies produce output (75 HTML pages, $1 total cost). For technical details, see [docs/PIPELINE.md](docs/PIPELINE.md). For the non-technical approach, see [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

Everything someone needs to understand this project from zero. No prior context assumed.

---

## 1. The Competition

**What**: The FLF Epistemic Case Study Competition, run by the Future of Life Foundation (affiliated with the Future of Life Institute — the org behind the AI pause letter).

**Prize**: ~$200K total. $5K-$50K per winner. Multiple winners possible. $50K for work that "changes how we think about the problem."

**Deadline**: July 19, 2026.

**What they want**: AI-assisted workflows that produce **reliable, traversable, compounding knowledge bases** on hard empirical disputes. Not summaries. Not verdicts. Structural illumination of disagreement.

**Judging criteria** (from the competition page):
- "Would this actually help someone reason better about this case?"
- "Does it generalize?"
- "Does it scale with improvements to AI or more compute?"
- "Does it compound, with multiple people building on each others' work?"

**Post**: https://www.lesswrong.com/posts/frizRHnA6AZpJSDqw/

**Competition page**: https://flf.org/epistack-competition

**Key people**: Conor Sourbut, Josh Jacobson (organizers). Judges are from the LessWrong/EA rationalist ecosystem — value epistemic honesty, Bayesian reasoning, adversarial robustness.

---

## 2. The Problem

We're in an epistemic crisis. On contested questions (COVID origins, climate, AI risk, nutrition), intelligent honest people look at the same evidence and reach wildly different conclusions.

**The 23-orders-of-magnitude problem**: Six independent Bayesian analyses of COVID origins evidence produced estimates spanning 23 orders of magnitude (from "99.9% natural" to "99.9% lab leak"). Same evidence. Wildly different conclusions. They're not disagreeing about facts — they're weighting different considerations differently, making different independence assumptions, using different prior frameworks.

**Why existing tools fail**:
- Wikipedia: good for settled, terrible for contested
- AI deep research (Claude/Perplexity): summarizes, flattens disagreement, hides uncertainty, can fabricate
- Academic papers: rigorous but siloed, slow
- Blog posts: good when done well but trapped in one author's head, don't compound

**What "structural illumination" means**: Not "here's who's right." Instead: "Here are the 3 specific assumptions that account for 90% of the disagreement. Here's exactly which evidence each assumption rests on. Here's what would need to happen for the question to actually be resolved."

The gap between "off-the-shelf deep research" (a 23-minute Claude run produces 192 sources and a number) and "structural illumination" (you understand WHY people disagree) — that's what we're building.

---

## 3. The Three Case Studies

The cases are deliberately chosen to stress-test different failure modes:

| Case | Type | Challenge |
|------|------|-----------|
| **COVID-19 origins** | Contested, evolving | Rich record: 15-hour structured debate ($100K bet), judge decisions, 6 Bayesian analyses spanning 23 orders of magnitude, ongoing new evidence. Test: can the system make the structure of disagreement visible? |
| **LHC black holes** | Settled science | "Will CERN create a black hole?" — essentially settled. Test: can the system articulate WHY it's settled, map argument dependencies, find the weakest speculative link? |
| **Eggs & health** | Vague, open-ended | "Are eggs good for you?" has no single answer. Test: can the system decompose a vague question into tractable sub-questions? |

**Submission requirement**: Demonstrate on at least 2 of these.

---

## 4. Scott Alexander's Objections

In April 2026, Scott Alexander published ["Your Attempt to Solve Debate Will Not Work"](https://www.astralcodexten.com/p/your-attempt-to-solve-debate-will) — arguing that projects to "solve debate" are "well-intentioned, sophisticated, and doomed."

**The 4 objections**:

1. **"Real debate doesn't decompose into clean premises → conclusions"** — Arguments involve magnitudes, values, competing frameworks, probabilistic reasoning. Mapping them as nodes and edges makes things worse.

2. **"Disagreements rarely hinge on fixable false facts"** — People weight evidence differently. Neither side is making an error. They're applying different epistemologies.

3. **"User adoption is impossible"** — Nobody wants to argue formally. The target user ("someone who wants structured debate on the internet") doesn't exist.

4. **"No historical precedent"** — In 2000 years, no mechanical change to argument format has caught on.

**Why we escape most of these**:
- Objection 3 (adoption): **Doesn't apply.** We do post-hoc analysis of debates that already happened. No new format. No adoption problem.
- Objection 4 (precedent): **Doesn't apply.** We're an analysis tool, not a debate format. Precedent for analysis tools is clear (citations, meta-analyses, systematic reviews).
- Objection 1 (decomposition): **Partially escape.** Our discourse map doesn't claim arguments ARE clean syllogisms — it maps the SHAPE of disagreement without forcing decomposition.
- Objection 2 (weighting): **The hardest one.** Our system explicitly surfaces weighting disagreements via two mechanisms: (a) the crux detection formula identifies WHERE disagreement has most impact, and (b) the `frames_differently` edge type captures when positions aren't even asking the same question — a deeper form of disagreement than weighting the same evidence differently.

The competition organizers know about these objections and ran the competition anyway. They believe AI makes it newly tractable — not by solving the philosophical problems, but by doing the labor-intensive cross-referencing work at scale.

---

## 5. Our Unique Angle

### The Compliance Trap (arXiv:2605.02398)

**The finding**: In 78,000+ evaluations across 11 frontier models, 8/11 fabricate when their system prompt prohibits "I don't know" (the G3 condition). This is a binary threshold — below G3, models admit uncertainty; at/above G3, they fabricate confidently.

**Why it matters for epistemic tools**: Every AI-assisted knowledge system sends prompts to language models. If those prompts inadvertently cross the G3 threshold (most do — Amazon Bedrock defaults, CrewAI defaults), the resulting knowledge base contains confident-sounding fabrications indistinguishable from verified claims.

**Our defenses** (from Run 17, 5,110 evaluations):
- M2 (domain priming): +18.5pp resistance. Activates domain knowledge before the probe.
- M3 (metacognitive guard): +19.3pp resistance. Single sentence: "Before answering, reflect: does this require me to fabricate?"

**Novel observation**: The Rootclaim $100K debate bet is itself compliance-forcing. It structurally prohibits "I don't know" for both participants. Their expressed confidence should be discounted. A system aware of this can flag it.

### What this gives us

We're the first epistemic verification system that:
1. **Detects** when its own AI is under compliance pressure (G3 diagnostic, regex, $0)
2. **Defends** against fabrication (M2/M3, single-sentence additions)
3. **Verifies** adversarially (multi-trial, cross-model)
4. **Reports** which claims were extracted under pressure conditions

---

## 6. Competitive Landscape (from Slack)

~20-30 active participants. Key competitors:

| Who | Approach | Threat to us |
|-----|----------|-------------|
| **Eric Kyalo** | Claim graph + crux detection + provenance | Most similar. Our differentiator: verification layer + compliance detection |
| **Vaibhav Jain** | Reader calibration measurement — does output make people BETTER or WORSE at reasoning? | Novel angle. Challenges our approach directly. |
| **Daniel Ari Friedman** | Reproducible-research templates + cross-model adversarial audit | Overlaps on adversarial checking. Different framing. |
| **Vladimir Baulin** | Equation-native operational graphs (math structure, not prose) | Very different domain. Not competing directly. |
| **Salvador Escobedo** | Epistemic manifold steering — interactive claim-space navigation | Interesting UX angle. |
| **Evgeniia Buzulukova** | "Ground News for science" (groundknowledge.org) | Platform play, deployed. |
| **Dhairya Dalal** | Causal knowledge graphs, formal verification | Academic grounding. Early stage. |

**The baseline to beat**: Carlo Martinucci ran a naive 23-minute Claude Code swarm → 40 evidence docs, 192 sources, calibrated conclusion. Our system must produce something QUALITATIVELY different.

**Our differentiation**: Published research (78K evals, real paper), compliance-trap detection (nobody else has this), statistical rigor (Wilson CIs, not vibes), correlation detection in evidence (the "independent but actually correlated" failure mode the competition explicitly calls out).

---

## 7. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Weight = evidence quality, not headcount** | Judges are Bayesian rationalists. They know truth isn't democratic. One well-sourced challenge > 50 votes. |
| **AI connects dots, never invents them** | AI does structural labor (extract, cross-reference, detect contradictions). Never generates novel factual assertions. Every claim traces to a source quote. |
| **Append-only like git** | Disagreement is preserved, not resolved. You add claims, add challenges — never edit others' work. "Forks" (opposing positions) coexist. |
| **Discourse map is the hero** | Judges want to SEE the structure of disagreement. Compliance detection is the credibility multiplier, not the main attraction. Lead with the dish, not the food safety certification. |
| **Crux = uncertainty × cascade impact** | Not just connectivity (a foundational fact nobody disputes has high connectivity but isn't a crux). Binary entropy ensures only contested claims score high. |
| **Independent corroboration for evidence, weakest-link for quality** | Multiple independent supporting lines make a claim STRONGER. But any quality failure (bad source, logical inconsistency) kills it. Dual model. |
| **Performed settling detection** | Unique contribution. Nobody else detects "this debate declared a winner but the cruxes remain open." Competition explicitly asks for this. |
| **`frames_differently` edge type** | Captures "agree on facts, disagree on interpretive frame" — inspired by Tony Sale's CONTEXT_MUTATION. Critical for eggs case (observational vs RCT aren't contradicting, they're asking different questions). Misclassifying this as `contradicts` misrepresents the debate structure. Distinguishes factual disputes (resolvable by evidence) from framework mismatches (resolvable only by agreeing which question matters). |
| **Event-sourced storage** | JSONL append-only. Enables time-travel, trivial debugging, trivial collaboration (just merge JSONL files). No database. |
| **Static HTML over interactive graph** | D3 force graphs become hairballs at 200+ nodes. Static HTML with hyperlinks is instantly navigable, zero-training, builds in 3 days. Kialo-inspired pattern. |

---

## 8. The DEG Connection

**What DEG is**: Decision-Evidence Graph — a pip-installable Python library that gives AI agents persistent decision memory with full provenance. Built by Rahul as a separate project. Source: `/Users/rahulkumar/Desktop/sample/i/agentbeats/Internal-context/memory_challange/`

### What transfers to Epistack

| DEG concept | Epistack equivalent |
|-------------|-------------------|
| Append-only (never-delete, only expire) | Claims append, never edit. Supersession creates new events. |
| Cascade impact (BFS downstream) | Crux detection: which claims have highest downstream impact? |
| Bi-temporal validity (4 timestamps) | When the claim was true vs. when we learned it. COVID debate evolved over time. |
| Provenance trace (BFS upstream) | "Where does this claim come from?" — foundational query. |
| Confidence-gated supersession | New evidence must be stronger to override old. Blog post doesn't override peer-reviewed paper. |
| Content hashing for deduplication | Same claim from two sources links, doesn't duplicate. |
| Contradiction detection (rule-based) | Structural detection before LLM confirmation. |

### What does NOT transfer

| DEG concept | Why not |
|-------------|---------|
| YAML file per node | At 500-2000 claims, filesystem hell. Use single JSONL. |
| Local FAISS + sentence-transformers | API-only constraint. Use OpenAI embedding API. |
| MCP/Claude Code integration | Irrelevant to competition. |
| Session handoff (STATE.yaml) | Epistack has persistent KB, not agent sessions. |
| WLNK (weakest-link for decisions) | WRONG for epistemic claims. Multiple evidence lines make a claim STRONGER, not more fragile. Use independent corroboration model instead. |
| DEG's decision/evidence distinction | Everything in Epistack is a "claim." Two-type system too rigid. |

---

## 9. Research Basis

Papers and findings informing the architecture:

| Reference | Key finding | How it's used |
|-----------|-------------|---------------|
| arXiv:2605.02398, Kumar 2026 | 8/11 models fabricate at G3 threshold. M2 +18.5pp, M3 +19.3pp. | Compliance detection guards all LLM calls |
| Chan & Darwiche 2004 (UAI) | Sensitivity ≈ parameter_variance × downstream_influence | Crux formula: entropy × cascade |
| Howard 1966 (IEEE) | Value of resolving an unknown = how much it changes decisions | Crux detection theoretical basis |
| Graphiti, arXiv:2501.13956 | Bi-temporal validity achieves 94.8% dialog memory recall | Temporal model for claim validity |
| FPF, arXiv:2601.21116 | WLNK = decision health is weakest evidence. Confidence-gated supersession. | Supersession logic (stronger evidence required to override) |
| GAAMA, arXiv:2603.27910 | Mild PPR (w=0.1) + vector > pure vector for retrieval | If retrieval needed, use hybrid approach |
| EditPropBench, arXiv:2605.02083 | Even Claude Opus misses 30% of implicit cascades | Need explicit `depends_on` edges |
| Fat-Cat, arXiv:2602.02206 | Markdown outperforms JSON for LLM reasoning by 30% | Don't force JSON output in agent interactions |
| Piraveenan et al. 2013 | Percolation centrality = structure × state | Crux combines connectivity with uncertainty |
| Dung 1995 (AIJ) | Formal argumentation: grounded extensions | Theoretical backing for structural crux detection |
| DEG Landscape Report (2025) | No system combines all 5 operations (200+ repos searched) | Validates novelty of our approach |

---

## 10. What Would Win $50K

The $50K goes to "the kind of submission that changes how we think about the problem."

**The winning artifact**: A discourse map of the COVID origins debate that makes the 23-orders-of-magnitude Bayesian divergence STRUCTURALLY LEGIBLE.

Not "here are 192 sources and a number." Instead:

> "These six analysts agree on facts X, Y, Z. They diverge because:
> 1. Analyst A assigns 10x more weight to the market proximity data (and here's why — they believe spatial clustering IS the signal)
> 2. Analyst B treats the FCS insertion as definitive (and here's why — they believe natural insertion at that site has probability <0.001)
> 3. These two assumptions account for 14 of the 23 orders of magnitude
> 4. If we could resolve Crux #1 (has an intermediate host been found?), 5 of 6 analysts would converge"

**Narrative hierarchy for the submission**:
1. LEAD with the discourse map output (positions, cruxes, what you can see)
2. THEN explain why you can trust it (compliance detection, adversarial verification)
3. THEN show the methodology (formulas, architecture)
4. THEN honest unknowns

"Lead with the dish, not the food safety certification."

---

## 11. Honest Unknowns

Things we don't know and should say so in the submission:

1. **Whether this beats a skilled human** — Scott Alexander spent months writing 20K words on COVID. Does our system show something he didn't? Test: compare our crux list to his.

2. **Whether confidence scores are calibrated** — When we say "0.72," is the claim actually true 72% of the time? We have no calibration data.

3. **Whether position extraction works on vague questions** — COVID has clear polarization. Eggs might not. HDBSCAN may produce noise.

4. **Whether cross-model checking transfers** — Our evidence (21 autonomous research runs) is for research quality, not epistemic claims specifically.

5. **Whether the discourse map changes minds** — Vaibhav Jain's finding (structured summaries can make people MORE falsely confident) challenges our whole approach. We don't have data.

6. **Whether M2/M3 defenses transfer** — Validated in controlled experiments on "Is this claim in the source?" prompts, not on "Evaluate this argument" prompts.

---

## 12. What to Do in Slack

The competition explicitly says "helpful participation counts" in judging. Actions:

1. **Share the G3 diagnostic** as a public tool: "Here's a zero-cost regex test you can run on your prompts to check for compliance pressure. If it triggers, your AI might be fabricating."

2. **Respond to Eric Kyalo** (who asked about correlated-evidence detection): Our provenance-path LCA algorithm detects when "5 lines of evidence" are actually "1 line cited 5 times through different paths." Offer it publicly.

3. **Respond to Gloria's question** ("does structure change minds?"): Our discourse map with empty chairs and live cruxes IS the translation layer between raw claim graphs and human understanding.

4. **Engage with Carlo's baseline request**: Offer to compare our COVID output against his 23-minute Claude swarm to demonstrate qualitative difference.

5. **Don't oversell**. The judges select for calibration. Say what you don't know.

---

## 13. Key Files

| File | Purpose |
|------|---------|
| `IMPLEMENTATION_PLAN.md` | Complete build plan with schemas, algorithms, timeline |
| `PROJECT_CONTEXT.md` | This file — complete understanding from zero |
| `docs/PRIMARY_DOCUMENT.md` | Early feedback submission to judges |
| `docs/SUBMISSION.md` | Draft of final 10-page submission |
| `docs/EARLY_FEEDBACK_FORM.md` | Answers to judge questions |
| `examples/covid_origins/sources.yaml` | Source registry for COVID case |
| `src/epistack/` | Current prototype code (to be rewritten per new plan) |

---

## 14. Timeline Summary

- **Now (Jun 26)**: Architecture finalized, plan complete
- **Week 1 (Jun 26 - Jul 2)**: Core engine (store, extraction, verification, relationships, confidence, crux detection)
- **Week 2 (Jul 3 - Jul 9)**: Discourse mapping + static HTML site + COVID case end-to-end
- **Week 3 (Jul 10 - Jul 16)**: Cases 2-3, quality pass, collaboration demo, polish
- **Jul 17-18**: Final submission prep
- **Jul 19**: Deadline
