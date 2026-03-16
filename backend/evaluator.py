"""
Evaluation pipeline orchestrator.

Loads models and prompts from config, runs evaluations sequentially
(Phase 1: raw inference; Phase 2: structured validation; Phase 3: temperature sweep),
and writes results to CSV. Supports --dry-run, --phase, and --model CLI flags.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from backend.csv_writer import CSVWriter
from backend.ollama_client import OllamaClient
from backend.schemas import ModelResponse
from backend.temperature import run_sweep as run_phase3_sweep

# Default paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
MODELS_CONFIG = CONFIG_DIR / "models.json"
PROMPTS_CONFIG = CONFIG_DIR / "prompts.json"
RESULTS_CSV = DATA_DIR / "results.csv"

# CSV columns for results.csv (Phase 1 + Phase 2)
RESULTS_HEADER = [
    "timestamp",
    "model",
    "prompt_id",
    "prompt_category",
    "ttft_ms",
    "tokens_per_second",
    "total_latency_ms",
    "token_count",
    "valid_json",
    "retry_used",
    "raw_output",
    "error",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_json_config(path: Path) -> list | dict:
    """Load a JSON config file; raise with clear error if missing or invalid."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_models_config() -> list[dict]:
    """Load model list from config/models.json."""
    data = load_json_config(MODELS_CONFIG)
    if not isinstance(data, list):
        raise ValueError("config/models.json must be a JSON array")
    return data


def load_prompts_config() -> list[dict]:
    """Load prompts from config/prompts.json."""
    data = load_json_config(PROMPTS_CONFIG)
    if not isinstance(data, list):
        raise ValueError("config/prompts.json must be a JSON array")
    return data


async def run_phase1(
    client: OllamaClient,
    csv_writer: CSVWriter,
    models: list[dict],
    prompts: list[dict],
    dry_run: bool = False,
    model_filter: str | None = None,
) -> None:
    """
    Phase 1: Raw inference benchmarking.
    Run every model against every prompt sequentially; write one row to CSV after each run.
    """
    model_list = [m for m in models if model_filter is None or m.get("name") == model_filter]
    if not model_list:
        logger.warning("No models to run (check --model filter or config)")
        return

    for model_cfg in model_list:
        model_name = model_cfg.get("name", "")
        for prompt_cfg in prompts:
            prompt_id = prompt_cfg.get("id", "")
            prompt_category = prompt_cfg.get("category", "")
            prompt_text = prompt_cfg.get("text", "")

            if dry_run:
                logger.info("Dry run: %s / %s", model_name, prompt_id)

            try:
                metrics = await client.generate(
                    model=model_name,
                    prompt=prompt_text,
                    prompt_id=prompt_id,
                    prompt_category=prompt_category,
                )
            except Exception as e:
                logger.exception("Evaluation failed for model=%s prompt_id=%s", model_name, prompt_id)
                row = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "model": model_name,
                    "prompt_id": prompt_id,
                    "prompt_category": prompt_category,
                    "ttft_ms": "",
                    "tokens_per_second": "",
                    "total_latency_ms": "",
                    "token_count": "",
                    "valid_json": "",
                    "retry_used": "",
                    "raw_output": "",
                    "error": str(e),
                }
                if not dry_run:
                    csv_writer.append_row(RESULTS_CSV, row)
                continue

            row = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "model": metrics.model,
                "prompt_id": metrics.prompt_id,
                "prompt_category": metrics.prompt_category,
                "ttft_ms": round(metrics.ttft_ms, 2),
                "tokens_per_second": round(metrics.tokens_per_second, 2),
                "total_latency_ms": round(metrics.total_latency_ms, 2),
                "token_count": metrics.token_count,
                "valid_json": True,  # Phase 1 does not validate JSON
                "retry_used": False,
                "raw_output": metrics.raw_text[:2000] if metrics.raw_text else "",  # cap for CSV
                "error": metrics.error or "",
            }

            if dry_run:
                print(json.dumps(row, indent=2))
                return  # One run only for dry-run

            csv_writer.append_row(RESULTS_CSV, row)
            logger.info(
                "Wrote result: %s / %s ttft=%.0fms tps=%.1f",
                model_name,
                prompt_id,
                metrics.ttft_ms,
                metrics.tokens_per_second,
            )


