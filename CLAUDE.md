# Feeltriva implementation instructions

Read README_START_HERE.md, docs/01_PRODUCT_AND_BUILD_SPEC.md,
docs/02_MEASURED_RESULTS.md, docs/03_CONTRACTS_AND_REPOSITORY.md,
specs/schema.sql and specs/openapi.json before coding.

Build in the staged order in the specification. Treat supplied crosswalks as lexical
candidates, not approved medical ontologies. Preserve original source rows and names.
Never label the offline baseline as clinically validated or expose its softmax as a
patient disease probability. Do not merge source case IDs across archives or splits.
Do not infer absence from unmentioned symptoms or import zeros without their meaning.

Clinical mode defaults OFF. Build the engine, schema and review workflow even when
real clinical rules are unavailable. Use clearly synthetic fixtures for code tests;
do not invent medical thresholds to make the demo appear complete. Use approved
source-linked clinical content for any eventual live guidance. Keep urgency screening
inside the assessment service, including on corrections and every new message.

Keep raw health data, private datasets, secrets, model artifacts and traces out of Git
and the GitNexus code index. Use redacted logs. Enforce caller ownership server-side.
Do not call external model providers until credentials and data handling are configured.
Never transmit user health data to development analytics or LLM tracing by default.

For each milestone: implement, run meaningful tests, document changes/limits and
update the handoff checklist. Verify API/SDK syntax against official installed-version
docs and pin dependencies. Do not report a deployment, model score, data mapping or
GitNexus graph as completed without actually producing and checking it.

Use GitNexus query/context/impact before relevant shared changes and detect_changes
before commit. Re-index the correct repo after substantive changes. It complements
rather than replaces tests. Preserve these instructions if indexing generates files.

## Working agreement for this repository

- Work follows `docs/IMPLEMENTATION_PLAN.md`. One sub-step = one commit, pushed, with its
  status updated in the plan and an entry in `docs/ENGINEERING_LOG.md` (implementation, tests
  actually run with real results, each bug with cause and resolution). New decisions go in
  `docs/DECISIONS.md`. Keep `README.md` current with what really runs.
- Never commit `data/`, `.env`, archives or model artifacts. Stage paths explicitly.

### Dependency check before critical changes (GitNexus)

A change is critical if it touches a shared module or contract: `specs/openapi.json`,
`services/api/feeltriva_api/{service,schemas,models,auth,db}.py`, anything in `packages/`,
`migrations/`, or `apps/web/src/api`. For those:

1. Before editing: GitNexus `context` on the symbol and `impact` (upstream) to list callers
   and affected flows across REST, MCP, tests and the web client. Read the result; if it
   includes callers you did not plan to touch, plan them.
2. Make the change and run the real tests (commands below).
3. Before commit: GitNexus `detect_changes`, compare with the intended scope.
4. After substantive changes re-index (`gitnexus analyze`) and note the indexed commit in the
   engineering log. The graph informs testing; it never replaces it.

### Commands

```bash
docker compose -f infra/docker-compose.yml up -d postgres      # local PostgreSQL on 127.0.0.1:5440
uv sync                                                        # Python 3.12 environment from uv.lock
uv run alembic upgrade head                                    # migrations (MIGRATION_DATABASE_URL)
uv run python -m feeltriva_api.seed                            # register the fixture release rows
uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000
uv run ruff check . && uv run pytest                           # lint + tests on SQLite
TEST_DATABASE_URL=postgresql+psycopg://feeltriva_app:feeltriva_app_dev@127.0.0.1:5440/feeltriva_test \
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://feeltriva:feeltriva_dev@127.0.0.1:5440/feeltriva_test \
  uv run pytest                                                # same suite + RLS/concurrency on PostgreSQL
```
