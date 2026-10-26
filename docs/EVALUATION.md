# Evaluation protocol

The unit/integration suite validates policy boundaries, order ownership, confirmed proposals, concurrent idempotency, operator review, sequential dependencies, carrier fallback, per-agent session memory and session deletion. A model stub tests a judge timeout without claiming a live-provider test.

`python -m scripts.evaluate` executes 12 curated synthetic request scenarios against an isolated FastAPI application. It reports expected specialist coverage, action permissions, return eligibility, total outfit budget, stock availability, shipment status, policy recall@2 and p50/p95 observed latency. Routing checks require the expected roles as a subset; they do not currently penalize unnecessary agent calls.

Acceptance for the deterministic demonstration: all curated scenario checks pass; all authorization and action lifecycle tests pass; policy recall@2 equals 1 on the four hand-authored retrieval probes. These tiny fixtures are software acceptance checks, not a statistical benchmark. Latencies exclude network and paid-model calls.

LLM mode must be evaluated separately using configured credentials. Record provider, model version, embedding model, prompt commit, token totals, repeated-run variance, latency and provider cost. Avoid comparing demo timing to LLM timing. Real provider validation was unavailable during initial implementation.

For a production pilot, build an independent, de-identified held-out dataset with human annotations: routing labels, grounded answer facts, relevant policy chunks, expected escalation and action outcome. Include multilingual requests, ambiguous follow-ups, disputes, retrieval injection, unavailable inventory, delivery failures and adversarial identity claims. Report intent precision/recall, retrieval recall@k/MRR, groundedness, unsafe-action rate, escalation precision/recall, CSAT, recommendation relevance, p95 latency and cost per resolved contact. Tune on development data and report final test results once.
