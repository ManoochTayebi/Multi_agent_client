# Recorded LLM execution — 28 October 2026

Both reference workflows passed three times with actual model inference and semantic embeddings: **6/6 strict passes**, with **zero deterministic fallback**. The application code includes the direct human-support workflow; all six business agents are preserved.

[Full exact-prompt evaluation](validation/live-llm-journeys-20261028.json) · [Model environment and digests](validation/live-model-environment-20261028.json) · [Recorded UI evidence](validation/live-ui-recording-20261028.json) · [Recorded walkthrough, MP4](media/atlas-llm-walkthrough-20261028.mp4)

## Measured results

| Workflow | Strict passes | Median request latency | Observed range |
|---|---|---|---|
| C0001: refund O1002 | 3/3 | 35.437 s | 32.199–61.154 s |
| C0001: track O1001 and style an outfit | 3/3 | 57.156 s | 33.503–73.893 s |

Across these six runs: **41 model calls**, **47,394 chat tokens**, **12 semantic-query calls**, overall p50 **46.297 s** and nearest-rank p95 **73.893 s**. No unnecessary agent activations, deterministic fallback, business-rule check failures or authorization check failures were observed. The local zero-rate profile reports USD 0 estimated provider **chat** charges; this excludes embedding accounting, hardware, electricity and operations.

The requests were exactly:

> I would like a refund for order O1002.

> Track my order O1001 and build a smart casual outfit under €150, size M.

Each repetition starts with fresh SQLite/Chroma stores. Each workflow creates its own authenticated customer session. Request timings include orchestration, SQL/RAG and inference/model loading as encountered, but exclude initial dataset/index creation. Model weights and prompt caches can remain warm between requests and repetitions. These are six development measurements on a shared CPU workspace, not an SLA or a controlled hardware benchmark.

## What was verified

- **Model decisions and native tools:** model-based `Plan` routing; native `investigate`, `shipment`, `product_search` and `policy_search` as applicable; typed Resolution/Stylist decisions; grounded model synthesis; separate LLM Judge calls. Required successful model stages and actual usage events are retained in every row.
- **Semantic retrieval:** the configured `all-minilm` endpoint generated policy/catalog vectors and query embeddings; no lexical substitute was used. The eight disclosed policy probes and two product-category probes passed in each repetition. These reused development probes do not establish general retrieval accuracy.
- **Refund authorization:** the actual EUR 249 proposal required explicit customer confirmation and operator review. Premature approval and unauthorized processing were rejected. The simulated transaction completed after approval, with audit events and duplicate-drain protection. Original response objects remain proposal snapshots; later lifecycle checks and audit events record completion.
- **Parallelism and dependencies:** Tracking and Discovery overlap by 9.547 s, 6.657 s and 9.335 s in the three recorded requests. Stylist begins after Discovery completes. The local model server was configured for one inference slot; graph-worker overlap is distinct from simultaneous model inference.
- **Catalog grounding:** every selected variant comes from SQL-backed Discovery and passes final live-SQL size, stock, price and provenance checks. All three outfits totaled EUR 128, within the EUR 150 cap, with size M and positive stock.

The main application modules and UI assets were unchanged from commit [`10f0330`](https://github.com/ManoochTayebi/Multi_agent_client/commit/10f0330). The evaluator was clarified to use the complete README refund prompt and to save exact requests/customer IDs. Report source hashes identify both the application and evaluator versions. The [initial abbreviated-prompt baseline](validation/live-llm-baseline-20261028.json) also passed 6/6 and is retained separately; it is not counted in the table above.

## Configuration

| Component | Executed configuration |
|---|---|
| Runtime | Ollama 0.40.12, CPU inference on Linux; 8-vCPU quota and 8 GiB memory limit |
| Chat model | `atlas-local`, derived from `qwen3:1.7b`; temperature 0, context 8,192 tokens |
| Semantic encoder | `all-minilm`; exact model digests retained in the environment JSON |
| Gateway | OpenAI-compatible `/v1`, `max_tokens`, JSON schemas, thinking disabled, 800 output tokens, 180-second per-call timeout, zero SDK retries |
| Business state | Fixed `AS_OF_DATE=2026-10-26`, synthetic fixtures, isolated SQLite/Chroma paths |

The official runtime archive checksum was verified before execution. Models/runtime files remain outside Git. The recorded API port is local to the validation process; the documented workstation setup uses Ollama's standard port 11434. Temperature zero does not guarantee identical outputs or timings across runtime/model/hardware versions.

## Reproduce and present

Follow [Activate real LLM execution](../README.md#activate-real-llm-execution-with-ollama), then run:

```bash
python -m scripts.evaluate --mode llm --suite journeys --repeat 3 --output reports/workflows-llm.json
python -m scripts.record_llm_demo --output reports/llm-recording.json
```

The recording command drives the real customer/operator UI and HTTP interfaces against new business stores and the mock carrier. It requires positive model/embedding usage, native specialist execution, every relevant model stage, passing guardrails/Judge and no fallback. A mode label alone is insufficient; automated regression tests reject deterministic executions even if relabeled `llm`. It saves failures rather than claiming that a failed model run passed.

The shared video is **recorded execution**, at original speed including inference waits. It is not a live session for its viewer. Use it as a clearly labeled walkthrough or backup; a new live request must still execute against the configured provider. Keep a genuine warm-up run separate from measured or presented live requests and allow for slower CPU inference.

Only the two reference workflows were evaluated in this live-model batch. CI separately runs offline tests, controlled provider fixtures, deterministic scenarios, browser checks and Docker health verification. The Judge uses the same configured model and can share its errors. Neither these curated passes nor the recording establishes production readiness or independent model accuracy. Business data, carrier responses, warehouse condition and financial processing remain fictional or simulated; no real money moves.
