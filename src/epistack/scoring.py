"""Statistical scoring primitives for epistemic claim verification.

Ported from: DAST/preseal/src/preseal/scorer.py
Reference: arXiv:2503.01747 ("Don't use CLT in LLM evals")
"""

import math


def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion.

    Returns (lower, upper) bounds. Handles edge cases gracefully.
    Superior to normal approximation at small N.
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


def score_cross_model(results: dict[str, bool]) -> float:
    """Score cross-model agreement.

    results: {model_name: verified} — True if model verified the claim.
    Same-family agreement is penalized 30% (correlated training → correlated blind spots).
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
        return (agreements / total) * 0.7

    return agreements / total


def score_source_quality(source_signals: dict) -> float:
    """Score source credibility from available signals.

    Signals: citation_count, retraction_status, peer_reviewed,
    author_h_index, publication_venue_impact, date_published.
    """
    score = 0.5  # default: unknown quality

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
