"""Layer 1: Ingestion — Multi-source document extraction with provenance tracking.

Extracts atomic claims from documents (PDFs, blog posts, debate transcripts,
papers) with full provenance metadata. Each claim is tagged with its source,
extraction context, and content hash for integrity verification.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .models import Claim, Source
from .compliance_detector import apply_defenses


EXTRACTION_PROMPT = """You are a precise claim extractor. Given a document, extract all falsifiable factual claims.

For each claim:
1. State it as a single, atomic, falsifiable assertion
2. Note the exact location (paragraph/page/timestamp) where it appears
3. Classify it: empirical_fact, causal_claim, statistical_claim, expert_opinion, logical_argument, methodological_claim

Rules:
- Each claim must be independently verifiable
- Split compound claims into atomic parts
- Preserve the strength of the original assertion (don't upgrade "may" to "does")
- Include claims from all sides of any debate/controversy
- Flag any claims that appear to be fabricated, unsupported, or contradicted by the source

Output as JSON array:
[
  {
    "text": "The exact claim as a single sentence",
    "location": "Paragraph 3 / Page 5 / Timestamp 12:34",
    "type": "empirical_fact|causal_claim|statistical_claim|expert_opinion|logical_argument|methodological_claim",
    "strength": "certain|probable|possible|speculative",
    "context": "Brief surrounding context (1-2 sentences)"
  }
]"""


@dataclass
class IngestionConfig:
    """Configuration for ingestion pipeline."""
    model: str = "claude-sonnet-4-20250514"
    max_claims_per_source: int = 50
    chunk_size: int = 8000  # chars per chunk for long documents
    overlap: int = 500
    domain: str = ""
    domain_facts: list = None

    def __post_init__(self):
        if self.domain_facts is None:
            self.domain_facts = []


def chunk_document(text: str, chunk_size: int = 8000, overlap: int = 500) -> list:
    """Split document into overlapping chunks for processing."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        # Try to break at paragraph boundary
        if end < len(text):
            newline_pos = text.rfind("\n\n", start + chunk_size - overlap, end)
            if newline_pos > start:
                end = newline_pos
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def build_extraction_prompt(chunk: str, source_title: str, chunk_index: int, config: IngestionConfig) -> str:
    """Build the claim extraction prompt with compliance defenses."""
    prompt = f"""{EXTRACTION_PROMPT}

---
SOURCE: {source_title}
SECTION: Chunk {chunk_index + 1}
---

{chunk}"""

    # Apply M2/M3 defenses if compliance pressure detected
    defended_prompt, assessment = apply_defenses(
        prompt,
        domain=config.domain,
        domain_facts=config.domain_facts,
    )

    return defended_prompt


def parse_extraction_response(response_text: str) -> list:
    """Parse LLM response into structured claims."""
    # Try to find JSON array in response
    try:
        # Handle markdown code blocks
        if "```json" in response_text:
            json_str = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            json_str = response_text.split("```")[1].split("```")[0]
        else:
            # Try to find array directly
            start = response_text.find("[")
            end = response_text.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = response_text[start:end]
            else:
                return []

        claims_raw = json.loads(json_str)
        return claims_raw if isinstance(claims_raw, list) else []
    except (json.JSONDecodeError, IndexError):
        return []


def create_claim_from_extraction(
    raw_claim: dict,
    source: Source,
    extractor_model: str,
    claim_counter: int,
    case_name: str,
) -> Claim:
    """Create a Claim object from raw extraction output."""
    claim_id = f"{case_name}_{claim_counter:04d}"

    return Claim(
        id=claim_id,
        text=raw_claim.get("text", ""),
        source=source,
        extracted_by=extractor_model,
        extraction_context=raw_claim.get("context", ""),
        metadata={
            "type": raw_claim.get("type", "unknown"),
            "strength": raw_claim.get("strength", "unknown"),
            "location": raw_claim.get("location", "unknown"),
        },
    )


def create_source(
    url: str,
    title: str,
    source_type: str,
    content: str,
    author: Optional[str] = None,
    date_published: Optional[str] = None,
    credibility_signals: Optional[dict] = None,
) -> Source:
    """Create a Source object with content hash for integrity."""
    return Source(
        url=url,
        title=title,
        source_type=source_type,
        accessed_at=datetime.now().isoformat(),
        content_hash=Source.hash_content(content),
        author=author,
        date_published=date_published,
        credibility_signals=credibility_signals or {},
    )


async def ingest_source(
    content: str,
    source: Source,
    config: IngestionConfig,
    llm_call,  # async callable: (prompt, model) -> response_text
    case_name: str = "default",
    claim_counter_start: int = 0,
) -> list:
    """Ingest a single source document and extract claims.

    Args:
        content: Full text of the source document
        source: Source metadata object
        config: Ingestion configuration
        llm_call: Async function that calls an LLM (prompt, model) -> str
        case_name: Name of the case study
        claim_counter_start: Starting number for claim IDs

    Returns:
        List of Claim objects extracted from the source
    """
    chunks = chunk_document(content, config.chunk_size, config.overlap)
    all_claims = []
    counter = claim_counter_start

    for i, chunk in enumerate(chunks):
        prompt = build_extraction_prompt(chunk, source.title, i, config)
        response = await llm_call(prompt, config.model)
        raw_claims = parse_extraction_response(response)

        for raw in raw_claims[:config.max_claims_per_source - len(all_claims)]:
            claim = create_claim_from_extraction(
                raw, source, config.model, counter, case_name
            )
            all_claims.append(claim)
            counter += 1

        if len(all_claims) >= config.max_claims_per_source:
            break

    return all_claims
