"""
Pydantic schemas for SLM Evaluation Dashboard.

Defines request/response models for evaluation results, validation,
and temperature variance experiments.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# --- Phase 2: Structured output validation ---


class ModelResponse(BaseModel):
    """Schema for validated model JSON output in Phase 2."""

    answer: str
    reasoning: str
    confidence: float = Field(ge=0, le=1)


# --- Phase 1 & 2: Inference benchmark results ---


class InferenceResult(BaseModel):
    """Result of a single model inference call (Phase 1)."""

    model: str
    prompt_id: str
    prompt_category: str
    ttft_ms: float
    tokens_per_second: float
    total_latency_ms: float
    token_count: int
    timestamp: datetime
    # Phase 2 fields (optional for Phase 1)
    valid_json: bool = True
    retry_used: bool = False
    response: Optional[ModelResponse] = None
    raw_output: str = ""
    error: Optional[str] = None


# --- Phase 3: Temperature variance ---


class TemperatureResult(BaseModel):
    """Result of a single temperature run (Phase 3)."""

    model: str
    prompt_id: str
    prompt_category: str
    temperature: float
    run_index: int
    response_text: str
    jaccard_similarity: float
    timestamp: datetime


# --- API response models ---


class RunStatus(BaseModel):
    """Current evaluation run status."""

    status: str  # idle | running | done
    message: Optional[str] = None


class ModelInfo(BaseModel):
    """Model metadata from config or Ollama."""

    name: str
    display_name: Optional[str] = None
    parameters: Optional[str] = None
