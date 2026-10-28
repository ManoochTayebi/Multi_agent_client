# Validation history

For the latest repository review and checks, see [REVIEW.md](REVIEW.md). The dated results below remain historical records tied to their own source hashes.

## Finalization validation — 27 October 2026

This section records the 27 October finalization. Everything under **Historical validation** below describes earlier code/model runs and is retained as provenance; it must not be attributed to the current source without matching hashes.

| Check | Observed on 27 October |
|---|---|
| Non-editable packaging | `atlas` and `scripts` installed; isolated import outside checkout passes |
| Ruff | Passed |
| Pytest | 42 passed; original overlap regression remains enabled |
| Full deterministic API evaluation | 13/13; exact role coverage, no fallback/extra agents |
| Two demo journeys, three repetitions | 6/6 against fresh SQL/Chroma stores per repetition |
| Real Chromium UI/HTTP rehearsal | Passed refund/approval/audit, duplicate drain, updated customer status, tracking/styling, mock carrier and mobile overflow checks; no JavaScript errors |
| Live model and semantic inference | Not executed in this workspace: no Ollama executable/reachable endpoint or provider credentials |
| Local Docker execution | Unavailable: no Docker executable. Actual build, startup and Docker HEALTHCHECK verification run in the GitHub Actions container job |

Current evidence: [full API report](validation/finalization-demo.json), [repeated journeys](validation/finalization-journeys.json), [browser evidence](validation/finalization-browser.json), [environment availability](validation/finalization-environment.json). Reports contain actual source hashes and execution evidence. Screenshots and full CI reports are uploaded as Actions artifacts; they are not synthetic illustrations.

The repeated deterministic journeys measured p50 36.5 ms / p95 97 ms in this workspace, with zero model calls, zero observed business/authorization check failures, zero fallback and zero unnecessary agent activations. These timings exclude model/index startup and do not describe LLM performance. Lexical policy recall@2 was **4/8** (including difficult paraphrases); category recall@3 was **2/2**. Semantic relevance and current strict LLM success/tokens/cost are unverified, not inferred from those scores.

Native provider tool calls, resolution/styling decisions, Judge invocation, argument repair, bounded provider retry and error handling are covered through controlled HTTP/model fixtures in the automated tests. Those protocol tests are not live-model inference. Earlier real-model results below remain historical evidence with their own source hashes. PostgreSQL support is preserved; this review's API/browser reports use SQLite.

The customer/operator UI now exposes actual overlap intervals, dependencies, selected tools, policy/SQL evidence, guardrail and Judge outcomes, audit transitions and simulated payment status. A final live SQL check rejects stale variant IDs, size, stock or prices before publishing a recommendation. No real financial connector was added.

Rehearsal instructions: [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md). CI installs non-editably, checks imports outside checkout, runs all tests/evaluations, rehearses actual Chromium UI journeys, builds the image and requires Docker health status `healthy`. The final commit's Actions run is the authoritative remote result; no remote result is inferred from local checks.

## Historical validation — prior implementation

All uses of “final” in this historical record refer to that earlier review only.

# Recorded validation — 26 October 2026

This record supersedes the original demo-only validation. Reports below describe development runs against fictional data, not a held-out benchmark, real customer operations or a production SLA.

## Environment and software checks

- Intel Mac, 16 GiB RAM, CPU inference; Python 3.13.9.
- Installed Ollama 0.40.11 after finding no local installation/model store in the usual locations.
- Final chat model: `atlas-local`, based on quantized `qwen3:1.7b`, 8192-token context, temperature 0, reasoning disabled. Semantic encoder: `all-minilm`.
- Installed the runtime lock and development extras in `.venv`. Fixed the missing ONNX Intel wheel with a conditional ONNX 1.23.2 pin and pinned its additional dependencies. `pip check`: passed.
- Ruff: passed. Pytest: **35 passed**, including provider/tool failures, model-decision repair, graph overlap and memory across app restart.
- `docker compose config --quiet`: passed with temporary validation-only Compose credentials. Container/PostgreSQL runtime and remote CI were not executed during this review.
- Native HTTP: UI delivery, authenticated customer access, operator isolation, session deletion and a real HTTP call to the included mock carrier passed. The adapter bug caused by an empty bearer header was found and corrected. [HTTP smoke result](validation/http-smoke.json).
- Browser rendering/accessibility and public hosting were not verified. The native web app and mock carrier were started locally. Ollama/API are session processes, not installed background services.

Exact model digests, package versions, non-secret configuration and source SHA-256 values are recorded in [model environment](validation/model-environment.json). `.env` is ignored and contains the configured local profile plus a generated operator key; it is not copied into reports.

## Final measurements

| Execution | Strict passes | p50 | p95, nearest rank | Chat calls |
|---|---:|---:|---:|---:|
| Deterministic, full curated suite | 13/13 | 10 ms | 23 ms | 0 |
| Real LLM, two journeys × two repetitions | 4/4 | 43300.0 ms | 64058 ms | 27 |
| Real LLM, full curated suite | 11/13 | 38422 ms | 136889 ms | 69 |

[Deterministic report](evaluation-demo.json) · [Repeated real-LLM journeys](validation/evaluation-llm-journeys.json)

