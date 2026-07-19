"""Tests for scoring module — verifies Wilson CI and cross-model scoring."""

from epistack.scoring import wilson_ci, score_cross_model, score_source_quality


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
