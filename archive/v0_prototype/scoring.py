"""Pass-cubed statistical scoring adapted from Preseal for epistemic claim verification.

Ported from: DAST/preseal/src/preseal/scorer.py
Adaptation: security dimensions → epistemic dimensions
"""

import math
from dataclasses import dataclass
from typing import Optional


def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple:
    """Wilson score confidence interval for binomial proportion.

    Returns (lower, upper) bounds. Handles edge cases gracefully.
    Directly ported from preseal/src/preseal/scorer.py.
    """
    if trials == 0:
        return (0.0, 1.0)

    p_hat = successes / trials
    denominator = 1 + z * z / trials
    center = (p_hat + z * z / (2 * trials)) / denominator
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * trials)) / trials) / denominator

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)


@dataclass
class EpistemicScore:
    """Multi-dimensional epistemic quality score.

    Multiplicative: any zero dimension kills the total score.
    Mirrors Preseal's DimensionScores but for epistemic verification.
    """
    evidence_strength: float  # Did the claim survive verification trials?
    logical_consistency: float  # Is it consistent with other claims in the DAG?
    adversarial_robustness: float  # Did it survive red-team attacks?
    source_quality: float  # How credible are the backing sources?
    cross_model_agreement: float  # Do different model families agree?

    @property
    def composite(self) -> float:
        """Multiplicative composite — any zero propagates."""
        return (
            self.evidence_strength
            * self.logical_consistency
            * self.adversarial_robustness
            * self.source_quality
            * self.cross_model_agreement
        )

    @property
    def weakest_dimension(self) -> tuple:
        """Returns (name, value) of the weakest dimension."""
        dims = {
            "evidence_strength": self.evidence_strength,
            "logical_consistency": self.logical_consistency,
            "adversarial_robustness": self.adversarial_robustness,
            "source_quality": self.source_quality,
            "cross_model_agreement": self.cross_model_agreement,
        }
        weakest = min(dims, key=dims.get)
        return (weakest, dims[weakest])


def score_claim_trials(successes: int, trials: int) -> tuple:
    """Score a claim based on verification trial results.

    Returns (point_estimate, wilson_ci_lower, wilson_ci_upper).
    """
    if trials == 0:
        return (0.0, 0.0, 1.0)

    point = successes / trials
    lower, upper = wilson_ci(successes, trials)
    return (point, lower, upper)


def score_cross_model(results: dict) -> float:
    """Score cross-model agreement.

    results: {model_family: bool} — True if model verified the claim.
    Returns agreement ratio. Handles the case where disagreement
    across families is more informative than within-family agreement.
    """
    if not results:
        return 0.0

    families = set()
    agreements = 0
    total = 0

    for model, verified in results.items():
        family = model.split("/")[0] if "/" in model else model.split("-")[0]
        families.add(family)
        if verified:
            agreements += 1
        total += 1

    if len(families) < 2:
        # Same-family agreement is worth less
        return (agreements / total) * 0.7  # 30% penalty for mono-family

    return agreements / total


def score_source_quality(source_signals: dict) -> float:
    """Score source credibility from available signals.

    Signals may include: citation_count, retraction_status, peer_reviewed,
    author_h_index, publication_venue_impact, date_published.
    """
    score = 0.5  # default unknown

    if source_signals.get("retracted"):
        return 0.0

    if source_signals.get("peer_reviewed"):
        score += 0.2

    citation_count = source_signals.get("citation_count", 0)
    if citation_count > 100:
        score += 0.2
    elif citation_count > 10:
        score += 0.1

    if source_signals.get("author_h_index", 0) > 20:
        score += 0.1

    return min(1.0, score)


def classify_confidence(ci_lower: float, cross_model: float) -> str:
    """Classify overall confidence level.

    Maps to human-readable categories matching the competition's
    expectation of transparent confidence reporting.
    """
    if cross_model < 0.6:
        return "CONTESTED"
    if ci_lower > 0.8:
        return "HIGH"
    if ci_lower > 0.5:
        return "MEDIUM"
    if ci_lower > 0.2:
        return "LOW"
    return "INSUFFICIENT_EVIDENCE"
