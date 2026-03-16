# SLM Evaluation Dashboard

A small language model (SLM) evaluation dashboard that runs **entirely offline** using [Ollama](https://ollama.com) as the local inference backend. It benchmarks multiple small models (2–5B parameters) across three phases: raw inference performance, structured output validation, and temperature variance analysis. Results are written to CSV and exposed via a REST API for a React dashboard.

## One-command setup

### Backend

```bash
pip install -r requirements.txt && uvicorn backend.main:app --reload
```

API runs at **http://localhost:8000**. Docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend && npm install && npm run dev
```

Dashboard runs at **http://localhost:5173** (Vite default).

### Ollama (required for inference)

Install [Ollama](https://ollama.com), then start the server and pull the evaluation models:

```bash
ollama serve
ollama pull phi3:mini && ollama pull gemma2:2b && ollama pull qwen2.5:3b && ollama pull llama3.2:3b
```

## Evaluation phases

| Phase | What it measures |
|-------|-------------------|
| **Phase 1** | Raw inference: tokens per second (TPS), time to first token (TTFT), total latency per prompt–model pair. |
| **Phase 2** | Structured output: JSON schema compliance (answer, reasoning, confidence) and one-retry recovery. |
| **Phase 3** | Temperature variance: Jaccard similarity across runs at different temperatures to see output stability. |

## Project layout

- **backend/** — FastAPI app, evaluator, Ollama client, schemas, CSV writer
- **config/** — `models.json`, `prompts.json`, `temperature.json` (Phase 3: temperatures, runs per temp, optional prompt filter)
- **data/** — `results.csv` (Phase 1 & 2), `temperature_runs.csv` (Phase 3)
- **frontend/** — React + Vite dashboard (Phase 1–3 tabs, charts, CSV download)

## Running evaluations

- **CLI:** from project root:
  ```bash
  python -m backend.evaluator --phase 1   # or --phase 2, --phase 3
  python -m backend.evaluator --phase 1 --dry-run    # one run, no CSV
  python -m backend.evaluator --phase 3 --model phi3:mini
  ```
- **API:**  
  - `POST /run?phase=1|2|3` — start Phase 1, 2, or 3 in the background.  
  - `POST /temperature-run` — start Phase 3 (temperature sweep) only.  
  - Poll `GET /status`; then `GET /results` (Phase 1/2), `GET /validation-summary` (Phase 2), or `GET /variance` (Phase 3).

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for rationale behind metrics, Jaccard similarity, single retry, and known limitations.
