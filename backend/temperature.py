"""
Phase 3: Temperature variance experiments.

Sweeps temperature values for each model × prompt, runs inference N times per setting,
computes pairwise Jaccard similarity of response token sets, and appends to
data/temperature_runs.csv. Config-driven via config/temperature.json.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from backend.csv_writer import CSVWriter
from backend.ollama_client import OllamaClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
TEMPERATURE_CONFIG = CONFIG_DIR / "temperature.json"
TEMPERATURE_CSV = DATA_DIR / "temperature_runs.csv"

# Defaults if config missing or partial
DEFAULT_TEMPERATURES = [0.0, 0.3, 0.7, 1.0, 1.4]
DEFAULT_RUNS_PER_TEMPERATURE = 3

logger = logging.getLogger(__name__)


def _token_set(text: str) -> set[str]:
    """Tokenise by splitting on whitespace and lowercasing."""
    return set(text.lower().split())


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    """|A ∩ B| / |A ∪ B|; 0.0 if both empty."""
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


def mean_pairwise_jaccard(texts: list[str]) -> float:
    """
    For N response texts, tokenise each, compute Jaccard for every pair,
    return the mean. Values near 1.0 = low variance, near 0.0 = high variance.
    """
    if len(texts) < 2:
        return 1.0
    sets = [_token_set(t) for t in texts]
    total = 0.0
    count = 0
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            total += jaccard_similarity(sets[i], sets[j])
            count += 1
    return total / count if count else 1.0


def load_temperature_config() -> dict:
    """Load config/temperature.json; use defaults for missing keys."""
    out = {
        "temperatures": DEFAULT_TEMPERATURES,
        "runs_per_temperature": DEFAULT_RUNS_PER_TEMPERATURE,
        "prompt_ids": [],
    }
    if not TEMPERATURE_CONFIG.exists():
        return out
    try:
        with open(TEMPERATURE_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("temperatures"), list):
            out["temperatures"] = data["temperatures"]
        if isinstance(data.get("runs_per_temperature"), int):
            out["runs_per_temperature"] = data["runs_per_temperature"]
        if isinstance(data.get("prompt_ids"), list):
            out["prompt_ids"] = data["prompt_ids"]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Invalid temperature config: %s; using defaults", e)
    return out


async def run_sweep(
    client: OllamaClient,
    csv_writer: CSVWriter,
    models: list[dict],
    prompts: list[dict],
    dry_run: bool = False,
    model_filter: str | None = None,
) -> None:
    """
    For each (model × prompt × temperature), run inference N times, compute
    mean pairwise Jaccard similarity, append N rows to temperature_runs.csv.
    """
    cfg = load_temperature_config()
    temperatures: list[float] = cfg["temperatures"]
    n_runs: int = cfg["runs_per_temperature"]
    prompt_id_filter: list[str] = cfg["prompt_ids"]

    model_list = [m for m in models if model_filter is None or m.get("name") == model_filter]
    prompt_list = prompts
    if prompt_id_filter:
        prompt_list = [p for p in prompts if p.get("id") in prompt_id_filter]
    if not model_list or not prompt_list:
        logger.warning("No models or prompts to run for Phase 3")
        return

    for model_cfg in model_list:
        model_name = model_cfg.get("name", "")
        for prompt_cfg in prompt_list:
            prompt_id = prompt_cfg.get("id", "")
            prompt_category = prompt_cfg.get("category", "")
            prompt_text = prompt_cfg.get("text", "")

            for temp in temperatures:
                responses: list[str] = []

                for run_index in range(1, n_runs + 1):
                    if dry_run and (model_cfg != model_list[0] or prompt_cfg != prompt_list[0] or temp != temperatures[0] or run_index > 1):
                        continue
                    if dry_run:
                        logger.info("Phase 3 dry run: %s / %s / temp=%s run %s", model_name, prompt_id, temp, run_index)

                    try:
                        metrics = await client.generate(
                            model=model_name,
                            prompt=prompt_text,
                            prompt_id=prompt_id,
                            prompt_category=prompt_category,
                            temperature=temp,
                        )
                    except Exception as e:
                        logger.exception(
                            "Phase 3 failed model=%s prompt_id=%s temp=%s run=%s: %s",
                            model_name, prompt_id, temp, run_index, e,
                        )
                        response_text = ""
                    else:
                        response_text = metrics.raw_text or ""
                        if metrics.error:
                            response_text = ""

                    responses.append(response_text)

                if dry_run and responses:
                    j = mean_pairwise_jaccard(responses)
                    print(json.dumps({
                        "model": model_name,
                        "prompt_id": prompt_id,
                        "temperature": temp,
                        "runs": len(responses),
                        "jaccard_similarity": round(j, 4),
                    }, indent=2))
                    return

                jaccard = mean_pairwise_jaccard(responses)
                ts = datetime.utcnow().isoformat() + "Z"

                for run_index, response_text in enumerate(responses, start=1):
                    row = {
                        "timestamp": ts,
                        "model": model_name,
                        "prompt_id": prompt_id,
                        "prompt_category": prompt_category,
                        "temperature": round(temp, 2),
                        "run_index": run_index,
                        "response_text": (response_text[:5000] if response_text else ""),
                        "jaccard_similarity": round(jaccard, 4),
                    }
                    csv_writer.append_row(TEMPERATURE_CSV, row)

                logger.info(
                    "Phase 3: %s / %s temp=%.1f jaccard=%.3f",
                    model_name, prompt_id, temp, jaccard,
                )
