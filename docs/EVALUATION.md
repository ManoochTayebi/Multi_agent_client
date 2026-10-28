# Evaluation protocol

## Reproducible commands

```bash
ruff check atlas scripts tests
pytest -q
python -m scripts.evaluate --mode demo --output reports/evaluation-demo.json
python -m scripts.evaluate --mode llm --suite journeys --repeat 2 --output reports/evaluation-llm-journeys.json
python -m scripts.evaluate --mode llm --output reports/evaluation-llm.json
```

All evaluation uses temporary SQL/Chroma stores and fictional users. `--repeat` uses a new store for each repetition. Operator actions affect only these stores. Exit status is nonzero if any scenario fails. Failed scenarios remain in the report. Startup/provider errors terminate the command visibly; they are not reported as passes.

## What is measured

Thirteen curated scenarios cover standard/high-value/late returns, forged identity, delayed tracking, styling, impossible budgets, category discovery, combined intents, parallel tracking/styling, unknown goals, missing order identity and French returns. Role checks require exact equality including the orchestrator, penalizing unnecessary roles. Checks cover extraction of budget/size, nonempty recommendations where expected, empty results for impossible constraints, stock, total budget, ownership, eligibility and review. Explicit currency/size/category/order literals are bound by validated parsing; any corrections of model-proposed values are counted and traced separately from model fallback. Empty outfits no longer pass a styling case just because their total is zero.

The high-value return journey follows the API through proposal, rejection of premature operator approval, customer confirmation, review queue, operator approval, simulated outbox completion, repeated drain and audit. The parallel journey checks that evidence workers' measured execution intervals overlap and styling starts after discovery finishes. The local model server may serialize inference even when graph workers overlap.

Strict LLM success additionally requires actual recorded provider calls at every relevant stage: routing, native specialist tool selection, resolution/styling decisions when applicable, synthesis and required judge. Strict acceptance also requires configured semantic embeddings and actual query embedding calls. Any fallback/degraded execution fails strict acceptance even if deterministic recovery produces a useful answer. A no-result stylist correctly makes no model selection. The judge is a separate call using the same model and evidence, not a seventh business agent or an independent statistical evaluator.

Reports include stage latency, per-run prompt/completion tokens, failed provider calls, tool arguments/status, embedding request counts/tokens, warnings and estimated chat cost. Costs require configured per-million input/output rates; absent rates or unavailable usage produce null. Zero rates in the local profile mean no provider invoice, excluding hardware/electricity, embedding and operator costs. Index creation is excluded from contact inference usage. Latency p50 is the median; p95 uses nearest rank. HTTP failures are not inserted as zero-latency samples.

Policy recall@2 uses eight development probes, including paraphrases. Product category recall@3 uses two semantic paraphrases. These probes compare lexical and pretrained semantic retrieval configurations; they are not a held-out relevance benchmark. All report parameters and per-probe results are retained.

## Failure and regression coverage

The offline tests also reject an empty model routing response and blank operator reasons, serialize session deletion against active chat, and verify replies after an existing refund is confirmed/rejected/queued/completed. The offline tests cover return-window boundaries, stock changes after indexing, owned SQL lookups, forged credentials, concurrent idempotency, operator review, agent/session memory isolation and deletion, explicit follow-ups, real graph-worker overlap using a barrier, native tool validation and repair, rejected cross-role tools, premature specialist termination, unknown variants, invalid outfit composition, model attempts to bypass review, missing SQL evidence, carrier failure, judge timeout, concurrent per-run usage attribution and provider errors. Controlled provider stubs validate failure contracts, not real-model quality.

See [recorded validation](VALIDATION.md) for the tests actually run, model experiments, exact results and limitations. Do not reuse old validation counts as evidence of the current implementation.

## Acceptance and production evaluation

Software/demo acceptance: all offline tests and all curated demo cases pass. Strict LLM journey acceptance: all journey checks and required model stages pass without fallback on each recorded repetition. Retrieval quality and latency remain separate metrics; report weaknesses even if the two journeys pass. Do not compare demo timing with model timing.

A production pilot needs a separately annotated, de-identified held-out dataset and human review. Measure intent precision/recall, retrieval MRR/recall, groundedness, unsupported-claim and unsafe-action rates, escalation precision/recall, recommendation relevance, multilingual performance, p95 latency and cost per resolved contact. Include ambiguity, conflicting conditions, stale stock, lost deliveries, tool outages and prompt injection. Tune on development data, then evaluate the untouched test set once. No CSAT, business ROI, production SLA or production-grade model reliability is established here.
