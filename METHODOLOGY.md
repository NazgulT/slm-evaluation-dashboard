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

## Known limitations

- **Machine-dependent:** Timings (TTFT, TPS, latency) depend on CPU/GPU, load, and thermal state. Results are comparable on the same machine; cross-machine comparison should be done with care.
- **Single-threaded by design:** Evaluations run sequentially (one model–prompt pair at a time) to avoid resource contention that would skew timing metrics.
- **Ollama-specific:** The pipeline targets Ollama’s API and streaming behaviour; other backends would need adapter changes.
