"""
FastAPI application for the SLM Evaluation Dashboard.

Thin route layer: orchestration lives in evaluator.py.
Routes: GET /models, POST /run, GET /results, GET /status.
"""

import asyncio
import csv
import dataclasses
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.csv_writer import CSVWriter
from backend.evaluator import (
    load_models_config,
    load_prompts_config,
    run_calibration,
    run_phase1,
    run_phase2,
)
from backend.ollama_client import OllamaClient
from backend.schemas import RunStatus
from backend.system_profile import capture_and_save, format_banner, load_profile
from backend.temperature import run_sweep as run_phase3_sweep

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESULTS_CSV = DATA_DIR / "results.csv"
TEMPERATURE_CSV = DATA_DIR / "temperature_runs.csv"

_log = logging.getLogger(__name__)

# Shared Ollama client — one connection pool for the lifetime of the process
_ollama = OllamaClient()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await _ollama.aclose()


# Run state
@dataclasses.dataclass
class _RunState:
    status: str = "idle"
    task: asyncio.Task | None = None


_state = _RunState()
_run_lock = asyncio.Lock()


async def run_evaluation_async(phase: int = 1) -> None:
    """Run the selected evaluation phase in the background (1, 2, or 3)."""
    try:
        models = load_models_config()
        prompts = load_prompts_config()
        csv_writer = CSVWriter()

        if phase in (1, 2):
            profile = capture_and_save()
            machine_id = profile.get("machine_id", "")
            baseline_tps = await run_calibration(_ollama, models)
            capture_and_save(baseline_tps=baseline_tps)

            if phase == 1:
                await run_phase1(_ollama, csv_writer, models, prompts, dry_run=False, machine_id=machine_id, baseline_tps=baseline_tps)
            else:
                await run_phase2(_ollama, csv_writer, models, prompts, dry_run=False, machine_id=machine_id, baseline_tps=baseline_tps)
        elif phase == 3:
            capture_and_save()
            await run_phase3_sweep(_ollama, csv_writer, models, prompts, dry_run=False)
    except Exception:
        _log.exception("Evaluation run failed (phase %s)", phase)
    finally:
        _state.status = "done"


app = FastAPI(
    title="SLM Evaluation Dashboard API",
    description="Backend for benchmarking small language models via Ollama",
    lifespan=lifespan,
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
    try:
        models = await _ollama.list_models()
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {e}")


@app.get("/config/models")
async def get_config_models():
    """Return model display metadata from config/models.json."""
    try:
        data = load_models_config()
    except Exception:
        data = []
    return {"models": data}


@app.get("/system-profile")
async def get_system_profile():
    """Return hardware context from data/system_profile.json for dashboard banner."""
    try:
        profile = load_profile()
        if not profile:
            profile = capture_and_save()
        return {"profile": profile, "banner": format_banner(profile)}
    except Exception:
        return {"profile": None, "banner": "Benchmarked on: unknown system"}


@app.get("/config/prompts")
async def get_config_prompts():
    """Return prompt metadata from config/prompts.json."""
    try:
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
    async with _run_lock:
        if _state.status == "running":
            return {"status": "running", "message": "Evaluation already in progress"}
        run_phase = phase if phase in (1, 2, 3) else 1
        _state.status = "running"
        _state.task = asyncio.create_task(run_evaluation_async(phase=run_phase))
    return {"status": "started", "message": f"Phase {run_phase} evaluation run started"}


@app.get("/status")
async def get_status():
    """Return current run status: idle | running | done."""
    return RunStatus(status=_state.status)


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
            for key in ("ttft_ms", "tokens_per_second", "total_latency_ms", "normalised_tps"):
                if key in row and row[key] != "":
                    try:
                        row[key] = float(row[key])
                    except (ValueError, TypeError):
                        pass
            for key in ("token_count", "phase"):
                if key in row and row[key] != "":
                    try:
                        row[key] = int(float(row[key]))
                    except (ValueError, TypeError):
                        pass
            rows.append(row)

    return {"results": rows}


@app.get("/validation-summary")
async def get_validation_summary():
    """
    Per-model counts of pass / retry / fail from Phase 2 rows in results.csv.
    pass = valid_json true, retry_used false; retry = valid_json true, retry_used true;
    fail = valid_json false.
    """
    if not RESULTS_CSV.exists():
        return {"summary": {}}

    per_model: dict[str, dict[str, int]] = {}
    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only Phase 2 rows carry meaningful valid_json data
            if row.get("phase", "") != "2":
                continue
            model = row.get("model", "")
            if not model:
                continue
            if model not in per_model:
                per_model[model] = {"pass": 0, "retry": 0, "fail": 0}
            vj = row.get("valid_json", "")
            ru = row.get("retry_used", "")
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
    async with _run_lock:
        if _state.status == "running":
            return {"status": "running", "message": "Evaluation already in progress"}
        _state.status = "running"
        _state.task = asyncio.create_task(run_evaluation_async(phase=3))
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
            for key in ("temperature", "jaccard_similarity"):
                if key in row and row[key] != "":
                    try:
                        row[key] = float(row[key])
                    except (ValueError, TypeError):
                        pass
            if "run_index" in row and row["run_index"] != "":
                try:
                    row["run_index"] = int(float(row["run_index"]))
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
