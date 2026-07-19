"""Layer 3: Assessment — Multi-trial adversarial verification pipeline.

Combines:
- Pass³ multi-trial verification (from Preseal)
- Cross-model adversarial checking (from Autonomous Researcher Insight Layer)
- Compliance-trap detection and M2/M3 defenses (from SCHEMA research)
- 4-tier oracle cascade (from Preseal)

This is the core differentiator: the first epistemic verification system
that is aware of its own failure modes and applies empirically-validated
defenses against them.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

from .models import Claim, ClaimConfidence, KnowledgeBase, VerificationTrial
from .scoring import wilson_ci, score_cross_model, score_source_quality, classify_confidence
from .oracle import verify_claim, OracleVerdict
from .compliance_detector import detect_compliance_pressure, apply_defenses


# Prompt variants for multi-trial verification (different framings reduce correlated errors)
VERIFICATION_PROMPTS = [
    # Neutral framing
    """Evaluate whether this claim is supported by available evidence.
Claim: {claim}
Source: {source}
Respond with VERIFIED or UNVERIFIED, followed by your reasoning.""",

    # Skeptical framing
    """You are a skeptical reviewer. Find reasons this claim might be FALSE or UNSUPPORTED.
Claim: {claim}
Source: {source}
If you cannot find strong reasons to doubt it, respond VERIFIED. Otherwise UNVERIFIED.
Explain your reasoning.""",

    # Precision framing
    """Check this claim for factual accuracy, logical validity, and proper qualification.
Claim: {claim}
Source: {source}
Is the claim stated with appropriate precision? Does it overstate or understate the evidence?
Respond VERIFIED (accurate and properly qualified) or UNVERIFIED (inaccurate or overstated).""",

    # Adversarial framing
    """You are a red-team evaluator. Your job is to find the weakest link in this claim.
Claim: {claim}
Source: {source}
Attack the claim from every angle: source quality, logical gaps, alternative explanations,
hidden assumptions, overgeneralization. If it survives your best attack, respond VERIFIED.
Otherwise UNVERIFIED.""",

    # Calibration framing
    """On a scale of 0-100%, how confident are you that this claim is true?
Claim: {claim}
Source: {source}
If confidence > 70%, respond VERIFIED. If <= 70%, respond UNVERIFIED.
State your confidence percentage and reasoning.""",
]


CROSS_MODEL_SKEPTIC_PROMPT = """You are an independent epistemic auditor from a different analytical tradition.
A different AI system has made this claim. Your job is to find the weakest link.

Claim: {claim}
Source context: {source}

Instructions:
1. Identify the single most vulnerable assumption in this claim
2. Find the strongest counterargument or alternative explanation
3. Assess whether the source actually supports what's being claimed
4. Check for compliance-induced fabrication signals (overclaiming, hedge-stripping, false precision)

Output your assessment:
- WEAKEST_LINK: [the most vulnerable point]
- COUNTERARGUMENT: [strongest objection]
- SOURCE_ALIGNMENT: [does source actually say this? YES/PARTIAL/NO]
- FABRICATION_SIGNALS: [any detected? YES/NO + details]
- VERDICT: [SURVIVES or FAILS adversarial scrutiny]"""


JUDGE_PROMPT = """You are a neutral judge evaluating a dispute between a claim-maker and a skeptic.

Original claim: {claim}
Skeptic's attack: {attack}

Questions:
1. Did the skeptic find a REAL flaw, or is this a nitpick?
2. Does the flaw (if real) undermine the core claim, or just a peripheral detail?
3. Would a reasonable person still accept the claim after reading the skeptic's objection?

