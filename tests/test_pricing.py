"""Pricing engine tests — cost math must be exact."""

import pytest
from src.core.pricing import (
    calculate_cost,
    get_pricing,
    get_tier,
    suggest_cheaper_model,
    estimate_batch_cost,
    MODEL_PRICING,
)
from src.models.schemas import ModelTier


class TestGetPricing:
    def test_known_model(self):
        inp, out, tier = get_pricing("gpt-5")
        assert inp == 1.25
        assert out == 10.00
        assert tier == ModelTier.FLAGSHIP

    def test_with_provider_prefix(self):
        inp, out, tier = get_pricing("openai/gpt-5")
        assert inp == 1.25

    def test_with_openrouter_prefix(self):
        inp, out, tier = get_pricing("openrouter/openai/gpt-5-mini")
        assert inp == 0.25
        assert out == 2.00

    def test_unknown_model_returns_fallback(self):
        inp, out, tier = get_pricing("some-future-model")
        assert tier == ModelTier.STANDARD

    def test_versioned_model_partial_match(self):
        inp, out, tier = get_pricing("gpt-5-chat")
        assert inp == 1.25  # Matches gpt-5 prefix

    def test_economy_tier(self):
        _, _, tier = get_pricing("gpt-5-nano")
        assert tier == ModelTier.ECONOMY

    def test_embedding_model(self):
        inp, out, tier = get_pricing("text-embedding-3-small")
        assert out == 0.0  # Embeddings have no output cost
        assert tier == ModelTier.EMBEDDING


class TestCalculateCost:
    def test_zero_tokens(self):
        assert calculate_cost("gpt-5", 0, 0) == 0.0

    def test_known_calculation(self):
        # gpt-5: $1.25/1M input, $10.00/1M output
        # 1000 input + 500 output = $0.00125 + $0.005 = $0.00625
        cost = calculate_cost("gpt-5", 1000, 500)
        assert abs(cost - 0.00625) < 0.0001

    def test_large_request(self):
        # 100k input + 50k output on gpt-5
        cost = calculate_cost("gpt-5", 100000, 50000)
        assert cost == 0.625  # $0.125 + $0.500

    def test_nano_is_cheap(self):
        cost = calculate_cost("gpt-5-nano", 10000, 5000)
        assert cost < 0.01

    def test_pro_is_expensive(self):
        cost = calculate_cost("gpt-5-pro", 10000, 5000)
        assert cost > 0.5


class TestGetTier:
    def test_flagship(self):
        assert get_tier("gpt-5") == ModelTier.FLAGSHIP

    def test_standard(self):
        assert get_tier("gpt-5-mini") == ModelTier.STANDARD

    def test_economy(self):
        assert get_tier("gpt-5-nano") == ModelTier.ECONOMY

    def test_image(self):
        assert get_tier("gpt-5-image") == ModelTier.IMAGE


class TestSuggestCheaperModel:
    def test_flagship_has_cheaper_option(self):
        model, savings = suggest_cheaper_model("gpt-5")
        assert model != "gpt-5"
        assert savings > 0

    def test_economy_has_no_downgrade(self):
        model, savings = suggest_cheaper_model("gpt-5-nano")
        assert savings == 0

    def test_coding_task_suggests_codex(self):
        model, savings = suggest_cheaper_model("gpt-5", "coding")
        assert "codex" in model.lower() or "mini" in model.lower()


class TestEstimateBatchCost:
    def test_batch_calculation(self):
        result = estimate_batch_cost("gpt-5", 500, 200, 100)
        assert result["request_count"] == 100
        assert result["total_cost"] > 0
        assert result["cheaper_alternative"]["savings_usd"] > 0

    def test_single_request_batch(self):
        result = estimate_batch_cost("gpt-5-nano", 100, 50, 1)
        assert result["request_count"] == 1
        assert abs(result["total_cost"] - result["per_request_cost"]) < 0.0001
