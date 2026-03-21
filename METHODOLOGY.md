# Methodology

## Why TTFT and TPS as primary metrics

- **Time to first token (TTFT)** reflects perceived responsiveness: users notice how long it takes before any output appears. It is especially important for streaming UIs.
- **Tokens per second (TPS)** reflects throughput after the first token and is the standard way to compare inference speed across models and hardware. Together, TTFT and TPS characterise both “time until something appears” and “how fast the rest streams.”

## Why Jaccard similarity for variance (Phase 3)

- **Simple and dependency-free:** Tokenise by splitting on whitespace and lowercasing; no extra NLP libraries.
- **Explainable:** Jaccard is “size of intersection over size of union” for token sets, so it’s easy to describe and debug.
- **Interpretable:** Values near 1.0 mean low variance (similar outputs); near 0.0 mean high variance. It gives a single number per (model × prompt × temperature) to compare stability.

## Why a single retry (Phase 2)

- The goal is to **measure** how reliably models produce valid JSON, not to keep retrying until they succeed. One retry with a corrective message (“Your previous response was not valid JSON…”) distinguishes “fixes after one nudge” from “fails even with guidance.” Multiple retries would blur that signal and make results less comparable.

## System fingerprinting and normalised TPS

- **Hardware context:** Before each run, the system captures CPU model, core count, RAM, GPU (if present), and OS. This is saved to `data/system_profile.json` and a short `machine_id` hash is appended to every result row for traceability.
- **Calibration baseline:** A 50-token synthetic task at temperature 0 is run per model before the main evaluation. The resulting TPS is stored as the **baseline** for that session.
- **Normalised TPS:** `normalised_tps = observed_tps / baseline_tps` gives a hardware-agnostic ratio. Values above 1.0 mean the model ran faster than its own calibration; below 1.0 means slower. This ratio can be meaningfully compared across different machines.

## Known limitations

- **Machine-dependent:** Raw timings (TTFT, TPS, latency) depend on CPU/GPU, load, and thermal state. Normalised TPS and the comparison mode help, but absolute numbers remain environment-specific.
- **Single-threaded by design:** Evaluations run sequentially (one model–prompt pair at a time) to avoid resource contention that would skew timing metrics.
- **Ollama-specific:** The pipeline targets Ollama’s API and streaming behaviour; other backends would need adapter changes.
