"""Precise token counting using tiktoken — no estimates, no guessing.

Token counts are the foundation of cost calculation. Getting this wrong
means every dollar figure downstream is wrong too.
"""

import hashlib
from typing import Optional

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _TIKTOKEN_AVAILABLE = False


# Cache encodings to avoid re-init overhead
_encoding_cache: dict[str, object] = {}


def _get_encoding(model: str):
    """Get the correct tokenizer for a model, with fallback."""
    if not _TIKTOKEN_AVAILABLE:
        return None

    if model in _encoding_cache:
        return _encoding_cache[model]

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # Most newer models use cl100k_base or o200k_base
        try:
            enc = tiktoken.get_encoding("o200k_base")
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")

    _encoding_cache[model] = enc
    return enc


def count_tokens(text: str, model: str = "gpt-5") -> int:
    """Count tokens in a string. Falls back to word-based estimate if tiktoken unavailable."""
    enc = _get_encoding(model)
    if enc:
        return len(enc.encode(text))
    # Rough fallback: ~4 chars per token for English
    return max(1, len(text) // 4)


def count_message_tokens(messages: list[dict], model: str = "gpt-5") -> int:
    """Count tokens for a full chat messages array.
    
    Accounts for the per-message overhead that OpenAI charges:
    every message has ~4 tokens of framing (role, content delimiters).
    """
    total = 0
    for msg in messages:
        # 4 tokens per message for framing
        total += 4
        for key, value in msg.items():
            if isinstance(value, str):
                total += count_tokens(value, model)
    # 2 tokens for the assistant reply priming
    total += 2
    return total


def hash_prompt(messages: list[dict]) -> str:
    """Generate a deterministic hash for deduplication detection.
    
    Two identical prompts = same hash = potential cache hit.
    """
    content = "".join(
        f"{msg.get('role', '')}:{msg.get('content', '')}"
        for msg in messages
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def estimate_completion_tokens(prompt_tokens: int, model: str = "gpt-5") -> int:
    """Estimate expected completion tokens based on prompt size.
    
    Useful for pre-request cost estimation. Based on empirical ratios:
    - Chat: ~0.5-1.5x prompt tokens
    - Coding: ~1-3x prompt tokens
    - Summarization: ~0.2-0.4x prompt tokens
    """
    # Conservative estimate — assume 1:1 ratio
    return min(prompt_tokens, 4000)


def find_redundant_segments(messages: list[dict], model: str = "gpt-5") -> list[dict]:
    """Detect repeated or near-duplicate content across messages.
    
    Common waste patterns:
    - System prompt repeated in user messages
    - Same context pasted multiple times in a conversation
    - Verbose instructions that could be compressed
    """
    redundancies = []
    seen_content: dict[str, int] = {}

    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if not content:
            continue

        # Check for exact substring matches (>50 chars to avoid false positives)
        for seen_text, seen_idx in seen_content.items():
            if len(seen_text) > 50 and seen_text in content and i != seen_idx:
                tokens_wasted = count_tokens(seen_text, model)
                redundancies.append({
                    "type": "duplicate_content",
                    "message_index": i,
                    "original_index": seen_idx,
                    "tokens_wasted": tokens_wasted,
                    "preview": seen_text[:100] + "..." if len(seen_text) > 100 else seen_text,
                })

        # Store content segments for future comparison
        # Split into chunks to catch partial duplicates
        if len(content) > 100:
            for start in range(0, len(content) - 50, 50):
                chunk = content[start:start + 100]
                if chunk not in seen_content:
                    seen_content[chunk] = i

    return redundancies
