"""Tests for dual confidence model."""

import tempfile
from pathlib import Path

from epistack.confidence import (
    compute_claim_confidence,
    _detect_correlation,
    _cluster_correlated,
    _compute_evidence_score,
    ConfidenceResult,
)
from epistack.config import get_config
from epistack.store import EpistemicStore


def _make_store(tmp_path) -> EpistemicStore:
    return EpistemicStore(data_dir=tmp_path / "test")


def test_no_evidence_returns_prior(tmp_path):
    store = _make_store(tmp_path)
    store.append("claim.asserted", {
        "claim_id": "clm_alone",
        "statement": {"natural_language": "An isolated claim"},
        "confidence": 0.5,
        "quote_verified": True,
    })

    result = compute_claim_confidence("clm_alone", store)
    # No supporting evidence → evidence_score = 0.5 (prior)
    assert result.evidence_score == 0.5
    # Final is evidence × quality dimensions — with unknown source quality, lands low
    assert result.final_confidence < 0.5


def test_supported_claim_higher_confidence(tmp_path):
    store = _make_store(tmp_path)
    store.append("claim.asserted", {
        "claim_id": "clm_target",
        "statement": {"natural_language": "Target claim"},
        "confidence": 0.5,
        "quote_verified": True,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_evidence",
        "statement": {"natural_language": "Supporting evidence"},
        "source_url": "https://independent-source.com",
        "category": "empirical",
    })
    store.append("edge.asserted", {
        "edge_id": "edg_001",
        "edge_type": "supports",
        "source": "clm_evidence",
        "target": "clm_target",
        "strength": 0.8,
    })

    result = compute_claim_confidence("clm_target", store)
    assert result.evidence_score > 0.5  # Better than prior


def test_assessment_evidence_weighted_lower(tmp_path):
    store = _make_store(tmp_path)
    store.append("claim.asserted", {
        "claim_id": "clm_target",
        "statement": {"natural_language": "Target claim"},
        "confidence": 0.5,
        "quote_verified": True,
    })
    # Empirical evidence
    store.append("claim.asserted", {
        "claim_id": "clm_emp",
        "statement": {"natural_language": "Empirical support"},
        "source_url": "https://source1.com",
        "category": "empirical",
    })
    store.append("edge.asserted", {
        "edge_id": "edg_emp",
        "edge_type": "supports",
        "source": "clm_emp",
        "target": "clm_target",
        "strength": 0.8,
    })

    result_emp = compute_claim_confidence("clm_target", store)

    # Now replace with assessment evidence (same strength but different category)
    store2 = _make_store(Path(tempfile.mkdtemp()) / "t2")
    store2.append("claim.asserted", {
        "claim_id": "clm_target",
        "statement": {"natural_language": "Target claim"},
        "confidence": 0.5,
        "quote_verified": True,
    })
    store2.append("claim.asserted", {
        "claim_id": "clm_assess",
        "statement": {"natural_language": "Assessment support"},
        "source_url": "https://source1.com",
        "category": "assessment",
    })
    store2.append("edge.asserted", {
        "edge_id": "edg_assess",
        "edge_type": "supports",
        "source": "clm_assess",
        "target": "clm_target",
        "strength": 0.8,
    })

    result_assess = compute_claim_confidence("clm_target", store2)

    # Assessment evidence should produce lower score
    assert result_assess.evidence_score < result_emp.evidence_score


def test_correlation_detection_same_source():
    ev_a = {"provenance_path": ["https://paper.com"]}
    ev_b = {"provenance_path": ["https://paper.com"]}
    assert _detect_correlation(ev_a, ev_b) == 1.0


def test_correlation_detection_independent():
    ev_a = {"provenance_path": ["https://source1.com"]}
    ev_b = {"provenance_path": ["https://source2.com"]}
    assert _detect_correlation(ev_a, ev_b) == 0.0


def test_clustering_groups_correlated():
    cfg = get_config()
    evidence = [
        {"strength": 0.7, "provenance_path": ["https://same.com"]},
        {"strength": 0.8, "provenance_path": ["https://same.com"]},
        {"strength": 0.6, "provenance_path": ["https://independent.com"]},
    ]
    clusters = _cluster_correlated(evidence, cfg)
    # First two should cluster together, third is independent
    assert len(clusters) == 2


def test_noisy_or_independent_lines_strengthen():
    cfg = get_config()
    # Two independent lines of evidence
    evidence = [
        {"strength": 0.6, "provenance_path": ["https://src1.com"]},
        {"strength": 0.6, "provenance_path": ["https://src2.com"]},
    ]
    score = _compute_evidence_score(evidence, cfg)
    # noisy-OR: 1 - (1-0.6)(1-0.6) = 1 - 0.16 = 0.84
    assert abs(score - 0.84) < 0.01


def test_noisy_or_correlated_dont_strengthen_much():
    cfg = get_config()
    # Two correlated lines (same source)
    evidence = [
        {"strength": 0.6, "provenance_path": ["https://same.com"]},
        {"strength": 0.6, "provenance_path": ["https://same.com"]},
    ]
    score_corr = _compute_evidence_score(evidence, cfg)

    # Independent lines
    evidence_ind = [
        {"strength": 0.6, "provenance_path": ["https://src1.com"]},
        {"strength": 0.6, "provenance_path": ["https://src2.com"]},
    ]
    score_ind = _compute_evidence_score(evidence_ind, cfg)

    # Correlated should be weaker than independent
    assert score_corr < score_ind


def test_contradiction_lowers_quality(tmp_path):
    store = _make_store(tmp_path)
    store.append("claim.asserted", {
        "claim_id": "clm_target",
        "statement": {"natural_language": "Target"},
        "confidence": 0.5,
        "quote_verified": True,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_contra",
        "statement": {"natural_language": "Contradicting claim"},
        "confidence": 0.8,
    })
    store.append("edge.asserted", {
        "edge_id": "edg_c",
        "edge_type": "contradicts",
        "source": "clm_contra",
        "target": "clm_target",
        "strength": 0.9,
    })

    result = compute_claim_confidence("clm_target", store)
    # Should have lower dimension_score due to contradiction
    assert result.dimension_score < 0.9
