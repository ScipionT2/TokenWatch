"""Task-aware model recommendations for lowering AI API spend."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.pricing import MODEL_PRICING, calculate_cost, get_pricing
from src.models.schemas import ModelTier, RecommendationRisk, TaskType


@dataclass(frozen=True)
class RecommendationCandidate:
    """A possible replacement model for a task class."""

    model: str
    risk: RecommendationRisk
    reason: str


_TASK_CANDIDATES: dict[TaskType, list[RecommendationCandidate]] = {
    TaskType.SIMPLE: [
        RecommendationCandidate("gpt-5-nano", RecommendationRisk.LOW, "Simple prompts usually do not need flagship reasoning."),
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.LOW, "Mini keeps more quality headroom while still cutting spend."),
    ],
    TaskType.CLASSIFICATION: [
        RecommendationCandidate("gpt-5-nano", RecommendationRisk.LOW, "Classification is usually short, structured, and safe on economy models."),
        RecommendationCandidate("gpt-4o-mini", RecommendationRisk.LOW, "Low-cost model with enough capability for labels and routing."),
    ],
    TaskType.EXTRACTION: [
        RecommendationCandidate("gpt-5-nano", RecommendationRisk.LOW, "Structured extraction is normally pattern-heavy and cost-sensitive."),
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.LOW, "Mini is safer for messy extraction while staying cheaper than flagship."),
    ],
    TaskType.SUMMARIZATION: [
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.LOW, "Summarization usually does not need flagship reasoning."),
        RecommendationCandidate("gpt-5-nano", RecommendationRisk.MEDIUM, "Nano is cheaper but may lose nuance on long or technical summaries."),
    ],
    TaskType.CHAT: [
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.LOW, "General chat rarely needs the most expensive model."),
        RecommendationCandidate("gpt-5-nano", RecommendationRisk.MEDIUM, "Nano is best for simple support/chat, not complex reasoning."),
    ],
    TaskType.CODING: [
        RecommendationCandidate("gpt-5.1-codex-mini", RecommendationRisk.MEDIUM, "Coding can often move to a code-tuned mini model with good savings."),
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.MEDIUM, "Mini is cheaper but may need verification on complex code changes."),
    ],
    TaskType.REASONING: [
        RecommendationCandidate("o4-mini", RecommendationRisk.MEDIUM, "Reasoning tasks can often use a smaller reasoning model."),
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.HIGH, "Mini is cheaper but risky for high-stakes reasoning."),
    ],
    TaskType.GENERAL: [
        RecommendationCandidate("gpt-5-mini", RecommendationRisk.LOW, "General workloads often do not need flagship models."),
        RecommendationCandidate("gpt-5-nano", RecommendationRisk.MEDIUM, "Nano gives maximum savings for simple general requests."),
    ],
}


def _is_cheaper(candidate: str, current_model: str, prompt_tokens: int, completion_tokens: int) -> bool:
    return calculate_cost(candidate, prompt_tokens, completion_tokens) < calculate_cost(current_model, prompt_tokens, completion_tokens)


def _risk_for_no_change(model: str) -> RecommendationRisk:
    _, _, tier = get_pricing(model)
    if tier == ModelTier.ECONOMY:
        return RecommendationRisk.LOW
    if tier == ModelTier.STANDARD:
        return RecommendationRisk.LOW
    return RecommendationRisk.MEDIUM


def _candidate_alternatives(
    current_model: str,
    task_type: TaskType,
    prompt_tokens: int,
    completion_tokens: int,
) -> list[dict]:
    alternatives: list[dict] = []
    current_cost = calculate_cost(current_model, prompt_tokens, completion_tokens)
    seen: set[str] = set()

    for candidate in _TASK_CANDIDATES.get(task_type, _TASK_CANDIDATES[TaskType.GENERAL]):
        if candidate.model in seen:
            continue
        seen.add(candidate.model)
        candidate_cost = calculate_cost(candidate.model, prompt_tokens, completion_tokens)
        savings = current_cost - candidate_cost
        alternatives.append({
            "model": candidate.model,
            "risk": candidate.risk.value,
            "estimated_cost_usd": candidate_cost,
            "estimated_savings_pct": round((savings / current_cost * 100), 1) if current_cost > 0 else 0.0,
            "reason": candidate.reason,
        })

    return alternatives


def recommend_model(
    current_model: str,
    task_type: TaskType,
    prompt_tokens: int,
    completion_tokens: int,
    monthly_requests: int = 10_000,
) -> dict:
    """Recommend a cheaper model for a known task and token profile."""
    current_cost = calculate_cost(current_model, prompt_tokens, completion_tokens)
    current_input, current_output, current_tier = get_pricing(current_model)
    candidates = _TASK_CANDIDATES.get(task_type, _TASK_CANDIDATES[TaskType.GENERAL])

    chosen: RecommendationCandidate | None = None
    for candidate in candidates:
        if candidate.model == current_model:
            continue
        if _is_cheaper(candidate.model, current_model, prompt_tokens, completion_tokens):
            chosen = candidate
            break

    if chosen is None:
        recommended_model = current_model
        recommended_cost = current_cost
        savings_pct = 0.0
        monthly_savings = 0.0
        yearly_savings = 0.0
        risk = _risk_for_no_change(current_model)
        reason = f"{current_model} is already cost-appropriate for {task_type.value} or no safer cheaper option is known."
    else:
        recommended_model = chosen.model
        recommended_cost = calculate_cost(recommended_model, prompt_tokens, completion_tokens)
        savings = max(current_cost - recommended_cost, 0.0)
        savings_pct = round((savings / current_cost * 100), 1) if current_cost > 0 else 0.0
        monthly_savings = round(savings * monthly_requests, 2)
        yearly_savings = round(monthly_savings * 12, 2)
        risk = chosen.risk
        reason = chosen.reason

    rec_input, rec_output, rec_tier = get_pricing(recommended_model)

    return {
        "current_model": current_model,
        "recommended_model": recommended_model,
        "task_type": task_type.value,
        "risk": risk.value,
        "current_tier": current_tier.value,
        "recommended_tier": rec_tier.value,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "monthly_requests": monthly_requests,
        "current_cost_usd": current_cost,
        "recommended_cost_usd": recommended_cost,
        "estimated_savings_pct": savings_pct,
        "monthly_savings_estimate": monthly_savings,
        "yearly_savings_estimate": yearly_savings,
        "reason": reason,
        "pricing": {
            "current": {"input_per_1m": current_input, "output_per_1m": current_output},
            "recommended": {"input_per_1m": rec_input, "output_per_1m": rec_output},
        },
        "alternatives": _candidate_alternatives(current_model, task_type, prompt_tokens, completion_tokens),
    }