# Phase 2: structured output validation
PHASE2_SYSTEM_PROMPT = (
    "Respond only with a JSON object. No preamble, no markdown fences, no extra text. "
    'Schema: {"answer": "<string>", "reasoning": "<string>", "confidence": <float between 0 and 1>}.'
)
PHASE2_RETRY_MESSAGE = (
    "Your previous response was not valid JSON. Return only the JSON object with keys: "
    "answer, reasoning, confidence. No other text."
)


def _validate_phase2_response(raw_text: str) -> tuple[bool, ModelResponse | None]:
    """Parse JSON and validate against ModelResponse. Returns (valid, parsed or None)."""
    raw_stripped = raw_text.strip()
    # Optional: strip markdown code fence if present
    if raw_stripped.startswith("```"):
        lines = raw_stripped.split("\n")
        raw_stripped = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()
    try:
        parsed = json.loads(raw_stripped)
        validated = ModelResponse.model_validate(parsed)
        return True, validated
    except (json.JSONDecodeError, Exception):
        return False, None


async def run_phase2(
    client: OllamaClient,
    csv_writer: CSVWriter,
    models: list[dict],
    prompts: list[dict],
    dry_run: bool = False,
    model_filter: str | None = None,
) -> None:
    """
    Phase 2: Structured output validation.
    System prompt enforces JSON schema; one retry with corrective message on validation failure.
    """
    model_list = [m for m in models if model_filter is None or m.get("name") == model_filter]
    if not model_list:
        logger.warning("No models to run (check --model filter or config)")
        return

    for model_cfg in model_list:
        model_name = model_cfg.get("name", "")
        for prompt_cfg in prompts:
            prompt_id = prompt_cfg.get("id", "")
            prompt_category = prompt_cfg.get("category", "")
            prompt_text = prompt_cfg.get("text", "")

            messages = [
                {"role": "system", "content": PHASE2_SYSTEM_PROMPT},
                {"role": "user", "content": prompt_text},
            ]

            if dry_run:
                logger.info("Phase 2 dry run: %s / %s", model_name, prompt_id)

            try:
                metrics = await client.generate_chat(
                    model=model_name,
                    messages=messages,
                    prompt_id=prompt_id,
                    prompt_category=prompt_category,
                )
            except Exception as e:
                logger.exception(
                    "Phase 2 evaluation failed for model=%s prompt_id=%s",
                    model_name,
                    prompt_id,
                )
                row = _result_row(
                    model_name,
                    prompt_id,
                    prompt_category,
                    ttft_ms="",
                    tps="",
                    latency_ms="",
                    token_count="",
                    valid_json=False,
                    retry_used=False,
                    raw_output="",
                    error=str(e),
                )
                if not dry_run:
                    csv_writer.append_row(RESULTS_CSV, row)
                else:
                    print(json.dumps(row, indent=2))
                    return
                continue

            if metrics.error:
                row = _result_row(
                    model_name,
                    prompt_id,
                    prompt_category,
                    ttft_ms=round(metrics.ttft_ms, 2),
                    tps=round(metrics.tokens_per_second, 2),
                    latency_ms=round(metrics.total_latency_ms, 2),
                    token_count=metrics.token_count,
                    valid_json=False,
                    retry_used=False,
                    raw_output=metrics.raw_text[:2000] if metrics.raw_text else "",
                    error=metrics.error,
                )
                if dry_run:
                    print(json.dumps(row, indent=2))
                    return
                csv_writer.append_row(RESULTS_CSV, row)
                continue

            valid, parsed = _validate_phase2_response(metrics.raw_text)
            if valid:
                row = _result_row(
                    model_name,
                    prompt_id,
                    prompt_category,
                    ttft_ms=round(metrics.ttft_ms, 2),
                    tps=round(metrics.tokens_per_second, 2),
                    latency_ms=round(metrics.total_latency_ms, 2),
                    token_count=metrics.token_count,
                    valid_json=True,
                    retry_used=False,
                    raw_output=metrics.raw_text[:2000] if metrics.raw_text else "",
                    error="",
                )
                if dry_run:
                    print(json.dumps(row, indent=2))
                    return
                csv_writer.append_row(RESULTS_CSV, row)
                logger.info("Phase 2 pass: %s / %s", model_name, prompt_id)
                continue

            # Retry with corrective user message
            retry_messages = messages + [{"role": "user", "content": PHASE2_RETRY_MESSAGE}]
            try:
                metrics_retry = await client.generate_chat(
                    model=model_name,
                    messages=retry_messages,
                    prompt_id=prompt_id,
                    prompt_category=prompt_category,
                )
            except Exception as e:
                logger.warning("Phase 2 retry failed (exception) %s / %s: %s", model_name, prompt_id, e)
                row = _result_row(
                    model_name,
                    prompt_id,
                    prompt_category,
                    ttft_ms=round(metrics.ttft_ms, 2),
                    tps=round(metrics.tokens_per_second, 2),
                    latency_ms=round(metrics.total_latency_ms, 2),
                    token_count=metrics.token_count,
                    valid_json=False,
                    retry_used=True,
                    raw_output=metrics.raw_text[:2000] if metrics.raw_text else "",
                    error=str(e),
                )
                if not dry_run:
                    csv_writer.append_row(RESULTS_CSV, row)
                else:
                    print(json.dumps(row, indent=2))
                continue

            if metrics_retry.error:
                row = _result_row(
                    model_name,
                    prompt_id,
                    prompt_category,
                    ttft_ms=round(metrics_retry.ttft_ms, 2),
                    tps=round(metrics_retry.tokens_per_second, 2),
                    latency_ms=round(metrics_retry.total_latency_ms, 2),
                    token_count=metrics_retry.token_count,
                    valid_json=False,
                    retry_used=True,
                    raw_output=metrics_retry.raw_text[:2000] if metrics_retry.raw_text else "",
                    error=metrics_retry.error,
                )
                if not dry_run:
                    csv_writer.append_row(RESULTS_CSV, row)
                else:
                    print(json.dumps(row, indent=2))
                continue

            valid_retry, _ = _validate_phase2_response(metrics_retry.raw_text)
            row = _result_row(
                model_name,
                prompt_id,
                prompt_category,
                ttft_ms=round(metrics_retry.ttft_ms, 2),
                tps=round(metrics_retry.tokens_per_second, 2),
                latency_ms=round(metrics_retry.total_latency_ms, 2),
                token_count=metrics_retry.token_count,
                valid_json=valid_retry,
                retry_used=True,
                raw_output=metrics_retry.raw_text[:2000] if metrics_retry.raw_text else "",
                error="",
            )
            if dry_run:
                print(json.dumps(row, indent=2))
                return
            csv_writer.append_row(RESULTS_CSV, row)
            logger.info(
                "Phase 2 %s: %s / %s",
                "pass (retry)" if valid_retry else "fail (retry)",
                model_name,
                prompt_id,
            )


