# Development validation — 2026-10-26

- Ruff: passed.
- Pytest: 16 integration and policy/security tests passed against isolated SQLite and Chroma stores.
- Curated deterministic evaluation: 12/12 scenarios passed; policy recall@2 was 4/4 hand-authored probes. See `evaluation-demo.json` for the recorded run. Timing numbers describe the local deterministic demo only.
- Full locked runtime dependency installation: completed; lint and tests passed afterward.
- JavaScript syntax: checked with `node --check`.
- Live HTTP and UI logic: verified using Uvicorn and a DOM integration harness: create a customer session, send a combined high-value refund/styling request, confirm the proposal, load operator reviews, approve with a reason and complete the simulated payment.
- Actual Chromium rendering was not verified: the environment's browser download returned an invalid archive. The DOM test is not a visual layout or accessibility audit.
- Docker/PostgreSQL runtime execution was not available locally. CI includes Docker build and health checks; those results must be inspected in GitHub Actions after publication.
- Live LLM/embedding calls were not tested because provider credentials were unavailable. Provider-failure behavior and a judge timeout were exercised with controlled stubs.
- No cloud hosting account was connected during implementation. The Render blueprint and Docker deployment are prepared; a public hosted URL is not implied by these checks.
