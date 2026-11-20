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

Codes and identifiers of outside vocabularies (ICD-11, LOINC, HPO, MONDO, SNOMED CT and any other source) are for the
internal database only. They are never shown to a user: not in the web app, not in an API or MCP response, not in
generated text. (Owner's instruction, 2026-11-18; decision E63.) The API's database role can read
`terminology_links` and set a decision on a row only inside a reviewer transaction (row-level security, migration 0008);
a user-facing request sees no row of it. Keep it so, and do not add a code field to a user-facing contract or route.

For each milestone: implement, run meaningful tests, document changes/limits and
update the handoff checklist. Verify API/SDK syntax against official installed-version
docs and pin dependencies. Do not report a deployment, model score, data mapping or
GitNexus graph as completed without actually producing and checking it.

Use GitNexus query/context/impact before relevant shared changes and detect_changes
before commit. Re-index the correct repo after substantive changes. It complements
rather than replaces tests. Preserve these instructions if indexing generates files.

## Working agreement for this repository

- **One sub-step at a time, then stop for the owner's go-ahead.** (Owner's instruction,
  2026-11-16, repeated after it was not followed.) The cycle for every sub-step is:
  1. State which single sub-step is next and what it will change; run the impact analysis.
  2. Implement only that sub-step.
  3. Run the tests; commit and push.
  4. Report to the owner: what was done, test results, bugs and their status, and the
     **test scenarios the owner should run themselves** (commands, and click-by-click steps
     with the expected result).
  5. **Stop. Do not start the next sub-step until the owner says to go ahead.** Planning the
     next sub-step in the report is fine; starting it is not.
  Never batch several sub-steps into one run, and never continue because a background job
  finished or because the next step "is obvious".
- **Plan from the whole handoff, not a summary of it.** Before adding or starting a sub-step,
  check it against every relevant handoff document (`docs/01` – `docs/06`, `specs/`,
  `data_audit/`, `figures/`) and against `docs/FIGURES_CROSSCHECK.md`. A requirement that has
  no sub-step is a defect in the plan and is reported to the owner.
- Work follows `docs/IMPLEMENTATION_PLAN.md`. Surface the plan, log and current status to the
  owner at each sub-step; do not run long stretches of work without reporting what was done,
  what can be tested and what is still missing. One sub-step = one commit, pushed, with its
  status updated in the plan and an entry in `docs/ENGINEERING_LOG.md` (implementation, tests
  actually run with real results, each bug with cause and resolution). New decisions go in
  `docs/DECISIONS.md`. Keep `README.md` current with what really runs.