def _result_row(
    model: str,
    prompt_id: str,
    prompt_category: str,
    ttft_ms: float | str,
    tps: float | str,
    latency_ms: float | str,
    token_count: int | str,
    valid_json: bool,
    retry_used: bool,
    raw_output: str,
    error: str,
) -> dict:
    """Build a single results.csv row dict."""
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "model": model,
        "prompt_id": prompt_id,
        "prompt_category": prompt_category,
        "ttft_ms": ttft_ms,
        "tokens_per_second": tps,
        "total_latency_ms": latency_ms,
        "token_count": token_count,
        "valid_json": valid_json,
        "retry_used": retry_used,
        "raw_output": raw_output,
        "error": error,
    }


async def check_ollama(client: OllamaClient) -> bool:
    """Verify Ollama is reachable; return True if ok."""
    try:
        await client.list_models()
        return True
    except Exception as e:
        logger.error("Ollama connection failed: %s", e)
        logger.error("Ensure Ollama is running: ollama serve")
        return False


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="SLM Evaluation Pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run one model against one prompt, print result, do not write CSV",
    )
    parser.add_argument(
        "--phase",
        type=str,
        choices=("1", "2", "3"),
        default="1",
        help="Run only this phase (default: 1)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Filter to a single model name",
    )
    return parser.parse_args()


async def main_async() -> int:
    """Entry point for CLI: load config, check Ollama, run selected phase."""
    args = parse_args()

    try:
        models = load_models_config()
        prompts = load_prompts_config()
    except (FileNotFoundError, ValueError) as e:
        logger.error("%s", e)
        return 1

    client = OllamaClient()
    if not await check_ollama(client):
        return 1

    csv_writer = CSVWriter()

    if args.phase == "1":
        await run_phase1(
            client,
            csv_writer,
            models,
            prompts,
            dry_run=args.dry_run,
            model_filter=args.model,
        )
    elif args.phase == "2":
        await run_phase2(
            client,
            csv_writer,
            models,
            prompts,
            dry_run=args.dry_run,
            model_filter=args.model,
        )
    elif args.phase == "3":
        await run_phase3_sweep(
            client,
            csv_writer,
            models,
            prompts,
            dry_run=args.dry_run,
            model_filter=args.model,
        )

    return 0


def main() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
