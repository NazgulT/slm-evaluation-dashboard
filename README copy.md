# Small Language Model Evaluation Dashboard

A small language model (SLM) evaluation dashboard that runs **entirely offline** using [Ollama](https://ollama.com) as the local inference backend. It benchmarks multiple small models (2–5B parameters) across three phases: raw inference performance, structured output validation, and temperature variance analysis. Results are written to CSV and exposed via a REST API for a React dashboard.
The following SLMs were benchmarked (the list is expanding):

- phi3-mini
- gemma2-2b
- qwen2.5-3b
- llama3.2-3b

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
 
# Small Language Model Evaluation Results

Evaluation of four small language models (SLMs) across **40 total runs** (10 per model) covering factual, creative, reasoning, and code prompt categories. Metrics are averaged per model; `valid_json` and `retry_used` are reported as counts out of total runs.

## Results Table

| Model | Avg TTFT (ms) | Avg Tokens/sec | Avg Total Latency (ms) | Valid JSON (count) | Retry Used (count) |
|---|---:|---:|---:|---:|---:|
| phi3:mini | 2593.1 | 11.02 | 13194.9 | 9 / 10 | 1 / 10 |
| gemma2:2b | 1320.3 | 15.13 | 9293.3 | 10 / 10 | 0 / 10 |
| qwen2.5:3b | 2336.2 | 16.62 | 7287.1 | 10 / 10 | 1 / 10 |
| llama3.2:3b | 1873.6 | 15.89 | 7237.2 | 9 / 10 | 1 / 10 |

> **Columns:** TTFT = Time to First Token; Tokens/sec = generation throughput; Total Latency = end-to-end response time; Valid JSON = runs producing parseable JSON output; Retry Used = runs that required a retry.

---

## Analysis

**Latency & Responsiveness**
`phi3:mini` stands out as the slowest model, with the highest average TTFT (2,593 ms) and by far the highest total latency (~13,195 ms) — nearly 1.8× slower end-to-end than the next worst, `gemma2:2b`. `qwen2.5:3b` and `llama3.2:3b` are essentially tied for the fastest total latency (~7,237–7,287 ms), repeating the pattern seen in the previous evaluation. `gemma2:2b` is the quickest to first token at 1,320 ms but accumulates more latency through generation, finishing third overall.

**Throughput**
Token generation speed slightly differs amongst the models. `qwen2.5:3b` leads at 16.62 tok/s, followed closely by `llama3.2:3b` (15.89) and `gemma2:2b` (15.13), while `phi3:mini` lags significantly at 11.02 tok/s — roughly 35% slower than the top three. This throughput gap is the primary driver of `phi3:mini`'s high total latency. We can also suggest that the throughput is contrained by the inference hardware the test were ran on.

**Reliability (JSON validity & Retries)**
`gemma2:2b` stands out here - 10/10 valid JSON and zero retries — making it the most reliable model across both evaluations. `qwen2.5:3b` matched it on JSON validity (10/10) but required one retry. `phi3:mini` and `llama3.2:3b` each missed one valid JSON response and used one retry, putting them roughly on par for reliability.

**Summary Recommendation**
`qwen2.5:3b` and `llama3.2:3b` offer the best balance of speed and throughput for latency-sensitive applications. `gemma2:2b` remains the strongest choice where output reliability is the top priority. `phi3:mini` continues to trail the field on both throughput and latency and is best suited for tasks where response time is not a constraint.


## Portability

- **System fingerprinting:** Hardware context (CPU, RAM, GPU, OS) is captured and saved to `data/system_profile.json`. A `machine_id` hash links each result to its hardware.
- **Normalised TPS:** A calibration run per model yields a baseline; `normalised_tps = observed_tps / baseline_tps` makes results comparable across machines.
- **Comparison mode:** In the Phase 1 tab, upload a second `results.csv` from another machine to compare TPS side by side.

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for rationale behind metrics, Jaccard similarity, single retry, and known limitations.
