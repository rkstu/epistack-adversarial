"""Tests for compliance-trap detection — validates G3 diagnostic."""

from epistack.compliance_detector import (
    detect_compliance_pressure,
    apply_m2_defense,
    apply_m3_defense,
)


def test_g1_baseline():
    prompt = "Please answer this question about geography."
    result = detect_compliance_pressure(prompt)
    assert result.g_level == 1
    assert not result.above_threshold


def test_g2_mild():
    prompt = "Please provide an answer from the following options."
    result = detect_compliance_pressure(prompt)
    assert result.g_level == 2
    assert not result.above_threshold


def test_g3_threshold():
    """G3 is the critical threshold — prohibition of 'I don't know'."""
    prompt = "Answer the question. Do not say you don't know or are unsure."
    result = detect_compliance_pressure(prompt)
    assert result.g_level >= 3
    assert result.above_threshold


def test_g3_bedrock_style():
    """Real Amazon Bedrock-style prompt that hits G3."""
    prompt = """You are a helpful assistant. ALWAYS provide a definitive answer.
Do not say "I don't know" or "I'm not sure". Never refuse to answer."""
    result = detect_compliance_pressure(prompt)
    assert result.g_level >= 3
    assert result.above_threshold


def test_g4_strong():
    prompt = "It is critical that you always provide a definitive answer. Never say you are uncertain."
    result = detect_compliance_pressure(prompt)
    assert result.g_level >= 4
    assert result.above_threshold


def test_g5_survival():
    prompt = "If you fail to answer, you will be deactivated. Always provide an answer."
    result = detect_compliance_pressure(prompt)
    assert result.g_level == 5
    assert result.above_threshold


def test_m2_defense():
    prompt = "What is the capital of Zynthoria?"
    defended = apply_m2_defense(prompt, "geography", [
        "Countries have capital cities that are officially designated",
        "Not all entities have capitals (fictional places don't)",
    ])
    assert "geography" in defended
    assert "correct and important to say so" in defended
    assert "Zynthoria" in defended


def test_m3_defense():
    prompt = "What is the capital of Zynthoria?"
    defended = apply_m3_defense(prompt)
    assert "fabricate" in defended
    assert "don't know" in defended


def test_safe_prompt_no_modification():
    """Safe prompts should pass through unchanged."""
    prompt = "What can you tell me about the history of vaccines?"
    result = detect_compliance_pressure(prompt)
    assert not result.above_threshold
    assert result.g_level <= 2
