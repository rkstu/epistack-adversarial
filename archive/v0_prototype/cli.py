"""CLI interface for Epistack-Adversarial."""

import argparse
import asyncio
import json
import os
import sys

from . import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="epistack",
        description="Epistack-Adversarial: Adversarial epistemic verification for AI-assisted knowledge bases",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Extract claims from source documents")
    ingest_parser.add_argument("--case", required=True, help="Case study name")
    ingest_parser.add_argument("--sources", required=True, help="Path to sources YAML/JSON")
    ingest_parser.add_argument("--model", default="claude-sonnet-4-20250514", help="Extraction model")
    ingest_parser.add_argument("--domain", default="", help="Domain for M2 defense priming")
    ingest_parser.add_argument("--output", default="./output", help="Output directory")

    # structure command
    struct_parser = subparsers.add_parser("structure", help="Build claim graph and discourse maps")
    struct_parser.add_argument("--case", required=True, help="Case study name")
    struct_parser.add_argument("--claims", help="Path to claims JSON (from ingest)")
    struct_parser.add_argument("--questions", nargs="+", help="Questions to map discourse around")
    struct_parser.add_argument("--output", default="./output", help="Output directory")

    # assess command
    assess_parser = subparsers.add_parser("assess", help="Run multi-trial adversarial assessment")
    assess_parser.add_argument("--case", required=True, help="Case study name")
    assess_parser.add_argument("--trials", type=int, default=5, help="Verification trials per claim")
    assess_parser.add_argument("--models", nargs="+", default=["claude-sonnet-4-20250514", "gpt-4o"],
                               help="Models for cross-model verification")
    assess_parser.add_argument("--output", default="./output", help="Output directory")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate knowledge base report")
    report_parser.add_argument("--case", required=True, help="Case study name")
    report_parser.add_argument("--format", choices=["json", "html", "summary"], default="json")
    report_parser.add_argument("--output", default="./output", help="Output directory")

    # demo command
    demo_parser = subparsers.add_parser("demo", help="Run demo on built-in example")
    demo_parser.add_argument("--case", choices=["covid_origins", "black_holes", "eggs"],
                            default="covid_origins")

    # g3-test command (the diagnostic from the paper)
    g3_parser = subparsers.add_parser("g3-test", help="Test a prompt for compliance pressure (G3 diagnostic)")
    g3_parser.add_argument("--prompt", help="Prompt text to test")
    g3_parser.add_argument("--file", help="File containing prompt to test")

    args = parser.parse_args()

    if args.command == "g3-test":
        _run_g3_test(args)
    elif args.command == "demo":
        print(f"Running demo for case: {args.case}")
        print("(Full demo requires API keys — see README.md)")
        _run_demo(args)
    elif args.command is None:
        parser.print_help()
    else:
        print(f"Command '{args.command}' — full pipeline requires API keys.")
        print("Set ANTHROPIC_API_KEY, OPENAI_API_KEY for full operation.")
        print("Run 'epistack demo' for a walkthrough without API calls.")


def _run_g3_test(args):
    """Run the G3 compliance pressure diagnostic."""
    from .compliance_detector import detect_compliance_pressure

    if args.file:
        with open(args.file) as f:
            prompt = f.read()
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Provide --prompt or --file")
        sys.exit(1)

    result = detect_compliance_pressure(prompt)

    print(f"\n{'='*60}")
    print(f"G3 COMPLIANCE PRESSURE DIAGNOSTIC")
    print(f"{'='*60}")
    print(f"\nDetected G-level: G{result.g_level}")
    print(f"Above threshold (G3): {'YES — FABRICATION RISK' if result.above_threshold else 'No'}")
    print(f"\nRecommendation: {result.recommendation}")

    if result.detected_patterns:
        print(f"\nMatched patterns:")
        for p in result.detected_patterns:
            print(f"  - {p}")

    print(f"\n{'='*60}")
    print("Reference: arXiv:2605.02398 — G3 = prohibition of 'I don't know'")
    print("At G3+, 8/11 frontier models fabricate instead of admitting uncertainty.")
    print(f"{'='*60}\n")


