# SLM Evaluation Dashboard — AI IDE Implementation Prompt

## Project overview

Build a small language model (SLM) evaluation dashboard that runs entirely offline using
Ollama as the local inference backend. The system benchmarks multiple small language models
(2–5 billion parameters) across three evaluation phases: raw inference performance, structured
output validation, and temperature variance analysis. Results are written to CSV files and
surfaced on a React frontend dashboard with charts.

This is a portfolio-grade project. Code should be clean, well-commented, and structured so a
recruiter or engineer can run the full stack with a single setup command.

---

## Tech stack

### Backend
- **Python 3.11+**
- **FastAPI** — REST API layer, serves evaluation results to the frontend
- **httpx** — async HTTP client for calling the Ollama REST API (streaming support required)
- **Pydantic v2** — request/response schema validation and structured output enforcement
- **uvicorn** — ASGI server for FastAPI
- **Python standard library** — `csv`, `json`, `time`, `asyncio`, `argparse`, `pathlib`

### Frontend
- **React 18** with **Vite** — scaffolded with `npm create vite@latest`
- **Recharts** — all charts and visualisations
- **Tailwind CSS** — utility-first styling, no component library needed

### Inference
- **Ollama** — local model server, accessed via REST at `http://localhost:11434`
- Models to load via `ollama pull`:
  - `phi3:mini` (~3.8B, Microsoft)
  - `gemma2:2b` (~2.6B, Google)
  - `qwen2.5:3b` (~3B, Alibaba)
  - `llama3.2:3b` (~3.2B, Meta)

### Config and data
- `config/models.json` — list of model names and display metadata
- `config/prompts.json` — evaluation prompts with `id`, `text`, and `category` fields
- `data/results.csv` — Phase 1 and 2 benchmark results, appended after each run
- `data/temperature_runs.csv` — Phase 3 variance experiment results

---

## Project structure

```
slm-eval/
├── backend/
│   ├── main.py              # FastAPI app and route definitions
│   ├── evaluator.py         # Orchestrates evaluation pipeline logic
│   ├── ollama_client.py     # Async Ollama REST wrapper (streaming)
│   ├── schemas.py           # All Pydantic models
│   ├── temperature.py       # Phase 3 temperature sweep logic
│   └── csv_writer.py        # Thread-safe CSV append utility
├── frontend/
│   └── src/
│       ├── App.jsx           # Root component with tab navigation
│       ├── MetricsTable.jsx  # Phase 1: sortable raw results table
│       ├── PerformanceChart.jsx # Phase 1: grouped bar + scatter charts
│       ├── ValidationPanel.jsx  # Phase 2: pass/fail/retry summary
│       └── TemperatureChart.jsx # Phase 3: variance line chart
├── config/
│   ├── models.json
│   └── prompts.json
├── data/
│   ├── results.csv
│   └── temperature_runs.csv
├── requirements.txt
├── README.md
└── METHODOLOGY.md
```

---

## Architecture

The system is three layers:

1. **Ollama** — runs locally on port 11434, exposes `/api/generate` with streaming support.
   The backend never batches calls; each model evaluation is a separate streaming request.

2. **FastAPI backend** — orchestrates evaluation phases, writes results to CSV, and exposes a
   REST API the frontend polls. The evaluation logic lives in `evaluator.py`, not in route
   handlers. Routes are thin.

3. **React frontend** — polls the FastAPI REST API on a configurable interval and renders
   results. Tabs separate the three phases. CSV download buttons are present on each tab.

All configuration (model list, temperature values, retry count, prompt file path) is read
from `config/` JSON files at startup. No values are hardcoded in application logic.

---

## Phase 1 — Inference benchmarking

### Goal
Measure raw inference performance of each model. Record tokens per second, time to first
token (TTFT), and total response latency for every prompt–model combination.

### Implementation requirements

**Ollama streaming client (`ollama_client.py`)**
- Use `httpx.AsyncClient` with `stream=True` to call `POST /api/generate`
- Set `"stream": true` in the request body
- Record wall-clock time at request start using `time.perf_counter()`
- Record TTFT when the first non-empty `response` field appears in the streamed JSON chunks
- Extract `eval_count` and `eval_duration` (nanoseconds) from the final chunk where
  `"done": true` to compute tokens per second: `eval_count / (eval_duration / 1e9)`
