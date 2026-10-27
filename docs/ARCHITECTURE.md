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
| Product discovery | Profile; semantic product search constrained by catalog/variant SQL; policy RAG | Prior discovery evidence | Semantically ranked, diverse candidate set with live size, budget, category and stock checks |
| Order tracking | Owned order; live carrier API or cache; shipping RAG | Prior shipment evidence | Status and source freshness |
| Personal stylist | Discovery variants, requested occasion and total budget | Prior outfit evidence | Model-selected exact variants, verified compatibility, size and total budget |

In LLM mode the orchestrator extracts structured semantic intent and constraints. Explicit budget, size, category and order-ID literals are bound by trusted parsing before downstream tools run; model-value corrections are traced. This prevents a model from changing a stated EUR 1 cap into EUR 150. These input guards are separate from semantic intent selection. Independent evidence agents select native function calls and search queries from separate registries. Each specialist can make up to three model rounds/six tool calls; invalid arguments are returned as tool errors so it can correct them. Minimum evidence contracts require both a domain lookup and policy retrieval. Missing evidence, including an attempted early answer, prompts the specialist to call the missing tools within the same three-round budget. Denied tools or an exhausted budget trigger an explicit degraded fallback. SQL identity, order ID and commerce constraints are bound by the server, never accepted as tool arguments.

Discovery retrieves semantic relevance from Chroma, restricts IDs to the authoritative SQL-eligible variants, and keeps category diversity for outfit construction. Factual garment-category definitions enrich the repetitive fictional descriptions. SQL size, stock, price and category checks precede ranking, avoiding the old arbitrary top-30 lexical/style ordering. The stylist consumes this shortlist and chooses exact variants for complementary garments, with a brief customer-facing explanation. Before publication, a second SQL lookup rechecks selected variant/product IDs, requested size, current positive stock and unchanged prices. A failed recheck suppresses the stale recommendation and blocks automated action. Validation rejects invented/duplicate variants, incorrect size, invalid combinations and excess total spend. The stylist gets one model repair attempt with explicit validation feedback; both choices are traced. Only exhausted or unavailable model decisions use a labeled fallback. The deterministic baseline enumerates feasible complete combinations rather than greedily choosing unaffordable separates. No complete combination produces a clear request to adjust constraints.

Returns investigation establishes facts and review signals. Resolution consumes those facts and cited policy to decide a standard refund proposal, exception review or human support, with next steps. It cannot set money or waive required review. Human-support recommendations suppress automated proposals. The orchestrator combines results and synthesizes a grounded reply; it does not repeat specialist investigation. Model judgements of risky/financial or multi-intent replies run as a separate quality call after deterministic checks, with no additional business role.

These remain bounded agents, not autonomous financial operators. Deterministic domain rules are intentional trust boundaries. Demo mode uses explicit fixed tool/decision baselines; it never simulates model calls. Traces distinguish `demo`, `llm_tools`, `llm_decision`, `fallback`, `failed` and `no_feasible_outfit` executions. The UI exposes the selected routing plan, tool evidence, actual overlapping monotonic intervals, downstream dependencies, deterministic guardrails and the separately recorded Judge decision. The current graph joins all independent workers before downstream nodes; it does not optimize for the earliest possible stylist start.

Per-run usage is isolated across parallel worker contexts and saved with SQL run history.

## Persistence and state

SQLAlchemy supports SQLite locally and PostgreSQL in Compose. SQL stores domain entities, session credentials as hashes, messages grouped by agent, run traces, proposals, audit events and an outbox. Session history supplies durable memory between completed requests; individual LangGraph supersteps are not durably checkpointed. A crash can be retried as a new run, and proposal uniqueness prevents duplicate financial actions.

`actions` has a unique order/kind constraint. Customer confirmation rechecks current order state. Conditional SQL updates and a unique action/outbox relation prevent duplicate enqueueing, including concurrent confirmations. Operator decisions apply only to confirmed pending-review actions. Outbox draining records simulated completion atomically; no external payment is called.

## Trust boundaries

User input and retrieved content are data. The model never selects customer identity, executes arbitrary SQL, sets refund amounts, or selects arbitrary API URLs. Parameterized SQL is scoped to the authenticated customer. Model responses and public request bodies use Pydantic schemas; graph state uses a typed dictionary. Tool schemas forbid unknown arguments. Session tokens expire after 24 hours.

Demo access is intentionally permissive because every account is fictional. Protected mode uses a minimal operator-configured token map; enterprise SSO and granular operator identity are future work. Operator audit currently identifies a shared operator role, not an individually authenticated employee.

LLM text can still contain unsupported claims: structured validation covers domain evidence and proposals, and an independent model judge is applied to financial and multi-intent runs. A judge is not a proof of factual accuracy. A production rollout needs held-out evaluation, adversarial tests, citation-claim checks and operator sampling.

## Scaling projection

The tested deployment is a single API process with embedded Chroma, SQL persistence, a bounded request semaphore and per-session thread locks. PostgreSQL is available for server deployment; it does not alone make the app horizontally scalable. Before increasing replicas, move embeddings to a shared vector service, introduce distributed session locks, serialize initial data migrations and seeding, add queue-based admission control, and centralize model usage and tracing. Keep financial execution in a separate idempotent worker with a real provider adapter.

Configuration and schema creation currently use `metadata.create_all`, not a versioned migration system. Rollout requires adding Alembic migrations, backups and restore rehearsals. Avoid running multiple initializers against an empty database.

## Error behavior

Provider routing/tool-selection/decision/synthesis failures use visible deterministic fallback. Tool failures produce missing-evidence markers and block quality validation. A judge timeout blocks proposals. Carrier failures use labeled cached data. Unexpected pipeline failures return 503 and persist a failed run. The UI offers retry without silently changing identities or claiming that an action completed.

## Technical references

- [LangGraph Send](https://reference.langchain.com/python/langgraph/types/Send)
- [Chroma](https://docs.trychroma.com/)
- [Render blueprint reference](https://render.com/docs/blueprint-spec)
- [Docker Compose interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)

## Demonstration and packaging contracts

`atlas` and `scripts` are both installed packages. CI tests their imports outside the checkout after a non-editable installation, preserving the real overlap test without path manipulation. Docker copies both packages before building the wheel. CI also rehearses both real browser journeys against isolated HTTP services and checks the actual Docker HEALTHCHECK status, not just an HTTP response. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) for exact setup, prompts, resets, evidence inspection and limitations. Browser automation is an optional development dependency, not another business service.