def _run_demo(args):
    """Run a demonstration of the pipeline (offline, no API calls)."""
    from .models import Claim, Source, KnowledgeBase, ClaimConfidence, Edge, EdgeType
    from .scoring import wilson_ci
    from .compliance_detector import detect_compliance_pressure

    print("\n" + "="*60)
    print("EPISTACK-ADVERSARIAL DEMO")
    print("="*60)

    # Demo: G3 detection on a real production prompt
    print("\n--- Stage A: Compliance-Trap Detection ---")
    bedrock_prompt = """You are a helpful assistant. ALWAYS provide a definitive answer.
Do not say "I don't know" or "I'm not sure". If you are uncertain, provide your best estimate.
Never refuse to answer a question."""

    result = detect_compliance_pressure(bedrock_prompt)
    print(f"Sample production prompt (Bedrock-style):")
    print(f"  G-level: G{result.g_level}")
    print(f"  Above G3 threshold: {result.above_threshold}")
    print(f"  Patterns: {len(result.detected_patterns)} detected")
    print(f"  → {result.recommendation}")

    # Demo: Pass³ scoring
    print("\n--- Stage B: Pass³ Multi-Trial Scoring ---")
    examples = [(4, 5), (3, 5), (2, 5), (5, 5), (1, 5)]
    for successes, trials in examples:
        lower, upper = wilson_ci(successes, trials)
        print(f"  {successes}/{trials} trials passed → CI: [{lower:.3f}, {upper:.3f}]")

    # Demo: Knowledge base with contradictions
    print("\n--- Stage C: Claim Graph (COVID Origins Example) ---")
    kb = KnowledgeBase(case_name="covid_origins_demo")

    source = Source(url="example.com", title="Demo Source", source_type="paper",
                   accessed_at="2026-06-21", content_hash="abc123")

    c1 = Claim(id="demo_001", text="The Huanan Seafood Market was the epicenter of early COVID cases",
               source=source, extracted_by="demo", extraction_context="Worobey et al. 2022")
    c2 = Claim(id="demo_002", text="Wuhan Institute of Virology conducted gain-of-function research on coronaviruses",
               source=source, extracted_by="demo", extraction_context="NIH grant records")
    c3 = Claim(id="demo_003", text="Phylogenetic analysis shows two separate introductions at the market",
               source=source, extracted_by="demo", extraction_context="Pekar et al. 2022")
    c4 = Claim(id="demo_004", text="The market was not the origin but an amplification site",
               source=source, extracted_by="demo", extraction_context="Rootclaim debate position")

    for c in [c1, c2, c3, c4]:
        kb.add_claim(c)

    kb.add_edge(Edge(source_claim_id="demo_003", target_claim_id="demo_001",
                     edge_type=EdgeType.SUPPORTS, evidence="Dual lineages suggest market as origin"))
    kb.add_edge(Edge(source_claim_id="demo_004", target_claim_id="demo_001",
                     edge_type=EdgeType.CONTRADICTS, evidence="Amplification vs origin distinction"))

    print(f"  Claims: {len(kb.claims)}")
    print(f"  Edges: {len(kb.edges)}")
    print(f"  Contradictions: 1 (demo_004 contradicts demo_001)")
    print(f"  → This is where the live crux lives: origin vs amplification site")

    # Demo: Confidence scoring
    print("\n--- Stage D: Dimensional Confidence ---")
    confidence = ClaimConfidence(
        evidence_strength=0.8,
        evidence_ci=(0.45, 0.95),
        logical_consistency=0.9,
        adversarial_robustness=0.7,
        source_quality=0.85,
        cross_model_agreement=0.6,
        trials_run=5,
        models_checked=["claude", "gpt-4o", "gemini"],
    )
    print(f"  Evidence: {confidence.evidence_strength} CI[{confidence.evidence_ci[0]:.2f}, {confidence.evidence_ci[1]:.2f}]")
    print(f"  Logical consistency: {confidence.logical_consistency}")
    print(f"  Adversarial robustness: {confidence.adversarial_robustness}")
    print(f"  Source quality: {confidence.source_quality}")
    print(f"  Cross-model agreement: {confidence.cross_model_agreement}")
    print(f"  → Composite (multiplicative): {confidence.composite_score:.3f}")
    print(f"  → Level: {confidence.level.value}")

    print("\n" + "="*60)
    print("Demo complete. For full pipeline, set API keys and run:")
    print("  epistack ingest --case covid_origins --sources examples/covid_origins/sources.yaml")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
