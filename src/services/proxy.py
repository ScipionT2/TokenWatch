"""OpenAI-compatible proxy service for Token-Tracker.

Keeps forwarding, budget decisions, cache behavior, rate limits, request
logging, and provider metadata out of the API route declarations.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config import settings
from src.core.alerts import check_and_alert, get_daily_spend
from src.core.budget import evaluate_budget
from src.core.cache import response_cache
from src.core.pricing import calculate_cost
from src.core.token_counter import count_message_tokens, hash_prompt
from src.middleware.rate_limiter import rate_limiter
from src.services.projects import project_store
from src.services.request_logger import RequestEntry, request_logger


def messages_from_payload(payload: dict[str, Any]) -> list[dict]:
    """Normalize OpenAI Chat/Responses/Embeddings payloads to message-like input."""
    if isinstance(payload.get("messages"), list):
        return payload["messages"]
    if "input" in payload:
        value = payload["input"]
        if isinstance(value, str):
            return [{"role": "user", "content": value}]
        if isinstance(value, list):
            content = "\n".join(str(item) for item in value)
            return [{"role": "user", "content": content}]
    return [{"role": "user", "content": ""}]


def completion_estimate(payload: dict[str, Any], prompt_tokens: int) -> int:
    """Estimate output tokens conservatively from OpenAI-style max token fields."""
    max_tokens = payload.get("max_tokens") or payload.get("max_completion_tokens") or payload.get("max_output_tokens")
    try:
        return min(prompt_tokens, int(max_tokens)) if max_tokens else min(prompt_tokens, 4000)
    except (TypeError, ValueError):
        return min(prompt_tokens, 4000)


def tokenwatch_metadata(decision, prompt_tokens: int, completion_tokens: int, cost: float, cache_hit: bool = False) -> dict:
    """Build provider response metadata payload."""
    return {
        "tokenwatch": True,
        "budget": asdict(decision),
        "prompt_tokens": prompt_tokens,
        "estimated_completion_tokens": completion_tokens,
        "estimated_cost_usd": cost,
        "cache_hit": cache_hit,
    }


def _project_metadata(project_context: dict | None) -> dict:
    """Metadata to attach to logs when a Token-Tracker project API key is used."""
    if not project_context:
        return {}
    return {
        "project_id": project_context["project_id"],
        "project_name": project_context["project_name"],
        "tokenwatch_key_id": project_context["key_id"],
    }


async def proxy_to_openai(endpoint: str, payload: dict[str, Any], tokenwatch_key: str | None = None):
    """Forward an OpenAI-compatible request through Token-Tracker controls."""
    project_context = None
    if tokenwatch_key:
        project_context = project_store.authenticate(tokenwatch_key)
        if project_context is None:
            raise HTTPException(status_code=401, detail={"error": "invalid_tokenwatch_key"})

    model = payload.get("model", "gpt-5")
    messages = messages_from_payload(payload)
    prompt_tokens = count_message_tokens(messages, model)
    est_completion = completion_estimate(payload, prompt_tokens)
    estimated_cost = calculate_cost(model, prompt_tokens, est_completion)
    decision = evaluate_budget(model, estimated_cost)

    if not decision.allowed:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "budget_blocked",
                "tokenwatch_metadata": tokenwatch_metadata(decision, prompt_tokens, est_completion, estimated_cost),
            },
        )

    payload = dict(payload)
    payload["model"] = decision.model
    model = decision.model

    rate = rate_limiter.check(prompt_tokens + est_completion)
    if not rate["allowed"]:
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "rate_limit": rate})

    temperature = payload.get("temperature")
    cached = response_cache.get(model, messages, temperature)
    if cached is not None:
        request_logger.log(RequestEntry(
            model=model,
            endpoint=endpoint,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            total_tokens=prompt_tokens,
            cost_usd=0.0,
            cache_hit=True,
            tokens_saved=prompt_tokens + est_completion,
            cost_saved_usd=estimated_cost,
            prompt_hash=hash_prompt(messages),
            user_id=payload.get("user"),
            request_id=str(uuid.uuid4())[:8],
            metadata={"budget": asdict(decision), **(_project_metadata(project_context))},
        ))
        cached = dict(cached)
        cached["tokenwatch_metadata"] = tokenwatch_metadata(
            decision,
            prompt_tokens,
            est_completion,
            estimated_cost,
            cache_hit=True,
        )
        return cached

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "OPENAI_API_KEY not configured",
                "tokenwatch_metadata": tokenwatch_metadata(decision, prompt_tokens, est_completion, estimated_cost),
            },
        )

    started = time.perf_counter()
    url = f"https://api.openai.com{endpoint}"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        provider_response = await client.post(url, headers=headers, json=payload)

    latency_ms = (time.perf_counter() - started) * 1000
    try:
        data = provider_response.json()
    except ValueError:
        data = {"raw": provider_response.text}

    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    actual_prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or prompt_tokens)
    actual_completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or est_completion)
    total_tokens = int(usage.get("total_tokens") or actual_prompt + actual_completion)
    actual_cost = calculate_cost(model, actual_prompt, actual_completion)

    rate_limiter.record(total_tokens)
    if provider_response.status_code < 400:
        check_and_alert(actual_cost, get_daily_spend(), model)

    request_logger.log(RequestEntry(
        model=model,
        endpoint=endpoint,
        prompt_tokens=actual_prompt,
        completion_tokens=actual_completion,
        total_tokens=total_tokens,
        cost_usd=actual_cost,
        timestamp=datetime.now(),
        request_id=str(uuid.uuid4())[:8],
        latency_ms=latency_ms,
        status_code=provider_response.status_code,
        prompt_hash=hash_prompt(messages),
        user_id=payload.get("user"),
        metadata={"budget": asdict(decision), "provider": "openai", **(_project_metadata(project_context))},
    ))

    if isinstance(data, dict):
        data["tokenwatch_metadata"] = tokenwatch_metadata(decision, actual_prompt, actual_completion, actual_cost)
        if provider_response.status_code < 400:
            response_cache.put(model, messages, data, total_tokens, actual_cost, temperature)

    return JSONResponse(content=data, status_code=provider_response.status_code)