- After **every** sub-step, backend or frontend, give the owner (1) an update: what was done,
  what the impact analysis and tests showed, bugs found and their status; and (2) **the tests
  the owner should carry out themselves**: exact commands and, for anything visible, the
  click-by-click steps with what they should see. (Owner's instruction, 2026-11-16.)
- Keep the backend and one frontend running for the owner while working: API on
  `http://localhost:8000` and the web app on `http://localhost:5173` (`pnpm dev`, design demo
  with sample data). Do not leave a second web server running: the live-API mode on
  `http://localhost:5174` (`pnpm dev:api`) is started only when a sub-step needs it or the
  owner asks, and stopped afterwards (owner's instruction, 2026-11-17). Restart servers after
  changes that need it and say so.
- Never commit `data/`, `.env`, archives or model artifacts. Stage paths explicitly.

### GitNexus impact analysis before ANY code change (mandatory)

Owner's standing instruction (2026-11-16): **always run GitNexus impact analysis before making
any change to the code, and follow this process diligently.** It applies to every code edit:
application code, tests, migrations, scripts, CI and the web app. Documentation-only edits are
the single exception. No step may be skipped because a change "looks small".

For every change, in this order:

1. **Before editing — impact.** For each existing symbol you will modify, run GitNexus
   `impact` with `direction: "upstream"` (and `context` when the callers need reading).
   For new code, run `impact`/`context` on the existing symbols it will call, extend or be
   called from (the integration points). State the result — direct callers, affected flows,
   risk level — to the owner before editing.
2. **Stop and warn on HIGH or CRITICAL risk.** Report it to the owner and explain the plan for
   every listed caller before proceeding. Never ignore a HIGH/CRITICAL result.
3. **Make the change**, covering every caller the analysis listed.
4. **Run the real tests** (commands below): lint, type check, SQLite suite and PostgreSQL
   suite; the web checks when `apps/web` is touched. The graph never replaces tests.
5. **Before committing — `detect_changes`.** Compare the changed symbols and affected flows
   with the intended scope. Anything unexpected is investigated, not committed.
6. **Commit and push** the sub-step, then **re-index** (`gitnexus analyze --skip-agents-md`)
   so the index matches the new commit (`gitnexus status` must say up-to-date).
7. **Record it** in `docs/ENGINEERING_LOG.md`: the impact result, tests run with real numbers,
   bugs and resolutions, and the indexed commit.

Changes to shared modules and contracts deserve the most care: `specs/openapi.json`,
`services/api/feeltriva_api/{service*,schemas,models,auth,db}.py`, anything in `packages/`,
`migrations/`, and `apps/web/src/api`.

Known limits of the graph in this repository (measured, see the engineering log, entry G):

- GitNexus cannot parse a source file larger than 32 KB; the file then silently has no call
  edges. Keep modules below that size (this is why the assessment service is split in three
  and the claim rules in two, `claims.py` and `claim_sentences.py`).
- REST route → service edges are resolved. MCP tool → `AssessmentService` edges are **not**
  (inherited methods called across package roots), and tests reach the service over HTTP, so
  they never appear as callers. Any change to a public `AssessmentService` method therefore
  also requires reading `services/mcp/feeltriva_mcp/server.py` and running `tests/mcp`.
- `detect_changes` maps diff hunks to the line ranges of the last index, so code inserted in the
  middle of a file makes every function below it look "touched" (measured in M1.13: `_h`,
  `source_id` and `read_csv_positional` were listed although their bodies were identical). Add new
  module-level code at the end of a file, and confirm any unexpected "touched" symbol against
  `git diff` before accepting or dismissing it.
- The index is local (`.gitnexus/` is ignored). Never run `gitnexus wiki` or publish the index.

### Commands

```bash
docker compose -f infra/docker-compose.yml up -d postgres      # local PostgreSQL on 127.0.0.1:5440
docker compose -f infra/docker-compose.yml --profile storage up -d objectstore   # object store on 127.0.0.1:9010
uv sync                                                        # Python 3.12 environment from uv.lock
uv run alembic upgrade head                                    # migrations (MIGRATION_DATABASE_URL)
uv run python -m feeltriva_api.seed                            # register the fixture release rows
uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000
uv run ruff check . && uv run pytest                           # lint + tests on SQLite
TEST_DATABASE_URL=postgresql+psycopg://feeltriva_app:feeltriva_app_dev@127.0.0.1:5440/feeltriva_test \
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://feeltriva:feeltriva_dev@127.0.0.1:5440/feeltriva_test \
  uv run pytest                                                # same suite + RLS/concurrency on PostgreSQL
uv run python -m feeltriva_ingestion completeness              # read-only: loaded data vs the handoff mapping table
uv run python -m feeltriva_ingestion load-release              # trace archive 15 to its source release; question dictionary
uv run python -m feeltriva_ingestion derive-meanings           # proposed feature kinds and zero meanings (pending)
uv run python -m feeltriva_ingestion load-answers              # archive-15 answers that are not yes/no, from the release (run load-release first; first run about 80 min)
uv run python -m feeltriva_ingestion load-conditions           # what the release lists per condition, as pending source-provided evidence and links
uv run python -m feeltriva_ingestion link-vocabularies         # candidate ICD-11 and LOINC codes (needs the ICD key in .env)
uv run python -m feeltriva_ingestion link-ontologies           # candidate HPO and MONDO terms from hp.json and mondo.owl in data/raw (offline)
uv run python -m feeltriva_ingestion import-identifiers        # SNOMED CT and ICD-11 identifiers MONDO marks equivalent (needs the ICD key)
uv run python -m feeltriva_ingestion suggest-relations         # possible synonyms and subtypes for review (nothing merged)
uv run python -m feeltriva_ingestion extract-claims            # statements split into single claims with spans (pending); --remake after a change of the rules
uv run python -m feeltriva_api.rule_drafts                     # the draft urgency rules, checked against the feature vocabulary and stored pending
```

Run the PostgreSQL suite **without** `-m "not archives"` at least once per sub-step when the
archives are in `data/raw/`: the real-archive tests were skipped that way from M1.7 to M1.12 and a
failing one went unnoticed (BUG-015).

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
