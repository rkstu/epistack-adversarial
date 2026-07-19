"""Single source of truth for all Epistack configuration.

Every parameter used anywhere in the pipeline reads from this module.
No magic numbers or provider-specific logic in other files.

To change provider/model/thresholds: edit config.yaml or set env vars.
The pipeline is provider-agnostic — only this file knows about specific APIs.

Follows: Apollo Research pattern (ExperimentConfig), 12-factor app (env-based config).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ─── Load .env if present ───────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            if key.strip() not in os.environ:
                os.environ[key.strip()] = value


# ─── Provider Definitions ───────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider."""
    name: str
    base_url: str | None = None
    api_key_env: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)


PROVIDERS: dict[str, ProviderConfig] = {
    "openrouter": ProviderConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
    "anthropic": ProviderConfig(
        name="anthropic",
        base_url=None,  # Uses anthropic SDK default
        api_key_env="ANTHROPIC_API_KEY",
    ),
    "openai": ProviderConfig(
        name="openai",
        base_url=None,  # Uses openai SDK default
        api_key_env="OPENAI_API_KEY",
    ),
    "nebius": ProviderConfig(
        name="nebius",
        base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1"),
        api_key_env="NEBIUS_API_KEY",
    ),
}


# ─── Model Definitions ──────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """Configuration for a single model."""
    id: str                         # Model identifier for the API
    provider: str                   # Key into PROVIDERS
    cost_per_m_input: float = 0.0   # $ per 1M input tokens
    cost_per_m_output: float = 0.0  # $ per 1M output tokens
    max_tokens: int = 4096
    supports_system: bool = True
    supports_json_mode: bool = False

    @property
    def provider_config(self) -> ProviderConfig:
        return PROVIDERS[self.provider]


MODELS: dict[str, ModelConfig] = {
    # ─── OpenRouter (cheap experimentation) ───
    "gpt-4.1-mini": ModelConfig(
        id="openai/gpt-4.1-mini",
        provider="openrouter",
        cost_per_m_input=0.40,
        cost_per_m_output=1.60,
        max_tokens=8192,
    ),
    "gpt-4.1-nano": ModelConfig(
        id="openai/gpt-4.1-nano",
        provider="openrouter",
        cost_per_m_input=0.10,
        cost_per_m_output=0.40,
        max_tokens=8192,
    ),
    "deepseek-v4-pro": ModelConfig(
        id="deepseek/deepseek-v4-pro",
        provider="openrouter",
        cost_per_m_input=0.43,
        cost_per_m_output=0.87,
        max_tokens=8192,
    ),
    "deepseek-v4-flash": ModelConfig(
        id="deepseek/deepseek-v4-flash",
        provider="openrouter",
        cost_per_m_input=0.09,
        cost_per_m_output=0.18,
        max_tokens=8192,
    ),
    "qwen3-235b": ModelConfig(
        id="qwen/qwen3-235b-a22b-2507",
        provider="openrouter",
        cost_per_m_input=0.09,
        cost_per_m_output=0.10,
        max_tokens=8192,
    ),
    "gemini-flash-lite": ModelConfig(
        id="google/gemini-3.1-flash-lite",
        provider="openrouter",
        cost_per_m_input=0.25,
        cost_per_m_output=1.50,
        max_tokens=8192,
    ),
    # ─── Anthropic (direct, for production) ───
    "claude-sonnet": ModelConfig(
        id="claude-sonnet-4-6",
        provider="anthropic",
        cost_per_m_input=3.00,
        cost_per_m_output=15.00,
        max_tokens=8192,
    ),
    "claude-haiku": ModelConfig(
        id="claude-haiku-4-5-20251001",
        provider="anthropic",
        cost_per_m_input=0.80,
        cost_per_m_output=4.00,
        max_tokens=4096,
    ),
    # ─── OpenAI ───
    "gpt-4o": ModelConfig(
        id="gpt-4o",
        provider="openai",
        cost_per_m_input=2.50,
        cost_per_m_output=10.00,
        max_tokens=4096,
    ),
    "embedding-small": ModelConfig(
        id="text-embedding-3-small",
        provider="openai",
        cost_per_m_input=0.02,
        cost_per_m_output=0.0,
        max_tokens=8191,
    ),
}


# ─── Pipeline Role Assignments ──────────────────────────────────────────────
# Change these to switch models for different pipeline stages.
# Only edit HERE — all modules read from this.

@dataclass
class PipelineModels:
    """Which model handles which pipeline stage.

    Speed-optimized: gpt-4.1-mini (3s, quality) for extraction/confirmation.
    gpt-4.1-nano (3s, cheapest) for batch tasks.
    Previous: deepseek-v4-pro was 7s+ per call (2.3× slower).
    """
    extraction: str = "gpt-4.1-mini"             # Claim extraction (fast + quality)
    verification_nli: str = "gpt-4.1-nano"       # Layer 3: NLI entailment (batch, cheap)
    verification_cross: str = "gpt-4.1-nano"     # Layer 4: Cross-provider check (batch)
    relationship_batch: str = "gpt-4.1-nano"     # Edge classification (batch, cheap)
    relationship_confirm: str = "gpt-4.1-mini"   # Contradiction confirmation (needs quality)
    discourse_label: str = "gpt-4.1-nano"        # Position labeling (batch)
    discourse_crux: str = "gpt-4.1-mini"         # Crux identification (needs reasoning)
    discourse_empty: str = "gpt-4.1-mini"        # Empty chair generation (needs reasoning)
    embedding: str = "embedding-small"           # Claim embeddings


# ─── Pipeline Parameters ────────────────────────────────────────────────────

