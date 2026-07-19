"""Day 2 Smoke Test: Fetch a real source → extract claims → write events.jsonl.

Run: uv run python scripts/smoke_test.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from epistack.fetch import fetch_source
from epistack.extraction import extract_claims, ExtractionConfig
from epistack.store import EpistemicStore
from epistack.config import get_config
from epistack.llm import get_cost_summary, reset_tracker


async def main():
    reset_tracker()

    print("=" * 60)
    print("EPISTACK SMOKE TEST — Real source → claims → events.jsonl")
    print("=" * 60)

    # Step 1: Fetch
    print("\n[1/3] Fetching Scott Alexander ACX post...")
    result = await fetch_source(
        url="https://www.astralcodexten.com/p/practically-a-book-review-rootclaim",
        source_type="blog",
        title="Practically A Book Review: Rootclaim COVID Origins Debate",
    )
    print(f"  Title: {result.title}")
    print(f"  Chars: {result.char_count:,}")
    print(f"  Type: {result.source_type}")

    if result.is_empty:
        print("  ERROR: Fetch returned empty content!")
        return

    print(f"  Preview: {result.text[:200]}...")

    # Step 2: Extract (first 2 chunks only for smoke test — saves cost)
    print("\n[2/3] Extracting claims (first 16K chars only — smoke test)...")
    store = EpistemicStore(data_dir=Path("data/covid_origins"))

    config = ExtractionConfig(
        max_claims_per_source=15,  # Limit for smoke test
        chunk_size=8000,
        domain="virology and epidemiology",
        domain_facts=[
            "SARS-CoV-2 was first identified in Wuhan, China in December 2019",
            "The Huanan Seafood Market was linked to many early cases",
            "The Wuhan Institute of Virology studies bat coronaviruses",
            "Gain-of-function research involves modifying viruses",
            "Zoonotic spillover is the most common pathway for new human viruses",
        ],
    )

    # Only process first 16K chars for cost control
    truncated_text = result.text[:16000]

    results = await extract_claims(
        source_text=truncated_text,
        source_title=result.title,
        source_url=result.url,
        store=store,
        config=config,
    )

    # Step 3: Report
    print(f"\n[3/3] Results:")
    print(f"  Claims extracted: {len(results)}")
    print(f"  Claims in store: {store.claim_count}")
    print(f"  Events file: {store.events_path}")

    if results:
        print(f"\n  Sample claim:")
        sample = results[0]
        print(f"    ID: {sample.claim_id}")
        print(f"    Text: {sample.natural_language}")
        print(f"    Quote: \"{sample.relevant_quote[:80]}...\"")
        print(f"    Verified: {sample.verified_quote}")
        print(f"    Overclaiming flags: {sample.overclaiming_flags}")
        print(f"    Evidence type: {sample.strength_of_evidence}")

    # Cost summary
    cost = get_cost_summary()
    print(f"\n  Cost tracking:")
    print(f"    Total cost: ${cost['total_cost']:.4f}")
    print(f"    Total calls: {cost['total_calls']}")
    print(f"    By model: {json.dumps(cost['by_model'], indent=6)}")

    # Verify events.jsonl
    if store.events_path.exists():
        with open(store.events_path) as f:
            event_count = sum(1 for _ in f)
        print(f"\n  events.jsonl: {event_count} events written")
    else:
        print("\n  WARNING: No events.jsonl created")

    print("\n" + "=" * 60)
    print("SMOKE TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