The two presentation journeys are:

- `return_high_value`, repetition 1: **pass**, 32.672 seconds; 6 chat calls; degraded=false.
- `parallel_tracking_styling`, repetition 1: **pass**, 51.653 seconds; 7 chat calls; degraded=false.
- `return_high_value`, repetition 2: **pass**, 34.947 seconds; 6 chat calls; degraded=false.
- `parallel_tracking_styling`, repetition 2: **pass**, 64.058 seconds; 8 chat calls; degraded=false.

The return journey verifies proposal, blocked premature approval, customer confirmation, operator queue/approval, simulated completion, audit and duplicate-drain protection. The parallel journey verifies both worker execution overlap and discovery-before-styling, owned shipment status, exact agent roles, size, nonempty outfit and total budget. Strict LLM passes require the relevant provider stages and no fallback. A bounded successful model repair counts as model execution, with both attempts recorded.

The repeated-journey report predates the final greeting-only routing clarification in `atlas/agents.py`. Its recorded source hashes expose that difference. The full-suite report matches the final implementation hashes and re-verifies both journeys without fallback (25.183 s for the high-value return and 71.155 s for parallel tracking/styling). Earlier experiments intentionally retain their original outputs and precede the documented fixes.

[Full real-LLM report](validation/evaluation-llm.json). Remaining failed development cases:

- `tracking`: no_fallback. order_tracking: model tool selection failed (ToolSelectionError); bounded tools used.
- `missing_order`: no_fallback. returns_investigation: model tool selection failed (ToolSelectionError); bounded tools used.

Final journey policy recall@2: **100%**, on eight disclosed development probes repeated twice. Product category recall@3: **100%**, on two disclosed probes repeated twice. Lexical demo scores are **50%** and **100%** respectively. Catalog-category definitions were added during development; these results therefore demonstrate corrected development behavior, not generalization.

The repeated journey run used **30,011 chat tokens** and reports **USD 0.00 provider chat charges** under the local zero-rate profile. This excludes embeddings, indexing, CPU/electricity, hardware and supervision. Usage per run and embedding requests/tokens are retained in JSON. Unknown external-provider rates produce null, not zero.

Timings include request orchestration, SQL/RAG and model inference/loading as encountered, but exclude application/index startup. Models were already used in preceding development experiments, so these are mostly warm runs. Graph workers overlap; the local Ollama server can serialize inference. Tiny-sample p95 values must not be presented as an SLA.

## Failed experiments retained

- [Qwen 2.5 1.5B initial run](validation/evaluation-llm-initial.json): 0/2 strict passes, with tool/decision fallbacks and a judge miss. It also used an incompatible token setting and context truncation, so it is not a clean model comparison. One draft incorrectly claimed approval; the same-model judge missed that claim.
- [Qwen3 before judge calibration](validation/evaluation-llm-judge-before.json): 0/4, despite no degraded execution. The judge incorrectly treated review requirements as violations and budgets as exact spending targets. The evidence-auditing rubric now distinguishes allowed proposals and maximum budgets from breaches.
- [Qwen3 before stylist repair](validation/evaluation-llm-before-repair.json): 2/4. Both returns passed; both parallel requests recovered through deterministic outfit fallback and failed strict acceptance. The final implementation gives the model one bounded correction opportunity and traces its choices.

The first full-suite experiment also exposed unnecessary tracking on shopping-only requests, a misread tiny budget and an empty single-product result. The model judge missed the literal-budget error. The final implementation binds explicit budget/size/category/order literals through trusted parsing, records any model-value corrections, constrains category values and uses a focused semantic-routing prompt without numeric examples. This preserves model intent/tool decisions while protecting the input boundary. [Full suite before input guards](validation/evaluation-llm-before-input-guards.json).

A subsequent full run corrected semantic routing and literal constraints but exposed specialists stopping after policy retrieval without the domain lookup. The tool loop now explicitly requests missing evidence within its existing three-round budget, retaining the same six roles and domain boundaries. Greeting-only messages were also clarified as zero business goals after the small model suggested unsolicited styling. [Before missing-evidence feedback](validation/evaluation-llm-before-tool-feedback.json).

These experiments guided implementation changes. The final acceptance set is development data and was repeatedly inspected. Improvements cannot be described as statistically established model-quality gains.

## Practical limits and next verification

The solution preserves all six business roles and demonstrates real native function calls, semantic retrieval, SQL, APIs, persistent per-agent/session memory, human approval and LLM-as-a-Judge. Domain checks remain authoritative. Payments, warehouse inspection and carrier data are simulated; only the HTTP integration itself is real.

The small English-oriented encoder and small chat model require broader multilingual, ambiguity, hallucination and relevance evaluation. An observed stylist explanation gave incorrect arithmetic despite selecting valid variants; the executable outfit total came from SQL prices and Python validation, and the raw explanation remains in the trace. Model explanations are not proofs of correctness. Judge errors are correlated with the generator and both false positives and a miss were observed. The scripted software checks do not prove answer completeness or production safety. Production needs independent human annotations, stronger model comparison, load and outage testing, real identity/connectors, migrations/retention and distributed/durable execution according to scale requirements.
