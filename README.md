# Feeltriva

**Understand your symptoms. Know your next step.**

Feeltriva is a conversational symptom-assessment and care-navigation product. A person describes
how they feel, confirms what the system understood, answers relevant follow-up questions and
gets a provisional next step plus a consultation-ready summary.

> **Status: engineering prototype in fixture mode.** Clinical mode is disabled. Everything the
> service returns today is a synthetic, nonmedical fixture ("Illustrative possibility A").
> Feeltriva does not confirm a diagnosis, has not been clinically validated and is not
> production-ready. The datasets it was scoped from have unknown origin and licence.

## What is in this repository

| Path | Contents |
|---|---|
| `apps/web` | React + TypeScript web app (mock and HTTP service adapters) |
| `services/api` | FastAPI transport, auth, ownership and the assessment application service |
| `services/mcp` | Product MCP adapter calling the same application service |
| `packages/clinical` | Bounded rule AST, answer validation, release bundles, synthetic fixture |
| `packages/llm`, `packages/inference`, `packages/retrieval` | Provider boundaries (mock / bundle-backed implementations only) |
| `pipelines/ingestion` | Archive verification, positional audit, reference loaders |
| `migrations` | Alembic migrations including row-level security |
| `infra` | Local Docker Compose stack |
| `tests` | Unit, API, PostgreSQL, MCP and ingestion suites |
| `specs`, `data_audit`, `experiments`, `figures` | Handoff contracts, measured audit and baseline results (unchanged) |
| `docs` | Product spec, plan, engineering log, decisions |

## Progress

Work follows [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md): steps and sub-steps with
a verification command and status each. Test results, bugs and resolutions per sub-step are in
[`docs/ENGINEERING_LOG.md`](docs/ENGINEERING_LOG.md); decisions made and still open are in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Safety boundaries that the code enforces

- Clinical mode is off by default and refuses to start with synthetic or unapproved content.
- Unmentioned symptoms are unknown, never absent. An imported zero is not a denial.
- No numerical disease probability is exposed. The offline baseline scored below the majority
  comparator and is rejected for serving.
- A failed or incomplete assessment never renders as a completed or reassuring result.
- Raw datasets, secrets, model artifacts and session data stay out of Git and the code index.

## Documentation

Start with [`docs/HANDOFF_README.md`](docs/HANDOFF_README.md), then
[`docs/01_PRODUCT_AND_BUILD_SPEC.md`](docs/01_PRODUCT_AND_BUILD_SPEC.md),
[`docs/03_CONTRACTS_AND_REPOSITORY.md`](docs/03_CONTRACTS_AND_REPOSITORY.md) and
[`docs/04_DATA_MAPPING.md`](docs/04_DATA_MAPPING.md).
