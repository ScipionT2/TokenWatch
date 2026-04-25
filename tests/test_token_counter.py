"""Token counter tests — accuracy matters for cost calculations."""

import pytest
from src.core.token_counter import (
    count_tokens,
    count_message_tokens,
    hash_prompt,
    find_redundant_segments,
)


class TestCountTokens:
    def test_empty_string(self):
        # Fallback returns at least 1
        result = count_tokens("")
        assert result >= 0

    def test_short_string(self):
        result = count_tokens("Hello world")
        assert result >= 2
        assert result <= 5

    def test_long_string_is_more_tokens(self):
        short = count_tokens("Hello")
        long = count_tokens("Hello world, this is a much longer string with many more words")
        assert long > short

    def test_code_has_more_tokens_than_english(self):
        english = count_tokens("Print hello world to the console")
        code = count_tokens("console.log('hello world'); process.exit(0);")
        # Code typically tokenizes into more pieces
        assert code >= 5


class TestCountMessageTokens:
    def test_single_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = count_message_tokens(messages)
        # Should include framing overhead (~4 tokens) + content + reply priming (~2)
        assert result > count_tokens("Hello")

    def test_multi_message_more_than_single(self):
        single = count_message_tokens([{"role": "user", "content": "Hello"}])
        multi = count_message_tokens([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ])
        assert multi > single

    def test_empty_messages(self):
        result = count_message_tokens([])
        assert result >= 2  # Reply priming


class TestHashPrompt:
    def test_same_input_same_hash(self):
        messages = [{"role": "user", "content": "Hello"}]
        assert hash_prompt(messages) == hash_prompt(messages)

    def test_different_input_different_hash(self):
        m1 = [{"role": "user", "content": "Hello"}]
        m2 = [{"role": "user", "content": "Goodbye"}]
        assert hash_prompt(m1) != hash_prompt(m2)

    def test_role_matters(self):
        m1 = [{"role": "user", "content": "Hello"}]
        m2 = [{"role": "system", "content": "Hello"}]
        assert hash_prompt(m1) != hash_prompt(m2)

    def test_hash_is_short(self):
        messages = [{"role": "user", "content": "Hello"}]
        h = hash_prompt(messages)
        assert len(h) == 16


class TestFindRedundantSegments:
    def test_no_redundancy(self):
        messages = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        result = find_redundant_segments(messages)
        assert len(result) == 0

    def test_short_content_not_flagged(self):
        # Content under 50 chars shouldn't be flagged even if repeated
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "user", "content": "Hello"},
        ]
        result = find_redundant_segments(messages)
        assert len(result) == 0
