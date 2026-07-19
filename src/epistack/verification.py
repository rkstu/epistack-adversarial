"""Verification Layers 3-4 — LLM-based entailment and cross-provider checking.

Layer 3: NLI entailment (does the quote actually support the claim?)
Layer 4: Cross-provider check (independent model verifies claim is in source)

Layers 1-2 (quote containment + overclaiming regex) run during extraction ($0).
Layers 3-4 run post-extraction on claims that passed Layers 1-2.

Design sources:
- IMPLEMENTATION_PLAN.md §5.2
- Preseal oracle.py (most-reliable-first, short-circuit on failure)
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from . import llm
from .config import get_config
from .store import EpistemicStore

log = structlog.get_logger()

NLI_PROMPT = """You are checking whether a source quote actually supports a claim.

Claim: {claim}
Source quote: "{quote}"
Source: {source_title}

Question: Does the quote ENTAIL the claim? Consider:
1. Does the quote explicitly state what the claim asserts?
2. Is the claim overstating what the quote says (upgrading "may" to "does")?
3. Is the claim inferring something not present in the quote?

Output JSON:
{{"entailed": true/false, "reason": "brief explanation", "severity": "pass|overstatement|fabrication"}}"""

CROSS_PROVIDER_PROMPT = """You are an independent verifier. A different AI system extracted this claim from a source document.

Claim: {claim}
Source title: {source_title}
Source quote provided as evidence: "{quote}"

Verify independently:
1. Is this claim actually stated in or supported by the quote?
2. Does the claim add information NOT in the quote?
3. Are there signs of fabrication (specific details that seem made up)?

Output JSON:
{{"verified": true/false, "issues": ["list of problems if any"], "confidence": 0.0-1.0}}"""


async def verify_claims(
    store: EpistemicStore,
    layer3: bool | None = None,
    layer4: bool | None = None,
    layer4_top_pct: float | None = None,
) -> dict[str, Any]:
    """Run verification Layers 3-4 on all active claims.

    Only processes claims that already passed Layers 1-2 (quote_verified=true).
    Layer 4 only runs on top N% medium-confidence claims (cost optimization).

    Returns summary dict.
    """
    cfg = get_config()
    layer3 = layer3 if layer3 is not None else cfg.verification.layer3_enabled
    layer4 = layer4 if layer4 is not None else cfg.verification.layer4_enabled
    layer4_top_pct = layer4_top_pct if layer4_top_pct is not None else cfg.verification.layer4_only_top_pct

    claims_to_verify = [
        (cid, c) for cid, c in store.claims.items()
        if c.get("status") == "active" and c.get("quote_verified") is True
    ]

    if not claims_to_verify:
        return {"verified": 0, "failed_l3": 0, "failed_l4": 0}

    failed_l3 = 0
    failed_l4 = 0
    verified = 0

    # Layer 3: NLI entailment
    if layer3:
        for claim_id, claim in claims_to_verify:
            text = claim.get("statement", {}).get("natural_language", "")
            quote = claim.get("relevant_quote", "")
            source_title = claim.get("source_title", "")

            if not text or not quote:
                continue

            prompt = NLI_PROMPT.format(claim=text, quote=quote, source_title=source_title)
            response = await llm.call(prompt, role="verification_nli")
            result = _parse_json(response)

            if result and not result.get("entailed", True):
                severity = result.get("severity", "overstatement")
                log.info("layer3_failed", claim_id=claim_id, severity=severity,
                         reason=result.get("reason", ""))

                store.append(
                    event_type="meta.flag",
                    payload={
                        "claim_id": claim_id,
                        "flag_type": "verification_failed",
                        "layer": 3,
                        "severity": severity,
                        "reason": result.get("reason", ""),
                    },
                    actor="pipeline:verification",
                    method="nli_entailment",
                )
                failed_l3 += 1

                # Fabrication = reject claim
                if severity == "fabrication":
                    store.append(
                        event_type="claim.rank_changed",
                        payload={
                            "claim_id": claim_id,
                            "confidence": 0.1,
                            "reason": "Layer 3 NLI: fabrication detected",
                        },
                        actor="pipeline:verification",
                        method="nli_entailment",
                    )
            else:
                verified += 1

    # Layer 4: Cross-provider (only on medium-confidence claims)
    if layer4:
        # Sort by confidence, take middle band
        sorted_claims = sorted(
            claims_to_verify,
            key=lambda x: abs(x[1].get("confidence", 0.5) - 0.5),
        )
        n_to_check = max(1, int(len(sorted_claims) * layer4_top_pct))
        layer4_claims = sorted_claims[:n_to_check]

        for claim_id, claim in layer4_claims:
            text = claim.get("statement", {}).get("natural_language", "")
            quote = claim.get("relevant_quote", "")
            source_title = claim.get("source_title", "")

            if not text or not quote:
                continue

            prompt = CROSS_PROVIDER_PROMPT.format(
                claim=text, quote=quote, source_title=source_title,
            )
            response = await llm.call(prompt, role="verification_cross")
            result = _parse_json(response)

            if result and not result.get("verified", True):
                issues = result.get("issues", [])
                log.info("layer4_failed", claim_id=claim_id, issues=issues)

                store.append(
                    event_type="meta.flag",
                    payload={
                        "claim_id": claim_id,
                        "flag_type": "cross_provider_failed",
                        "layer": 4,
                        "issues": issues,
                        "cross_confidence": result.get("confidence", 0.0),
                    },
                    actor="pipeline:verification",
                    method="cross_provider",
                )
                failed_l4 += 1

    summary = {
        "total_checked": len(claims_to_verify),
        "verified": verified,
        "failed_l3": failed_l3,
        "failed_l4": failed_l4,
    }
    log.info("verification_complete", **summary)
    return summary


def _parse_json(text: str) -> dict | None:
    """Parse JSON from LLM response."""
    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except (json.JSONDecodeError, IndexError):
        pass
    return None
