# Local LLM and semantic retrieval

Historical model experiments were recorded on an Intel Mac with 16 GiB RAM and CPU inference. Those reports describe their own model digests and source hashes; they do not imply Ollama or its models are installed on your machine or in a new execution workspace. Install the runtime and models below for each machine. Model files and virtual environments remain outside version control. See [current review](REVIEW.md) for what was actually reverified.

## Reproduce

Install [Ollama](https://docs.ollama.com/macos), then run these commands in separate terminals where indicated:

```bash
ollama serve  # keep running; skip if the desktop app already serves port 11434
```

```bash
ollama pull qwen3:1.7b
ollama pull all-minilm
ollama create atlas-local -f models/Modelfile
cp .env.local.example .env
# Replace ADMIN_API_KEY with a random value before starting the API.
source .venv/bin/activate
python -m uvicorn atlas.api:app --host 127.0.0.1 --port 8000
```

Qwen3 1.7B is a quantized small chat model (approximately 1.4 GB download). all-minilm is a small semantic encoder (approximately 46 MB). `models/Modelfile` sets an 8192-token context to fit grounded multi-agent prompts. `LLM_REASONING_EFFORT=none` disables optional thinking for this model. Private reasoning is neither requested nor persisted. Bounded tool calls, operational decisions and sources are recorded.

Ollama's [compatibility endpoint](https://docs.ollama.com/api/openai-compatibility) uses the existing SDK with a dummy `ollama` key, `max_tokens`, JSON schemas and native function calls. Keep the generic `.env.example` for other providers, selecting the token parameter and output mode they support. No paid account or API key is needed locally. Model tags can change; compare installed digests with the recorded model-environment JSON when reproducing a run. Temperature zero does not guarantee bitwise-identical outputs across runtime/hardware versions.

```bash
python -m scripts.evaluate --mode llm --suite journeys --repeat 2 --output reports/evaluation-llm-journeys.json
python -m scripts.evaluate --mode llm --output reports/evaluation-llm.json
```

`--suite journeys` checks customer confirmation, required human approval, audit, outbox completion and idempotency for O1002, followed by parallel order tracking and product styling. Strict LLM success requires every relevant model stage, no deterministic fallback, and all business checks. Reports retain failures. `--repeat` uses fresh isolated business stores; within each repeat the second journey runs against an already loaded chat model. Timings include cold-model loading but exclude corpus indexing/application startup.

## Limits

Small local models are useful for a reproducible prototype, not evidence of production service quality. Intel CPU inference can take tens of seconds or minutes per complete journey. Workers execute concurrently in LangGraph; the local model server may serialize inference. Model downloads and provider warm-up are separate from application request timing. Do not present deterministic demo latency as real-model latency.

all-minilm is primarily useful for English short texts and has a short input window. Corpus chunks are short paragraphs, but some may truncate; multilingual and long-document retrieval need a stronger encoder and an independently evaluated corpus. An embedding-model change creates separate Chroma collections. Failure to load the configured embedding model fails startup visibly rather than silently substituting lexical retrieval.

The initial Qwen 2.5 1.5B experiment exposed routing and tool-argument errors. Its initial run also used an incompatible token parameter and a default context that truncated evidence. Those results do not qualify as strict LLM verification. Qwen3 initially made tool calls successfully but its broad judge rubric rejected valid proposals and treated budgets as exact targets. An explicit evidence-auditing rubric corrected this. Catalog enrichment also exposed invalid outfit selections; the bounded repair step retains those attempts. See the recorded reports and validation notes for the final run, model digests and remaining errors.

The API process stores session/agent memory and run evidence in SQL. It does not install an operating-system background service for Ollama or checkpoint individual graph steps. Restart Ollama and the API using the commands above after a machine reboot.
