"""Tests for relationship detection."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from epistack.relationships import (
    _find_candidate_pairs,
    _parse_json_response,
    _parse_json_array,
    load_embeddings,
)
from epistack.store import EpistemicStore


def _make_store_with_claims(tmp_path) -> tuple[EpistemicStore, list[str]]:
    store = EpistemicStore(data_dir=tmp_path / "test")
    store.append("claim.asserted", {
        "claim_id": "clm_0001",
        "statement": {"natural_language": "The market was the epicenter"},
        "source_url": "https://source1.com",
    })
    store.append("claim.asserted", {
        "claim_id": "clm_0002",
        "statement": {"natural_language": "The market was an amplification site"},
        "source_url": "https://source2.com",
    })
    store.append("claim.asserted", {
        "claim_id": "clm_0003",
        "statement": {"natural_language": "WIV conducted gain-of-function research"},
        "source_url": "https://source2.com",
    })
    return store, ["clm_0001", "clm_0002", "clm_0003"]


def test_find_candidate_pairs_includes_both_source_types(tmp_path):
    store, claim_ids = _make_store_with_claims(tmp_path)

    # Create embeddings where clm_0001 and clm_0002 are similar (same topic)
    emb_matrix = np.array([
        [1.0, 0.0, 0.0],  # clm_0001 (source1)
        [0.95, 0.05, 0.0],  # clm_0002 (source2, similar to 0001)
        [0.9, 0.1, 0.0],  # clm_0003 (source2, also similar)
    ])

    from epistack.config import get_config
    cfg = get_config()
    pairs = _find_candidate_pairs(store, claim_ids, emb_matrix, cfg)

    # clm_0001 and clm_0002 should be a pair (cross-source)
    pair_ids = [(a, b) for a, b, _, _ in pairs]
    assert ("clm_0001", "clm_0002") in pair_ids

    # clm_0002 and clm_0003 should ALSO be a pair now (within-source allowed)
    assert ("clm_0002", "clm_0003") in pair_ids

    # Cross-source pairs should be marked
    cross_flags = {(a, b): cross for a, b, _, cross in pairs}
    assert cross_flags[("clm_0001", "clm_0002")] is True
    assert cross_flags[("clm_0002", "clm_0003")] is False


def test_find_candidate_pairs_skips_superseded(tmp_path):
    store, claim_ids = _make_store_with_claims(tmp_path)
    store.claims["clm_0002"]["status"] = "superseded"

    emb_matrix = np.array([
        [1.0, 0.0, 0.0],
        [0.95, 0.05, 0.0],
        [0.0, 0.0, 1.0],
    ])

    from epistack.config import get_config
    cfg = get_config()
    pairs = _find_candidate_pairs(store, claim_ids, emb_matrix, cfg)

    pair_ids = [(a, b) for a, b, _, _ in pairs]
    assert all("clm_0002" not in p for p in pair_ids)


def test_parse_json_response_basic():
    response = '```json\n{"type": "supports", "evidence": "A strengthens B", "strength": 0.8}\n```'
    result = _parse_json_response(response)
    assert result["type"] == "supports"
    assert result["strength"] == 0.8


def test_parse_json_response_bare():
    response = '{"type": "contradicts", "evidence": "conflict", "strength": 0.9}'
    result = _parse_json_response(response)
    assert result["type"] == "contradicts"


def test_parse_json_response_invalid():
    assert _parse_json_response("Not JSON at all") is None
    assert _parse_json_response("") is None


def test_parse_json_array():
    response = '[{"type": "supports"}, {"type": "none"}]'
    result = _parse_json_array(response)
    assert len(result) == 2
    assert result[0]["type"] == "supports"


def test_load_embeddings_missing():
    result = load_embeddings(Path("/nonexistent"))
    assert result is None


def test_load_embeddings_roundtrip(tmp_path):
    ids = ["clm_001", "clm_002"]
    vectors = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    emb_path = tmp_path / "embeddings.npz"
    np.savez_compressed(emb_path, ids=ids, vectors=vectors)

    loaded = load_embeddings(tmp_path)
    assert loaded is not None
    loaded_ids, loaded_vecs = loaded
    assert loaded_ids == ids
    assert np.allclose(loaded_vecs, vectors)
