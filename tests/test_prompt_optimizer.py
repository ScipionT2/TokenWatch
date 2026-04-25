"""Prompt optimizer tests — verify waste detection and compression."""

import pytest
from src.core.prompt_optimizer import analyze_prompt, compress_messages


class TestAnalyzePrompt:
    def test_clean_prompt_no_issues(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is 2+2?"},
        ]
        result = analyze_prompt(messages, "gpt-5")
        assert result.original_tokens > 0
        assert result.estimated_cost_original > 0

    def test_long_system_prompt_flagged(self):
        long_system = "You are a helpful assistant. " * 200  # ~1000+ tokens
        messages = [
            {"role": "system", "content": long_system},
            {"role": "user", "content": "Hello"},
        ]
        result = analyze_prompt(messages, "gpt-5")
        assert any("System prompt" in i or "system" in i.lower() for i in result.issues)

    def test_multiple_system_messages_flagged(self):
        messages = [
            {"role": "system", "content": "First system message."},
            {"role": "system", "content": "Second system message."},
            {"role": "user", "content": "Hello"},
        ]
        result = analyze_prompt(messages, "gpt-5")
        assert any("Multiple system" in i or "multiple" in i.lower() for i in result.issues)

    def test_small_prompt_gets_model_recommendation(self):
        messages = [{"role": "user", "content": "Hi"}]
        result = analyze_prompt(messages, "gpt-5")
        # Small prompts on flagship models should suggest cheaper alternatives
        if result.original_tokens < 500:
            assert result.model_recommendation is not None


class TestCompressMessages:
    def test_whitespace_cleanup(self):
        messages = [
            {"role": "user", "content": "Hello\n\n\n\n\nworld   with   spaces"},
        ]
        compressed = compress_messages(messages)
        content = compressed[0]["content"]
        assert "\n\n\n" not in content
        assert "   " not in content

    def test_system_message_merge(self):
        messages = [
            {"role": "system", "content": "Rule 1."},
            {"role": "system", "content": "Rule 2."},
            {"role": "user", "content": "Hello"},
        ]
        compressed = compress_messages(messages)
        system_msgs = [m for m in compressed if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert "Rule 1" in system_msgs[0]["content"]
        assert "Rule 2" in system_msgs[0]["content"]

    def test_preserves_non_system_order(self):
        messages = [
            {"role": "system", "content": "System."},
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer."},
        ]
        compressed = compress_messages(messages)
        assert len(compressed) == 3
        assert compressed[0]["role"] == "system"
        assert compressed[1]["role"] == "user"
        assert compressed[2]["role"] == "assistant"
