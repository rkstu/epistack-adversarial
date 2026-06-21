"""Tests for scoring module — verifies Wilson CI and epistemic scoring."""

import sys
sys.path.insert(0, "../src")

from epistack.scoring import wilson_ci, score_cross_model, score_source_quality, classify_confidence, EpistemicScore


def test_wilson_ci_basic():
    lower, upper = wilson_ci(4, 5)
    assert 0.3 < lower < 0.6, f"Expected lower ~0.4, got {lower}"
    assert 0.9 < upper <= 1.0, f"Expected upper ~0.99, got {upper}"


def test_wilson_ci_perfect():
    lower, upper = wilson_ci(5, 5)
    assert lower > 0.5, f"Expected lower > 0.5, got {lower}"
    assert upper == 1.0


def test_wilson_ci_zero():
    lower, upper = wilson_ci(0, 5)
    assert lower == 0.0
    assert upper < 0.5


def test_wilson_ci_no_trials():
    lower, upper = wilson_ci(0, 0)
    assert lower == 0.0
    assert upper == 1.0


def test_cross_model_agreement():
    results = {"claude-sonnet": True, "gpt-4o": True, "gemini-pro": False}
    score = score_cross_model(results)
    assert 0.5 < score < 0.8, f"Expected ~0.67, got {score}"


def test_cross_model_mono_family_penalty():
    results = {"claude-sonnet": True, "claude-haiku": True}
    score = score_cross_model(results)
    # Same family gets 30% penalty
    assert score < 1.0, "Same-family should be penalized"
    assert score == 0.7, f"Expected 0.7, got {score}"


def test_source_quality_retracted():
    score = score_source_quality({"retracted": True})
    assert score == 0.0


def test_source_quality_high():
    score = score_source_quality({
        "peer_reviewed": True,
        "citation_count": 150,
        "author_h_index": 25,
    })
    assert score >= 0.99


def test_multiplicative_scoring():
    score = EpistemicScore(
        evidence_strength=0.8,
        logical_consistency=0.9,
        adversarial_robustness=0.7,
        source_quality=0.85,
        cross_model_agreement=0.6,
    )
    expected = 0.8 * 0.9 * 0.7 * 0.85 * 0.6
    assert abs(score.composite - expected) < 0.001


def test_multiplicative_zero_propagation():
    score = EpistemicScore(
        evidence_strength=0.8,
        logical_consistency=0.0,  # zero kills total
        adversarial_robustness=0.9,
        source_quality=0.95,
        cross_model_agreement=0.8,
    )
    assert score.composite == 0.0


def test_classify_confidence():
    assert classify_confidence(0.85, 0.8) == "HIGH"
    assert classify_confidence(0.6, 0.8) == "MEDIUM"
    assert classify_confidence(0.3, 0.8) == "LOW"
    assert classify_confidence(0.1, 0.8) == "INSUFFICIENT_EVIDENCE"
    assert classify_confidence(0.9, 0.4) == "CONTESTED"


if __name__ == "__main__":
    test_wilson_ci_basic()
    test_wilson_ci_perfect()
    test_wilson_ci_zero()
    test_wilson_ci_no_trials()
    test_cross_model_agreement()
    test_cross_model_mono_family_penalty()
    test_source_quality_retracted()
    test_source_quality_high()
    test_multiplicative_scoring()
    test_multiplicative_zero_propagation()
    test_classify_confidence()
    print("All scoring tests passed!")
