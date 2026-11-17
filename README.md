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

## Quick start (backend, fixture mode)

Requirements: Docker, [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 if needed).

```bash
cp .env.example .env                                         # local, non-secret development values
docker compose -f infra/docker-compose.yml up -d postgres    # PostgreSQL 18 + pgvector on 127.0.0.1:5440
uv sync                                                      # install locked dependencies
uv run alembic upgrade head                                  # schema, constraints, row-level security
uv run python -m feeltriva_api.seed                          # register the synthetic fixture release
uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000
```

Then, in another terminal:

```bash
curl -s localhost:8000/readyz
# {"status":"ready","database":"up","clinical_mode":false,"release":"fixture-rules-0","synthetic_release":true}

AUTH='Authorization: Bearer dev:local-user'      # mock auth exists only in development/test
curl -s -X POST localhost:8000/v1/sessions -H "$AUTH" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' -d '{"consent_version":"demo-1","demographics":{"age_years":34}}'
```

The fixture vocabulary is deliberately nonmedical: try the text `I have alpha but no beta`
(`escalation marker` triggers the urgent-state preview, `scope marker` the out-of-scope one).
Interactive API docs are at `http://localhost:8000/docs` in development.

## Quick start (web app)

Requirements: Node 22.22 or newer and pnpm.

```bash
cd apps/web
pnpm install
pnpm dev        # http://localhost:5173  design demo: in-memory sample scenarios, no backend needed
pnpm dev:api    # http://localhost:5174  live mode: every action goes through the API on :8000
```

In the design demo, **Demo tools** (top right) switches between the ten scenarios and turns on
the reviewer preview. In live mode, type the fixture vocabulary (`I have alpha but no beta`,
`escalation marker`). Identity and session state are held in memory only, so reloading the page
starts fresh by design.

```bash
pnpm typecheck && pnpm lint && pnpm test && pnpm build
pnpm smoke      # real Chrome against :5173 — routes, ten scenarios, four viewports
pnpm e2e:live   # real Chrome against :5174 + the API — intake to deletion through REST
```

### Tests

```bash
uv run ruff check . && uv run mypy packages services pipelines
uv run pytest                                    # SQLite; PostgreSQL-only tests are skipped
TEST_DATABASE_URL=postgresql+psycopg://feeltriva_app:feeltriva_app_dev@127.0.0.1:5440/feeltriva_test \
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://feeltriva:feeltriva_dev@127.0.0.1:5440/feeltriva_test \
  uv run pytest                                  # same suite plus row-level security and concurrency
```

### Source data (optional)

The six source archives are not in the repository. Place `archive(11).zip` … `archive(16).zip`
unchanged in `data/raw/`, then:

```bash
uv run python -m feeltriva_ingestion verify      # SHA-256 against the manifest + ZIP safety checks
uv run python -m feeltriva_ingestion audit       # positional audit; must reproduce data_audit/audit.json
uv run python -m feeltriva_ingestion load        # pending crosswalks and statements into PostgreSQL
uv run python -m feeltriva_ingestion load-cases     # 1.37 M case rows in 20,000-row batches (about 35 min, 1.7 GB)
uv run python -m feeltriva_ingestion load-features  # 14.8 M feature values (zeros are not stored; 15 – 60 min, 3.3 GB)
uv run python -m feeltriva_ingestion load-lists     # 1.2 M listed symptoms + declared-count checks (about 12 min)
uv run python -m feeltriva_ingestion load-chunks    # 85 narrative files -> 3,651 pending chunks (seconds)
uv run python -m feeltriva_ingestion search-text "night cough wheezing"   # review search over pending text
uv run python -m feeltriva_ingestion load-evidence  # pending disease–feature proposals (about 13 min)
```

### MCP

```bash
FEELTRIVA_MCP_BEARER_TOKEN=dev:local-user uv run python -m feeltriva_mcp     # stdio transport
```

The product MCP server exposes the same assessment service as the REST API. It is unrelated to
GitNexus, the developer code-intelligence index described in `CLAUDE.md`.

## Progress

| Step | State |
|---|---|
| M0 Bootable project and contracts | Backend, migrations, auth, generated web client, CI (backend and web jobs) done |
| M1 Reproducible ingestion | Verification, audit, reference load, 1,365,363 case rows, 16,013,976 feature rows, 3,651 narrative chunks and 22,059 pending disease–feature evidence proposals done. **Not done: raw archives in object storage, completeness check** (M1.12, M1.13) |
| M2 Reviewable knowledge model | Review API and reviewed-only serving done; release publishing and review UI wiring not started |
| M3 Fixture-mode vertical slice | Service, REST, contract tests, stdio MCP and the web app done; web verified against the live API in a browser (43 checks) |
| C User conversations on Apache Cassandra (replaces the PostgreSQL session tables) | Planned, not started |
| M4 – M5 Modelling, retrieval and LLM adapters | Not started |
| L Continuous learning: automated retraining, evaluation gates, promotion | Planned, not started |
| M6 – M7 Pilot, expansion | Not started |
| G GitNexus code intelligence | Indexed; dependency check documented |

Every handoff requirement is traced to its status and sub-step in
[`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) (203 requirements; the current count is at the top of that file).

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
