# examples — Case Study Source Registries

Source configurations for the three demonstration cases. Each `sources.yaml` defines URLs, metadata, and credibility signals that the pipeline uses to fetch and process debate materials.

## `covid_origins/`

**The contested case.** Six independent Bayesian analyses spanning 23 orders of magnitude. The Rootclaim debate ($100K bet, 15 hours, two PhD judges) provides structured adversarial source material.

5 sources: Scott Alexander's ACX analysis, both judge decisions, Weissman's Bayesian analysis, Rootclaim's response.

**Result**: 230 claims, 1,242 edges, 3 positions, 10 cruxes, settling detected on all 9 verdicts.

## `lhc_black_holes/`

**The settled case.** Whether CERN's LHC could create dangerous black holes. Scientific consensus is clear — the system should show WHY it's settled (dependency chain) rather than open cruxes.

5 sources: CERN FAQ, LSAG safety report, Wilczek/Busza paper, Wikipedia overview, Scientific American.

**Result**: 53 claims, 232 edges, 5 positions, 2 cruxes. Heavy consensus (215/232 edges = supports).

## `eggs_health/`

**The vague/open-ended case.** "Are eggs good for you?" has no single answer. The system decomposes it into framework mismatches — observational studies ask different questions than RCTs.

5 sources: Zhong BMJ (observational), Xu meta-analysis, Zhong JAMA (cohort), Soliman review (RCT evidence), Harvard Nutrition Source.

**Result**: 60 claims, 219 edges, 5 positions, 4 cruxes. **11 `frames_differently` edges** correctly identify methodology mismatches.
