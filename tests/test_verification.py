"""Tests for verification Layers 3-4."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from epistack.store import EpistemicStore
from epistack.verification import verify_claims, _parse_json


def _make_store_with_claims(tmp_path) -> EpistemicStore:
    store = EpistemicStore(data_dir=tmp_path / "test")
    store.append("claim.asserted", {
        "claim_id": "clm_good",
        "statement": {"natural_language": "The market was linked to early cases"},
        "relevant_quote": "The market was linked to many early cases of COVID-19",
        "quote_verified": True,
        "source_title": "Test Source",
        "confidence": 0.5,
    })
    store.append("claim.asserted", {
        "claim_id": "clm_bad",
        "statement": {"natural_language": "The virus was definitely engineered"},
        "relevant_quote": "The virus may have originated from a lab",
        "quote_verified": True,
        "source_title": "Test Source",
        "confidence": 0.5,
    })
    return store


def test_parse_json_valid():
    result = _parse_json('{"entailed": true, "reason": "matches", "severity": "pass"}')
    assert result["entailed"] is True


def test_parse_json_with_markdown():
    result = _parse_json('```json\n{"entailed": false, "severity": "overstatement"}\n```')
    assert result["entailed"] is False


def test_parse_json_invalid():
    assert _parse_json("not json") is None
    assert _parse_json("") is None


@pytest.mark.asyncio
async def test_layer3_passes_good_claim(tmp_path, monkeypatch):
    store = _make_store_with_claims(tmp_path)

    mock_call = AsyncMock(return_value=json.dumps({
        "entailed": True,
        "reason": "Quote directly states the claim",
        "severity": "pass",
    }))

    monkeypatch.setattr("epistack.verification.llm.call", mock_call)

    result = await verify_claims(store, layer3=True, layer4=False)
    assert result["failed_l3"] == 0
    assert result["verified"] == 2


@pytest.mark.asyncio
async def test_layer3_catches_overstatement(tmp_path, monkeypatch):
    store = _make_store_with_claims(tmp_path)

    call_count = [0]

    async def mock_call(prompt, **kwargs):
        call_count[0] += 1
        if "definitely engineered" in prompt:
            return json.dumps({
                "entailed": False,
                "reason": "Quote says 'may have' but claim says 'definitely'",
                "severity": "overstatement",
            })
        return json.dumps({"entailed": True, "reason": "ok", "severity": "pass"})

    monkeypatch.setattr("epistack.verification.llm.call", mock_call)

    result = await verify_claims(store, layer3=True, layer4=False)
    assert result["failed_l3"] == 1
    assert result["verified"] == 1


@pytest.mark.asyncio
async def test_layer4_runs_on_subset(tmp_path, monkeypatch):
    store = _make_store_with_claims(tmp_path)

    calls = []

    async def mock_call(prompt, **kwargs):
        calls.append(kwargs.get("role", "unknown"))
        return json.dumps({"verified": True, "issues": [], "confidence": 0.9})

    monkeypatch.setattr("epistack.verification.llm.call", mock_call)

    result = await verify_claims(store, layer3=False, layer4=True, layer4_top_pct=0.5)
    # With 2 claims and top_pct=0.5, should check 1
    l4_calls = [c for c in calls if c == "verification_cross"]
    assert len(l4_calls) == 1