- Return a structured result object (Pydantic model) with all timing fields

**Evaluator (`evaluator.py`)**
- Load models from `config/models.json` and prompts from `config/prompts.json`
- Run every model against every prompt sequentially (not in parallel — prevents resource
  contention skewing timings)
- After each individual run, flush one row to `data/results.csv` immediately
- Support a `--dry-run` CLI flag via `argparse` that runs one model against one prompt to
  validate the pipeline before committing to a full benchmark

**CSV schema for `results.csv`**
```
timestamp, model, prompt_id, prompt_category, ttft_ms, tokens_per_second,
total_latency_ms, token_count, valid_json, retry_used, error
```

**FastAPI routes**
- `GET /models` — return list of available Ollama models (call Ollama's `/api/tags`)
- `POST /run` — trigger a full evaluation run asynchronously
- `GET /results` — return all rows from `results.csv` as JSON
- `GET /status` — return current run status (idle / running / done)

### Frontend (Phase 1 tab)
- **Grouped bar chart** — one group per model, bars for TTFT, TPS, and latency
- **Scatter chart** — latency (X) vs tokens per second (Y), one dot per model
- **Raw results table** — sortable by any column, with model and prompt filters

---

## Phase 2 — Structured output validation

### Goal
Enforce a JSON response schema on model outputs. Validate with Pydantic. Implement a
one-retry mechanism that re-prompts with a corrective message before failing gracefully.

### Implementation requirements

**System prompt design**
Every prompt sent to a model in Phase 2 must include a system prompt that instructs the
model to respond only with a JSON object conforming to the following schema, with no
preamble, no markdown fences, and no extra text:
```json
{
  "answer": "<string>",
  "reasoning": "<string>",
  "confidence": <float between 0 and 1>
}
```

**Validation logic (in `evaluator.py`)**
- After receiving the full model response, attempt `json.loads()` on the raw text
- If parsing succeeds, validate the parsed dict against the `ModelResponse` Pydantic model
- If either step raises an exception, this is attempt 1 failure — proceed to retry
- For the retry: append a second user message to the conversation context:
  `"Your previous response was not valid JSON. Return only the JSON object with keys:
  answer, reasoning, confidence. No other text."`
- Re-submit the updated conversation to the model
- If the retry also fails, mark the result as `valid_json=false`, `retry_used=true`,
  capture `raw_output` for debugging, and continue to the next evaluation — do not raise

**Pydantic schemas (`schemas.py`)**
Define the following models:
- `ModelResponse` — fields: `answer: str`, `reasoning: str`, `confidence: float` (0–1)
- `EvalResult` — fields: `model`, `prompt_id`, `ttft_ms`, `tps`, `latency_ms`,
  `valid_json: bool`, `retry_used: bool`, `response: ModelResponse | None`, `raw_output: str`,
  `timestamp: datetime`
- `TemperatureResult` — fields: `model`, `prompt_id`, `temperature: float`, `run_index: int`,
  `response_text: str`, `jaccard_similarity: float`, `timestamp: datetime`

**CSV schema addition**
Add `valid_json`, `retry_used`, and `raw_output` columns to `results.csv`.

**FastAPI addition**
- `GET /validation-summary` — return per-model counts of pass / retry / fail

### Frontend (Phase 2 tab)
- **Pie chart** — per-model pass / retry / fail distribution (one pie per model, arranged
  in a row)
- **Results table** — same as Phase 1 table with additional `Valid JSON` and `Retry Used`
  badge columns (green / amber / red)

---

## Phase 3 — Temperature variance experiments

### Goal
Measure how output variance changes across temperature settings. For each model and prompt,
run inference at multiple temperature values multiple times. Document and visualise the
variance in outputs.

### Implementation requirements

**Temperature sweep (`temperature.py`)**
- Read temperature values from `config/models.json` or a dedicated field in `config/prompts.json`
- Default sweep: `[0.0, 0.3, 0.7, 1.0, 1.4]`
- For each combination of (model × prompt × temperature), run inference `N=3` times
- Capture the full text response for each run
- After collecting all N responses for a given (model × prompt × temperature), compute the
  pairwise Jaccard similarity between response token sets:
  - Tokenise each response by splitting on whitespace and lowercasing
  - Compute Jaccard: `|A ∩ B| / |A ∪ B|` for every pair
  - Store the mean pairwise similarity as `jaccard_similarity` — values near 1.0 indicate
    low variance, values near 0.0 indicate high variance
- Append each run as a row to `data/temperature_runs.csv`

**CSV schema for `temperature_runs.csv`**
```
timestamp, model, prompt_id, prompt_category, temperature, run_index,
response_text, jaccard_similarity
```

**FastAPI addition**
- `POST /temperature-run` — trigger the temperature sweep asynchronously
- `GET /variance` — return `temperature_runs.csv` as JSON, grouped by model and prompt

**Config-driven**
Temperatures, number of runs per temperature (N), and which prompts to include in the
sweep are all read from `config/` files. A separate `"temperature_experiment"` key in
`config/models.json` (or a standalone `config/temperature.json`) should hold these values.

### Frontend (Phase 3 tab)
- **Line chart** — X axis: temperature value, Y axis: mean Jaccard similarity.
  One line per model. This is the primary visualisation — it shows at a glance which
  models become more unpredictable at high temperatures.
- **Response comparison grid** — for a selected prompt and model, show side-by-side text
  cards for each run at temperature 0.0 and temperature 1.4. This gives the human-readable
  evidence behind the similarity score.

---

## Cross-cutting requirements

### Configuration (`config/models.json` and `config/prompts.json`)
All runtime parameters must be read from these files. Nothing is hardcoded. The system must
be fully re-runnable with different models or prompts by editing config files only.

Example `config/prompts.json` structure:
```json
[
  { "id": "factual_01", "text": "What is the capital of France?", "category": "factual" },
  { "id": "creative_01", "text": "Write a one-sentence story about a robot.", "category": "creative" },
  { "id": "reason_01",   "text": "All cats are mammals. Is a cat a mammal?", "category": "reasoning" },
  { "id": "code_01",     "text": "Write a Python function to reverse a string.", "category": "code" },
  { "id": "instruct_01", "text": "List three tips for writing clean code.", "category": "instruction" }
]
```

### Error handling
- Ollama connection failure: catch at startup, print a clear error and exit with a message
  directing the user to run `ollama serve`
- Model not available: catch the 404 from Ollama, skip that model, log the skip, continue
- All exceptions during a single evaluation run must be caught, logged with the model and
  prompt ID, and recorded in the CSV with an `error` column — the runner must never crash

### CORS
FastAPI must include `CORSMiddleware` configured to allow requests from `localhost:5173`
(Vite dev server default). This is required for the frontend to call the backend in development.

### CSV writer (`csv_writer.py`)
Implement a simple class with an `append_row(filepath, row_dict)` method. It must:
- Create the file with a header row if it does not exist
- Append the row otherwise
- Use a threading lock to prevent concurrent writes from corrupting the file

### CLI (`evaluator.py`)
Support the following flags via `argparse`:
- `--dry-run` — run one model against one prompt, print the result, do not write CSV
- `--phase` — accepts `1`, `2`, or `3`, runs only that phase
- `--model` — filter to a single model name

---

## README requirements

The README must include:
1. One-command setup for the backend: `pip install -r requirements.txt && uvicorn backend.main:app --reload`
2. One-command setup for the frontend: `cd frontend && npm install && npm run dev`
3. Ollama setup: `ollama pull phi3:mini && ollama pull gemma2:2b && ollama pull qwen2.5:3b && ollama pull llama3.2:3b`
4. A brief description of each phase and what it measures
5. A screenshot of the dashboard (add after implementation)

Include a separate `METHODOLOGY.md` that explains:
- Why TTFT and TPS were chosen as primary metrics
- Why Jaccard similarity was chosen for variance (simple, dependency-free, explainable)
- Why a single retry was chosen over multiple retries (to measure model JSON reliability, not patch it)
- Known limitations (e.g. results are machine-dependent, single-threaded by design)