@dataclass
class ExtractionParams:
    """Parameters for claim extraction."""
    max_claims_per_source: int = 50
    claims_per_chunk: int = 5       # Target: 3-5 most important per chunk
    chunk_size: int = 8000
    chunk_overlap: int = 500
    min_quote_length: int = 10
    temperature: float = 0.0


@dataclass
class VerificationParams:
    """Parameters for verification pipeline."""
    layer1_enabled: bool = True      # Quote containment ($0)
    layer2_enabled: bool = True      # Overclaiming regex ($0)
    layer3_enabled: bool = True      # NLI entailment
    layer4_enabled: bool = True      # Cross-provider
    layer4_only_top_pct: float = 0.1  # Only check top 10% medium-confidence


@dataclass
class RelationshipParams:
    """Parameters for relationship detection."""
    cosine_threshold: float = 0.6
    cross_source_cosine_threshold: float = 0.4  # Lower for opposing sources (different vocabulary)
    batch_size: int = 15
    dedup_merge_threshold: float = 0.92
    dedup_check_threshold: float = 0.80
    embedding_persist: bool = True   # Save to data/{case}/embeddings.npz


@dataclass
class ConfidenceParams:
    """Parameters for confidence model."""
    correlation_threshold: float = 0.25    # Single-linkage clustering
    empirical_default: float = 0.5         # Default confidence for empirical claims
    assessment_default: float = 0.35       # Lower default for assessment claims
    assessment_evidence_weight: float = 0.3  # When assessment claims support empirical claims, their strength × this
    supersession_decay_days: int = 365     # Max decay period
    supersession_max_decay: float = 0.3    # Max 30% decay


@dataclass
class CruxParams:
    """Parameters for crux detection."""
    decay: float = 0.7              # Exponential decay per hop
    max_depth: int = 20             # BFS max traversal depth
    cascade_edge_types: tuple = ("supports", "depends_on", "is_crux_for")


@dataclass
class DiscourseParams:
    """Parameters for discourse mapping."""
    min_cluster_size_values: list = field(default_factory=lambda: [5, 10, 15, 20])
    valid_cluster_range: tuple = (2, 8)   # Accept 2-8 positions
    fallback_to_llm: bool = True          # If HDBSCAN fails, use LLM


@dataclass
class BudgetParams:
    """Budget controls."""
    dev_budget: float = 5.0          # Max $ per dev/test session
    production_budget: float = 20.0  # Max $ per case study (production)
    warn_at_pct: float = 0.8        # Warn at 80% of budget


# ─── Master Config ──────────────────────────────────────────────────────────

@dataclass
class EpistackConfig:
    """Master configuration — single source of truth for entire pipeline."""
    models: PipelineModels = field(default_factory=PipelineModels)
    extraction: ExtractionParams = field(default_factory=ExtractionParams)
    verification: VerificationParams = field(default_factory=VerificationParams)
    relationships: RelationshipParams = field(default_factory=RelationshipParams)
    confidence: ConfidenceParams = field(default_factory=ConfidenceParams)
    crux: CruxParams = field(default_factory=CruxParams)
    discourse: DiscourseParams = field(default_factory=DiscourseParams)
    budget: BudgetParams = field(default_factory=BudgetParams)

    def resolve_model(self, role: str) -> ModelConfig:
        """Resolve a pipeline role to its full model config."""
        model_key = getattr(self.models, role)
        if model_key not in MODELS:
            raise ValueError(f"Unknown model '{model_key}' for role '{role}'. Available: {list(MODELS.keys())}")
        return MODELS[model_key]

    def to_dict(self) -> dict[str, Any]:
        """Serialize config for logging/debugging."""
        import dataclasses
        return dataclasses.asdict(self)


# ─── Config Loading ─────────────────────────────────────────────────────────

def load_config(config_path: str | Path | None = None) -> EpistackConfig:
    """Load config from YAML file, falling back to defaults.

    Precedence: YAML file > env vars > defaults.
    """
    config = EpistackConfig()

    # Load from YAML if provided
    if config_path:
        path = Path(config_path)
        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            config = _apply_yaml(config, data)

    # Check default location
    default_path = _PROJECT_ROOT / "config.yaml"
    if not config_path and default_path.exists():
        with open(default_path) as f:
            data = yaml.safe_load(f) or {}
        config = _apply_yaml(config, data)

    # Env var overrides (highest precedence)
    if os.environ.get("EPISTACK_EXTRACTION_MODEL"):
        config.models.extraction = os.environ["EPISTACK_EXTRACTION_MODEL"]
    if os.environ.get("EPISTACK_DEV_BUDGET"):
        config.budget.dev_budget = float(os.environ["EPISTACK_DEV_BUDGET"])

    return config


def _apply_yaml(config: EpistackConfig, data: dict) -> EpistackConfig:
    """Apply YAML overrides to config."""
    if "models" in data:
        for key, value in data["models"].items():
            if hasattr(config.models, key):
                setattr(config.models, key, value)
    if "extraction" in data:
        for key, value in data["extraction"].items():
            if hasattr(config.extraction, key):
                setattr(config.extraction, key, value)
    if "verification" in data:
        for key, value in data["verification"].items():
            if hasattr(config.verification, key):
                setattr(config.verification, key, value)
    if "relationships" in data:
        for key, value in data["relationships"].items():
            if hasattr(config.relationships, key):
                setattr(config.relationships, key, value)
    if "budget" in data:
        for key, value in data["budget"].items():
            if hasattr(config.budget, key):
                setattr(config.budget, key, value)
    return config


# ─── Singleton (loaded once, used everywhere) ───────────────────────────────

_config: EpistackConfig | None = None


def get_config() -> EpistackConfig:
    """Get the global config singleton. Loads on first access."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config(config: EpistackConfig | None = None):
    """Reset config (for testing or re-loading)."""
    global _config
    _config = config
