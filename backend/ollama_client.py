"""
Async Ollama REST API client with streaming support.

Calls POST /api/generate with stream=True, records timing metrics
(TTFT, TPS, total latency), and returns structured results.
"""

import json
import time
import httpx
from pydantic import BaseModel


class InferenceMetrics(BaseModel):
    """Structured result from a streaming inference call."""

    model: str
    prompt_id: str
    prompt_category: str
    ttft_ms: float
    tokens_per_second: float
    total_latency_ms: float
    token_count: int
    raw_text: str
    error: str | None = None


class OllamaClient:
    """Async client for Ollama REST API with streaming inference."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(
        self,
        model: str,
        prompt: str,
        prompt_id: str = "",
        prompt_category: str = "",
        system_prompt: str | None = None,
        temperature: float | None = None,
        num_predict: int | None = None,
    ) -> InferenceMetrics:
        """
        Run streaming inference and record timing metrics.

        Records:
        - TTFT: time to first token (wall-clock from request start to first response)
        - TPS: tokens per second from eval_count / eval_duration in final chunk
        - Total latency: wall-clock from request start to stream end
        """
        ttft_ms: float | None = None
        token_count = 0
        eval_count = 0
        eval_duration_ns = 0.0
        raw_chunks: list[str] = []
        start_time = time.perf_counter()

        body: dict = {
            "model": model,
            "prompt": prompt,
            "stream": True,
        }
        if system_prompt:
            body["system"] = system_prompt
        opts = {}
        if temperature is not None:
            opts["temperature"] = temperature
        if num_predict is not None:
            opts["num_predict"] = num_predict
        if opts:
            body["options"] = opts

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=body,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # First non-empty response = TTFT
                        response_text = chunk.get("response", "")
                        if ttft_ms is None and response_text:
                            ttft_ms = (time.perf_counter() - start_time) * 1000

                        if response_text:
                            raw_chunks.append(response_text)
                            token_count += 1

                        # Final chunk has eval metrics
                        if chunk.get("done"):
                            eval_count = chunk.get("eval_count", token_count)
                            eval_duration_ns = chunk.get("eval_duration", 0) or 1

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return InferenceMetrics(
                    model=model,
                    prompt_id=prompt_id,
                    prompt_category=prompt_category,
                    ttft_ms=0.0,
                    tokens_per_second=0.0,
                    total_latency_ms=0.0,
                    token_count=0,
                    raw_text="",
                    error=f"Model not found: {model}",
                )
            raise
        except Exception as e:
            return InferenceMetrics(
                model=model,
                prompt_id=prompt_id,
                prompt_category=prompt_category,
                ttft_ms=0.0,
                tokens_per_second=0.0,
                total_latency_ms=0.0,
                token_count=0,
                raw_text="",
                error=str(e),
            )

        total_latency_ms = (time.perf_counter() - start_time) * 1000
        tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0.0

        return InferenceMetrics(
            model=model,
            prompt_id=prompt_id,
            prompt_category=prompt_category,
            ttft_ms=ttft_ms or 0.0,
            tokens_per_second=tps,
            total_latency_ms=total_latency_ms,
            token_count=eval_count or token_count,
            raw_text="".join(raw_chunks),
        )

    async def generate_chat(
        self,
        model: str,
        messages: list[dict],
        prompt_id: str = "",
        prompt_category: str = "",
    ) -> InferenceMetrics:
        """
        Multi-turn chat via POST /api/chat with streaming.
        Used for Phase 2 (system + user, optional retry user message).
        messages: list of {"role": "system"|"user"|"assistant", "content": "..."}.
        """
        ttft_ms: float | None = None
        token_count = 0
        eval_count = 0
        eval_duration_ns = 0.0
        raw_chunks: list[str] = []
        start_time = time.perf_counter()

        body = {"model": model, "messages": messages, "stream": True}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=body,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg = chunk.get("message") or {}
                        content = msg.get("content") or ""
                        if ttft_ms is None and content:
                            ttft_ms = (time.perf_counter() - start_time) * 1000
                        if content:
                            raw_chunks.append(content)

                        if chunk.get("done"):
                            eval_count = chunk.get("eval_count", 0)
                            eval_duration_ns = chunk.get("eval_duration", 0) or 1

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return InferenceMetrics(
                    model=model,
                    prompt_id=prompt_id,
                    prompt_category=prompt_category,
                    ttft_ms=0.0,
                    tokens_per_second=0.0,
                    total_latency_ms=0.0,
                    token_count=0,
                    raw_text="",
                    error=f"Model not found: {model}",
                )
            raise
        except Exception as e:
            return InferenceMetrics(
                model=model,
                prompt_id=prompt_id,
                prompt_category=prompt_category,
                ttft_ms=0.0,
                tokens_per_second=0.0,
                total_latency_ms=0.0,
                token_count=0,
                raw_text="",
                error=str(e),
            )

        total_latency_ms = (time.perf_counter() - start_time) * 1000
        full_text = "".join(raw_chunks)
        token_count = eval_count or len(raw_chunks)
        tps = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0.0

        return InferenceMetrics(
            model=model,
            prompt_id=prompt_id,
            prompt_category=prompt_category,
            ttft_ms=ttft_ms or 0.0,
            tokens_per_second=tps,
            total_latency_ms=total_latency_ms,
            token_count=eval_count or token_count,
            raw_text=full_text,
        )

    async def list_models(self) -> list[dict]:
        """Fetch available models from Ollama /api/tags."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
