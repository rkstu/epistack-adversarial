# Epistack — Early Feedback Submission

> This was submitted to the competition organizers before the final submission. Kept as historical reference.

---

## 1. About you (2-3 sentences)

Applied AI Engineer at DevRev. I've spent the last six months measuring when frontier models fabricate under compliance pressure (arXiv:2605.02398, 78K evaluations). Also built Preseal (adversarial testing for AI agents, on PyPI) and won 1st at UC Berkeley RDI AgentX. See LinkedIn and litmusevals.org.

---

## 2. Submission type

Prototype tool/pipeline

---

## 3. Which layer(s) does your submission address?

All / integrated

---

## 4. Primary Document

See [docs/PRIMARY_DOCUMENT.md](PRIMARY_DOCUMENT.md)

---

## 5. Repo URL

https://github.com/rkstu/epistack-adversarial

---

## 6. What does your submission do?

The pipeline takes existing debate materials (papers, transcripts, blog posts) and produces a structured knowledge base where each claim has a statistically grounded confidence score instead of a single-pass AI assertion.

The part I think is new: I found empirically (arXiv:2605.02398) that AI fabricates under compliance pressure, and most epistemic tools unknowingly trigger this. My system checks for that pressure before sending verification prompts, applies defenses that recovered +18-19 percentage points in controlled testing, and verifies claims through multi-trial adversarial testing across different model families with proper confidence intervals.

Nobody needs to change how they argue. The system analyzes debates that already happened and makes the structure of disagreement navigable after the fact.

---

## 7. Interest in further paid work

Yes. Available 20-30 hours/week. I'd be most useful testing whether the compliance-trap defenses transfer to epistemic verification contexts (I expect they do but haven't proven it for this specific use case yet). Beyond that, mapping which production AI frameworks inadvertently push models past the fabrication threshold, and building the interoperability layer for shared knowledge bases. I have infrastructure (litmusevals.org, Preseal on PyPI) that extends naturally into this space.

---

## 8. Additional context

Aware of "Your Attempt to Solve Debate Will..." and the four hard objections. This is post-hoc analysis of existing debates, not a new format. No adoption problem.

One angle I haven't seen elsewhere: the Rootclaim $100K bet is itself compliance-forcing. It structurally prohibits "I don't know" for both debaters. A system aware of this can discount their confidence levels accordingly.

Open unknowns: whether this beats a skilled human with Claude deep research on the same material, whether discourse mapping works on vague questions (eggs case), whether cross-model checking transfers from research contexts to epistemic claims. Will report honestly on all three.

**Questions for judges:**

1. Is compliance-trap detection useful framing for the assessment layer, or too narrow?
2. For COVID: more valuable to explain WHY the six Bayesian analyses disagree by 23 orders of magnitude, or to produce an independent assessment?
3. How important is interoperability vs depth on worked examples?

---

## 9. How did you hear about this?

EA Forum. Compliance-induced fabrication is an epistemic failure mode at its core, so the connection to building better epistemic tools felt direct.
