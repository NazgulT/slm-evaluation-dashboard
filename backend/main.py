"""
FastAPI application for the SLM Evaluation Dashboard.

Thin route layer: orchestration lives in evaluator.py.
Routes: GET /models, POST /run, GET /results, GET /status.
"""

import asyncio
import csv
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.ollama_client import OllamaClient
from backend.schemas import RunStatus

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_CSV = DATA_DIR / "results.csv"
TEMPERATURE_CSV = DATA_DIR / "temperature_runs.csv"
MODELS_CONFIG = CONFIG_DIR / "models.json"

# Run state: "idle" | "running" | "done"
_run_status = "idle"
_run_task: asyncio.Task | None = None


def load_models_config() -> list[dict]:
    """Load model list from config (display metadata)."""
    if not MODELS_CONFIG.exists():
        return []
    import json
    with open(MODELS_CONFIG, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


async def run_evaluation_async(phase: int = 1) -> None:
    """Run the selected evaluation phase in the background (1, 2, or 3)."""
    global _run_status
    _run_status = "running"
    try:
        from backend.evaluator import (
            load_models_config as load_models,
            load_prompts_config,
            run_phase1,
            run_phase2,
        )
        from backend.temperature import run_sweep as run_phase3_sweep
        from backend.csv_writer import CSVWriter

        models = load_models()
        prompts = load_prompts_config()
        client = OllamaClient()
        csv_writer = CSVWriter()
        if phase == 1:
            await run_phase1(client, csv_writer, models, prompts, dry_run=False)
        elif phase == 2:
            await run_phase2(client, csv_writer, models, prompts, dry_run=False)
        else:
            await run_phase3_sweep(client, csv_writer, models, prompts, dry_run=False)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Evaluation run failed: %s", e)
    finally:
        _run_status = "done"


app = FastAPI(
    title="SLM Evaluation Dashboard API",
    description="Backend for benchmarking small language models via Ollama",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/models")
async def get_models():
    """
    Return list of available Ollama models (from Ollama /api/tags).
    Used by frontend to show which models are installed.
    """
    client = OllamaClient()
    try:
        models = await client.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {e}")


@app.get("/config/models")
async def get_config_models():
    """Return model display metadata from config/models.json."""
    data = load_models_config()
    return {"models": data}


@app.get("/config/prompts")
async def get_config_prompts():
    """Return prompt metadata from config/prompts.json."""
    try:
        from backend.evaluator import load_prompts_config

        prompts = load_prompts_config()
    except Exception:
        prompts = []
    return {"prompts": prompts}


@app.post("/run")
async def trigger_run(phase: int = Query(1, description="Evaluation phase: 1, 2, or 3")):
    """
    Start an evaluation run asynchronously (phase 1, 2, or 3).
    Returns immediately; poll GET /status for completion.
    """
    global _run_status, _run_task

    if _run_status == "running":
        return {"status": "running", "message": "Evaluation already in progress"}

    run_phase = 1 if phase not in (1, 2, 3) else phase
    _run_task = asyncio.create_task(run_evaluation_async(phase=run_phase))
    return {"status": "started", "message": f"Phase {run_phase} evaluation run started"}


@app.get("/status")
async def get_status():
    """Return current run status: idle | running | done."""
    return RunStatus(status=_run_status)


@app.get("/results")
async def get_results():
    """
    Return all rows from data/results.csv as JSON.
    Returns list of objects with keys matching CSV columns.
    """
    if not RESULTS_CSV.exists():
        return {"results": []}

    rows: list[dict] = []
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Coerce numeric columns for frontend
            for key in ("ttft_ms", "tokens_per_second", "total_latency_ms", "token_count"):
                if key in row and row[key] != "":
                    try:
                        if key == "token_count":
                            row[key] = int(float(row[key]))
                        else:
                            row[key] = float(row[key])
                    except (ValueError, TypeError):
                        pass
            rows.append(row)

    return {"results": rows}


@app.get("/validation-summary")
async def get_validation_summary():
    """
    Per-model counts of pass / retry / fail from results.csv.
    pass = valid_json true, retry_used false; retry = valid_json true, retry_used true;
    fail = valid_json false.
    """
    if not RESULTS_CSV.exists():
        return {"summary": {}}

    # Rows with valid_json/retry_used; skip rows that are Phase 1-only (no valid_json column or empty)
    per_model: dict[str, dict[str, int]] = {}
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row.get("model", "")
            if not model:
                continue
            if model not in per_model:
                per_model[model] = {"pass": 0, "retry": 0, "fail": 0}
            vj = row.get("valid_json", "")
            ru = row.get("retry_used", "")
            # Coerce to bool: "True"/"true"/"1" -> True, else False
            valid = str(vj).lower() in ("true", "1", "yes") if vj != "" else False
            retry = str(ru).lower() in ("true", "1", "yes") if ru != "" else False
            if valid and not retry:
                per_model[model]["pass"] += 1
            elif valid and retry:
                per_model[model]["retry"] += 1
            else:
                per_model[model]["fail"] += 1

    return {"summary": per_model}


@app.post("/temperature-run")
async def trigger_temperature_run():
    """
    Start the Phase 3 temperature sweep asynchronously.
    Returns immediately; poll GET /status for completion.
    """
    global _run_status, _run_task

    if _run_status == "running":
        return {"status": "running", "message": "Evaluation already in progress"}

    _run_task = asyncio.create_task(run_evaluation_async(phase=3))
    return {"status": "started", "message": "Temperature sweep (Phase 3) started"}


@app.get("/variance")
async def get_variance():
    """
    Return temperature_runs.csv as JSON.
    Flat list in "results"; grouped by model then prompt in "by_model_prompt".
    """
    if not TEMPERATURE_CSV.exists():
        return {"results": [], "by_model_prompt": {}}

    rows: list[dict] = []
    with open(TEMPERATURE_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key in ("temperature", "run_index", "jaccard_similarity"):
                if key in row and row[key] != "":
                    try:
                        if key == "run_index":
                            row[key] = int(float(row[key]))
                        else:
                            row[key] = float(row[key])
                    except (ValueError, TypeError):
                        pass
            rows.append(row)

    by_model_prompt: dict[str, dict[str, list]] = {}
    for r in rows:
        model = r.get("model", "")
        prompt_id = r.get("prompt_id", "")
        if model not in by_model_prompt:
            by_model_prompt[model] = {}
        if prompt_id not in by_model_prompt[model]:
            by_model_prompt[model][prompt_id] = []
        by_model_prompt[model][prompt_id].append(r)

    return {"results": rows, "by_model_prompt": by_model_prompt}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
