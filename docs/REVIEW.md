# Repository review — 28 October 2026

Reviewed `ManoochTayebi/Multi_agent_client` from commit `0795c0a`, including the code, dependency/install path, existing CI, API lifecycle, browser demonstrations, README and architecture. The six business agents, LangGraph topology, native model tool calling, SQL/Chroma and existing deployment choices are preserved.

## Findings and fixes

| Finding reproduced before the fix | Result |
|---|---|
| A model response of `{}` became an empty routing plan through schema defaults | The `intents` field is required. An explicit `[]` remains valid for a greeting; malformed routing now triggers the existing visible fallback. |
| A whitespace-only operator reason could authorize a decision | Reasons are trimmed before length validation; blank reasons return 422 without changing approval/outbox state. |
| Session deletion during an active chat caused foreign-key failures in memory/run writes | Chat and deletion share the same session lock. Conflicts return 409; session existence is rechecked after lock acquisition. Deletion after the request completes removes the session's memory and runs. |
| Repeating a confirmed/rejected/completed refund request still described a fresh proposal | Investigation retrieves the owned refund lifecycle from SQL. The response and resolution evidence use that status, and the existing unique action/outbox protections remain in place. |

Seven new regression cases first failed against the previous implementation, then passed after the fixes. The original tests, including actual worker-overlap and provider-protocol checks, remain enabled.

## Verification

- **Ruff:** passed.
- **Tests:** 49 passed after a non-editable install, including the outside-checkout package import check.
- **Full deterministic evaluation:** 13/13 scenarios passed; no degraded runs or unnecessary agent activations in those cases.
- **Chromium/HTTP rehearsal:** both customer/operator demonstrations passed, including approval, audit, duplicate processing, updated customer status, live mock-carrier HTTP, measured worker overlap and mobile overflow checks. No JavaScript errors were reported.
- **Documentation:** README now prioritizes setup, the exact two demos, mode differences, checks and navigation. Architecture diagrams map to actual routing/join behavior, quality gates and refund transitions. Runbook and related docs were aligned.

The local execution summary and source hashes are in [review-20261028.json](validation/review-20261028.json). Full current reports and screenshots are produced by CI under its `evaluation` artifact. [GitHub Actions](https://github.com/ManoochTayebi/Multi_agent_client/actions/workflows/ci.yml) reruns lint, tests, evaluations, repeated journeys, the real browser rehearsal, Docker build/startup and the actual HEALTHCHECK on each final commit. Its commit-specific run is the authoritative remote result.

## Remaining boundaries

No Ollama executable, reachable local model endpoint or compatible credentials were available in this execution workspace. Current live LLM/semantic inference quality, latency, tokens and cost are therefore **unverified**. Controlled provider tests check the protocol and failure handling, not model quality. Historical real-model reports in [validation history](VALIDATION.md) remain tied to their earlier source hashes; they are not current live runs.

Offline lexical policy recall@2 remains **4/8** on the eight literal/paraphrase probes, and product-category recall@3 is **2/2**. These are separate from the 13 scenario checks and are not a held-out relevance benchmark. No claim of semantic quality follows from deterministic success.

Docker is unavailable locally; the actual image build/health checks run in GitHub Actions. Local API/browser tests use SQLite; PostgreSQL support remains in Compose but is not reclassified as a locally verified database deployment. Public hosting is not required for the case study and has not been provisioned. Data, carrier, inspection/approval and payments remain fictional/simulated; no production readiness or ROI is claimed.

The documented single-process boundary still applies: embedded Chroma and session locks are local, graph steps are not durably checkpointed, setup uses `create_all`, and operator authentication is a shared key rather than enterprise SSO/RBAC.
