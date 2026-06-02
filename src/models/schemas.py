"""Request/response schemas — strict typing for every API surface."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# --- Enums ---

class ModelTier(str, Enum):
    """Pricing tiers to bucket models for cost analysis."""
    FLAGSHIP = "flagship"       # gpt-5, gpt-5.5, o3-pro
    STANDARD = "standard"       # gpt-5-mini, o3, o4-mini
    ECONOMY = "economy"         # gpt-5-nano, gpt-4o-mini
    EMBEDDING = "embedding"     # text-embedding-3-*
    IMAGE = "image"             # dall-e, gpt-5-image


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TaskType(str, Enum):
    """Workload categories for model recommendation."""
    GENERAL = "general"
    SIMPLE = "simple"
    CHAT = "chat"
    CODING = "coding"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    REASONING = "reasoning"


class RecommendationRisk(str, Enum):
    """Quality/regression risk from switching models."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --- Request Logging ---

class APIRequestLog(BaseModel):
    """Single logged API request with full cost breakdown."""
    id: str
    timestamp: datetime
    model: str
    model_tier: ModelTier
    endpoint: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    status_code: int
    # Optimization metadata
    cache_hit: bool = False
    tokens_saved: int = 0
    cost_saved_usd: float = 0.0
    # Request fingerprint for dedup detection
    prompt_hash: Optional[str] = None
    user_id: Optional[str] = None


# --- Analytics ---

class UsageSummary(BaseModel):
    """Aggregated usage stats for a time window."""
    period_start: datetime
    period_end: datetime
    total_requests: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_cost_usd: float
    total_saved_usd: float
    avg_latency_ms: float
    cache_hit_rate: float
    requests_by_model: dict[str, int]
    cost_by_model: dict[str, float]
    top_expensive_requests: list[dict]
    duplicate_request_count: int


class CostForecast(BaseModel):
    """Projected spend based on current usage patterns."""
    current_daily_spend: float
    projected_monthly_spend: float
    projected_yearly_spend: float
    budget_daily: float
    budget_utilization_pct: float
    days_until_budget_exceeded: Optional[int] = None
    recommendation: str


class PromptAnalysis(BaseModel):
    """Detailed analysis of a single prompt for optimization."""
    original_tokens: int
    optimized_tokens: Optional[int] = None
    token_reduction_pct: float = 0.0
    estimated_cost_original: float
    estimated_cost_optimized: float
    issues: list[str]
    suggestions: list[str]
    redundant_segments: list[str]
    model_recommendation: Optional[str] = None


# --- Model Recommendations ---

class ModelRecommendationRequest(BaseModel):
    """Request for task-aware model optimization guidance."""
    current_model: str = Field(..., description="Current model used by the workload")
    task_type: TaskType = Field(TaskType.GENERAL, description="Workload type")
    prompt_tokens: int = Field(..., ge=0, description="Average prompt/input tokens per request")
    completion_tokens: int = Field(..., ge=0, description="Average completion/output tokens per request")
    monthly_requests: int = Field(10_000, ge=1, description="Projected monthly request volume")


class ModelRecommendationResponse(BaseModel):
    """Task-aware recommendation with cost and risk metadata."""
    current_model: str
    recommended_model: str
    task_type: TaskType
    risk: RecommendationRisk
    current_tier: ModelTier
    recommended_tier: ModelTier
    prompt_tokens: int
    completion_tokens: int
    monthly_requests: int
    current_cost_usd: float
    recommended_cost_usd: float
    estimated_savings_pct: float
    monthly_savings_estimate: float
    yearly_savings_estimate: float
    reason: str
    pricing: dict
    alternatives: list[dict]


# --- Alerts ---

class CostAlert(BaseModel):
    level: AlertLevel
    message: str
    current_spend: float
    threshold: float
    triggered_at: datetime


# --- Health ---

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    database: str = "connected"
    cache_entries: int = 0
    requests_logged_today: int = 0
    admin_auth_enabled: bool = False


# --- Webhook Configuration ---

class WebhookConfig(BaseModel):
    """Configuration for alert webhook delivery."""
    url: str = Field(..., description="Webhook URL to POST alerts to")
    threshold: Optional[float] = Field(None, description="Custom spend threshold to trigger alerts")
    enabled: bool = True


# --- Projects ---

class ProjectCreate(BaseModel):
    """Create a project for grouping TokenWatch usage."""
    name: str = Field(..., min_length=1, max_length=120)
    daily_budget: Optional[float] = Field(None, ge=0)


class ProjectResponse(BaseModel):
    id: str
    name: str
    daily_budget: Optional[float] = None
    created_at: str


class APIKeyCreate(BaseModel):
    """Create an API key scoped to a project."""
    name: str = Field("default", min_length=1, max_length=120)


class APIKeyResponse(BaseModel):
    id: str
    project_id: str
    name: str
    api_key: str
    created_at: str


# --- Proxy ---

class ProxyRequest(BaseModel):
    """Intercept and analyze requests before forwarding to OpenAI."""
    model: str
    messages: list[dict]
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    user: Optional[str] = None


class ProxyResponse(BaseModel):
    """Enriched response with cost and optimization metadata."""
    openai_response: dict
    tokenwatch_metadata: dict
