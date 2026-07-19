"""Tests for crux detection — binary entropy × cascade BFS."""

import tempfile
from pathlib import Path

from epistack.crux_detection import (
    binary_entropy,
    compute_crux_scores,
    get_top_cruxes,
    CASCADE_EDGE_TYPES,
)
from epistack.store import EpistemicStore


def _make_graph(tmp_path) -> EpistemicStore:
    """Build a synthetic graph with known crux structure.

    Structure:
        clm_foundation (conf=0.5) --supports--> clm_mid (conf=0.7) --supports--> clm_target
        clm_irrelevant (conf=0.5) --supports--> clm_dead_end (conf=0.5)
        clm_certain (conf=0.95) --supports--> clm_target
        clm_framework (conf=0.5) --frames_differently--> clm_target  (EXCLUDED from cascade)
    """
    store = EpistemicStore(data_dir=tmp_path / "test")

    # Target (conclusion)
    store.append("claim.asserted", {"claim_id": "clm_target", "confidence": 0.8})

    # Foundation → mid → target (cascade path)
    store.append("claim.asserted", {"claim_id": "clm_foundation", "confidence": 0.5})
    store.append("claim.asserted", {"claim_id": "clm_mid", "confidence": 0.7})
    store.append("edge.asserted", {
        "edge_id": "e1", "edge_type": "supports",
        "source": "clm_foundation", "target": "clm_mid", "strength": 0.8,
    })
    store.append("edge.asserted", {
        "edge_id": "e2", "edge_type": "supports",
        "source": "clm_mid", "target": "clm_target", "strength": 0.8,
    })

    # Irrelevant path (doesn't reach target)
    store.append("claim.asserted", {"claim_id": "clm_irrelevant", "confidence": 0.5})
    store.append("claim.asserted", {"claim_id": "clm_dead_end", "confidence": 0.5})
    store.append("edge.asserted", {
        "edge_id": "e3", "edge_type": "supports",
        "source": "clm_irrelevant", "target": "clm_dead_end", "strength": 0.5,
    })

    # Certain claim (low entropy → low crux score)
    store.append("claim.asserted", {"claim_id": "clm_certain", "confidence": 0.95})
    store.append("edge.asserted", {
        "edge_id": "e4", "edge_type": "supports",
        "source": "clm_certain", "target": "clm_target", "strength": 0.9,
    })

    # Framework edge (should be EXCLUDED from cascade)
    store.append("claim.asserted", {"claim_id": "clm_framework", "confidence": 0.5})
    store.append("edge.asserted", {
        "edge_id": "e5", "edge_type": "frames_differently",
        "source": "clm_framework", "target": "clm_target", "strength": 0.7,
    })

    return store


def test_binary_entropy_peaks_at_half():
    assert binary_entropy(0.5) == 1.0


def test_binary_entropy_zero_at_extremes():
    assert binary_entropy(0.0) == 0.0
    assert binary_entropy(1.0) == 0.0
    assert binary_entropy(0.001) < 0.02


def test_binary_entropy_symmetric():
    assert abs(binary_entropy(0.3) - binary_entropy(0.7)) < 0.0001


def test_foundation_is_top_crux(tmp_path):
    """The uncertain claim with cascade path to target should score highest."""
    store = _make_graph(tmp_path)
    scores = compute_crux_scores(store, target_ids=["clm_target"])

    # clm_foundation has conf=0.5 (max entropy) AND cascade to target
    assert scores["clm_foundation"] > scores.get("clm_certain", 0)
    assert scores["clm_foundation"] > scores.get("clm_irrelevant", 0)


def test_certain_claim_low_score(tmp_path):
    """High-confidence claims have lower crux score than uncertain ones."""
    store = _make_graph(tmp_path)
    scores = compute_crux_scores(store, target_ids=["clm_target"])

    # clm_certain (conf=0.95) should score much lower than clm_foundation (conf=0.5)
    assert scores["clm_certain"] < scores["clm_foundation"]


def test_irrelevant_claim_zero_score(tmp_path):
    """Claims that can't reach any target get zero cascade."""
    store = _make_graph(tmp_path)
    scores = compute_crux_scores(store, target_ids=["clm_target"])

    # clm_irrelevant → clm_dead_end (doesn't reach clm_target)
    assert scores["clm_irrelevant"] == 0.0


def test_frames_differently_excluded_from_cascade(tmp_path):
    """frames_differently edges should NOT contribute to cascade."""
    store = _make_graph(tmp_path)
    scores = compute_crux_scores(store, target_ids=["clm_target"])

    # clm_framework connects via frames_differently only → no cascade
    assert scores["clm_framework"] == 0.0


def test_cascade_edge_types_correct():
    """Verify only supports/depends_on/is_crux_for form cascades."""
    assert "supports" in CASCADE_EDGE_TYPES
    assert "depends_on" in CASCADE_EDGE_TYPES
    assert "is_crux_for" in CASCADE_EDGE_TYPES
    assert "frames_differently" not in CASCADE_EDGE_TYPES
    assert "contradicts" not in CASCADE_EDGE_TYPES


def test_get_top_cruxes_returns_context(tmp_path):
    store = _make_graph(tmp_path)
    top = get_top_cruxes(store, target_ids=["clm_target"], n=3)

    assert len(top) > 0
    assert "claim_id" in top[0]
    assert "crux_score" in top[0]
    assert "entropy" in top[0]
    assert "confidence" in top[0]
    assert top[0]["crux_score"] > 0


def test_multiple_targets(tmp_path):
    """Crux scores should consider reach to ANY target."""
    store = _make_graph(tmp_path)
    # Add dead_end as a second target — now clm_irrelevant reaches a target
    scores = compute_crux_scores(store, target_ids=["clm_target", "clm_dead_end"])

    # clm_irrelevant should now have a positive score (reaches clm_dead_end)
    assert scores["clm_irrelevant"] > 0.0
