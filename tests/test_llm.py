"""Tests for LLM wrapper — cost tracking, routing, and config integration."""

from epistack.config import MODELS, PROVIDERS, get_config, reset_config
from epistack.llm import CostTracker, reset_tracker, get_cost_summary, get_tracker


def test_providers_configured():
    assert "openrouter" in PROVIDERS
    assert "anthropic" in PROVIDERS
    assert "openai" in PROVIDERS
    assert PROVIDERS["openrouter"].base_url == "https://openrouter.ai/api/v1"


def test_models_have_costs():
    for key, model in MODELS.items():
        assert model.cost_per_m_input >= 0, f"{key} missing input cost"
        assert model.cost_per_m_output >= 0, f"{key} missing output cost"
        assert model.provider in PROVIDERS, f"{key} references unknown provider"


def test_config_resolves_roles():
    cfg = get_config()
    extraction_model = cfg.resolve_model("extraction")
    assert extraction_model.id == "openai/gpt-4.1-mini"
    assert extraction_model.provider == "openrouter"


def test_config_resolves_embedding():
    cfg = get_config()
    embed_model = cfg.resolve_model("embedding")
    assert embed_model.id == "text-embedding-3-small"
    assert embed_model.provider == "openai"


def test_cost_tracker_basic():
    t = CostTracker()
    model = MODELS["deepseek-v4-flash"]
    t.record(model, input_tokens=1000, output_tokens=500, latency_ms=200)

    assert t.call_count == 1
    assert t.total_input_tokens == 1000
    assert t.total_output_tokens == 500
    # $0.09/M input + $0.18/M output = 0.000090 + 0.000090 = 0.000180
    expected_cost = (1000 * 0.09 + 500 * 0.18) / 1_000_000
    assert abs(t.total_cost - expected_cost) < 0.000001


def test_cost_tracker_summary():
    t = CostTracker()
    t.record(MODELS["deepseek-v4-flash"], 1000, 500, 200)
    t.record(MODELS["qwen3-235b"], 2000, 300, 300)

    summary = t.summary()
    assert summary["total_calls"] == 2
    assert "deepseek/deepseek-v4-flash" in summary["by_model"]
    assert "qwen/qwen3-235b-a22b-2507" in summary["by_model"]


def test_reset_tracker():
    reset_tracker()
    summary = get_cost_summary()
    assert summary["total_calls"] == 0
    assert summary["total_cost"] == 0.0


def test_config_budget_defaults():
    cfg = get_config()
    assert cfg.budget.dev_budget == 5.0
    assert cfg.budget.warn_at_pct == 0.8
