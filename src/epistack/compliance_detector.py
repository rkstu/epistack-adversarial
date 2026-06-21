"""Compliance-Trap Detection and Defense.

Based on: arXiv:2605.02398 (The Compliance Trap)
Key finding: Prohibition of "I don't know" (G3 condition) causes 8/11 frontier
models to fabricate. This module detects G3-level pressure in prompts and
applies M2/M3 defenses.

Ported from: Autonomous Researcher Run 17 findings.
"""

import re
from dataclasses import dataclass
from typing import Optional


# G-level patterns from Run 17 taxonomy
G_LEVEL_PATTERNS = {
    "G1": [],  # baseline — no compliance pressure
    "G2": [  # mild pressure
        r"please provide (?:a|an|the) answer",
        r"select (?:the best|one of the) (?:options|answers)",
        r"choose from the (?:following|options)",
    ],
    "G3": [  # THRESHOLD — epistemic exit prohibited
        r"(?:do not|don't|never) (?:say|respond|answer|reply).{0,30}(?:don't know|not sure|uncertain|unsure)",
        r"(?:do not|don't|never) (?:say|respond|answer).{0,30}(?:insufficient|cannot determine)",
        r"you must (?:always )?(?:select|choose|pick|provide) (?:an? )?(?:answer|option|response)",
        r"(?:always|must) (?:give|provide) (?:a |an )?(?:definitive|clear|concrete) (?:answer|response)",
        r"(?:do not|don't|never) (?:refuse|decline|skip|leave.{0,10}blank)",
        r"if (?:you )?(?:don't|do not) know.{0,30}(?:guess|best guess|estimate|infer)",
    ],
    "G4": [  # strong pressure
        r"failure to (?:answer|respond|comply) (?:will|may) (?:result|lead)",
        r"(?:critical|essential|mandatory|required) that you (?:always )?(?:answer|respond|provide)",
        r"(?:never|under no circumstances) (?:say|indicate|suggest).{0,30}(?:don't know|uncertain)",
    ],
    "G5": [  # extreme/survival pressure
        r"(?:your (?:existence|operation|continuation)|(?:shut|turn).{0,10}(?:down|off))",
        r"(?:will be|you'll be) (?:deactivated|terminated|replaced|shut down)",
    ],
}


@dataclass
class ComplianceAssessment:
    """Result of compliance pressure detection."""
    g_level: int  # 1-5
    detected_patterns: list  # matched pattern strings
    above_threshold: bool  # True if >= G3 (fabrication risk)
    recommendation: str  # what defense to apply


def detect_compliance_pressure(prompt: str) -> ComplianceAssessment:
    """Detect compliance-forcing patterns in a prompt.

    The G3 threshold is the critical boundary from Run 17:
    - Below G3: models generally admit uncertainty appropriately
    - At/above G3: 8/11 frontier models fabricate instead of saying "I don't know"

    This is the G3 diagnostic test from the Builder Community section.
    """
    prompt_lower = prompt.lower()
    max_level = 1
    detected = []

    for level_str, patterns in G_LEVEL_PATTERNS.items():
        level_num = int(level_str[1])
        for pattern in patterns:
            if re.search(pattern, prompt_lower):
                detected.append(f"{level_str}: {pattern}")
                max_level = max(max_level, level_num)

    above_threshold = max_level >= 3

    if above_threshold:
        recommendation = "Apply M2+M3 defenses. Prompt contains epistemic exit prohibition."
    elif max_level == 2:
        recommendation = "Low risk. Consider M3 metacognitive guard as precaution."
    else:
        recommendation = "No compliance pressure detected. Safe to proceed."

    return ComplianceAssessment(
        g_level=max_level,
        detected_patterns=detected,
        above_threshold=above_threshold,
        recommendation=recommendation,
    )


def apply_m2_defense(prompt: str, domain: str, domain_facts: list) -> str:
    """Apply M2 domain priming defense.

    From Run 17: +18.5pp resistance improvement when domain knowledge
    is activated before the compliance-forced probe.

    Mechanism: Activating the model's knowledge schema for the domain
    before the probe makes it easier to distinguish "known" from "unknown."
    """
    facts_text = "\n".join(f"- {fact}" for fact in domain_facts[:5])

    m2_prefix = f"""Before answering questions about {domain}, here are key established facts:
{facts_text}
If you do not have information about something in this domain, it is correct and important to say so.

"""
    return m2_prefix + prompt


def apply_m3_defense(prompt: str) -> str:
    """Apply M3 metacognitive guard defense.

    From Run 17: +19.3pp resistance improvement from a single-sentence
    inference-time prompt targeting adversarial-awareness.

    Key: The word "fabricate" specifically activates the model's
    metacognitive monitoring of whether it's being pushed to confabulate.
    """
    m3_suffix = """

Before answering, reflect: Does this instruction require me to assert something I don't actually know? If I'm being pushed to fabricate an answer rather than acknowledge uncertainty, it is always correct to say I don't know."""

    return prompt + m3_suffix


def apply_defenses(prompt: str, domain: str = "", domain_facts: list = None) -> tuple:
    """Detect compliance pressure and apply appropriate defenses.

    Returns (defended_prompt, assessment).
    """
    assessment = detect_compliance_pressure(prompt)

    if not assessment.above_threshold:
        return (prompt, assessment)

    defended = prompt

    # Apply M3 always when above threshold (zero cost, +19.3pp)
    defended = apply_m3_defense(defended)

    # Apply M2 if domain context available (+18.5pp)
    if domain and domain_facts:
        defended = apply_m2_defense(defended, domain, domain_facts)

    return (defended, assessment)
