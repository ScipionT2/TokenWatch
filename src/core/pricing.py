"""Model pricing engine — accurate to-the-token cost calculation.

Prices are per 1M tokens. Updated for 2026 model lineup.
This is the single source of truth for cost math — everything else delegates here.
"""

from src.models.schemas import ModelTier

# Pricing: (input_per_1m, output_per_1m, tier)
MODEL_PRICING: dict[str, tuple[float, float, ModelTier]] = {
    # Flagship
    "gpt-5.5": (5.00, 30.00, ModelTier.FLAGSHIP),
    "gpt-5.5-pro": (30.00, 180.00, ModelTier.FLAGSHIP),
    "gpt-5.4": (2.50, 15.00, ModelTier.FLAGSHIP),
    "gpt-5.4-pro": (30.00, 180.00, ModelTier.FLAGSHIP),
    "gpt-5.3-codex": (1.75, 14.00, ModelTier.FLAGSHIP),
    "gpt-5.2": (1.75, 14.00, ModelTier.FLAGSHIP),
    "gpt-5.2-pro": (21.00, 168.00, ModelTier.FLAGSHIP),
    "gpt-5.1": (1.25, 10.00, ModelTier.FLAGSHIP),
    "gpt-5": (1.25, 10.00, ModelTier.FLAGSHIP),
    "gpt-5-pro": (15.00, 120.00, ModelTier.FLAGSHIP),
    "o3": (2.00, 8.00, ModelTier.FLAGSHIP),
    "o3-pro": (20.00, 80.00, ModelTier.FLAGSHIP),
    # Standard
    "gpt-5.4-mini": (0.75, 4.50, ModelTier.STANDARD),
    "gpt-5.1-codex-mini": (0.25, 2.00, ModelTier.STANDARD),
    "gpt-5-mini": (0.25, 2.00, ModelTier.STANDARD),
    "o3-mini": (1.10, 4.40, ModelTier.STANDARD),
    "o4-mini": (1.10, 4.40, ModelTier.STANDARD),
    # Economy
    "gpt-5.4-nano": (0.20, 1.25, ModelTier.ECONOMY),
    "gpt-5-nano": (0.05, 0.40, ModelTier.ECONOMY),
    "gpt-4o-mini": (0.15, 0.60, ModelTier.ECONOMY),
    # Embedding
    "text-embedding-3-large": (0.13, 0.0, ModelTier.EMBEDDING),
    "text-embedding-3-small": (0.02, 0.0, ModelTier.EMBEDDING),
    # Image
    "gpt-5-image": (10.00, 10.00, ModelTier.IMAGE),
    "gpt-5-image-mini": (2.50, 2.00, ModelTier.IMAGE),

    # --- Anthropic (Claude) ---
    "claude-4": (3.00, 15.00, ModelTier.FLAGSHIP),
    "claude-4-opus": (15.00, 75.00, ModelTier.FLAGSHIP),
    "claude-4-sonnet": (3.00, 15.00, ModelTier.FLAGSHIP),
    "claude-4-haiku": (0.80, 4.00, ModelTier.STANDARD),
    "claude-4.6": (4.00, 20.00, ModelTier.FLAGSHIP),
    "claude-4.6-opus": (20.00, 100.00, ModelTier.FLAGSHIP),
    "claude-4.6-sonnet": (4.00, 20.00, ModelTier.FLAGSHIP),
    "claude-3.5-sonnet": (3.00, 15.00, ModelTier.FLAGSHIP),
    "claude-3.5-haiku": (0.80, 4.00, ModelTier.STANDARD),

    # --- Google (Gemini) ---
    "gemini-2.5-pro": (1.25, 10.00, ModelTier.FLAGSHIP),
    "gemini-2.5-flash": (0.15, 0.60, ModelTier.ECONOMY),
    "gemini-2.0-flash": (0.10, 0.40, ModelTier.ECONOMY),
    "gemini-2.0-pro": (1.00, 5.00, ModelTier.STANDARD),
}

# Fallback for unknown models — assume standard pricing
_FALLBACK_PRICING = (1.00, 5.00, ModelTier.STANDARD)


def get_pricing(model: str) -> tuple[float, float, ModelTier]:
    """Look up pricing for a model. Handles provider prefixes and aliases."""
    # Strip common prefixes (openai/, openrouter/openai/, etc.)
    clean = model.lower()
    for prefix in ("openai/", "openrouter/openai/", "openrouter/"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
            break

    if clean in MODEL_PRICING:
        return MODEL_PRICING[clean]

    # Try partial match for versioned models (gpt-5.1-chat → gpt-5.1)
    for known_model in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if clean.startswith(known_model):
            return MODEL_PRICING[known_model]

    return _FALLBACK_PRICING


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate exact cost in USD for a single request."""
    input_price, output_price, _ = get_pricing(model)
    cost = (prompt_tokens * input_price / 1_000_000) + (completion_tokens * output_price / 1_000_000)
    return round(cost, 6)


def get_tier(model: str) -> ModelTier:
    """Get the pricing tier for a model."""
    _, _, tier = get_pricing(model)
    return tier


def suggest_cheaper_model(model: str, task_type: str = "general") -> tuple[str, float]:
    """Suggest a cheaper model that could handle the task.
    
    Returns (suggested_model, estimated_savings_pct).
    """
    _, _, current_tier = get_pricing(model)

    suggestions = {
        ModelTier.FLAGSHIP: {
            "general": ("gpt-5-mini", 80),
            "coding": ("gpt-5.1-codex-mini", 75),
            "simple": ("gpt-5-nano", 95),
            "reasoning": ("o4-mini", 45),
        },
        ModelTier.STANDARD: {
            "general": ("gpt-5-nano", 70),
            "simple": ("gpt-5-nano", 70),
            "coding": ("gpt-5-nano", 60),
            "reasoning": ("gpt-5-nano", 60),
        },
    }

    tier_suggestions = suggestions.get(current_tier, {})
    return tier_suggestions.get(task_type, tier_suggestions.get("general", (model, 0)))


def estimate_batch_cost(model: str, avg_prompt_tokens: int, avg_completion_tokens: int, count: int) -> dict:
    """Estimate total cost for a batch of requests — useful for planning."""
    per_request = calculate_cost(model, avg_prompt_tokens, avg_completion_tokens)
    total = per_request * count
    cheaper_model, savings_pct = suggest_cheaper_model(model)
    cheaper_per_request = calculate_cost(cheaper_model, avg_prompt_tokens, avg_completion_tokens)
    cheaper_total = cheaper_per_request * count

    return {
        "model": model,
        "per_request_cost": per_request,
        "total_cost": round(total, 4),
        "request_count": count,
        "cheaper_alternative": {
            "model": cheaper_model,
            "per_request_cost": cheaper_per_request,
            "total_cost": round(cheaper_total, 4),
            "savings_usd": round(total - cheaper_total, 4),
            "savings_pct": savings_pct,
        },
    }
