"""
Async Ollama REST API client with streaming support.

Calls POST /api/generate with stream=True, records timing metrics
(TTFT, TPS, total latency), and returns structured results.
"""

import json
import time
from collections.abc import Callable

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
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "OllamaClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    def _error_metrics(
        self,
        model: str,
        prompt_id: str,
        prompt_category: str,
        error: str,
    ) -> InferenceMetrics:
        return InferenceMetrics(
            model=model,
            prompt_id=prompt_id,
            prompt_category=prompt_category,
            ttft_ms=0.0,
            tokens_per_second=0.0,
            total_latency_ms=0.0,
            token_count=0,
            raw_text="",
            error=error,
        )

    async def _stream(
        self,
        endpoint: str,
        body: dict,
        extract_content: Callable[[dict], str],
    ) -> tuple[list[str], float, int, float, float]:
        """
        Stream a POST request and collect timing metrics.
        Returns (raw_chunks, ttft_ms, eval_count, eval_duration_ns, total_latency_ms).
        """
        ttft_ms: float | None = None
        eval_count = 0
        eval_duration_ns = 0.0
        raw_chunks: list[str] = []
        start_time = time.perf_counter()

        async with self._client.stream("POST", f"{self.base_url}{endpoint}", json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = extract_content(chunk)
                if ttft_ms is None and content:
                    ttft_ms = (time.perf_counter() - start_time) * 1000
                if content:
                    raw_chunks.append(content)
                if chunk.get("done"):
                    eval_count = chunk.get("eval_count", len(raw_chunks))
                    eval_duration_ns = chunk.get("eval_duration", 0) or 1

        total_latency_ms = (time.perf_counter() - start_time) * 1000
        return raw_chunks, ttft_ms or 0.0, eval_count, eval_duration_ns, total_latency_ms

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
        body: dict = {"model": model, "prompt": prompt, "stream": True}
        if system_prompt:
            body["system"] = system_prompt
        opts: dict = {}
        if temperature is not None:
            opts["temperature"] = temperature
        if num_predict is not None:
            opts["num_predict"] = num_predict
        if opts:
            body["options"] = opts

        try:
            chunks, ttft, eval_count, eval_dur, latency = await self._stream(
                "/api/generate",
                body,
                lambda chunk: chunk.get("response", ""),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self._error_metrics(model, prompt_id, prompt_category, f"Model not found: {model}")
            raise
        except Exception as e:
            return self._error_metrics(model, prompt_id, prompt_category, str(e))

        tps = eval_count / (eval_dur / 1e9) if eval_dur else 0.0
        return InferenceMetrics(
            model=model,
            prompt_id=prompt_id,
            prompt_category=prompt_category,
            ttft_ms=ttft,
            tokens_per_second=tps,
            total_latency_ms=latency,
            token_count=eval_count or len(chunks),
            raw_text="".join(chunks),
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
        body = {"model": model, "messages": messages, "stream": True}

        try:
            chunks, ttft, eval_count, eval_dur, latency = await self._stream(
                "/api/chat",
                body,
                lambda chunk: (chunk.get("message") or {}).get("content") or "",
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self._error_metrics(model, prompt_id, prompt_category, f"Model not found: {model}")
            raise
        except Exception as e:
            return self._error_metrics(model, prompt_id, prompt_category, str(e))

        tps = eval_count / (eval_dur / 1e9) if eval_dur else 0.0
        return InferenceMetrics(
            model=model,
            prompt_id=prompt_id,
            prompt_category=prompt_category,
            ttft_ms=ttft,
            tokens_per_second=tps,
            total_latency_ms=latency,
            token_count=eval_count or len(chunks),
            raw_text="".join(chunks),
        )

    async def list_models(self) -> list[dict]:
        """Fetch available models from Ollama /api/tags."""
        response = await self._client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])
