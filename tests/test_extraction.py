"""Tests for grounded claim extraction with quote verification."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from epistack.extraction import (
    ExtractionConfig,
    chunk_document,
    verify_quote_containment,
    check_overclaiming,
    parse_extraction_response,
    extract_claims,
)
from epistack.store import EpistemicStore


# --- Layer 1: Quote Containment ---

def test_quote_containment_exact_match():
    source = "The Huanan Seafood Market was linked to many early cases of COVID-19."
    quote = "Huanan Seafood Market was linked to many early cases"
    assert verify_quote_containment(quote, source)


def test_quote_containment_case_insensitive():
    source = "SARS-CoV-2 was first identified in Wuhan, China."
    quote = "sars-cov-2 was first identified in wuhan"
    assert verify_quote_containment(quote, source)


def test_quote_containment_rejects_hallucinated():
    source = "The virus emerged in late 2019 in Wuhan."
    quote = "The virus was engineered in a laboratory setting"
    assert not verify_quote_containment(quote, source)


def test_quote_containment_rejects_too_short():
    source = "A long document about virology and epidemiology."
    quote = "viro"
    assert not verify_quote_containment(quote, source, min_length=10)


def test_quote_containment_fuzzy_match():
    source = "The phylogenetic analysis strongly suggests two separate introductions at the market"
    quote = "phylogenetic analysis suggests two separate introductions at the market"
    assert verify_quote_containment(quote, source)


def test_quote_containment_whitespace_normalized():
    source = "The   market   was   the    epicenter   of  early   cases."
    quote = "The market was the epicenter of early cases"
    assert verify_quote_containment(quote, source)


# --- Layer 2: Overclaiming Detection ---

def test_overclaiming_detects_absolute():
    assert check_overclaiming("This proves conclusively that the virus was natural")
    assert check_overclaiming("The evidence irrefutably shows lab origin")
    assert check_overclaiming("All scientists agree on natural origin")


def test_overclaiming_passes_qualified():
    assert not check_overclaiming("The evidence suggests a natural origin")
    assert not check_overclaiming("Most analyses point toward market exposure")
    assert not check_overclaiming("The data is consistent with lab leak hypothesis")


def test_overclaiming_multiple_flags():
    flags = check_overclaiming("This proves conclusively with no possible alternative")
    assert len(flags) == 2


# --- Chunking ---

def test_chunk_short_document():
    text = "Short document under chunk size."
    chunks = chunk_document(text, chunk_size=8000)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_long_document():
    text = "Paragraph one.\n\n" * 500  # ~8000 chars
    chunks = chunk_document(text, chunk_size=1000, overlap=100)
    assert len(chunks) > 1
    # Verify overlap
    for i in range(1, len(chunks)):
        assert chunks[i-1][-50:] in text
        assert chunks[i][:50] in text


# --- Response Parsing ---

def test_parse_json_array():
    response = '''```json
[
  {"natural_language": "Claim 1", "relevant_quote": "quote 1", "tags": ["test"]},
  {"natural_language": "Claim 2", "relevant_quote": "quote 2", "tags": ["test"]}
]
```'''
    claims = parse_extraction_response(response)
    assert len(claims) == 2
    assert claims[0]["natural_language"] == "Claim 1"


def test_parse_bare_json():
    response = '[{"natural_language": "Test", "relevant_quote": "Q"}]'
    claims = parse_extraction_response(response)
    assert len(claims) == 1


def test_parse_malformed_returns_empty():
    assert parse_extraction_response("This is not JSON at all") == []
    assert parse_extraction_response("") == []


# --- Full Extraction (with mock LLM) ---

@pytest.mark.asyncio
async def test_extract_claims_basic():
    source_text = (
        "The Huanan Seafood Market was linked to many early cases. "
        "Phylogenetic analysis shows two separate lineages. "
        "The WIV conducted gain-of-function research."
    )

    mock_response = json.dumps([
        {
            "natural_language": "The Huanan market was linked to early cases",
            "relevant_quote": "Huanan Seafood Market was linked to many early cases",
            "category": "empirical",
            "strength_of_evidence": "cohort",
            "assertion_strength": "certain",
            "tags": ["epidemiology"],
        },
        {
            "natural_language": "Two separate lineages were identified",
            "relevant_quote": "Phylogenetic analysis shows two separate lineages",
            "category": "empirical",
            "strength_of_evidence": "expert_opinion",
            "assertion_strength": "probable",
            "tags": ["genomics"],
        },
    ])

    mock_llm = AsyncMock(return_value=mock_response)

    store = EpistemicStore(data_dir=Path(tempfile.mkdtemp()) / "test")
    config = ExtractionConfig(max_claims_per_source=10)

    results = await extract_claims(
        source_text=source_text,
        source_title="Test Source",
        source_url="https://example.com",
        store=store,
        config=config,
        llm_call=mock_llm,
    )

    assert len(results) == 2
    assert results[0].verified_quote is True
    assert results[0].claim_id == "clm_0001"
    assert results[0].category == "empirical"
    assert store.claim_count == 2


@pytest.mark.asyncio
async def test_extract_claims_rejects_hallucinated_quote():
    source_text = "The virus emerged in late 2019."

    mock_response = json.dumps([
        {
            "natural_language": "The virus was engineered",
            "relevant_quote": "engineered in a laboratory through gain-of-function",
            "strength_of_evidence": "expert_opinion",
            "assertion_strength": "speculative",
            "tags": ["origins"],
        },
    ])

    mock_llm = AsyncMock(return_value=mock_response)
    store = EpistemicStore(data_dir=Path(tempfile.mkdtemp()) / "test")

    results = await extract_claims(
        source_text=source_text,
        source_title="Test",
        source_url="https://example.com",
        store=store,
        llm_call=mock_llm,
    )

    # Hallucinated quote should be rejected
    assert len(results) == 0
    assert store.claim_count == 0


@pytest.mark.asyncio
async def test_extract_claims_flags_overclaiming():
    source_text = "This proves conclusively that the market was the origin."

    mock_response = json.dumps([
        {
            "natural_language": "This proves conclusively the market was the origin",
            "relevant_quote": "proves conclusively that the market was the origin",
            "strength_of_evidence": "cohort",
            "assertion_strength": "certain",
            "tags": ["origins"],
        },
    ])

    mock_llm = AsyncMock(return_value=mock_response)
    store = EpistemicStore(data_dir=Path(tempfile.mkdtemp()) / "test")

    results = await extract_claims(
        source_text=source_text,
        source_title="Test",
        source_url="https://example.com",
        store=store,
        llm_call=mock_llm,
    )

    # Claim is NOT rejected (overclaiming is flagged, not fatal)
    assert len(results) == 1
    assert len(results[0].overclaiming_flags) > 0