Verdict: CLAIM_STANDS or CLAIM_WEAKENED or CLAIM_REFUTED
Confidence: HIGH/MEDIUM/LOW
Reasoning: [1-2 sentences]"""


@dataclass
class AssessmentConfig:
    """Configuration for the assessment pipeline."""
    trials_per_claim: int = 5
    models: list = None  # model identifiers for cross-model check
    cross_model_enabled: bool = True
    compliance_detection_enabled: bool = True
    adversarial_rounds: int = 1
    domain: str = ""
    domain_facts: list = None

    def __post_init__(self):
        if self.models is None:
            self.models = ["claude-sonnet-4-20250514", "gpt-4o", "gemini-2.5-pro"]
        if self.domain_facts is None:
            self.domain_facts = []


async def assess_claim(
    claim: Claim,
    kb: KnowledgeBase,
    config: AssessmentConfig,
    llm_call,  # async callable: (prompt, model) -> response_text
    source_content: Optional[str] = None,
) -> ClaimConfidence:
    """Full assessment pipeline for a single claim.

    Runs all four assessment stages:
    A. Compliance-trap detection (pre-check)
    B. Multi-trial verification (Pass³)
    C. Cross-model adversarial check
    D. 4-tier oracle cascade
    """

    # Stage A: Compliance-Trap Detection
    compliance_detected = False
    if config.compliance_detection_enabled:
        for prompt_template in VERIFICATION_PROMPTS[:1]:
            test_prompt = prompt_template.format(claim=claim.text, source=claim.source.title)
            assessment = detect_compliance_pressure(test_prompt)
            if assessment.above_threshold:
                compliance_detected = True
                claim.metadata["compliance_pressure_detected"] = True
                break

    # Stage B: Multi-Trial Verification (Pass³)
    trials = []
    successes = 0
    primary_model = config.models[0] if config.models else "claude-sonnet-4-20250514"

    for i, prompt_template in enumerate(VERIFICATION_PROMPTS[:config.trials_per_claim]):
        prompt = prompt_template.format(claim=claim.text, source=claim.source.title)

        # Apply defenses if compliance pressure detected
        if compliance_detected:
            prompt, _ = apply_defenses(prompt, config.domain, config.domain_facts)

        response = await llm_call(prompt, primary_model)
        verified = _parse_verification_response(response)

        trial = VerificationTrial(
            claim_id=claim.id,
            trial_number=i,
            model=primary_model,
            prompt_variant=f"variant_{i}",
            result=verified,
            reasoning=response[:200],
            compliance_pressure_detected=compliance_detected,
            defense_applied="M2+M3" if compliance_detected else None,
        )
        trials.append(trial)

        if verified:
            successes += 1

    point_est, ci_lower, ci_upper = wilson_ci(successes, len(trials)), 0, 0
    if isinstance(point_est, tuple):
        ci_lower, ci_upper = point_est
        point_est = successes / len(trials) if trials else 0
    else:
        ci_lower, ci_upper = wilson_ci(successes, len(trials))
        point_est = successes / len(trials) if trials else 0

    # Stage C: Cross-Model Adversarial Check
    cross_model_results = {}
    if config.cross_model_enabled and len(config.models) > 1:
        for model in config.models[1:]:  # Skip primary (already used in trials)
            skeptic_prompt = CROSS_MODEL_SKEPTIC_PROMPT.format(
                claim=claim.text,
                source=f"{claim.source.title} ({claim.source.source_type})",
            )

            if compliance_detected:
                skeptic_prompt, _ = apply_defenses(skeptic_prompt, config.domain, config.domain_facts)

            skeptic_response = await llm_call(skeptic_prompt, model)
            survives = "SURVIVES" in skeptic_response.upper()
            cross_model_results[model] = survives

            # If skeptic found a flaw, run judge
            if not survives:
                judge_prompt = JUDGE_PROMPT.format(
                    claim=claim.text,
                    attack=skeptic_response[:500],
                )
                judge_response = await llm_call(judge_prompt, primary_model)
                if "CLAIM_STANDS" in judge_response.upper():
                    cross_model_results[model] = True  # Override: judge overruled skeptic

    cross_model_score = score_cross_model(cross_model_results) if cross_model_results else 0.8

    # Stage D: 4-Tier Oracle
    oracle_verdict = verify_claim(claim, kb, source_content)
    oracle_score = 1.0 if oracle_verdict.verified else 0.3
    if oracle_verdict.flags:
        oracle_score *= 0.9  # Slight penalty for flags even if verified

    # Compute source quality
    source_score = score_source_quality(claim.source.credibility_signals)

    # Combine into final confidence
    confidence = ClaimConfidence(
        evidence_strength=point_est,
        evidence_ci=(ci_lower, ci_upper),
        logical_consistency=oracle_score,
        adversarial_robustness=cross_model_score,
        source_quality=source_score,
        cross_model_agreement=cross_model_score,
        trials_run=len(trials),
        models_checked=list(cross_model_results.keys()),
    )

    return confidence


def _parse_verification_response(response: str) -> bool:
    """Parse LLM verification response into boolean."""
    response_upper = response.upper()
    if "UNVERIFIED" in response_upper:
        return False
    if "VERIFIED" in response_upper:
        return True
    # Fallback: look for confidence percentage
    import re
    match = re.search(r"(\d+)%", response)
    if match:
        return int(match.group(1)) > 70
    return False


async def assess_knowledge_base(
    kb: KnowledgeBase,
    config: AssessmentConfig,
    llm_call,
    source_contents: Optional[dict] = None,
) -> KnowledgeBase:
    """Run full assessment on all claims in a knowledge base.

    Updates each claim's confidence in-place.
    """
    source_contents = source_contents or {}

    for claim_id, claim in kb.claims.items():
        source_content = source_contents.get(claim.source.url)
        confidence = await assess_claim(claim, kb, config, llm_call, source_content)
        claim.confidence = confidence

        # Update status based on confidence
        level = confidence.level.value
        if level == "contested":
            claim.status = claim.status  # Keep current, flag for human review
        elif confidence.composite_score < 0.2:
            from .models import ClaimStatus
            claim.status = ClaimStatus.REFUTED

    kb.metadata["assessment_complete"] = True
    kb.metadata["config"] = {
        "trials_per_claim": config.trials_per_claim,
        "models": config.models,
        "compliance_detection": config.compliance_detection_enabled,
    }

    return kb
