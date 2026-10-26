# Deployment and runbook

## Verified local service

Install with Python 3.12, run `python -m uvicorn atlas.api:app --host 127.0.0.1 --port 8000`, then check `/health`. The main UI, chat and operator endpoints share one service. Data initialization runs at startup. Runtime state is stored in `runtime/`, separate from version-controlled fixtures.

## Docker Compose

Copy `.env.example` to `.env`, set unique `POSTGRES_PASSWORD` and `ADMIN_API_KEY`, then `docker compose up --build -d`. Three services start: API, PostgreSQL 16, and a mock carrier HTTP API. Named volumes persist database and Chroma state. `docker compose logs -f api` shows operational logs. `docker compose down` stops services; do not add `-v` unless you intend to remove the stored state.

The API binds the published port to localhost. Use a TLS reverse proxy for remote access. The container runs as UID 10001 and needs a writable `/app/runtime` mount. The image exposes port 8000 by default and honors `PORT` for hosted environments.

## Optional Render deployment

The repository includes `render.yaml` and a Deploy to Render button. Authorize the repository in your Render account, review the selected paid persistent-disk service, and create the blueprint. This step may incur hosting costs. The blueprint defaults to deterministic demo mode and a single instance. Set optional model fields to blank for the no-key demonstration if prompted.

Render generates `ADMIN_API_KEY`; retrieve it in the service environment dashboard to use Operations. For real model calls, set `ATLAS_MODE=llm`, `OPENAI_API_KEY`, and a supported `OPENAI_MODEL`. Store secrets only in the host environment, never in Git. Demo access allows visitors to switch among synthetic accounts. Set `DEMO_ACCESS=false` with `CUSTOMER_TOKENS` JSON for restricted customer access.

The supplied blueprint uses persistent SQLite and Chroma for the single-instance interview demo. Compose provides PostgreSQL; a multi-replica production service requires the architecture changes described in ARCHITECTURE.md. Public hosting is not automatically provisioned by committing these files.

## CI and image release

On pushes to main and pull requests, `ci.yml` runs lint, pytest, scenario evaluation and a Docker health smoke test. Evaluation results are uploaded as an Actions artifact. `release.yml` can be manually started to publish `ghcr.io/<owner>/<repository>:<commit>` and `:latest`. Publishing an image does not start an application server. Use immutable commit tags for promotion/rollback.

## Operational checks

1. `/health` must report SQL and policy availability.
2. Authenticated `/metrics` should show successful run growth; monitor failed/review runs and latency. Model counters are process-local and reset after restart.
3. Review pending actions in Operations. Approval requires an explicit reason; no human review can precede customer confirmation.
4. Drain the simulation outbox from Operations. There is intentionally no automatic real payment adapter.
5. Back up both SQL and Chroma runtime storage. Rebuild Chroma from policy files if necessary.
6. To roll back, deploy a previously validated image tag with a compatible database schema. There is no automated schema migration or downgrade tool in v1.

## Not yet production integrations

Real CRM/payment providers, enterprise SSO/RBAC, external durable queue, distributed rate limiting, managed vector storage, schema migration/retention jobs, alert delivery and real-user load testing are operationalization tasks. The included carrier is a standalone mock API with a real HTTP adapter; the default direct local run uses cached carrier fixtures. No live payment, customer or carrier credentials are bundled.
