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
4. After substantive changes re-index (`gitnexus analyze --skip-agents-md`) and note the
   indexed commit in the engineering log. The graph informs testing; it never replaces it.

Known limits of the graph in this repository (measured, see the engineering log, entry G):

- GitNexus cannot parse a source file larger than 32 KB; the file then silently has no call
  edges. Keep modules below that size (this is why the assessment service is split in three).
- REST route → service edges are resolved. MCP tool → `AssessmentService` edges are **not**
  (inherited methods called across package roots), and tests reach the service over HTTP, so
  they never appear as callers. Any change to a public `AssessmentService` method therefore
  also requires reading `services/mcp/feeltriva_mcp/server.py` and running `tests/mcp`.
- The index is local (`.gitnexus/` is ignored). Never run `gitnexus wiki` or publish the index.

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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Feeltriva**. Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Feeltriva/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Feeltriva/clusters` | All functional areas |
| `gitnexus://repo/Feeltriva/processes` | All execution flows |
| `gitnexus://repo/Feeltriva/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
