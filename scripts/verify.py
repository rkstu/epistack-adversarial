"""
Epistack verification script — no API key required.

Runs all 103 unit tests and validates the pre-built output against expected
results. A judge or reviewer can run this to confirm the pipeline works
correctly without spending any API budget.

Usage:
    uv run python scripts/verify.py

Exit code 0 = all checks pass. Exit code 1 = something failed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "✓" if condition else "✗"
    line = f"  {mark}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return condition


def main() -> int:
    root = Path(__file__).parent.parent
    failures = 0

    # ── 1. Unit tests ────────────────────────────────────────────────────────
    section("1. Unit Tests  (103 tests, no API keys)")
    result = subprocess.run(
        ["uv", "run", "--extra", "dev", "pytest", "tests/", "-q", "--tb=short"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    passed = result.returncode == 0
    print(result.stdout[-1200:] if result.stdout else "")
    if result.stderr and not passed:
        print(result.stderr[-400:])
    if not check("pytest exit code 0", passed):
        failures += 1

    # ── 2. Pre-built output present ──────────────────────────────────────────
    section("2. Pre-Built Output (no API key needed to view)")
    cases = {
        "covid_origins":  {"min_html": 25, "min_claims": 200, "min_edges": 1000},
        "lhc_black_holes": {"min_html": 18, "min_claims": 30,  "min_edges": 200},
        "eggs_health":    {"min_html": 18, "min_claims": 30,  "min_edges": 180},
    }
    for case, thresholds in cases.items():
        out_dir = root / "output" / case
        html_files = list(out_dir.rglob("*.html")) if out_dir.exists() else []
        index_exists = (out_dir / "index.html").exists()
        n_html = len(html_files)
        ok_html = check(
            f"{case}: index.html present",
            index_exists,
        )
        ok_count = check(
            f"{case}: ≥{thresholds['min_html']} HTML pages",
            n_html >= thresholds["min_html"],
            f"found {n_html}",
        )
        if not (ok_html and ok_count):
            failures += 1

    # ── 3. Event store integrity ─────────────────────────────────────────────
    section("3. Event Store Integrity (events.jsonl)")
    for case, thresholds in cases.items():
        events_path = root / "data" / case / "events.jsonl"
        if not events_path.exists():
            check(f"{case}: events.jsonl exists", False, "file missing — run pipeline first")
            # Not a failure for a cold clone (data/ is gitignored)
            continue

        events = [json.loads(l) for l in events_path.read_text().splitlines() if l.strip()]
        claims = [e for e in events if e["event_type"] == "claim.asserted"]
        superseded = {
            e["payload"].get("old_claim_id") or e["payload"].get("claim_id")
            for e in events if e["event_type"] == "claim.superseded"
        }
        active = [c for c in claims if c["payload"]["claim_id"] not in superseded]
        edges = [e for e in events if e["event_type"] == "edge.asserted"]

        # All active claims must have quote_verified = true
        unverified = [c for c in active if not c["payload"].get("quote_verified")]

        ok_claims = check(
            f"{case}: ≥{thresholds['min_claims']} active claims",
            len(active) >= thresholds["min_claims"],
            f"{len(active)} found",
        )
        ok_edges = check(
            f"{case}: ≥{thresholds['min_edges']} edges",
            len(edges) >= thresholds["min_edges"],
            f"{len(edges)} found",
        )
        ok_quotes = check(
            f"{case}: all active claims quote_verified",
            len(unverified) == 0,
            f"{len(unverified)} unverified" if unverified else "all verified",
        )
        if not (ok_claims and ok_edges and ok_quotes):
            failures += 1

    # ── 4. Key structural findings ───────────────────────────────────────────
    section("4. Key Structural Findings (COVID case)")
    covid_events_path = root / "data" / "covid_origins" / "events.jsonl"
    if covid_events_path.exists():
        events = [json.loads(l) for l in covid_events_path.read_text().splitlines() if l.strip()]

        # Settling detection
        settling = [
            e for e in events
            if e["event_type"] == "meta.flag"
            and e["payload"].get("flag_type") == "performed_settling"
        ]
        verdict_ids = {e["payload"]["verdict_claim_id"] for e in settling}
        ok_settling = check(
            "Performed settling detected on verdict claims",
            len(verdict_ids) >= 5,
            f"{len(verdict_ids)} verdicts flagged",
        )

        # Positions present
        positions = {e["payload"]["position_id"] for e in events if e["event_type"] == "position.stated"}
        ok_positions = check(
            "≥3 positions detected",
            len(positions) >= 3,
            f"{len(positions)} found: {sorted(positions)}",
        )

        # frames_differently edges present (key novel edge type)
        fd_edges = [
            e for e in events
            if e["event_type"] == "edge.asserted"
            and e["payload"].get("edge_type") == "frames_differently"
        ]
        ok_fd = check(
            "frames_differently edges present",
            len(fd_edges) >= 10,
            f"{len(fd_edges)} found",
        )

        if not (ok_settling and ok_positions and ok_fd):
            failures += 1
    else:
        print("  (skipped — data/covid_origins/events.jsonl not present; run pipeline first)")

    # ── 5. Summary ───────────────────────────────────────────────────────────
    section("Summary")
    if failures == 0:
        print("  All checks passed.")
        print()
        print("  To view results:")
        print("    open output/covid_origins/index.html")
        print("    open output/lhc_black_holes/index.html")
        print("    open output/eggs_health/index.html")
        print()
        print("  To reproduce from scratch (requires OPENROUTER_API_KEY in .env):")
        print("    uv run python run_pipeline.py covid_origins --phase full --budget 1.0")
        return 0
    else:
        print(f"  {failures} check group(s) failed. See above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
