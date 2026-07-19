"""Tests for performed settling detection."""

import tempfile
from pathlib import Path

from epistack.settling import detect_performed_settling, _find_verdict_claims
from epistack.store import EpistemicStore


def _make_settling_graph(tmp_path) -> EpistemicStore:
    """Build graph where verdict depends on unresolved cruxes.

    Structure:
        clm_verdict ("judges ruled for zoonosis") conf=0.9
            ← supports ← clm_market_evidence (conf=0.7)
                ← supports ← clm_contested_crux (conf=0.5) ← is_crux_for → clm_verdict
        clm_framework_dep (conf=0.6) ← frames_differently → clm_other
    """
    store = EpistemicStore(data_dir=tmp_path / "test")

    # Verdict claim
    store.append("claim.asserted", {
        "claim_id": "clm_verdict",
        "statement": {"natural_language": "Both judges ruled in favor of the zoonosis hypothesis"},
        "confidence": 0.9,
    })

    # Supporting evidence
    store.append("claim.asserted", {
        "claim_id": "clm_market_evidence",
        "statement": {"natural_language": "Market evidence supports zoonotic spillover"},
        "confidence": 0.7,
    })
    store.append("edge.asserted", {
        "edge_id": "e1", "edge_type": "supports",
        "source": "clm_market_evidence", "target": "clm_verdict", "strength": 0.8,
    })

    # Contested crux in dependency chain
    store.append("claim.asserted", {
        "claim_id": "clm_contested_crux",
        "statement": {"natural_language": "The market was the origin, not amplification site"},
        "confidence": 0.5,  # Contested!
    })
    store.append("edge.asserted", {
        "edge_id": "e2", "edge_type": "supports",
        "source": "clm_contested_crux", "target": "clm_market_evidence", "strength": 0.7,
    })
    store.append("edge.asserted", {
        "edge_id": "e3", "edge_type": "is_crux_for",
        "source": "clm_contested_crux", "target": "clm_verdict", "strength": 0.9,
    })

    # Framework edge in dependency chain (Type 2)
    store.append("claim.asserted", {
        "claim_id": "clm_framework_dep",
        "statement": {"natural_language": "Epidemiological patterns indicate market origin"},
        "confidence": 0.6,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_other_frame",
        "statement": {"natural_language": "Molecular evidence suggests lab modification"},
        "confidence": 0.6,
    })
    store.append("edge.asserted", {
        "edge_id": "e4", "edge_type": "supports",
        "source": "clm_framework_dep", "target": "clm_market_evidence", "strength": 0.6,
    })
    store.append("edge.asserted", {
        "edge_id": "e5", "edge_type": "frames_differently",
        "source": "clm_framework_dep", "target": "clm_other_frame", "strength": 0.8,
    })

    return store


def test_detects_unresolved_cruxes(tmp_path):
    store = _make_settling_graph(tmp_path)
    results = detect_performed_settling(store, verdict_claim_ids=["clm_verdict"])

    assert len(results) == 1
    assert results[0]["detected"] is True
    assert "unresolved_cruxes" in results[0]["settling_type"]


def test_detects_framework_adjudication(tmp_path):
    store = _make_settling_graph(tmp_path)
    results = detect_performed_settling(store, verdict_claim_ids=["clm_verdict"])

    assert results[0]["detected"] is True
    assert "framework_adjudication" in results[0]["settling_type"]


def test_severity_reflects_contested_proportion(tmp_path):
    store = _make_settling_graph(tmp_path)
    results = detect_performed_settling(store, verdict_claim_ids=["clm_verdict"])

    assert results[0]["severity"] > 0
    assert results[0]["severity"] <= 1.0


def test_no_settling_when_all_resolved(tmp_path):
    store = EpistemicStore(data_dir=tmp_path / "test")
    store.append("claim.asserted", {
        "claim_id": "clm_verdict",
        "statement": {"natural_language": "The judges ruled for zoonosis"},
        "confidence": 0.95,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_support",
        "statement": {"natural_language": "Strong evidence supports verdict"},
        "confidence": 0.9,
    })
    store.append("edge.asserted", {
        "edge_id": "e1", "edge_type": "supports",
        "source": "clm_support", "target": "clm_verdict", "strength": 0.9,
    })

    results = detect_performed_settling(store, verdict_claim_ids=["clm_verdict"])
    assert results[0]["detected"] is False


def test_auto_detect_verdict_claims(tmp_path):
    store = EpistemicStore(data_dir=tmp_path / "test")
    store.append("claim.asserted", {
        "claim_id": "clm_v1",
        "statement": {"natural_language": "Both judges ruled in favor of zoonosis"},
        "confidence": 0.9,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_normal",
        "statement": {"natural_language": "The market had many animal vendors"},
        "confidence": 0.8,
    })

    verdicts = _find_verdict_claims(store)
    assert "clm_v1" in verdicts
    assert "clm_normal" not in verdicts


def test_explanation_includes_details(tmp_path):
    store = _make_settling_graph(tmp_path)
    results = detect_performed_settling(store, verdict_claim_ids=["clm_verdict"])

    explanation = results[0]["explanation"]
    assert "unresolved" in explanation.lower() or "contested" in explanation.lower()
    assert "framework" in explanation.lower()
