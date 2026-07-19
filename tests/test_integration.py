"""Integration test: full pipeline on fixture data produces valid HTML site."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from epistack.store import EpistemicStore
from epistack.discourse import build_discourse_map
from epistack.generate_site import generate_site
from epistack.settling import detect_performed_settling


def _build_fixture_store(tmp_path) -> EpistemicStore:
    """Build a small store with known structure for integration testing."""
    store = EpistemicStore(data_dir=tmp_path / "fixture")

    # 6 claims: 3 zoonosis, 3 lab-leak
    store.append("claim.asserted", {
        "claim_id": "clm_z1",
        "statement": {"natural_language": "Early cases clustered at the Huanan Seafood Market"},
        "relevant_quote": "cases clustered at the market",
        "quote_verified": True,
        "category": "empirical",
        "source_url": "https://source1.com",
        "source_title": "Source 1",
        "confidence": 0.7,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_z2",
        "statement": {"natural_language": "Phylogenetic analysis shows two spillover events at market"},
        "relevant_quote": "two spillover events",
        "quote_verified": True,
        "category": "empirical",
        "source_url": "https://source1.com",
        "source_title": "Source 1",
        "confidence": 0.6,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_z3",
        "statement": {"natural_language": "The judges ruled for zoonosis hypothesis"},
        "relevant_quote": "judges ruled for zoonosis",
        "quote_verified": True,
        "category": "assessment",
        "source_url": "https://source1.com",
        "source_title": "Source 1",
        "confidence": 0.8,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_l1",
        "statement": {"natural_language": "WIV conducted gain-of-function research on coronaviruses"},
        "relevant_quote": "gain-of-function research",
        "quote_verified": True,
        "category": "empirical",
        "source_url": "https://source2.com",
        "source_title": "Source 2",
        "confidence": 0.5,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_l2",
        "statement": {"natural_language": "The furin cleavage site suggests engineering"},
        "relevant_quote": "furin cleavage site suggests",
        "quote_verified": True,
        "category": "empirical",
        "source_url": "https://source2.com",
        "source_title": "Source 2",
        "confidence": 0.4,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_l3",
        "statement": {"natural_language": "WIV database was removed before the outbreak"},
        "relevant_quote": "database was removed",
        "quote_verified": True,
        "category": "empirical",
        "source_url": "https://source2.com",
        "source_title": "Source 2",
        "confidence": 0.5,
    })

    # Edges: supports within each side, contradicts across
    store.append("edge.asserted", {"edge_id": "e1", "edge_type": "supports",
                                    "source": "clm_z1", "target": "clm_z3", "strength": 0.8})
    store.append("edge.asserted", {"edge_id": "e2", "edge_type": "supports",
                                    "source": "clm_z2", "target": "clm_z3", "strength": 0.7})
    store.append("edge.asserted", {"edge_id": "e3", "edge_type": "supports",
                                    "source": "clm_l1", "target": "clm_l2", "strength": 0.6})
    store.append("edge.asserted", {"edge_id": "e4", "edge_type": "contradicts",
                                    "source": "clm_l1", "target": "clm_z1", "strength": 0.7})
    store.append("edge.asserted", {"edge_id": "e5", "edge_type": "contradicts",
                                    "source": "clm_l2", "target": "clm_z2", "strength": 0.6})
    store.append("edge.asserted", {"edge_id": "e6", "edge_type": "frames_differently",
                                    "source": "clm_l3", "target": "clm_z1", "strength": 0.5})

    return store


def test_site_generation_from_fixture(tmp_path):
    """Integration: fixture store with pre-built discourse → valid HTML site."""
    store = _build_fixture_store(tmp_path)

    # Build discourse result manually (skip LLM calls)
    discourse_result = {
        "positions": [
            {
                "position_id": "pos_00",
                "stance": "Zoonotic spillover at the market",
                "core_commitment": "Virus emerged naturally",
                "summary": "Market cases indicate natural origin",
                "member_claims": ["clm_z1", "clm_z2", "clm_z3"],
                "strongest_claims": ["clm_z1"],
            },
            {
                "position_id": "pos_01",
                "stance": "Laboratory leak from WIV",
                "core_commitment": "Gain-of-function research caused release",
                "summary": "WIV research + furin site indicate engineering",
                "member_claims": ["clm_l1", "clm_l2", "clm_l3"],
                "strongest_claims": ["clm_l1"],
            },
        ],
        "cruxes": [
            {"claim_id": "clm_l1", "crux_score": 0.8, "text": "WIV GoF research",
             "confidence": 0.5, "entropy": 1.0, "category": "empirical", "source_title": "S2"},
        ],
        "empty_chairs": [
            {"perspective": "Lab safety whistleblowers", "why_it_matters": "Direct knowledge"},
        ],
        "disagreement_types": [
            {"position_a": "pos_00", "position_b": "pos_01", "type": "factual_dispute",
             "contradicts": 2, "frames_differently": 1},
        ],
        "questions": ["What is the origin?"],
    }

    # Generate site
    output_dir = tmp_path / "output"
    site_path = generate_site(store, discourse_result, output_dir, case_name="Integration Test")

    # Assertions: HTML site exists and has expected content
    assert (output_dir / "index.html").exists()
    index_html = (output_dir / "index.html").read_text()
    assert "Integration Test" in index_html
    assert "Claims" in index_html
    assert "Positions" in index_html
    assert "Zoonotic spillover" in index_html
    assert "Laboratory leak" in index_html
    assert "Lab safety whistleblowers" in index_html

    # Position pages exist
    assert (output_dir / "positions" / "pos_00.html").exists()
    assert (output_dir / "positions" / "pos_01.html").exists()

    # Crux page exists
    assert (output_dir / "cruxes" / "crux_00.html").exists()

    # Settling fires on the verdict claim
    settling = detect_performed_settling(store)
    detected = [r for r in settling if r.get("detected")]
    assert len(detected) >= 1
