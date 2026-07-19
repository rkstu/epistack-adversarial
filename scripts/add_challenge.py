"""Add a challenge to an existing claim in the knowledge base.

Demonstrates the collaboration protocol: new evidence enters the system,
triggers re-assessment, and cascades through the discourse map.

Usage:
    uv run python scripts/add_challenge.py covid_origins \
        --target clm_0029 \
        --body "NIH review board classified WIV research as not gain-of-function under the HHS P3CO framework" \
        --source-url "https://www.nih.gov/p3co-framework" \
        --source-label "NIH P3CO Review Board"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from epistack.store import EpistemicStore


def main():
    parser = argparse.ArgumentParser(description="Add a challenge to a claim")
    parser.add_argument("case", help="Case study name")
    parser.add_argument("--target", required=True, help="Claim ID to challenge")
    parser.add_argument("--body", required=True, help="Challenge text")
    parser.add_argument("--source-url", default="", help="Source URL for the challenge")
    parser.add_argument("--source-label", default="", help="Source label")
    parser.add_argument("--challenge-type", default="evidential",
                        choices=["evidential", "methodological", "logical"],
                        help="Type of challenge")
    args = parser.parse_args()

    data_dir = Path("data") / args.case
    store = EpistemicStore(data_dir=data_dir)
    store.replay()

    # Verify target exists
    if args.target not in store.claims:
        print(f"ERROR: Claim '{args.target}' not found in store.")
        print(f"Available claims: {list(store.claims.keys())[:10]}...")
        return

    target_claim = store.claims[args.target]
    target_text = target_claim.get("statement", {}).get("natural_language", "")

    # Append challenge event
    event = store.append(
        event_type="challenge.raised",
        payload={
            "challenge_id": f"chl_{store.tx + 1:04d}",
            "target": args.target,
            "challenge_type": args.challenge_type,
            "body": args.body,
            "source_url": args.source_url,
            "source_label": args.source_label,
        },
        actor="researcher:manual",
        method="manual",
    )

    # Also add a contradicting edge
    store.append(
        event_type="edge.asserted",
        payload={
            "edge_id": f"edg_chl_{store.tx:04d}",
            "edge_type": "contradicts",
            "source": event.event_id,
            "target": args.target,
            "strength": 0.7,
            "evidence": args.body,
            "cross_source": True,
        },
        actor="researcher:manual",
        method="manual_challenge",
    )

    print(f"\n{'='*60}")
    print(f"CHALLENGE ADDED")
    print(f"{'='*60}")
    print(f"  Target: [{args.target}] {target_text[:80]}")
    print(f"  Challenge: {args.body[:80]}")
    print(f"  Source: {args.source_label or args.source_url or 'manual'}")
    print(f"  Event: {event.event_id} (tx={event.tx})")
    print(f"\n  To see cascade effect, re-run:")
    print(f"  uv run python run_pipeline.py {args.case} --phase full")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
