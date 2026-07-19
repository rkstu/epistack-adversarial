"""Epistack pipeline orchestrator — grows incrementally as modules are built.

Usage:
    uv run python run_pipeline.py covid_origins
    uv run python run_pipeline.py covid_origins --phase extract
    uv run python run_pipeline.py covid_origins --budget 10.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import structlog

from epistack import llm
from epistack.config import get_config, load_config, reset_config, EpistackConfig
from epistack.store import EpistemicStore
from epistack.fetch import fetch_source
from epistack.extraction import extract_claims, ExtractionConfig

log = structlog.get_logger()

SOURCES_DIR = Path("examples")
DATA_DIR = Path("data")


def load_source_config(case_name: str) -> list[dict]:
    """Load sources from YAML config."""
    import yaml

    config_path = SOURCES_DIR / case_name / "sources.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Source config not found: {config_path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    return config.get("sources", []), config


async def run_extract(case_name: str, max_sources: int | None = None):
    """Phase 1: Fetch sources + extract claims."""
    sources, config = load_source_config(case_name)
    store = EpistemicStore(data_dir=DATA_DIR / case_name)

    extraction_config = ExtractionConfig(
        domain=config.get("domain", ""),
        domain_facts=config.get("domain_facts", []),
    )

    if max_sources:
        sources = sources[:max_sources]

    total_claims = 0
    for i, source in enumerate(sources):
        log.info("processing_source", index=i + 1, total=len(sources),
                 title=source.get("title", "")[:60])

        # Fetch (checks manual_fallback first for Google Drive / failed URLs)
        try:
            result = await fetch_source(
                url=source["url"],
                source_type=source.get("type", "auto"),
                title=source.get("title", ""),
                manual_fallback=source.get("manual_fallback"),
            )
        except Exception as e:
            log.error("fetch_failed", url=source["url"], error=str(e))
            continue

        if result.is_empty:
            log.warning("empty_source", url=source["url"])
            continue

        # Extract
        claims = await extract_claims(
            source_text=result.text,
            source_title=result.title,
            source_url=source["url"],
            store=store,
            config=extraction_config,
        )
        total_claims += len(claims)

        log.info("source_complete", title=result.title[:40],
                 claims=len(claims), total_so_far=total_claims)

    return store, total_claims


async def run_relationships(store: EpistemicStore, data_dir: Path):
    """Phase 2: Embed claims, detect edges, deduplicate."""
    from epistack.relationships import detect_relationships
    return await detect_relationships(store, data_dir=data_dir)


async def run_confidence(store: EpistemicStore):
    """Phase 3: Compute confidence for all claims."""
    from epistack.confidence import compute_all_confidences
    results = compute_all_confidences(store)
    return {"claims_scored": len(results)}


async def run_verification(store: EpistemicStore):
    """Phase 3b: Verification Layers 3-4."""
    from epistack.verification import verify_claims
    return await verify_claims(store)


def run_crux_detection(store: EpistemicStore, target_ids: list[str]):
    """Phase 4: Crux detection (pure computation, no LLM calls)."""
    from epistack.crux_detection import get_top_cruxes
    return get_top_cruxes(store, target_ids=target_ids, n=10)

async def run_discourse(store: EpistemicStore, data_dir: Path, questions: list[str]):
    """Phase 5: Build discourse map (positions, cruxes, empty chairs)."""
    from epistack.discourse import build_discourse_map
    return await build_discourse_map(store, data_dir=data_dir, questions=questions)


def run_site_generation(store: EpistemicStore, discourse_result: dict, output_dir: Path, case_name: str):
    """Phase 6: Generate static HTML site."""
    from epistack.generate_site import generate_site
    return generate_site(store, discourse_result, output_dir, case_name=case_name)


def print_summary(store: EpistemicStore, case_name: str):
    """Print pipeline run summary."""
    cost = llm.get_cost_summary()

    print("\n" + "=" * 60)
    print(f"PIPELINE SUMMARY: {case_name}")
    print("=" * 60)
    print(f"  Claims: {store.claim_count}")
    print(f"  Edges: {store.edge_count}")
    print(f"  Positions: {len(store.positions)}")
    print(f"  Events file: {store.events_path}")

    if store.claims:
        # Show category breakdown
        categories = {}
        for c in store.claims.values():
            cat = c.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
        print(f"  Categories: {categories}")

        # Sample claim
        sample = next(iter(store.claims.values()))
        print(f"\n  Sample claim:")
        print(f"    [{sample.get('claim_id')}] {sample.get('statement', {}).get('natural_language', '')[:80]}")
        print(f"    Quote: \"{sample.get('relevant_quote', '')[:60]}...\"")
        print(f"    Category: {sample.get('category')}")

    print(f"\n  Cost:")
    print(f"    Total: ${cost['total_cost']:.4f}")
    print(f"    Calls: {cost['total_calls']}")
    if cost["by_model"]:
        print(f"    By model: {json.dumps(cost['by_model'], indent=6)}")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Epistack pipeline")
    parser.add_argument("case", help="Case study name (covid_origins, lhc_black_holes, eggs_health)")
    parser.add_argument("--phase", default="full",
                        choices=["extract", "relationships", "full"],
                        help="Pipeline phase to run (default: full)")
    parser.add_argument("--budget", type=float, default=5.0,
                        help="Max API budget in dollars (default: $5 dev cap)")
    parser.add_argument("--max-sources", type=int, default=None,
                        help="Limit number of sources to process")
    args = parser.parse_args()

    # Set budget via config
    cfg = get_config()
    cfg.budget.dev_budget = args.budget
    llm.reset_tracker()

    log.info("pipeline_start", case=args.case, phase=args.phase, budget=f"${args.budget:.2f}")

    data_dir = DATA_DIR / args.case

    if args.phase == "extract":
        store, total = await run_extract(args.case, max_sources=args.max_sources)
    elif args.phase == "relationships":
        store = EpistemicStore(data_dir=data_dir)
        store.replay()
        result = await run_relationships(store, data_dir)
        log.info("relationships_done", **result)
    elif args.phase == "full":
        # Full pipeline: extract → verify → relationships → confidence → discourse → site
        sources_config, case_config = load_source_config(args.case)
        questions = case_config.get("questions", [])
        output_dir = Path("output") / args.case

        store, total = await run_extract(args.case, max_sources=args.max_sources)
        log.info("phase_extract_done", claims=total)

        verify_result = await run_verification(store)
        log.info("phase_verify_done", **verify_result)

        rel_result = await run_relationships(store, data_dir)
        log.info("phase_relationships_done", **rel_result)

        conf_result = await run_confidence(store)
        log.info("phase_confidence_done", **conf_result)

        # Discourse mapping (positions, cruxes with real targets, empty chairs)
        discourse_result = await run_discourse(store, data_dir, questions)
        log.info("phase_discourse_done",
                 positions=len(discourse_result.get("positions", [])),
                 cruxes=len(discourse_result.get("cruxes", [])),
                 empty_chairs=len(discourse_result.get("empty_chairs", [])))

        # Generate HTML site
        site_path = run_site_generation(store, discourse_result, output_dir,
                                        case_name=args.case.replace("_", " ").title())
        log.info("phase_site_done", output=str(site_path))

    else:
        print(f"Phase '{args.phase}' not recognized. Available: extract, relationships, full")
        return

    print_summary(store, args.case)


if __name__ == "__main__":
    asyncio.run(main())
