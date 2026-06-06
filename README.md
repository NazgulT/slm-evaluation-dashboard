# Small Language Model Evaluation Dashboard

A small language model (SLM) evaluation dashboard that runs **entirely offline** using [Ollama](https://ollama.com) as the local inference backend. It benchmarks multiple small models (2–5B parameters) across three phases: raw inference performance, structured output validation, and temperature variance analysis. Results are written to CSV and exposed via a REST API for a React dashboard.

## Quick results summary

> Evaluated across **40 runs** (4 models × 5 prompts × 2 phases) on a single machine.
>
> - **`gemma2:2b`** — fastest time to first token (1,199 ms), perfect JSON validity (5/5), and zero retries. Best choice when output reliability and responsiveness matter most.
> - **`qwen2.5:3b`** — highest raw throughput (17.54 tok/s), perfect JSON validity (5/5), and only one retry. Best balance of speed and reliability.
> - **`llama3.2:3b`** — lowest end-to-end latency (7,277 ms) with solid reliability (4/5 JSON). Strong all-rounder.
> - **`phi3:mini`** — trails in every dimension: ~30% lower TPS than the field, 2× the latency of the fastest model, and the weakest JSON compliance (3/5). Suitable only where response time is not a constraint.

The following SLMs were benchmarked (the list is expanding):

- phi3:mini
- gemma2:2b
- qwen2.5:3b
- llama3.2:3b

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

Evaluation of four small language models (SLMs) across **40 total runs** (10 per model — 5 prompts × Phase 1 + Phase 2) covering factual, creative, reasoning, code, and instruction-following categories. TTFT, TPS, latency, and normalised TPS are averaged across all 10 runs per model; JSON validity and retries are Phase 2 counts (5 runs each).

## Results Table

| Model | Avg TTFT (ms) | Avg TPS (tok/s) | Avg Latency (ms) | Avg Norm TPS | Valid JSON (Phase 2) | Retries (Phase 2) |
|---|---:|---:|---:|---:|---:|---:|
| phi3:mini | 2,640.7 | 11.88 | 15,075.9 | 0.83 | 3 / 5 | 2 / 5 |
| gemma2:2b | 1,198.8 | 16.86 | 8,311.6 | 1.45 | 5 / 5 | 0 / 5 |
| qwen2.5:3b | 1,643.0 | 17.54 | 8,952.4 | 1.10 | 5 / 5 | 1 / 5 |
| llama3.2:3b | 2,637.9 | 15.21 | 7,276.8 | 0.95 | 4 / 5 | 1 / 5 |

> **Columns:** TTFT = Time to First Token (lower is better); TPS = generation throughput (higher is better); Total Latency = end-to-end response time (lower is better); Norm TPS = observed TPS divided by per-model calibration baseline — values above 1.0 indicate above-baseline throughput; Valid JSON / Retries = Phase 2 structured-output counts out of 5 prompts.

---

## Analysis

**Latency & Responsiveness**
`gemma2:2b` is the quickest to first token at 1,199 ms — more than 2× faster than `phi3:mini` and `llama3.2:3b` (both near 2,640 ms). Despite that advantage at the start, `gemma2:2b` accumulates latency through longer generations and finishes second overall (8,312 ms). `llama3.2:3b` posts the lowest end-to-end latency (7,277 ms) by producing more concise outputs, while `phi3:mini` is the clear outlier at 15,076 ms — nearly double the next-worst model — driven by verbose responses on code and instruction prompts.

**Throughput**
`qwen2.5:3b` leads raw token generation at 17.54 tok/s, followed by `gemma2:2b` (16.86) and `llama3.2:3b` (15.21). `phi3:mini` lags at 11.88 tok/s — roughly 32% slower than the field. The normalised TPS column (relative to each model's own calibration baseline) reinforces this: `gemma2:2b` scores 1.45, well above its baseline, while `phi3:mini` sits at 0.83, consistently below it. `qwen2.5:3b` (1.10) and `llama3.2:3b` (0.95) track close to their baselines, indicating stable, predictable throughput.

**Reliability (JSON validity & Retries)**
`gemma2:2b` is the standout — 5/5 valid JSON on the first attempt, zero retries. `qwen2.5:3b` also achieved 5/5 validity but required one retry (on the creative prompt), suggesting occasional schema non-conformance that self-corrects. `llama3.2:3b` missed one prompt (instruction-following) and used one retry, landing at 4/5. `phi3:mini` was the weakest here: two prompts failed to produce valid JSON even after a retry (creative and instruction), and two retries were used — a meaningful reliability gap for structured-output workloads.

**Summary Recommendation**
For latency-sensitive applications, `llama3.2:3b` delivers the lowest end-to-end response time with solid reliability. For structured-output or tool-calling workloads where schema compliance is critical, `gemma2:2b` is the safest choice — perfect validity, fastest first token, zero retries. `qwen2.5:3b` is the best all-rounder: highest throughput, perfect validity, and competitive latency. `phi3:mini` trails in every dimension and is best suited to offline, throughput-insensitive tasks where response quality outweighs speed.

---

## Portability

- **System fingerprinting:** Hardware context (CPU, RAM, GPU, OS) is captured and saved to `data/system_profile.json`. A `machine_id` hash links each result to its hardware.
- **Normalised TPS:** A calibration run per model yields a baseline; `normalised_tps = observed_tps / baseline_tps` makes results comparable across machines.
- **Comparison mode:** In the Phase 1 tab, upload a second `results.csv` from another machine to compare TPS side by side.

## Methodology

See [METHODOLOGY.md](METHODOLOGY.md) for rationale behind metrics, Jaccard similarity, single retry, and known limitations.
