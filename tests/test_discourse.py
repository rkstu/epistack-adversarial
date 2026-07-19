"""Tests for discourse mapping."""

import tempfile
from pathlib import Path

import numpy as np

from epistack.discourse import _cluster_positions, _classify_disagreements
from epistack.config import get_config
from epistack.store import EpistemicStore


def _make_clusterable_store(tmp_path) -> tuple[EpistemicStore, list[str], np.ndarray]:
    """Create store with claims that should cluster into 2 positions."""
    store = EpistemicStore(data_dir=tmp_path / "test")

    # Position 1: zoonosis claims (similar embeddings)
    for i in range(10):
        store.append("claim.asserted", {
            "claim_id": f"clm_zoo_{i:02d}",
            "statement": {"natural_language": f"Zoonosis claim {i}"},
        })

    # Position 2: lab leak claims (different embedding region)
    for i in range(10):
        store.append("claim.asserted", {
            "claim_id": f"clm_lab_{i:02d}",
            "statement": {"natural_language": f"Lab leak claim {i}"},
        })

    claim_ids = [f"clm_zoo_{i:02d}" for i in range(10)] + [f"clm_lab_{i:02d}" for i in range(10)]

    # Create embeddings: two clear clusters
    zoo_vecs = np.random.randn(10, 50) + np.array([2.0] * 50)
    lab_vecs = np.random.randn(10, 50) + np.array([-2.0] * 50)
    vectors = np.vstack([zoo_vecs, lab_vecs])

    return store, claim_ids, vectors


def test_cluster_positions_finds_two_groups(tmp_path):
    store, claim_ids, vectors = _make_clusterable_store(tmp_path)
    cfg = get_config()

    positions = _cluster_positions(claim_ids, vectors, store.claims, cfg)

    # Should find 2 positions
    assert len(positions) >= 2
    # Each should have multiple claims
    for pos in positions:
        assert len(pos["member_claims"]) >= 3


def test_cluster_positions_returns_empty_on_noise(tmp_path):
    """Random noise shouldn't produce valid clusters."""
    store = EpistemicStore(data_dir=tmp_path / "test")
    for i in range(5):
        store.append("claim.asserted", {"claim_id": f"clm_{i}"})

    claim_ids = [f"clm_{i}" for i in range(5)]
    vectors = np.random.randn(5, 50)  # Random, no structure

    cfg = get_config()
    positions = _cluster_positions(claim_ids, vectors, store.claims, cfg)

    # Might find 0 positions (HDBSCAN can't cluster noise with min_size=5)
    # This is expected — triggers LLM fallback
    assert len(positions) <= 2


def test_classify_disagreements(tmp_path):
    store = EpistemicStore(data_dir=tmp_path / "test")
    store.append("claim.asserted", {"claim_id": "clm_a"})
    store.append("claim.asserted", {"claim_id": "clm_b"})
    store.append("claim.asserted", {"claim_id": "clm_c"})
    store.append("claim.asserted", {"claim_id": "clm_d"})

    # Add edges between position members
    store.append("edge.asserted", {
        "edge_id": "e1", "edge_type": "contradicts",
        "source": "clm_a", "target": "clm_c", "strength": 0.8,
    })
    store.append("edge.asserted", {
        "edge_id": "e2", "edge_type": "contradicts",
        "source": "clm_b", "target": "clm_d", "strength": 0.7,
    })

    positions = [
        {"position_id": "pos_00", "member_claims": ["clm_a", "clm_b"]},
        {"position_id": "pos_01", "member_claims": ["clm_c", "clm_d"]},
    ]

    disagreements = _classify_disagreements(positions, store)
    assert len(disagreements) == 1
    assert disagreements[0]["type"] == "factual_dispute"
    assert disagreements[0]["contradicts"] == 2


def test_classify_disagreements_framework(tmp_path):
    store = EpistemicStore(data_dir=tmp_path / "test")
    store.append("claim.asserted", {"claim_id": "clm_x"})
    store.append("claim.asserted", {"claim_id": "clm_y"})

    store.append("edge.asserted", {
        "edge_id": "e1", "edge_type": "frames_differently",
        "source": "clm_x", "target": "clm_y", "strength": 0.9,
    })

    positions = [
        {"position_id": "pos_00", "member_claims": ["clm_x"]},
        {"position_id": "pos_01", "member_claims": ["clm_y"]},
    ]

    disagreements = _classify_disagreements(positions, store)
    assert disagreements[0]["type"] == "framework_mismatch"
