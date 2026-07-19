"""Provider-agnostic LLM client — routes calls based on config.

All modules call llm.call(role="extraction") or llm.call(model_key="deepseek-v4-flash").
Routing, API keys, retries, cost tracking — all handled here.
No provider-specific logic exists anywhere else in the codebase.

Config-driven: change config.yaml to switch providers. Zero code changes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import EpistackConfig, ModelConfig, ProviderConfig, get_config, MODELS, PROVIDERS

log = structlog.get_logger()


# ─── Cost Tracking ──────────────────────────────────────────────────────────

@dataclass
class UsageRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class CostTracker:
    records: list[UsageRecord] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(r.cost for r in self.records)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)

    @property
    def call_count(self) -> int:
        return len(self.records)

    def record(self, model_config: ModelConfig, input_tokens: int, output_tokens: int, latency_ms: float) -> UsageRecord:
        cost = (
            input_tokens * model_config.cost_per_m_input
            + output_tokens * model_config.cost_per_m_output
        ) / 1_000_000
        rec = UsageRecord(
            model=model_config.id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
        )
        self.records.append(rec)
        return rec

    def summary(self) -> dict[str, Any]:
        by_model: dict[str, float] = {}
        for r in self.records:
            by_model[r.model] = by_model.get(r.model, 0) + r.cost
        return {
            "total_cost": round(self.total_cost, 4),
            "total_calls": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "by_model": {k: round(v, 4) for k, v in by_model.items()},
        }


_tracker = CostTracker()


class BudgetExceeded(Exception):
    """Raised when budget cap is hit."""


class LLMError(Exception):
    """Raised when an LLM call fails after all retries."""


# ─── Public API ─────────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
    reraise=True,
)
async def call(
    prompt: str,
    *,
    role: str | None = None,
    model_key: str | None = None,
    system: str | None = None,
    max_tokens: int | None = None,
    temperature: float = 0.0,
) -> str:
    """Call an LLM. Provider-agnostic — routed by config.

    Specify EITHER:
      role="extraction"  → resolved via config.models.extraction
      model_key="deepseek-v4-flash"  → direct model lookup

    Returns the response text. Tracks cost automatically.
    """
    cfg = get_config()

    # Resolve model
    if role:
        model_config = cfg.resolve_model(role)
    elif model_key:
        if model_key not in MODELS:
            raise ValueError(f"Unknown model_key '{model_key}'. Available: {list(MODELS.keys())}")
        model_config = MODELS[model_key]
    else:
        raise ValueError("Must specify either role= or model_key=")

    # Budget check
    budget_limit = cfg.budget.dev_budget
    if _tracker.total_cost >= budget_limit:
        raise BudgetExceeded(
            f"Budget ${budget_limit:.2f} exceeded (spent: ${_tracker.total_cost:.2f}). "
            f"Increase budget.dev_budget in config.yaml for production runs."
        )
    if _tracker.total_cost >= budget_limit * cfg.budget.warn_at_pct:
        log.warning("budget_warning", spent=f"${_tracker.total_cost:.2f}",
                    limit=f"${budget_limit:.2f}")

    # Resolve provider
    provider = model_config.provider_config
    if not provider.is_available:
        raise LLMError(
            f"Provider '{provider.name}' not available. "
            f"Set {provider.api_key_env} in .env or environment."
        )

    effective_max_tokens = max_tokens or model_config.max_tokens
    start = time.monotonic()

    try:
        if provider.name == "anthropic":
            result = await _call_anthropic(prompt, model_config, provider, system, effective_max_tokens, temperature)
        else:
            # OpenAI-compatible (openai, openrouter, nebius)
            result = await _call_openai_compatible(prompt, model_config, provider, system, effective_max_tokens, temperature)
    except (httpx.ConnectError, httpx.TimeoutException):
        raise
    except Exception as e:
        log.error("llm_call_failed", model=model_config.id, provider=provider.name, error=str(e))
        raise LLMError(f"LLM call failed ({provider.name}/{model_config.id}): {e}") from e

    latency_ms = (time.monotonic() - start) * 1000
    rec = _tracker.record(model_config, result["input_tokens"], result["output_tokens"], latency_ms)

    log.info(
        "llm_call",
        model=model_config.id,
        provider=provider.name,
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost=f"${rec.cost:.5f}",
        latency_ms=f"{latency_ms:.0f}",
        total_cost=f"${_tracker.total_cost:.4f}",
    )

    return result["text"]


async def embed(texts: list[str], *, role: str = "embedding") -> list[list[float]]:
    """Embed a batch of texts. Returns list of vectors."""
    import openai

    cfg = get_config()
    model_config = cfg.resolve_model(role)
    provider = model_config.provider_config

    start = time.monotonic()
    client = openai.AsyncOpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url,
    )

    response = await client.embeddings.create(input=texts, model=model_config.id)

    latency_ms = (time.monotonic() - start) * 1000
    input_tokens = response.usage.total_tokens if response.usage else len(" ".join(texts)) // 4
    _tracker.record(model_config, input_tokens, 0, latency_ms)

    log.info("embed_call", model=model_config.id, texts=len(texts),
             input_tokens=input_tokens)

    return [item.embedding for item in response.data]


# ─── Provider Implementations ───────────────────────────────────────────────

async def _call_anthropic(
    prompt: str,
    model_config: ModelConfig,
    provider: ProviderConfig,
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=provider.api_key)

    kwargs: dict[str, Any] = {
        "model": model_config.id,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = await client.messages.create(**kwargs)

    return {
        "text": response.content[0].text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


async def _call_openai_compatible(
    prompt: str,
    model_config: ModelConfig,
    provider: ProviderConfig,
    system: str | None,
    max_tokens: int,
    temperature: float,
) -> dict:
    """Works for: OpenAI, OpenRouter, Nebius, or any OpenAI-compatible API."""
    import openai

    client = openai.AsyncOpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url,
    )

    messages = []
    if system and model_config.supports_system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await client.chat.completions.create(
        model=model_config.id,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    choice = response.choices[0]
    usage = response.usage

    return {
        "text": choice.message.content or "",
        "input_tokens": usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
    }


# ─── Utilities ──────────────────────────────────────────────────────────────

def reset_tracker():
    """Reset cost tracker (call at start of each pipeline run)."""
    global _tracker
    _tracker = CostTracker()


def get_cost_summary() -> dict[str, Any]:
    """Get current cost tracking summary."""
    return _tracker.summary()


def get_tracker() -> CostTracker:
    """Get the tracker instance (for testing)."""
    return _tracker
