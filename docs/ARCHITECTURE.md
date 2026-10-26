# Architecture and implementation boundaries

## Business goal

Reduce the handoffs needed to resolve retail requests while making useful product recommendations. A customer can combine a return, a delivery question and a styling request in one message. The workflow shares verified evidence rather than asking the customer to repeat information to multiple bots.

The business case should be evaluated with measured handling time, resolution rate, escalation appropriateness, CSAT, return-to-exchange conversion and recommendation conversion. This implementation does not claim measured ROI. A pilot estimate is: monthly eligible contacts × minutes saved per contact × loaded hourly cost / 60, minus platform, provider and operator costs. Keep recommendation uplift separate to avoid double counting.

## Six roles

| Role | Inputs / allowlisted tools | Session memory | Output |
|---|---|---|---|
| Orchestrator | Current request, prior plan | Previous routing plans | Validated intent plan and dependency selection |
| Returns investigation | Owned SQL order, condition, return history, policy RAG | Prior investigation evidence | Eligibility and human-review signals |
| Resolution | Investigation evidence; current order revalidation | Prior resolution proposals | Bounded refund proposal or exception review |
| Product discovery | Profile; catalog/variant SQL; policy RAG | Prior discovery evidence | Available products filtered by size, budget and category |
| Order tracking | Owned order; live carrier API or cache; shipping RAG | Prior shipment evidence | Status and source freshness |
| Personal stylist | Discovery evidence and total budget | Prior outfit evidence | Complementary categories under total budget |

In LLM mode each selected specialist creates a bounded plan using its own prior memory. The central orchestrator selects workers dynamically; the worker executes trusted domain tools. The execution sequence remains constrained by business dependencies. Discovery ranks products using explicit style/price rules, and the stylist uses a transparent greedy baseline. Neither is a trained recommender.

## Persistence and state

SQLAlchemy supports SQLite locally and PostgreSQL in Compose. SQL stores domain entities, session credentials as hashes, messages grouped by agent, run traces, proposals, audit events and an outbox. Session history supplies durable memory between completed requests; individual LangGraph supersteps are not durably checkpointed. A crash can be retried as a new run, and proposal uniqueness prevents duplicate financial actions.

`actions` has a unique order/kind constraint. Customer confirmation rechecks current order state. Conditional SQL updates and a unique action/outbox relation prevent duplicate enqueueing, including concurrent confirmations. Operator decisions apply only to confirmed pending-review actions. Outbox draining records simulated completion atomically; no external payment is called.

## Trust boundaries

User input and retrieved content are data. The model never selects customer identity, executes arbitrary SQL, sets refund amounts, or selects arbitrary API URLs. Parameterized SQL is scoped to the authenticated customer. State and model responses use Pydantic schemas. Session tokens expire after 24 hours.

Demo access is intentionally permissive because every account is fictional. Protected mode uses a minimal operator-configured token map; enterprise SSO and granular operator identity are future work. Operator audit currently identifies a shared operator role, not an individually authenticated employee.

LLM text can still contain unsupported claims: structured validation covers domain evidence and proposals, and an independent model judge is applied only to complex/high-risk runs. A judge is not a proof of factual accuracy. A production rollout needs held-out evaluation, adversarial tests, citation-claim checks and operator sampling.

## Scaling projection

The tested deployment is a single API process with embedded Chroma, SQL persistence, a bounded request semaphore and per-session thread locks. PostgreSQL is available for server deployment; it does not alone make the app horizontally scalable. Before increasing replicas, move embeddings to a shared vector service, introduce distributed session locks, serialize initial data migrations and seeding, add queue-based admission control, and centralize model usage and tracing. Keep financial execution in a separate idempotent worker with a real provider adapter.

Configuration and schema creation currently use `metadata.create_all`, not a versioned migration system. Rollout requires adding Alembic migrations, backups and restore rehearsals. Avoid running multiple initializers against an empty database.

## Error behavior

Provider routing/planning/synthesis failures use visible deterministic fallback. Tool failures produce missing-evidence markers and block quality validation. A judge timeout blocks proposals. Carrier failures use labeled cached data. Unexpected pipeline failures return 503 and persist a failed run. The UI offers retry without silently changing identities or claiming that an action completed.

## Technical references

- [LangGraph Send](https://reference.langchain.com/python/langgraph/types/Send)
- [Chroma](https://docs.trychroma.com/)
- [Render blueprint reference](https://render.com/docs/blueprint-spec)
- [Docker Compose interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
