# Atlas CustomerAI finalization — 27 October 2026

Preserved all six business agents, native model tool calling/decisions, LangGraph routing and parallel workers, persistent memory, SQL/RAG, approval safeguards, synthetic data and existing deployment choices. No seventh business agent or real payment connector was introduced.

## Changes

- Fixed the CI packaging defect: setuptools now includes the `scripts` package, and Docker copies it before installation. Added an isolated import regression outside the checkout; retained the original concurrency test unchanged.
- Revalidated recommended product/variant IDs, requested size, current stock and prices against SQL at the publication boundary. Stale recommendations are suppressed.
- Exposed separate deterministic checks, Judge decisions, measured overlap/dependencies and per-role execution modes in the existing interface. Added exact Demo A/B buttons, audit inspection and updated customer payment status after operator decisions.
- Expanded integration coverage for the EUR 249 lifecycle, rejection, authorization, confirmations/idempotency, both native-LLM protocol journeys and bounded provider retry. Controlled provider responses are explicitly labeled as tests, not inference evidence.
- Expanded evaluation reports with actual findings, proposals, audit events, exact roles, overlap, current retrieval mode, usage, fallback and observed rule failures. Strict LLM acceptance now requires configured/executed semantic retrieval.
- Added an isolated Chromium/HTTP rehearsal and strengthened CI to run it and inspect actual Docker health. Updated the renamed repository's URLs and provided the full demonstration runbook.

## Executed verification

Ruff passed; 42 pytest tests passed; full deterministic evaluation passed 13/13. Two API journeys repeated three times passed 6/6, with measured overlap, zero observed authorization/business-rule check failures and zero fallback. A real Chromium rehearsal passed both UI journeys through customer confirmation, operator approval, audit, simulated processing and duplicate-processing protection, plus desktop/mobile checks. Reports and source hashes are in `docs/validation/finalization-*.json`.

The final GitHub Actions run must also pass package import, tests, evaluation, Chromium rehearsal, Docker build, startup and image HEALTHCHECK before the work is marked complete. Its linked run is the authoritative remote execution record, not a promise that local Docker ran.

## Simulation and remaining limits

All business records, carrier responses and financial processing remain synthetic/simulated. Deterministic mode makes no LLM calls. Current lexical policy recall@2 was 4/8 on the broader literal/paraphrase probes; semantic retrieval on this changed commit needs a working provider.

No Ollama installation/endpoint or compatible credentials were available in this workspace. Therefore the changed code has **not** been revalidated with live LLM/semantic calls; strict current LLM success, latency, tokens and costs remain unmeasured. Prior model reports retain their historical source hashes and must not be represented as current live runs. The runbook gives exact commands for three repeated live rehearsals and an honest fallback/recording strategy if inference is slow.

Local Docker was unavailable; use the actual remote CI container result. PostgreSQL integration, independent model quality, production load, production readiness and business ROI are not claimed. The Judge remains a separate prompt to the same configured model and may share its errors. Static UI traces show completed execution rather than a live streaming timeline.
