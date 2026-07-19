"""Grounded claim extraction with mandatory source quotes.

Extracts atomic claims from source documents. Every claim MUST include
a direct quote from the source for verification.

Verification Layers 1-2 (free, applied immediately):
- Layer 1: Quote string containment — rejects hallucinated quotes
- Layer 2: Overclaiming regex — flags absolute/overclaiming language
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

from .compliance_detector import apply_defenses
from .config import get_config
from .store import EpistemicStore

log = structlog.get_logger()

EXTRACTION_PROMPT = """You are extracting the most important claims from a source document. RULES:
1. Only extract claims EXPLICITLY stated in the text
2. Every claim MUST include a direct quote from the source
3. Never infer, synthesize, or generate claims not present in the source
4. If ambiguous, extract with qualifier "ambiguous"
5. Preserve assertion strength (don't upgrade "may" to "does")
6. Extract 3-5 MOST IMPORTANT claims per section. Focus on:
   - Factual assertions about the world (empirical)
   - Causal claims and statistical claims
   - Key conclusions and disagreements
   Skip: background context, definitions, tangential examples

For each claim output JSON:
[
  {{
    "natural_language": "The claim as one atomic sentence",
    "relevant_quote": "Exact quote from source supporting this claim",
    "category": "empirical|assessment|methodological",
    "strength_of_evidence": "anecdote|case_report|cohort|rct|meta_analysis|expert_opinion|logical_argument",
    "assertion_strength": "certain|probable|possible|speculative",
    "tags": ["domain", "keywords"]
  }}
]

Category definitions:
- empirical: factual assertion about the world (verifiable)
- assessment: someone's judgment about evidence quality or argument strength
- methodological: about how analysis should be conducted

SOURCE TITLE: {source_title}
SECTION: {section_label}

---
{chunk}
---

Extract the 3-5 most important claims. Output ONLY valid JSON array."""

OVERCLAIMING_PATTERNS = [
    r"proves?\s+conclusively",
    r"definitively\s+shows?",
    r"beyond\s+(?:any\s+)?doubt",
    r"irrefutabl[ye]",
    r"no\s+possible\s+alternative",
    r"the\s+only\s+explanation",
    r"unanimously\s+agree",
    r"all\s+(?:scientists?|experts?|studies)\s+(?:agree|show|confirm)",
    r"no\s+evidence\s+(?:whatsoever|at all)\s+(?:exists?|supports?)",
    r"completely\s+(?:disproven|refuted|debunked)",
]


@dataclass
class ExtractionConfig:
    model_role: str = "extraction"  # Resolved via config.models
    max_claims_per_source: int | None = None  # None = use config default
    chunk_size: int | None = None
    overlap: int | None = None
    domain: str = ""
    domain_facts: list[str] | None = None
    min_quote_length: int | None = None

    def __post_init__(self):
        if self.domain_facts is None:
            self.domain_facts = []
        # Fill from global config defaults
        cfg = get_config()
        if self.max_claims_per_source is None:
            self.max_claims_per_source = cfg.extraction.max_claims_per_source
        if self.chunk_size is None:
            self.chunk_size = cfg.extraction.chunk_size
        if self.overlap is None:
            self.overlap = cfg.extraction.chunk_overlap
        if self.min_quote_length is None:
            self.min_quote_length = cfg.extraction.min_quote_length


CLAIM_CATEGORIES = ("empirical", "assessment", "methodological")


@dataclass
class ExtractionResult:
    claim_id: str
    natural_language: str
    relevant_quote: str
    category: str  # empirical, assessment, methodological
    strength_of_evidence: str
    assertion_strength: str
    tags: list[str]
    source_title: str
    source_url: str
    chunk_index: int
    verified_quote: bool
    overclaiming_flags: list[str]


def chunk_document(text: str, chunk_size: int = 8000, overlap: int = 500) -> list[str]:
    """Split document into overlapping chunks at paragraph boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            newline_pos = text.rfind("\n\n", start + chunk_size - overlap, end)
            if newline_pos > start:
                end = newline_pos
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def verify_quote_containment(quote: str, source_text: str, min_length: int = 10) -> bool:
    """Layer 1: Check if the quote actually appears in the source text.

    Cost: $0. Catches hallucinated quotes immediately.
    """
    if len(quote) < min_length:
        return False

    quote_clean = " ".join(quote.lower().split())
    source_clean = " ".join(source_text.lower().split())

    if quote_clean in source_clean:
        return True

    # Fuzzy: check if 80%+ of quote words appear in order in source
    quote_words = quote_clean.split()
    if len(quote_words) < 3:
        return quote_clean in source_clean

    source_words = source_clean.split()
    match_count = 0
    source_idx = 0
    for qw in quote_words:
        for i in range(source_idx, len(source_words)):
            if source_words[i] == qw:
                match_count += 1
                source_idx = i + 1
                break

    return match_count / len(quote_words) >= 0.8


def check_overclaiming(claim_text: str) -> list[str]:
    """Layer 2: Regex check for overclaiming language.

    Cost: $0. Flags claims with absolute/unqualified assertions.
    These aren't rejected — they're flagged for human review.
    """
    flags = []
    text_lower = claim_text.lower()
    for pattern in OVERCLAIMING_PATTERNS:
        if re.search(pattern, text_lower):
            flags.append(pattern)
    return flags


def parse_extraction_response(response_text: str) -> list[dict[str, Any]]:
    """Parse LLM JSON response into list of raw claims."""
    import json

    try:
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            start = response_text.find("[")
            end = response_text.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
            else:
                return []

        claims = json.loads(json_str)
        return claims if isinstance(claims, list) else []
    except (json.JSONDecodeError, IndexError):
        log.warning("extraction_parse_failed", response_preview=response_text[:200])
        return []


async def extract_claims(
    source_text: str,
    source_title: str,
    source_url: str,
    store: EpistemicStore,
    config: ExtractionConfig | None = None,
    llm_call=None,
) -> list[ExtractionResult]:
    """Extract grounded claims from a source document.

    Runs Layer 1 (quote containment) and Layer 2 (overclaiming regex) immediately.
    Claims with hallucinated quotes are rejected.

    Args:
        source_text: Full text of the source document
        source_title: Human-readable source title
        source_url: URL or path of the source
        store: EpistemicStore to append events to
        config: Extraction configuration
        llm_call: Async LLM call function (prompt, model) -> str.
                  If None, uses epistack.llm.call.
    """
    if llm_call is None:
        from . import llm

        async def _default_llm_call(prompt, _model=None):
            return await llm.call(prompt, role=config.model_role)

        llm_call = _default_llm_call

    config = config or ExtractionConfig()

    # Idempotency: skip if this source was already extracted
    existing_sources = {
        c.get("source_url") for c in store.claims.values() if c.get("source_url")
    }
    if source_url in existing_sources:
        existing_count = sum(1 for c in store.claims.values() if c.get("source_url") == source_url)
        log.info("extraction_skipped", source=source_title, reason="already extracted",
                 existing_claims=existing_count)
        return []

    chunks = chunk_document(source_text, config.chunk_size, config.overlap)
    results: list[ExtractionResult] = []
    rejected_count = 0

    for chunk_idx, chunk in enumerate(chunks):
        if len(results) >= config.max_claims_per_source:
            break

        # Build prompt with compliance defenses
        prompt = EXTRACTION_PROMPT.format(
            source_title=source_title,
            section_label=f"Chunk {chunk_idx + 1}/{len(chunks)}",
            chunk=chunk,
        )
        defended_prompt, compliance_assessment = apply_defenses(
            prompt, domain=config.domain, domain_facts=config.domain_facts or [],
        )

        # Call LLM (mock llm_call takes (prompt, model) for compat; real uses role)
        response = await llm_call(defended_prompt, config.model_role)
        raw_claims = parse_extraction_response(response)

        for raw in raw_claims:
            if len(results) >= config.max_claims_per_source:
                break

            natural_language = raw.get("natural_language", "").strip()
            relevant_quote = raw.get("relevant_quote", "").strip()

            if not natural_language or not relevant_quote:
                rejected_count += 1
                continue

            # Layer 1: Quote containment verification ($0)
            quote_verified = verify_quote_containment(
                relevant_quote, source_text, config.min_quote_length
            )
            if not quote_verified:
                log.debug(
                    "quote_rejected",
                    claim=natural_language[:80],
                    quote=relevant_quote[:60],
                    reason="not found in source",
                )
                rejected_count += 1
                continue

            # Layer 2: Overclaiming check ($0)
            overclaiming_flags = check_overclaiming(natural_language)

            # Category (empirical / assessment / methodological)
            category = raw.get("category", "empirical")
            if category not in CLAIM_CATEGORIES:
                category = "empirical"

            # Generate claim ID
            claim_id = f"clm_{store.claim_count + len(results) + 1:04d}"

            result = ExtractionResult(
                claim_id=claim_id,
                natural_language=natural_language,
                relevant_quote=relevant_quote,
                category=category,
                strength_of_evidence=raw.get("strength_of_evidence", "unknown"),
                assertion_strength=raw.get("assertion_strength", "unknown"),
                tags=raw.get("tags", []),
                source_title=source_title,
                source_url=source_url,
                chunk_index=chunk_idx,
                verified_quote=quote_verified,
                overclaiming_flags=overclaiming_flags,
            )
            results.append(result)

            # Append to event store
            # Assessment claims get lower default confidence (one person's judgment)
            default_confidence = 0.5 if category == "empirical" else 0.35

            store.append(
                event_type="claim.asserted",
                payload={
                    "claim_id": claim_id,
                    "statement": {
                        "natural_language": natural_language,
                    },
                    "relevant_quote": relevant_quote,
                    "quote_verified": True,
                    "category": category,
                    "strength_of_evidence": result.strength_of_evidence,
                    "assertion_strength": result.assertion_strength,
                    "tags": result.tags,
                    "source_title": source_title,
                    "source_url": source_url,
                    "chunk_index": chunk_idx,
                    "overclaiming_flags": overclaiming_flags,
                    "extraction_model": config.model_role,
                    "compliance_pressure": compliance_assessment.above_threshold,
                    "confidence": default_confidence,
                },
                actor="pipeline:extraction",
                method="llm_extraction",
            )

    log.info(
        "extraction_complete",
        source=source_title,
        claims_extracted=len(results),
        claims_rejected=rejected_count,
        chunks_processed=len(chunks),
    )

    return results
