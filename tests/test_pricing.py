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


class TestThirdPartyModels:
    """Tests for Claude and Gemini model pricing."""

    def test_claude_4_pricing(self):
        inp, out, tier = get_pricing("claude-4")
        assert inp == 3.00
        assert out == 15.00
        assert tier == ModelTier.FLAGSHIP

    def test_claude_4_6_pricing(self):
        inp, out, tier = get_pricing("claude-4.6")
        assert inp == 4.00
        assert out == 20.00
        assert tier == ModelTier.FLAGSHIP

    def test_claude_4_6_opus_pricing(self):
        inp, out, tier = get_pricing("claude-4.6-opus")
        assert inp == 20.00
        assert out == 100.00
        assert tier == ModelTier.FLAGSHIP

    def test_claude_4_haiku_is_standard(self):
        _, _, tier = get_pricing("claude-4-haiku")
        assert tier == ModelTier.STANDARD

    def test_gemini_2_5_pro_pricing(self):
        inp, out, tier = get_pricing("gemini-2.5-pro")
        assert inp == 1.25
        assert out == 10.00
        assert tier == ModelTier.FLAGSHIP

    def test_gemini_2_5_flash_pricing(self):
        inp, out, tier = get_pricing("gemini-2.5-flash")
        assert inp == 0.15
        assert out == 0.60
        assert tier == ModelTier.ECONOMY

    def test_claude_cost_calculation(self):
        # claude-4.6: $4.00/1M in, $20.00/1M out
        # 10k input + 5k output = $0.04 + $0.10 = $0.14
        cost = calculate_cost("claude-4.6", 10000, 5000)
        assert abs(cost - 0.14) < 0.0001

    def test_gemini_flash_is_cheap(self):
        cost = calculate_cost("gemini-2.5-flash", 10000, 5000)
        assert cost < 0.01

    def test_model_count_includes_third_party(self):
        assert len(MODEL_PRICING) >= 35  # 25 OpenAI + 9 Claude + 4 Gemini


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
