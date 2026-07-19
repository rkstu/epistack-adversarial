"""Tests for event-sourced store."""

import json
import tempfile
from datetime import date
from pathlib import Path

from epistack.store import EpistemicStore


def make_store(tmp_path: Path | None = None) -> EpistemicStore:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    return EpistemicStore(data_dir=tmp_path / "test_case")


def test_append_and_replay(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {
        "claim_id": "clm_0001",
        "statement": {"natural_language": "SARS-CoV-2 emerged in Wuhan"},
        "confidence": 0.95,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_0002",
        "statement": {"natural_language": "The market was the epicenter"},
        "confidence": 0.72,
    })

    assert store.claim_count == 2
    assert store.tx == 2
    assert store.claims["clm_0001"]["confidence"] == 0.95

    # Replay from disk
    store2 = EpistemicStore(data_dir=tmp_path / "test_case")
    store2.replay()
    assert store2.claim_count == 2
    assert store2.claims["clm_0002"]["confidence"] == 0.72
    assert store2.tx == 2


def test_time_travel(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {"claim_id": "clm_a", "confidence": 0.5})
    store.append("claim.asserted", {"claim_id": "clm_b", "confidence": 0.6})
    store.append("claim.asserted", {"claim_id": "clm_c", "confidence": 0.7})

    # Travel to tx=2 — should only see clm_a and clm_b
    store2 = EpistemicStore(data_dir=tmp_path / "test_case")
    store2.replay_to(2)
    assert store2.claim_count == 2
    assert "clm_c" not in store2.claims


def test_supersession(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {
        "claim_id": "clm_old",
        "statement": {"natural_language": "Original claim"},
        "confidence": 0.6,
    })

    store.append("claim.asserted", {
        "claim_id": "clm_new",
        "statement": {"natural_language": "Updated claim"},
        "confidence": 0.8,
    }, supersedes="clm_old")

    assert store.claims["clm_old"]["status"] == "superseded"
    assert store.claims["clm_new"]["status"] == "active"


def test_confidence_gated_supersession(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {
        "claim_id": "clm_strong",
        "confidence": 0.9,
        "created_at": "2026-06-01",
    })

    # Low confidence should be blocked
    can, reason = store.can_supersede(0.5, "clm_strong")
    assert not can
    assert "BLOCKED" in reason

    # High confidence should succeed
    can, reason = store.can_supersede(0.95, "clm_strong")
    assert can


def test_edge_assertion(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {"claim_id": "clm_a"})
    store.append("claim.asserted", {"claim_id": "clm_b"})
    store.append("edge.asserted", {
        "edge_id": "edg_001",
        "edge_type": "supports",
        "source": "clm_a",
        "target": "clm_b",
        "strength": 0.8,
    })

    assert store.edge_count == 1
    assert store.edges["edg_001"]["edge_type"] == "supports"


def test_frames_differently_edge(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {"claim_id": "clm_rct"})
    store.append("claim.asserted", {"claim_id": "clm_observational"})
    store.append("edge.asserted", {
        "edge_id": "edg_frame",
        "edge_type": "frames_differently",
        "source": "clm_rct",
        "target": "clm_observational",
        "qualifiers": {
            "source_frame": "Causal mechanism (LDL under controlled conditions)",
            "target_frame": "Population outcome (mortality in free-living cohorts)",
        },
    })

    assert store.edges["edg_frame"]["edge_type"] == "frames_differently"


def test_snapshot_and_restore(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {"claim_id": "clm_x", "confidence": 0.77})
    store.append("edge.asserted", {"edge_id": "edg_x", "edge_type": "supports",
                                    "source": "clm_x", "target": "clm_x"})

    snapshot = store.snapshot()
    assert snapshot["tx"] == 2
    assert "clm_x" in snapshot["claims"]

    # Load into fresh store
    store2 = EpistemicStore(data_dir=tmp_path / "fresh")
    store2.load_snapshot(snapshot)
    assert store2.claim_count == 1
    assert store2.claims["clm_x"]["confidence"] == 0.77


def test_is_valid(tmp_path):
    store = make_store(tmp_path)

    store.append("claim.asserted", {
        "claim_id": "clm_valid",
        "valid_from": "2020-01-01",
        "valid_until": "2030-12-31",
    })
    store.append("claim.asserted", {
        "claim_id": "clm_expired",
        "valid_from": "2020-01-01",
        "valid_until": "2021-01-01",
    })

    assert store.is_valid("clm_valid")
    assert not store.is_valid("clm_expired")
    assert not store.is_valid("nonexistent")


def test_events_jsonl_format(tmp_path):
    store = make_store(tmp_path)
    store.append("claim.asserted", {"claim_id": "test_1"})

    with open(store.events_path) as f:
        line = f.readline()
        data = json.loads(line)

    assert "event_id" in data
    assert "event_type" in data
    assert "tx" in data
    assert "timestamp" in data
    assert "actor" in data
    assert "method" in data
    assert "payload" in data
    assert data["event_type"] == "claim.asserted"
    assert data["payload"]["claim_id"] == "test_1"
