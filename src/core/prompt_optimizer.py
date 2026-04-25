"""Prompt optimization engine — reduce tokens without losing meaning.

The biggest cost lever in any LLM application is prompt efficiency.
Most prompts waste 20-40% of tokens on redundancy, over-explanation,
and verbose formatting that the model doesn't need.
"""

import re
from typing import Optional

from src.core.token_counter import count_tokens, count_message_tokens, find_redundant_segments
from src.core.pricing import calculate_cost, suggest_cheaper_model, get_tier
from src.models.schemas import PromptAnalysis


def analyze_prompt(messages: list[dict], model: str = "gpt-5") -> PromptAnalysis:
    """Full prompt analysis — find waste, suggest optimizations."""
    original_tokens = count_message_tokens(messages, model)
    issues = []
    suggestions = []
    redundant = []

    # Check system prompt length
    system_msgs = [m for m in messages if m.get("role") == "system"]
    if system_msgs:
        sys_tokens = sum(count_tokens(m.get("content", ""), model) for m in system_msgs)
        if sys_tokens > 1000:
            issues.append(f"System prompt is {sys_tokens} tokens — consider condensing to <500 tokens.")
            suggestions.append("Move detailed examples to user messages instead of system prompt.")
        if len(system_msgs) > 1:
            issues.append(f"Multiple system messages ({len(system_msgs)}) — consolidate into one.")

    # Check for redundant content
    redundancies = find_redundant_segments(messages, model)
    total_wasted = sum(r["tokens_wasted"] for r in redundancies)
    if redundancies:
        issues.append(f"Found {len(redundancies)} redundant segments wasting ~{total_wasted} tokens.")
        redundant = [r["preview"] for r in redundancies]

    # Check for common waste patterns
    for i, msg in enumerate(messages):
        content = msg.get("content", "")
        if not content:
            continue

        # Excessive whitespace
        stripped = re.sub(r'\n{3,}', '\n\n', content)
        stripped = re.sub(r' {2,}', ' ', stripped)
        if len(stripped) < len(content) * 0.9:
            issues.append(f"Message {i}: excessive whitespace — {len(content) - len(stripped)} chars wasted.")

        # Overly polite prefixes that burn tokens
        polite_patterns = [
            r'^(please |kindly |could you please |i would like you to |i need you to )',
            r'(thank you|thanks in advance|i appreciate)',
        ]
        for pattern in polite_patterns:
            if re.search(pattern, content.lower()):
                suggestions.append(f"Message {i}: Remove polite filler — the model doesn't need it.")
                break

        # JSON/XML in prompts that could be compressed
        if content.count('{') > 5 or content.count('<') > 10:
            suggestions.append(f"Message {i}: Large structured data detected — consider summarizing instead of including raw JSON/XML.")

    # Model recommendation
    model_rec = None
    tier = get_tier(model)
    if original_tokens < 500:
        cheaper, savings = suggest_cheaper_model(model, "simple")
        if cheaper != model:
            model_rec = f"This prompt is only {original_tokens} tokens — consider using {cheaper} (save ~{savings}%)"

    # Estimate optimized token count
    optimized_tokens = original_tokens - total_wasted
    # Account for whitespace cleanup (~5-10% savings typically)
    if any("whitespace" in i for i in issues):
        optimized_tokens = int(optimized_tokens * 0.92)

    reduction_pct = ((original_tokens - optimized_tokens) / original_tokens * 100) if original_tokens > 0 else 0

    return PromptAnalysis(
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens if optimized_tokens < original_tokens else None,
        token_reduction_pct=round(reduction_pct, 1),
        estimated_cost_original=calculate_cost(model, original_tokens, 0),
        estimated_cost_optimized=calculate_cost(model, optimized_tokens, 0),
        issues=issues,
        suggestions=suggestions,
        redundant_segments=redundant,
        model_recommendation=model_rec,
    )


def compress_messages(messages: list[dict], model: str = "gpt-5") -> list[dict]:
    """Apply automatic compression to reduce token count.
    
    Non-destructive: preserves meaning while removing waste.
    """
    compressed = []

    for msg in messages:
        content = msg.get("content", "")
        if not content:
            compressed.append(msg)
            continue

        # Clean excessive whitespace
        clean = re.sub(r'\n{3,}', '\n\n', content)
        clean = re.sub(r' {2,}', ' ', clean)
        clean = clean.strip()

        compressed.append({**msg, "content": clean})

    # Merge consecutive system messages
    merged = []
    for msg in compressed:
        if merged and msg.get("role") == "system" and merged[-1].get("role") == "system":
            merged[-1] = {
                **merged[-1],
                "content": merged[-1]["content"] + "\n" + msg["content"],
            }
        else:
            merged.append(msg)

    return merged
