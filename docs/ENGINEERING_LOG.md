# Feeltriva — engineering log

One entry per sub-step in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md): what was
implemented, the tests that were actually run with their real results, and every bug found
with its cause and resolution. Newest entries are at the bottom. Figures are copied from
command output, not estimated.

## Bug index

| Bug | Sub-step | Summary | Status |
|---|---|---|---|
| BUG-001 | M3.3 | Every authenticated endpoint returned 422 `query.who: Field required` | Fixed |
| BUG-002 | M0.4 | `uv run alembic upgrade head` failed on a checkout that only had `.env` | Fixed |
| BUG-003 | G1 | GitNexus silently produced no call edges for the 37 KB `service.py` | Fixed |
| BUG-004 | M1.6 | Ingestion load test failed on the persistent test database (43 sources, expected 13) | Fixed |
| BUG-005 | M1.7 / M1.8 | PostgreSQL restarted itself during bulk loads (twice) | Fixed in M1.8 — root cause found: the health check orphaned a probe that PostgreSQL, as process 1, treated as a crashed child |
| BUG-006 | M1.7 | Formatter re-wrapped two already-applied migrations | Fixed — reverted before commit |
| BUG-007 | M3.6 | Web: keyboard focus is not returned to the footer button after its dialog closes | Open |
| BUG-008 | M3.6 | Web: a duration answer is displayed twice ("3 days · 3 days") | Open |
| BUG-009 | M3.6 | Web: an explicit "None of these" answer shows the raw option value "none" under the detail | Open |
| BUG-010 | M3.6 / M3.3 | "Not sure" on multiple-choice and free-text questions is sent in a form the API does not treat as uncertain (latent: no such question in the fixture) | Open |
| BUG-011 | M1.8 | Feature loader refused any file that contains a malformed row | Fixed |
| BUG-012 | M1.11 | Large aggregate failed: PostgreSQL could not resize a shared memory segment | Fixed |
| BUG-013 | M0.3 / M1.12 | The Compose `objectstore` service named an image that cannot be pulled | Fixed |
| BUG-014 | M1.12 | New `store-archives` command was not registered in the CLI | Fixed before commit |
| BUG-015 | M1.3 / M1.13 | The real-archive reference-load test failed on the persistent PostgreSQL test database; unnoticed from M1.7 to M1.12 because PostgreSQL runs excluded the real-archive tests | Fixed |
| BUG-016 | M1.3, M1.7, M1.9 / M1.13 | Loaders did not refuse a file whose columns had changed: the case loader loaded it, the list and reference loaders stopped with an unexplained error | Fixed |
| BUG-017 | M2.11 | The ICD client did not retry a dropped connection; the first real run died on a network timeout | Fixed |
| BUG-018 | M2.11 | The ICD client opened a new secure connection for every request and ran the lookups inside a database transaction; the real run crawled at about 6 terms a minute | Fixed |
| BUG-019 | M2.11 | LOINC matching on the component name alone gave a wrong-sense link ("fever" to "Fever in Mother") | Fixed before commit |

## Entries

### M0.1 — Repository scaffold

**Implemented.** Monorepo directories from `docs/03_CONTRACTS_AND_REPOSITORY.md`. The handoff
package (`docs/`, `specs/`, `data_audit/`, `experiments/`, `figures/`) copied in unchanged so
its relative links still resolve. `.gitignore` and `.env.example` adapted from the handoff
templates; `CLAUDE.md` keeps the authored instructions and adds this repository's working
agreement. The six source ZIPs were moved, unmodified, from the project root to `data/raw/`
(ignored by Git). `Feeltriva_Claude_Handoff.zip` stays at the root, also ignored.

**Checks run.**

- `shasum -a 256 -c SHA256SUMS.txt` inside the extracted handoff: 0 mismatches.
- `shasum -a 256 data/raw/*.zip`: all six digests equal `specs/ingestion_manifest.json`
  (`92be3363…`, `6f81c9c4…`, `fbe1d4b7…`, `19ff1f13…`, `9e21f94b…`, `61749286…`).
- `git check-ignore`: `.env`, `data/raw/*.zip`, the handoff ZIP and `*.npy` are ignored.
- Text search of everything staged for personal details or credentials: none found.

**Bugs.** None.

### M0.2 — Python toolchain

**Implemented.** `pyproject.toml` (one distribution; packages mapped to the monorepo paths),
`.python-version` = 3.12, `uv.lock`. Lint with ruff, types with mypy, tests with pytest.
Versions resolved on 2026-11-16 and locked: FastAPI 0.163.1, Starlette 1.10.0, Pydantic 2.14.3,
SQLAlchemy 2.1.8, Alembic 1.20.1, psycopg 3.3.9, cryptography 50.0.2, PyJWT 2.15.1, MCP SDK 2.3.0,
pytest 9.2.0, ruff 0.17.5, mypy 2.4.1.

**Checks run.** `uv sync` resolves and installs; `uv run ruff check .` → "All checks passed!".

**Bugs / notes.**

- Environment note (not a product bug): the shell had `VIRTUAL_ENV` pointing at another
  project's environment, so `uv pip list` reported that project's packages. Resolution: always
  use `uv run …`, which targets this repository's `.venv` (uv prints a warning and ignores the
  foreign variable).
- Lint: the first `ruff check` reported only `E501` line-length findings. Resolution: line
  length set to 120 and `E501` left to the formatter.

### M0.3 — Local stack

**Implemented.** `infra/docker-compose.yml`: PostgreSQL 18 with pgvector on `127.0.0.1:5440`;
MinIO (`storage` profile) and Redis (`worker` profile) defined but optional. An init script
creates the `feeltriva_app` login and a separate `feeltriva_test` database. Credentials are
development defaults for a localhost-only container.

**Checks run.** `docker compose -f infra/docker-compose.yml up -d postgres` → container healthy
(`pg_isready` succeeds). MinIO and Redis services were written but **not started or tested**.

**Bugs.** None.

### M0.4 — Database migrations

**Implemented.** `0001` executes the 32 statements of `specs/schema.sql` unchanged (27 tables,
3 enum types). `0002` adds state/status/urgency check constraints, a partial unique index so an
observation can be superseded only once, indexes for the service's owner- and session-scoped
reads, and `review_notes`. `0003` grants the application role the minimum it needs and enables
**forced** row-level security on `sessions`, its child tables, `idempotency_keys` and
`audit_events`, plus reviewer-only update policies on mapping and statement tables.

**Checks run** against the Compose PostgreSQL:

- `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head`: all succeed;
  `alembic current` = `0003 (head)`.
- After upgrade: 29 tables in `public` (27 + `review_notes` + `alembic_version`), 15 policies.
- `feeltriva_app`: `rolsuper = f`, `rolbypassrls = f`.

**Bugs / notes.** Alembic 1.20 warned that `path_separator` was missing from `alembic.ini`;
added `path_separator = os`.

### M3.1 / M2.3 — Rule engine, answer validation and release bundle

**Implemented** in `packages/clinical`:

- `rules.py`: declarative AST (`and`, `or`, `not`, `present`, `absent`, `missing`, `compare`)
  evaluated with three-valued logic. A concept nobody mentioned satisfies neither `present`
  nor `absent`. The validator rejects unknown operators, extra keys, unknown feature or field
  references, depth above 8 and more than 200 nodes. Rules are data; nothing is executed.
- `answers.py`: answer-schema validation for yes/no/not-sure, single and multiple choice,
  number with unit, duration and free text, and the observation each answer implies.
- `bundle.py`: release bundle model and loader. In clinical mode a bundle that is synthetic, not
  approved, or contains any unapproved item is refused.
- `engine.py`: urgency/scope screening and one-at-a-time question selection.
- `fixtures/fixture_release.json`: synthetic, nonmedical release (`fx.*` concepts, three rules,
  four questions, two illustrative candidates of which one cites evidence that does not exist).

**Tests run.** `uv run pytest tests/unit/test_rules.py` → 15 passed. Bundle and answer tests
are in `tests/unit/test_answers_bundle_extractor.py` (committed with M3.3) → 13 passed.

**Bugs.** None.

### M3.2 — Provider boundaries

**Implemented.** `packages/llm`: `Extractor` protocol, `MockExtractor` (whole-word match on
the supplied vocabulary; `absent` only after an explicit negation cue in the same clause;
`uncertain` after a hedge; exact character spans; text matching nothing is returned as one
unmapped, uncertain observation) and `UnavailableExtractor` for outage tests.
`packages/inference`: `CandidateProvider` protocol and a bundle-backed matcher; no statistical
model is wired in. `packages/retrieval`: `EvidenceProvider` protocol and a bundle-backed
lookup that simply does not return unknown IDs. No external provider is called anywhere.

**Tests run.** Extractor cases in `tests/unit/test_answers_bundle_extractor.py` (3 of its 13
tests); candidate and evidence behaviour is covered through the API flow tests in M3.3.

**Bugs.** None.

### M3.3 / M0.5 / M0.6 — Assessment application service, auth, health and errors

**Implemented** in `services/api/feeltriva_api`:

- `service.py` — `AssessmentService`, the only place assessment logic runs. Start session,
  get session, submit observations (free text or structured corrections), submit answer, next
  question, assess, summary, delete. Every method takes the verified `Principal`.
  Idempotent mutations store an encrypted replay body per `(owner, key)`; a different payload
  under the same key is 409. Observation versions use a row lock plus a conditional
  `UPDATE … WHERE observation_version = :expected`. Urgency/scope screening runs on every
  change. Corrections are append-only rows with `supersedes`.
- `auth.py` — bearer authentication: mock dev tokens (development/test only) and JWT
  verification (issuer, audience, expiry, RS256/ES256, known scopes only).
- `settings.py` — refuses mock auth, a missing encryption key or raw prompt logging outside
  development/test; clinical mode needs an approved bundle path.
- `main.py` — FastAPI routes, `/healthz`, `/readyz`, one error envelope, request IDs,
  `Cache-Control: no-store` on private routes, CORS from configuration.
- `crypto.py`, `db.py`, `models.py`, `schemas.py`, `seed.py`, `container.py`, `review.py`.

**Tests run** (figures from the runs on 2026-11-16):

| Command | Result |
|---|---|
| `uv run pytest tests/unit` | 28 passed |
| `uv run pytest tests/api/test_flow.py` | 12 passed |
| `uv run pytest tests/api/test_guards.py` | 19 passed |
| `uv run pytest tests/api/test_auth_jwt.py` | 9 passed |
| `uv run pytest` (SQLite) | 73 passed, 7 skipped (PostgreSQL-only) |
| same with `TEST_DATABASE_URL` / `TEST_MIGRATION_DATABASE_URL` (PostgreSQL, app role) | 80 passed |
| `uv run pytest tests/postgres` on PostgreSQL | 7 passed |
| `uv run mypy packages services` | no issues in 22 files |

What the PostgreSQL-only tests establish: the application role is not a superuser, owns no
tables and cannot bypass RLS; an unfiltered `SELECT` in one caller's transaction returns only
that caller's rows on every private table; cross-owner `UPDATE`/`DELETE` affect 0 rows and
cross-owner `INSERT` is rejected; six concurrent writers on one version produce exactly one
200 and five 409s; five concurrent identical retries apply once.

Live check with `uvicorn` against the Compose database: `/readyz` reported
`clinical_mode: false, synthetic_release: true`; create session → 201; text → extracted
`alpha` present and `beta` absent, both unconfirmed; assess with a stale version → 409;
another caller → 404; delete → `deletion_scheduled`; CORS preflight from
`http://localhost:5173` allowed `Authorization, Content-Type, Idempotency-Key`.

**Bugs.**

- **BUG-001 — every authenticated endpoint returned 422.** *Found by* the first run of
  `tests/api/test_flow.py` (`assert 422 == 201`); the body said
  `query.who: Field required; query.key: Field required`. *Cause:* `main.py` had
  `from __future__ import annotations`, which turns annotations into strings; the dependency
  aliases `Who` and `Key` are defined inside `create_app`, so FastAPI could not resolve the
  strings and treated them as query parameters. *Resolution:* removed the future import from
  `main.py` and documented why in the module docstring. *Verified:* full suite passes.
- **BUG-002 — migrations ignored `.env`.** *Found by* the live smoke run:
  `uv run alembic upgrade head` printed "Set MIGRATION_DATABASE_URL" although `.env` had it.
  *Cause:* `migrations/env.py` read only process environment variables, unlike the
  application. *Resolution:* `env.py` falls back to the application `Settings` (which loads
  `.env`). *Verified:* `uv run alembic current` → `0003 (head)` with no variables exported.
- Type check: mypy reported 15 errors on the first run (a reused loop variable name across
  two branches, `rowcount` on an untyped result, `str` passed where a `Literal` is declared).
  All fixed; none changed behaviour.

**Not done in this sub-step.** No rate limiting (429). JWT verification was tested with a
locally generated key, not against a real identity provider.

### M3.4 — REST transport and contract tests

**Implemented.** `tests/api/test_contract.py` loads `specs/openapi.json` and checks that all
eight operations are served with the declared `operationId`, and that real responses for
Session, Question, Assessment (needs_clarification, provisional, urgent_handoff,
out_of_scope), Summary, DeletionReceipt and Error (400, 401, 404, 409, 422) validate against
the contract schemas, including formats.

**Tests run.** `uv run pytest tests/api/test_contract.py` → 5 passed.

**Bugs.** Test-only: the first version read `route.operation_id` from every route and failed
on Starlette's documentation routes (`AttributeError`); it now skips routes without methods
or operation IDs. No API change was needed for the responses to validate.

**Limits.** 429 is declared in the contract but never returned (no rate limiting yet). The
contract has no 500; unexpected errors return 500 with the same envelope.

### M3.5 — Product MCP adapter

**Implemented.** `services/mcp/feeltriva_mcp/server.py`, built on the official MCP Python SDK
2.3.0 (`MCPServer`; the API was checked against the installed package rather than assumed).
Nine tools — `start_assessment`, `get_assessment_session`, `submit_observations`,
`submit_answer`, `assess_session`, `get_next_question`, `get_condition_information`,
`create_consultation_summary`, `delete_session` — each a thin call into the same
`AssessmentService` / `KnowledgeService` the REST routes use. The caller comes from a bearer
token verified by the API's `Authenticator` on every call; no tool takes a user or owner
identifier; `delete_session` requires `confirm_delete: true`. Errors are returned as tool
errors carrying the same `code` / `message` / `retryable` as REST. Run with
`FEELTRIVA_MCP_BEARER_TOKEN=dev:<subject> uv run python -m feeltriva_mcp`.

**Tests run.**

- `uv run pytest tests/mcp` → 5 passed. Covered: tool surface equals the contract table and
  exposes no identity/SQL/URL arguments; a full flow run independently over REST and over MCP
  gives identical responses at every step once per-session IDs and timestamps are normalised
  (sessions, questions, assessment, summary text); a session started over REST continues over
  MCP for the same caller and a REST write makes the MCP client's version stale; another caller
  gets `session_not_found` from every tool; out-of-turn and invalid answers are rejected;
  read-only scope cannot assess or delete; urgent state pauses questions over MCP too.
- Real protocol check: an MCP client over stdio initialised the server, listed the nine tools,
  started and deleted a session. With no token the call returned
  `is_error: true` with `{"code": "unauthenticated", …}`.
- Full suite after this change: `uv run pytest` → 78 passed, 7 skipped (SQLite).

**Bugs.** None in the adapter. Note: the SDK's own argument-validation errors echo the
offending value, so tools take loosely typed arguments and validate them with the API's
schemas, which report locations only.

**Not done.** Remote (streamable HTTP) transport with OAuth, token-audience validation and
per-tool scope metadata. Only stdio with an environment-supplied token exists.

### M1.1 / M1.2 — Archive verification, ZIP safety and positional audit

**Implemented** in `pipelines/ingestion/feeltriva_ingestion`:

- `archives.py` — SHA-256 of each archive against `specs/ingestion_manifest.json` before
  anything is opened; entry validation (absolute paths, `..`, drive letters, NUL bytes,
  symbolic links, duplicate names, encrypted entries, types other than `.csv`/`.txt`, more than
  500 entries, an entry over 512 MiB, over 1 GiB total, compression ratio above 200:1 — the
  largest real ratio is about 91:1); a positional CSV reader that returns plain lists so
  repeated header names stay separate columns, bounded by each entry's declared size. Nothing
  is extracted to disk.
- `audit.py` — one streaming pass per CSV: rows, columns, labels, exact duplicates, repeated
  profiles excluding patient ID, malformed rows, sex/gender row counts, repeated headers and
  rows where repeated columns disagree; text-file digests; label overlap between archives;
  archive-15 train/test shared profiles. `compare()` lists every difference from the manifest
  and from `data_audit/audit.json`.
- CLI: `uv run python -m feeltriva_ingestion verify | audit | load`.

**Tests and runs.**

- `uv run python -m feeltriva_ingestion verify` → all six archives "checksum ok"; 1 / 2 / 89 /
  1 / 2 / 2 entries passed the safety checks (97 = 12 CSV + 85 text).
- `uv run python -m feeltriva_ingestion audit` → `12 CSV files, 85 text files, 1368315 CSV
  rows; 960 lexical disease labels; 24s` and **"reproduces manifest and audit.json"** (zero
  differences). That includes 57,305 and 28,988 exact duplicate rows in archive 12, 27,622
  shared archive-15 profiles, and 37 repeated header names in archive 16, each with at least
  one disagreeing row.
- `uv run pytest tests/ingestion/test_archives.py` → 20 passed (crafted archives: traversal and
  absolute paths, disallowed types, symlink, 20 MiB-of-zeros bomb, size and count limits,
  non-ZIP, missing archive, tampered checksum, BOM, repeated headers, duplicate rows, repeated
  profiles, column conflict, malformed row, non-ASCII label, lexical-only normalisation).
- `uv run pytest tests/ingestion/test_real_archives.py` → 2 passed, 1 skipped on SQLite.

**Bugs.** None functional. mypy rejected wrapping a raw stream directly in `TextIOWrapper`;
the bounded reader is now wrapped in `io.BufferedReader`.

### M1.3 – M1.6 — Reference load (sources, crosswalks, narrative statements), idempotent

**Implemented** in `load.py`. One source row per file, versioned by its archive digest, plus
one for the 85 archive-13 text files. Under mapping release `mapping-lexical-0` (pending): the
960 lexical disease candidates and 958 lexical feature candidates from `data_audit/`, their
source-label and column-position mappings, and the measured conflict for every repeated-header
column. Archive 13 is joined on its native `disease_id`; the redundant `disease_name` is
compared with `diseases_main` and a mismatch would be stored as a quality flag. Archive-13
summaries/causes/symptoms/treatments and archive-16 descriptions become `pending` statements,
each linked to its source record, row locator and supplied URL. Deterministic IDs and
`ON CONFLICT DO NOTHING` make reruns no-ops. Nothing is approved, merged or served.

**Runs** against the Compose database:

| Table | First `load` inserted | Second `load` inserted | Total |
|---|---|---|---|
| sources | 13 | 0 | 13 |
| mapping_releases | 1 | 0 | 1 |
| diseases | 960 | 0 | 960 |
| disease_mappings | 3,117 | 0 | 3,117 |
| features | 958 | 0 | 965 (958 + 7 fixture concepts) |
| feature_mappings | 1,651 | 0 | 1,651 |
| source_records | 3,037 | 0 | 3,037 |
| statements | 2,952 | 0 | 2,952 |
| statement_sources | 2,952 | 0 | 2,952 |

Checked in SQL afterwards: statements by file = 85 descriptions, 714 causes, 712 symptoms, 621
treatments (archive 13) and 820 descriptions (archive 16); 855 distinct diseases have a
statement; 74 feature columns carry a repeated header (37 names), all 74 with a non-zero
disagreement count; 336 archive-13 mappings carry the native ID; 0 rows in any status other
than `pending`; 0 quality flags raised (no archive-13 name mismatch or unknown native ID).

`uv run pytest` with the PostgreSQL variables → 108 passed (SQLite: 100 passed, 8 skipped),
including `test_reference_load_is_idempotent_and_everything_is_pending`.

**Bugs.** None.

**Not done (M1.7).** The matrix files' 1.37 million rows are audited but not loaded row by row
(`dataset_cases`, `case_labels`, `case_features`), and profile-cluster IDs are not persisted.
Narrative text files are registered as source records but not split into statements.
List-valued fields (archive 12 `symptom_text`, archive 14 `Symptoms`) are not parsed into
feature candidates.

### M2.1 / M2.2 — Review API and reviewed-only serving

**Implemented** in `services/api/feeltriva_api/review.py` (routes in `main.py`):
`/internal/v1/review/overview`, `/disease-mappings`, `/feature-mappings` (with
`conflicts_only`), `/statements` and `POST /decisions`. All require the `reviewer` role from
the verified token. A decision records who, an obligatory note, the optional status change and
an audit event. `GET /v1/conditions/{disease_id}` (also the MCP tool
`get_condition_information`) returns a condition only if the disease is `approved`, and only
its `approved`, unexpired statements that have at least one source; a retired alias follows
its redirect.

**Tests run.** `uv run pytest tests/api/test_review.py` → 6 passed, 1 skipped on SQLite; 7
passed on PostgreSQL. Covered: 401 without a token and 403 without the role on every review
route; original spelling, column positions and conflict counts are returned; decisions are
attributed, noted and audited, and a note alone changes no status; invalid targets and
statuses are rejected; a pending disease is 404 even through a redirect; pending, unsourced
and expired statements are withheld; approving a statement makes it appear with its source and
retiring it removes it at once; imported dataset candidates are 404; on PostgreSQL an
`UPDATE` of a mapping outside a reviewer-scoped transaction changes 0 rows.

**Bugs.** None.

**Not done.** The web reviewer screens still use mock data (M2.4). No disease redirect/merge
history, immutable release publication or rollback (M2.5). No atomic claim extraction (M2.6).
Approving a row here does not publish it into a served release; fixture mode serves only the
synthetic bundle.

### G1 – G5 — GitNexus code intelligence

**Implemented.** GitNexus 1.6.3 (`gitnexus analyze`) indexes this repository into the local,
git-ignored `.gitnexus/` directory. `.gitnexusignore` excludes `data/`, `data_audit/`,
`experiments/results/`, `figures/`, lockfiles, CSV and PNG files on top of everything already
in `.gitignore`. No embeddings were generated and nothing left the machine. The analyzer
appended a marked GitNexus section to `CLAUDE.md` (authored content verified unchanged above
it) and created `AGENTS.md` and `.claude/skills/gitnexus/`. `CLAUDE.md` now states which
changes count as critical and the check to run before and after them. The developer GitNexus
MCP server is separate from the product MCP server in `services/mcp`.

**Checks run.**

- First index: 3,303 nodes, 6,797 edges, 247 flows. `gitnexus status` → "up-to-date".
- G2, call chain: `context` on `submit_observations` and `impact` on `AssessmentService`
  showed **no callers at all** → BUG-003 below. After the fix, `impact` (upstream) on
  `ServiceCore._idempotent` lists exactly its six callers (`start_session`,
  `submit_observations`, `submit_answer`, `assess_session`, `create_summary`,
  `delete_session`) at risk CRITICAL, and `impact` on `IntakeOperations.submit_observations`
  lists the REST route `main.py:submit_observations` (confidence 0.85).
- G3, a real critical change checked with the tool: splitting the assessment service and
  restructuring the MCP tools. `detect_changes` before commit reported the touched symbols
  (`create_app`, `AssessmentService`, `build_server` and the nine MCP tool functions) and 11
  affected flows, which matches the intended scope. Then the real tests: 106 passed, 9 skipped
  on SQLite; 115 passed on PostgreSQL; `mypy` clean; MCP stdio check repeated successfully.
- G5: generated `CLAUDE.md` section, `AGENTS.md` and skill files searched for local paths,
  names and e-mail addresses: none. `.gitnexus/meta.json` contains the local path and stays
  ignored. `gitnexus wiki` (external LLM, optional public gist) was not run.

**Bugs.**

- **BUG-003 — the graph had no call edges for the most important module.** *Found by* the G2
  check; the analyzer had printed `scope extraction failed for
  services/api/feeltriva_api/service.py: Invalid argument` and still reported success.
  *Cause:* the file was 37,323 bytes; GitNexus's parser fails above 32 KB. *Resolution:* the
  service was split by responsibility into `service_core.py` (9.0 KB), `service_intake.py`
  (14.3 KB) and `service_results.py` (15.0 KB); `service.py` keeps the public
  `AssessmentService` class, so no import changed. The REST and MCP modules now hold the
  service in a typed variable, and the MCP tools call it directly through a small error
  decorator instead of lambdas. *Verified:* the impact results above, and both test suites.
- **BUG-004 — ingestion load test failed on PostgreSQL (`43 == 13` sources).** *Found by* the
  full PostgreSQL run after the refactor. *Cause:* not the refactor. The test database
  persists between runs and `tests/api/test_review.py` adds its own synthetic sources,
  mappings and statements, so table-wide counts drifted. *Resolution:* the ingestion test
  counts only rows with the loader's deterministic ID prefixes. *Verified:* full PostgreSQL
  suite → 115 passed.

**Known limits (also in `CLAUDE.md`).** Files over 32 KB lose their edges without an error
exit. MCP tool → `AssessmentService` edges are still not resolved (inherited methods called
across package roots), and tests call the service over HTTP, so neither shows up as a caller:
changes to a public service method need a manual look at `services/mcp/feeltriva_mcp/server.py`
plus `tests/mcp`. Empty `__init__.py` files produce harmless "no Module scope" warnings.
The index must be rebuilt after each commit (`gitnexus analyze --skip-agents-md`).

### M0.8 — CI and repository hygiene

**Implemented.** `.github/workflows/ci.yml` (backend job): locked install, ruff, mypy, the
SQLite suite, then a PostgreSQL 18 + pgvector service container where it creates the
least-privilege role, runs migrations up → down → up and the same suite with row-level
security and concurrency tests, and finally fails if data, archives or `.env` files are
tracked. Tests that need the source archives are excluded (the archives are never committed).
Also: Dependabot (uv and GitHub Actions), a pull-request checklist that includes the GitNexus
dependency check, a bug-report template that mirrors this log, and `SECURITY.md`.

Repository settings applied on GitHub: description and 12 topics; Dependabot alerts and
security updates; secret scanning with push protection; private vulnerability reporting;
delete branch on merge. The repository was created private and made public on the owner's
instruction (decision E24).

**Checks run.** CI run 43848920712 on commit `bd53f4a` → **success** (every step of the
backend job passed, including both test suites and the migration round trip). Dependabot
opened its first update pull requests within a minute; none has been merged.

**Bugs.** None.

**Not done.** The web job (typecheck, tests, build, generated-client diff) is added together
with the web app in M3.6. No branch protection rule is set: commits go straight to `main`.

### M1.7 — Row-level case load and profile clustering

**Impact analysis before editing** (GitNexus, index at the then-current commit):

| Symbol | Action | Risk | Direct callers / flows |
|---|---|---|---|
| `main` (ingestion CLI) | modified: new `load-cases` command | LOW | 1 (module entry point) |
| `read_csv_positional` | called only | HIGH | `audit_csv`, `load_reference`; flows `main`, `run_audit` |
| `source_id` | called only | HIGH | `load_reference`, `load_reference.add` |
| `disease_candidate_id` | called only | HIGH | `load_reference.add` |
| `_load_file`, `load_cases` (new, re-indexed before the batching change) | modified | LOW | `load_cases` → `main` |

The three HIGH-risk functions were reported before editing and left unchanged; new code only
calls them.

**Implemented.** `pipelines/ingestion/feeltriva_ingestion/cases.py`, CLI
`uv run python -m feeltriva_ingestion load-cases [--files …] [--batch-rows N]`, migration
`0004` (indexes on `dataset_cases.profile_cluster_id`, `dataset_cases.source_split`,
`case_labels.disease_id`). Every row of a case file becomes a `source_records` row (file, row
locator, content hash, original split, quality flags), a `dataset_cases` row (source-scoped
patient ID, age as supplied with no unit assumed, demographic field and value as supplied,
profile cluster) and a `case_labels` row (original label, pending lexical candidate, label
origin `unknown`). Nothing is merged or dropped. After loading, each case gets
`duplicate_status` (`exact_duplicate_row`, `repeated_profile`, `no_duplicate_detected`) and
records whose profile occurs in more than one original split get the flag
`profile_shared_across_original_split`. Loading is idempotent.

Definition used: a *profile cluster* is the hash of all cells except the patient ID and the
disease label, scoped to the archive and column layout. It deliberately differs from the
audit's figure of 27,622 shared archive-15 profiles, which includes the label; identical
features with different labels must stay together when data is split.

**Tests run.**

- `uv run pytest tests/ingestion/test_cases.py` on PostgreSQL → 3 passed (crafted two-file
  archive, batch size 2: every row kept; malformed row flagged and not turned into a case;
  unparsable age flagged, not guessed; exact duplicates marked; same profile with different
  labels kept as one cluster with both labels; cross-split members flagged; patient IDs scoped
  per file; unknown labels become pending candidates; rerun inserts and updates nothing;
  unregistered source refused).
- Full suites after the change: PostgreSQL 115 passed (archive tests excluded while the load
  runs); SQLite 104 passed, 11 skipped; `ruff` and `mypy` clean.
- Real data so far: archive 11 → 100,000 records, cases and labels. Archive 14 → 25,000 /
  25,000 / 25,000 in 27 s, "matches manifest" (25,000 exact-unique rows, 24,999 profile
  clusters, 2 rows in one repeated profile, 0 malformed).
- `detect_changes` before commit: see BUG-006.

**Bugs.**

- **BUG-005 — PostgreSQL crashed during the first full load.** The first version loaded each
  file in a single transaction. Archive 11 committed; during archive 12 `data.csv` (246,945
  rows × 378 columns) the server logged a 139.6-second checkpoint, then
  `untracked child process … exited with exit code 2`, terminated all connections and spent
  about six minutes in crash recovery. The client saw `connection is lost`; the unfinished
  transaction was rolled back (0 rows for that file). At that moment the host had a load
  average of 16.8, about 66 MB of free memory and seven other containers running. *Cause:*
  not proven; no out-of-memory or out-of-disk message was logged, so resource starvation is
  the most likely explanation, not a confirmed one. *Mitigation:* the loader now commits every
  20,000 rows, so no transaction grows with file size and a rerun resumes; files can be loaded
  selectively; the owner had the other containers stopped. *Verified:* all seven case files (1,365,363 rows) then loaded without incident under the
  batched loader.
- **BUG-006 — formatter changed applied migrations.** *Found by* `detect_changes`, which
  listed `0001` and `0003` as touched although only `0004` was meant to be added. *Cause:*
  `ruff format` was run on the whole `migrations/` directory and re-wrapped long lines in the
  two older files (no SQL changed). *Resolution:* both files restored with `git checkout`
  before committing; new migrations are formatted individually.

**Full load result** (completed 2026-11-16; every file reported "matches manifest"):

| File | Rows = records = cases = labels | Exact-unique rows | Profile clusters | Rows in exact-duplicate groups | Rows in repeated profiles | Rows flagged shared across split |
|---|---|---|---|---|---|---|
| archive 11 matrix | 100,000 | 100,000 | 100,000 | 0 | 0 | 0 |
| archive 12 `data.csv` | 246,945 | 189,640 | 169,888 | 94,079 | 27,265 | 0 |
| archive 12 `final_symptoms_to_disease.csv` | 192,715 | 163,727 | 149,241 | 52,887 | 21,855 | 0 |
| archive 14 `Healthcare.csv` | 25,000 | 25,000 | 24,999 | 0 | 2 | 0 |
| archive 15 `test.csv` | 134,529 | 134,529 | 126,431 | 0 | 38,261 | 33,590 |
| archive 15 `train.csv` | 475,502 | 475,502 | 402,932 | 0 | 136,693 | 51,767 |
| archive 16 matrix | 190,672 | 190,672 | 170,911 | 0 | 32,397 | 0 |
| **Total** | **1,365,363** | | | 146,966 | 256,473 | 85,357 |

Cross-checks in SQL after the load:

- `source_records` (case rows), `dataset_cases` and `case_labels` each hold 1,365,363 rows; 0
  malformed rows; statuses sum to the total (146,966 + 256,473 + 961,924).
- Exact-unique row counts equal `specs/ingestion_manifest.json` for all seven files (for
  example 189,640 and 163,727 for archive 12, i.e. the handoff's 57,305 and 28,988 duplicate
  rows).
- Demographic row counts equal the handoff: archive 14 Male 8,271 / Female 8,336 / Other
  8,393; archive 15 M 296,145 / F 313,886. These are rows in files, not people or prevalence.
- Archive 15: 501,453 feature profiles; **27,910 occur in both train and test**, covering the
  85,357 flagged rows; 985 profiles carry more than one disease label (455 of them also span
  both splits). The audit's 27,622 counts label-inclusive profiles, so the two figures are
  expected to differ.
- 926 distinct lexical disease candidates are referenced by case labels; all 960 candidates
  are still `pending`.
- Timings on this machine: archive 15 in 949 s, archives 12 + 16 (plus a no-op pass over
  archive 11) in 1,244 s. Database size afterwards 1,729 MB (`source_records` 666 MB,
  `dataset_cases` 710 MB, `case_labels` 338 MB). Reruns insert nothing.

**Not done.** Cell-level feature values (`case_features`) are not loaded (decision E23), so
repeated-header conflicts are recorded per column (M1.3) but not per case. List-valued fields
(archive 12 `symptom_text`, archive 14 `Symptoms`) are stored only inside the row hash, not
parsed into feature candidates. The real-archive load has no automated test (it needs the
archives and about 35 minutes); the crafted-archive tests cover the logic in CI.

### M3.6 / M0.7 / M3.7 — Web application, generated client, web against the live API

**How it was built.** A background agent built `apps/web` from
`docs/06_LOVABLE_FRONTEND_PROMPT.md`. It stopped before sending its final report because the
account's usage limit was reached, so this entry is an independent review of what it left,
not the agent's own account.

**Impact analysis.** `apps/web` is a new directory: no existing symbol was modified. Its
integration point is `specs/openapi.json` (unchanged). Two files were added after the review
(`scripts/e2e-live.mjs`, a `dev:api` and `e2e:live` script entry). `.github/workflows/ci.yml`
and `.github/dependabot.yml` are YAML and not covered by the code graph; the root
`.env.example` gained a second allowed CORS origin.

**What exists.** Vite + React 19 + TypeScript (strict) + Tailwind 4 + react-router, Radix
dialogs/menus, self-hosted Manrope/Inter. All ten routes of the spec; all twenty named
components; a typed `AssessmentService` with a mock adapter (in-memory scenarios, fixtures in
their own folder) and an HTTP adapter; types generated from `specs/openapi.json`; a demo
toolbar with the ten scenarios and a labelled reviewer preview; print/copy summary; privacy and
history screens; a 325-line README including its own list of assumptions and known gaps.

**Checks run in this review.**

| Check | Result |
|---|---|
| `pnpm typecheck` | no errors |
| `pnpm lint` (zero warnings allowed) | no findings |
| `pnpm test` | 118 passed in 6 files |
| `pnpm build` | succeeds |
| `pnpm gen:api`, then compare the generated file | byte-identical (M0.7: deterministic) |
| `pnpm smoke` — real Chrome, mock mode: routes, ten scenarios, 320/390/768/1440 px, reviewer pages, console errors, overflow | 374 passed, **1 failed** (BUG-007) |
| `pnpm e2e:live` — real Chrome against the running API (new in this review) | **43 passed, 0 failed** |

Safety review by search and by reading the screens: the only key written to browser storage
is the navigation-collapsed preference; no emergency or phone number anywhere; no probability,
percentage or ranking in patient screens; only `example.org` sample links; no testimonial,
certification or accuracy claim; sample labels on results, exports and the persistent banner;
result sections in the required order.

**What the live run proves (M3.7).** Through the real REST API in a browser: session creation
with dev auth; free text extracted by the backend and shown for confirmation; a denial listed
under "Not present" and nothing unmentioned listed there; all four fixture question types
answered one at a time; next-question 204 handled as "no more questions"; the provisional
result rendered from the API response with "Urgency not assessed … does not mean low urgency"
and no percentage; evidence drawer showing the API's citation; a correction marking the old
result "needs updating" and the recomputed result dropping the possibility and stating it is
not reassurance; summary text from the API, export blocked until the review box is ticked;
deletion receipt showing "scheduled", not "completed"; urgent state from the API pausing
questions with no invented number; every mutation carrying a unique `Idempotency-Key`; no
console errors; no health data in storage; and after a reload the API returning 404 to the new
in-memory identity.

**Bugs and findings.**

- **BUG-007 (open) — focus not restored.** Smoke check "keyboard: focus returns to the footer
  button" fails: after closing an informational dialog opened from the footer, focus does not
  return to the button. The spec requires dialogs to restore focus.
- **BUG-008 (open) — duplicated duration.** A duration answer renders as "3 days · 3 days":
  the API returns both a `value` and a `duration` string and the detail row prints both.
- **BUG-009 (open) — raw option value shown.** After "None of these", the detail under "Not
  present" shows the option's internal value `none`.
- **BUG-010 (open, latent) — "not sure" formats.** The web app sends `["not_sure"]` for
  multiple choice and the string `"not_sure"` for free text; the API accepts "not sure" only
  for yes/no, single choice, number and duration. No fixture question uses those two types, so
  nothing fails today.
- **Contract gap, not a bug.** The API contract has no display name for a concept, so the
  web app shows the user's own phrase when there is one and otherwise a name derived from the
  identifier ("Signal beta"). A label field needs a contract decision.
- **By design.** In development the caller identity is generated per page load and kept in
  memory, so a reload cannot reopen a session. Real authentication is required for that.
- **First versions of the live test** failed three checks twice; both times the fault was in
  the test (reading the page before it rendered; treating the expected post-reload 404 as an
  error), not in the application. The test now waits properly and asserts the reload
  behaviour.

**Not done / not verified.** Condition pages, history listing and the reviewer console run on
fixtures (no REST endpoints in the contract; M2.4). No date answer type. Mobile keyboard
behaviour checked only in desktop Chrome at phone sizes. Screen reader and 200 % zoom not
tested by hand. `pnpm smoke` and `pnpm e2e:live` are not in CI (they need Chrome and, for the
live test, a running API and database). CI run 43866522296 on commit `e9dfbc8`: backend job and the new web job both succeeded.

### R0 — Requirements traceability (documents only, no code change)

**Why.** The owner pointed out that the complete data was not ingested and that the figures
had never been checked. Both were true. The plan had been written from the backlog summary
(`docs/05`) instead of from the whole handoff, `docs/02_MEASURED_RESULTS.md` had not been
read, and several sub-steps had been run back to back without waiting for the owner's
go-ahead. The working agreement in `CLAUDE.md` now requires one sub-step at a time and a stop
for go-ahead.

**Done.**

- Read `docs/02` in full and opened all five figures. The three result charts match
  `experiments/results/metrics.json` and `per_class.csv` value by value
  (`FIGURES_CROSSCHECK.md`).
- Measured the missing data (read-only): the four matrix files hold 371,234,666 cells, every
  one `0` or `1`, of which 14,565,013 are `1`; archive 12's symptom text has 1,081,459 items
  in 283 distinct terms; archive 14's symptom lists have 125,036 items in 28 terms, and its
  declared counts match the lists in every row.
- Wrote `TRACEABILITY.md`: 203 requirements traced. **73 done, 72 partial, 46 missing, 12
  need an external decision.**
- Added 14 sub-steps that had no place in the plan (M0.9, M0.10, M2.8, M2.9, M3.9 – M3.15,
  M5.6, M6.6, G6), after M1.8 – M1.13, M2.7 and M3.8 from the figures cross-check; widened
  M4.3, M4.5, M5.1, M5.2, M5.3 and M2.5.

**What was missing from the plan before this (the substance of the owner's complaint).**
Which features each case has (`case_features`, 14.6 million values); the symptom text and
lists; disease–feature evidence; the 85 narrative texts as searchable content; the serving
views and the vector / full-text knowledge base; the meaning of each feature; question
selection by safety, relevance and burden; a fresh untouched test set and the next experiments
listed in `docs/02`; the explanation step and its contradiction check; observability;
deployable images; rate limiting; remote MCP authentication; saved history; the evaluation
harness; the threat model.

**Checks run.** A script confirmed that all 68 sub-step IDs cited in the trace exist as rows
in the plan and that the 13 IDs marked new are present. No code changed, so no test suite was
re-run for this sub-step.

**Bugs.** None in code. Process failures recorded above.

### M1.8 — Cell-level feature values (`case_features`)

**Handoff clauses applied** (checked before writing code):

- `docs/04`: archive 11 `symptom_*`, archive 12 `data.csv` columns, archive 15 `E_*`, archive
  16 positions → `case_features`; "preserve column position"; "zero semantics unresolved";
  "duplicate headings remain separate mappings and conflicting values remain explicit".
- `docs/01` §2: "A blank matrix value, an imported zero and an explicit denial are different
  concepts." §3 rule 6: never OR contradictory values.
- `docs/02`: all 37 repeated headers disagree somewhere; "keep each column position".
- `specs/ingestion_manifest.json`: `zero_semantics: unknown_pending_review`,
  `duplicate_columns: retain_positional_and_flag_conflicts`.
- `specs/schema.sql`: `case_features(case_id, mapping_id, raw_value, normalized_value,
  presence, conflict)`.

**Impact analysis before editing.** `main` of the ingestion CLI (modified): LOW, one caller.
`_raw_cursor`, `_hash`, `case_files` (called only): LOW. `read_csv_positional`, `source_id`
(called only): HIGH, reported to the owner and left unchanged. New: `features.py`, a test
file. Infra: `infra/docker-compose.yml`.

**Implemented.** `pipelines/ingestion/feeltriva_ingestion/features.py` and the command
`uv run python -m feeltriva_ingestion load-features [--files …] [--batch-rows N]`.

- Measured first (read-only): the four matrix files hold 371,234,666 cells and every one is
  `0` or `1`; 14,565,013 are `1`.
- A `1` is stored as a row: raw value `1`, presence `present` (the source row affirms that
  column), normalised `true`.
- A `0` is **not** stored and never becomes `absent`. For a registered column, no row means
  the source cell was `0`; what that means stays `zero_semantics = unknown` on the mapping.
- A blank would be stored as `not_asked`; any other value verbatim as `uncertain`. Neither
  occurs in the supplied files; both are covered by tests.
- Repeated headers (archive 16): one row per position. Where the positions of a header
  disagree for a case, every position of that header is stored for that case, zeros included,
  with `conflict = true` and presence `uncertain`.
- The load stops if a column header no longer matches its registered mapping (schema drift).
- Idempotent; resumable; batches of 250,000 values.

`presence = present` says only that the source affirms the column. Whether a column is a
symptom, a history item or a risk factor is still unclassified (M2.7).

**Result** (final SQL cross-check, 2026-11-17):

| File | Rows stored | Value `1` | Zero side of a conflict | Conflict rows | Marked `absent` |
|---|---:|---:|---:|---:|---:|
| Archive 11 matrix | 2,852,472 | 2,852,472 | 0 | 0 | 0 |
| Archive 12 `data.csv` | 1,316,921 | 1,316,921 | 0 | 0 | 0 |
| Archive 15 `test.csv` | 2,093,631 | 2,093,631 | 0 | 0 | 0 |
| Archive 15 `train.csv` | 7,269,777 | 7,269,777 | 0 | 0 | 0 |
| Archive 16 matrix | 1,274,680 | 1,032,212 | 242,468 | 484,936 | 0 |
| **Total** | **14,807,481** | **14,565,013** | 242,468 | 484,936 | **0** |

- Value-`1` rows per file equal the non-zero cells counted while reading each file, and the
  total equals the independent read-only measurement (14,565,013).
- Archive 16: 37 headers have conflicts and the number of conflicting cases per header equals
  `data_audit/audit.json` for all 37; the six named in `docs/02` match exactly (vomiting
  22,272, cough 19,052, headache 18,996, nausea 18,946, back pain 18,588, fever 16,829).
- Database size is now 5,028 MB (`case_features` 3,299 MB).

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 34 files |
| `uv run pytest -m "not archives"` (SQLite) | 104 passed, 15 skipped |
| same on PostgreSQL | 119 passed |
| `uv run pytest tests/ingestion/test_features.py` on PostgreSQL | 4 passed |
| `uv run python -m feeltriva_ingestion verify` / `load` / `load-cases --files Healthcare.csv` (regression of the shared entry point) | all succeed; reruns insert 0 rows |
| `detect_changes` before commit | only `main` of the ingestion CLI among existing symbols |

The four new tests use a crafted matrix: an affirmed cell; a zero that must not appear; an
all-zero row; a repeated header that agrees; one that disagrees (both sides kept and
flagged); a blank; a non-binary value; a malformed row; rerun; schema drift; missing cases or
mappings.

**Bugs.**

- **BUG-005 — root cause found and fixed.** PostgreSQL restarted itself twice under load
  (first in M1.7, again here after 53 minutes of loading, followed by ten hours of log replay
  while the machine slept). The log shows the same sequence both times: a health probe's
  connection breaks, `untracked child process … exited with exit code 2`, then "terminating
  any other active server processes". *Cause:* the Compose health check ran `pg_isready`
  through a shell with a 3-second timeout. Under load the probe was slow, Docker killed the
  shell, and the orphaned `pg_isready` was adopted by process 1 in the container, which was
  PostgreSQL itself. PostgreSQL treats an unknown child that exits with a code other than 0 or
  1 as a crash and restarts the whole database; `pg_isready` exits with 2 when the server does
  not answer in time. *Resolution:* `init: true` (an init process is now process 1 and reaps
  orphans); health check in exec form with a 20-second timeout and 15-second interval.
  *Verified:* process 1 is `docker-init`; an orphan made to exit with code 2 inside the
  container left the postmaster start time unchanged; the remaining 10.7 million rows then
  loaded in one run with zero restarts. The earlier entry's guess of "resource starvation" was
  wrong as the cause: load only made the probe slow enough to trigger the defect.
- **BUG-011 — loader refused a file with a malformed row.** *Found by* the crafted test before
  any real data was loaded. *Cause:* the precondition compared the number of cases with the
  number of rows, but a malformed row is kept as a record without a case. *Resolution:* the
  precondition counts source records. *Verified:* the four tests pass.
- Timing: archive 16 loaded in 99 s; the other three files took an hour because the machine
  was short of memory (swap nearly full) with a cold database cache.

**Not done.** Symptom text and symptom lists (M1.9). Classification of each column's meaning
(M2.7). The `model_observations` view that turns "no row" into "zero with unknown meaning"
for training (M4.3). The real-archive load has no automated test (it needs the archives and
over an hour); the crafted tests cover the logic in CI.

### M1.9 — Symptom text and symptom lists; declared-count checks

**Handoff clauses applied** (checked before writing code):

- `docs/04`: archive 12 `symptom_text` → "parse symptom text into candidates; do not align row
  numbers to data.csv". Archive 14 `Symptoms` → "parse list/text safely; normalize terms into
  pending mappings". `Symptom_Count` → "data-quality comparison, not a diagnosis predictor".
  Archive 15 `SYMPTOM_COUNT` → "consistency check; do not treat … the count as ground truth".
- `docs/04` and `docs/02`: list-field terms "must be extracted separately and reviewed"; the
  positional crosswalk "excludes concepts that still need extraction from narrative/list fields".
- `docs/01` §3 rule 5: normalisation only as a candidate mapping. `docs/05` M1: "symptom-list
  adapter"; "quality flags for count mismatches".

**Measured first (read-only).** Archive 12 text: 192,715 rows, 1,081,459 items, 283 distinct
terms, 1 – 12 items per row. Archive 14: 25,000 rows, 125,036 items, 28 terms, 3 – 7 items per
row. In both: no empty list, no repeated item within a row, no separator other than a comma,
no spelling variants. All 283 archive-12 terms and 25 of archive 14's already exist as
lexical feature candidates from the matrix files.

**Impact analysis before editing.** `main` of the ingestion CLI (modified): LOW. `_flush` of
the feature loader (called only): LOW. `norm_label` (called only): **CRITICAL**, five direct
callers across every loader; reported to the owner and left unchanged. New: `lists.py`, a
test file.

**Implemented.** `pipelines/ingestion/feeltriva_ingestion/lists.py` and the command
`uv run python -m feeltriva_ingestion load-lists [--files …]`.

- Each distinct term becomes a list mapping: a `feature_mappings` row with no column position,
  the wording as written, `pending`, and "not listed means unknown" recorded on it.
- Term identity is the same lexical rule as for matrix columns, so a list term and a column
  with the same words share one candidate. A term matching nothing becomes a new pending
  candidate; an existing candidate is never modified.
- Each case gets one `case_features` row per listed term, presence `present`, wording as
  written. A term that is not listed gets no row and is never `absent`.
- The declared counts are compared with the parsed values; a mismatch or an empty list is
  flagged on the source record. The counts are not stored as features.

**Result** (loader output and SQL cross-check, 2026-11-17):

| File | Items in file | Rows stored | Terms | Reusing existing candidates | New candidates | Cases with items |
|---|---:|---:|---:|---:|---:|---:|
| Archive 12 `final_symptoms_to_disease.csv` | 1,081,459 | 1,081,459 | 283 | 283 | 0 | 192,715 |
| Archive 14 `Healthcare.csv` | 125,036 | 125,036 | 28 | 25 | 3 | 25,000 |
| **Total** | 1,206,495 | **1,206,495** | 311 mappings | | | |

- The three new candidates are "appetite loss", "swelling" and "tremors", all `pending`.
- Features: 968 (961 lexical candidates + 7 fixture concepts); none approved. Feature mappings:
  1,962 (1,651 columns + 311 list terms).
- No row is marked `absent`.
- Declared counts: archive 14 `Symptom_Count` equals the parsed list in all 25,000 rows;
  archive 15 `SYMPTOM_COUNT` equals the number of affirmed `E_*` columns in all 610,031 rows.
  0 mismatches, 0 flags added.
- Example of the lexical link: the candidate for "shortness of breath" is now reached from
  archive 11 (`symptom_shortness_of_breath`), archive 12 `data.csv` (`shortness_of_breath`),
  archive 12 text, archive 14 and archive 16 (two column positions).
- `case_features` now holds 16,013,976 rows (14,807,481 + 1,206,495). Load time 745 s.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 35 files |
| `uv run pytest -m "not archives"` (SQLite) | 104 passed, 21 skipped |
| same on PostgreSQL | 125 passed |
| `uv run pytest tests/ingestion/test_lists.py` on PostgreSQL | 6 passed |
| `verify` and `load` re-run (shared entry point) | succeed; 0 rows inserted |
| `detect_changes` before commit | only `main` of the ingestion CLI among existing symbols |

The six new tests use crafted archives: comma splitting; differing case and spacing linked to
an existing candidate without changing it; a new term; the same term twice in one list; an
empty list; a wrong declared count; a malformed row; the matrix declared-count check; rerun;
missing cases.

**Bugs.** None.

**Not done.** Whether each term is a symptom, sign or something else (M2.7). The original list
text is reachable through the row locator in the archive, not copied into the database; the
archives themselves are not yet in object storage (M1.12).

### M1.10 — Narrative text files as pending, searchable knowledge chunks

**Handoff clauses applied** (checked before writing code):

- `docs/04`: archive 13 text files → "source_records; statements/evidence_chunks after review.
  Preserve text, URL, extraction version, character offsets and attribution". `category` →
  "preserve original; do not trust as an approved taxonomy". `word_count` → "a source
  attribute, not an evidence score".
- `docs/01` §6: "chunk along clinical section boundaries … text offsets … maintain parent
  document links"; raw dataset text kept apart from reviewed clinical references.
- `specs/schema.sql`: `evidence_chunks` requires a knowledge release and a record or
  statement; `search_vector` with a GIN index. `docs/05` M2: pending content cannot be served.

**Measured first (read-only).** All 85 files start with a `Disease` / `Category` / `URL`
header that agrees exactly with `diseases_main.csv`; file names map one-to-one to disease
names. Bodies use wiki-style headings (3,143 in total, 8 to 69 per file, four levels). The
`word_count` column equals the number of words in the body for all 85 files. Total 3,881,305
characters; one paragraph in four is longer than 1,500 characters.

**Impact analysis before editing.** `main` of the ingestion CLI (modified): LOW. `verify_all`
(called only): **CRITICAL**, six direct callers. `disease_candidate_id` and `source_id`
(called only): HIGH. All three reported to the owner and left unchanged. New: `chunks.py`, a
test file. No migration: the table and its search index exist since `0001`.

**Implemented.** `pipelines/ingestion/feeltriva_ingestion/chunks.py` and two commands:
`load-chunks` and `search-text "<words>"`.

- A chunk is a run of whole paragraphs inside one section, at most 2,000 characters; a longer
  paragraph is cut at sentence ends. Heading lines are metadata (the section path), not chunk
  text. Offsets are character positions in the file as stored, so the slice of the file at
  `[char_start, char_end)` is exactly the chunk.
- Each chunk records: file, document SHA-256, extraction version `sections-1`, offsets, section
  path and level, the disease label with its lexical candidate ID and native ID, the source
  URL, the category as supplied under the name `source_category_unreviewed`, declared and
  measured word counts, and whether the section is a reference list.
- All chunks belong to knowledge release `knowledge-import-0`, status `pending`, with a
  full-text vector (`english`). The load refuses a file whose digest differs from the manifest.
- The disease table's 85 records are flagged `source_category_unreviewed`, and `word_count` is
  recorded beside each description statement.
- `search-text` is a review tool: it searches pending text on purpose, says so in its output,
  and hides reference-list sections by default. Nothing in the patient-facing service reads
  `evidence_chunks`.

**Result** (2026-11-17):

| Measure | Value |
|---|---:|
| Files chunked | 85 of 85 |
| Chunks | 3,651 (12 to 75 per file) |
| Characters in chunks | 3,771,105 |
| Body characters in no chunk | 0 |
| Longest chunk | 2,000 characters |
| Chunks in reference-list sections | 123 |
| Chunks with a search vector | 3,651 |
| Knowledge releases not `pending` | 0 |
| Header, digest or word-count mismatches | 0 |

- Independent check: every one of the 3,651 stored chunks was re-read from the original
  archive using its stored offsets; all 3,651 were identical.
- Search check: `search-text "night cough wheezing"` returns asthma, section "Signs and
  symptoms", with the release shown as pending.
- The category anomaly named in the handoff is preserved, not corrected: asthma's chunks carry
  `source_category_unreviewed = "Mental Health"`.
- Load takes 9 seconds; a rerun inserts and flags nothing.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 36 files |
| `uv run pytest -m "not archives"` (SQLite) | 107 passed, 23 skipped |
| same on PostgreSQL | 130 passed |
| `uv run pytest tests/ingestion/test_chunks.py` on PostgreSQL, with archives | 6 passed |
| `verify` and `load` re-run (shared entry point) | succeed; 0 rows inserted |
| `detect_changes` before commit | only `main` of the ingestion CLI among existing symbols |

The six new tests: section paths and sibling headings; offsets reproduce the text with Windows
line endings; a long paragraph cut at sentence ends; empty sections; reference lists marked;
a file without the header refused; all 85 real files fully covered; storage as pending with
search vectors; search hides reference lists unless asked; rerun; a tampered file and missing
records refused.

**Bugs.** None in the application. One lint finding in a new test (`zip` without `strict`),
fixed before commit.

**Not done.** The chunks are not reviewed and not split into atomic claims (M2.6). No
embeddings and no approved-release filter for serving (M5.2). The review search exists as a
command, not yet as a screen or API endpoint (M2.4).

### M1.11 — Proposed disease–feature evidence

**Handoff clauses applied** (checked before writing code):

- `docs/04`: archive 13 `symptoms.csv` → "proposed disease_feature_evidence: narrative claim
  first; extract atomic feature relations into review queue". Relationships: "Disease ↔
  feature evidence … with source record or statement provenance".
- `figures/data-relationships.png`: "These are different relationships; co-occurrence alone
  is not clinical proof."
- `docs/04` exports: "source-stratified occurrence counts may be produced with denominators and
  unknowns, clearly identified as sample counts. Dataset composition, synthetic sampling and
  duplicates can dominate those proportions." `docs/01` and `CLAUDE.md`: never call dataset
  frequencies prevalence. `docs/01` §5: no information gain manufactured from unvalidated counts.
- `specs/schema.sql`: every row needs a statement or a record; `frequency` between 0 and 1
  with `frequency_denominator`.

**Measured first (read-only).** 712 archive-13 symptom statements (82 diseases, 88,022
characters); 961 lexical feature candidates, of which 223 are archive-15 questionnaire items
that never occur in prose. Predicted: 586 mentions, 575 statement–feature pairs, 468 distinct
disease–feature pairs; 1,961 source–disease combinations for the counts.

**Impact analysis before editing.**

| Symbol | Action | Risk | Callers |
|---|---|---|---|
| `main` (ingestion CLI) | modified: `load-evidence` | LOW | 1 |
| `summarise` (cases.py) | modified: count row-level records only | LOW | `load_cases` |
| `_load_file` (features.py) | modified: same clause in its precondition | LOW | `load_case_features` |
| `_require_loaded` (lists.py) | modified: same clause | **HIGH** | `_load_list_file`, `check_declared_counts` |

The HIGH result was reported to the owner before editing with the plan for both callers. The
change was needed because a co-occurrence count comes from a whole file, the schema requires a
record as provenance, and the new whole-file record must not be counted as a data row.
`detect_changes` before commit listed exactly these four functions.

**Implemented.** `pipelines/ingestion/feeltriva_ingestion/evidence.py` and the command
`uv run python -m feeltriva_ingestion load-evidence`. Two kinds of proposal, kept apart:

- `narrative_lexical_mention` — a known feature term occurs in a symptom statement about a
  disease. Whole phrases only, case-insensitive, the longest term wins (so "chest pain" does
  not also propose "pain" for the same words). Provenance is the statement; the text span, the
  matched wording, the number of mentions and whether a negation cue appears earlier in the
  same sentence are stored. A mention is recorded as a mention, not as "the disease has it".
- `dataset_cooccurrence` — within one source file, the number of cases with a disease label
  that also have the feature affirmed, with the number of cases with that label as the
  denominator. Stored beside it: the distinct profiles and the exact-duplicate rows behind the
  denominator, the cases with conflicting column values, and explicit markers that it is a
  sample count, not prevalence, and that sources are not pooled. Provenance is a whole-file
  record of that source. A feature reached through several columns of one file is counted once
  per case. Pairs that never occur get no row.

Everything is `pending`. Nothing is served and nothing is used for ranking.

**Result** (2026-11-17, 783 s):

| Kind | Rows | Distinct disease–feature pairs | Not pending | Without provenance |
|---|---:|---:|---:|---:|
| Narrative mentions | 575 | 468 | 0 | 0 |
| Per-source co-occurrence | 21,484 | 14,010 | 0 | 0 |
| **Total** | **22,059** | | 0 | 0 |

| Source file | Pairs | Sum of "cases with feature" | Affirmed feature rows (independent count) |
|---|---:|---:|---:|
| Archive 11 matrix | 6,310 | 2,852,472 | 2,852,472 |
| Archive 12 `data.csv` | 5,321 | 1,316,921 | 1,316,921 |
| Archive 12 symptom text | 2,627 | 1,081,459 | 1,081,459 |
| Archive 14 lists | 840 | 125,036 | 125,036 |
| Archive 15 `test.csv` | 881 | 2,093,631 | 2,093,631 |
| Archive 15 `train.csv` | 882 | 7,269,777 | 7,269,777 |
| Archive 16 matrix | 4,623 | 789,744 | 789,744 |

- For every file the co-occurrence counts add up exactly to the affirmed feature rows loaded in
  M1.8 and M1.9, counted by a separate query with no label join.
- Direct check of one pair: in archive 14, 164 of the 858 cases labelled "allergy" have
  "fever" affirmed (counted row by row); the stored proposal says 164 of 858.
- Narrative: 283 of the 712 statements mention at least one known term; the measurement was
  reproduced exactly (586 mentions, 575 proposals, 468 pairs). Most proposed: fever 37,
  vomiting 24, weight loss 21, nausea 20, fatigue 20.
- The same disease–feature pair appears once per source where it occurs (21,484 rows for
  14,010 pairs); the sources are never added together.
- New data facts: in archive 16, 114 columns share a lexical feature with another column of
  the same file (the 74 repeated-header columns plus 40 whose different header strings
  normalise to the same term); 1,636 pairs were recounted per distinct case. No archive-16
  case has the same feature affirmed in two columns without a conflict.

**Limits to read with these numbers.**

- The negation flag only says a cue such as "no", "not" or "without" occurs earlier in the
  sentence. It fired for 11 proposals, including "Without treatment, symptoms – particularly
  the fever – can …", where fever is not negated. It is a hint for the reviewer, not a
  judgement.
- A mention under a disease is not a claim that the disease causes the feature.
- The co-occurrence shares describe the files. With unreviewed sampling and duplicates they say
  nothing reliable about real frequency; archive 12 `data.csv` alone has 57,305 duplicate rows.
- Feature meaning is still unclassified, so a "feature" may be a history or risk question
  (archive 15), not a symptom.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 37 files |
| `uv run pytest -m "not archives"` (SQLite) | 109 passed, 27 skipped |
| same on PostgreSQL | 136 passed |
| `uv run pytest tests/ingestion/test_evidence.py` on PostgreSQL | 6 passed |
| `load-cases --files Healthcare.csv` on real data, with a whole-file record present | 25,000 records, "matches manifest" |
| `detect_changes` before commit | the four declared functions only |

The six new tests: longest term wins and whole words only; negation cue per sentence;
co-occurrence with a repeated column, a conflict and an exact duplicate (0.75, 0.5 and 1.0
with denominators 4, 4 and 1); narrative proposals tied to the symptom statement only, with
spans; rerun inserts nothing and the three modified loaders still accept the file; every row
pending with provenance.

**Bugs.**

- **BUG-012 — shared memory.** The first real run failed after 1 min 49 s with
  `could not resize shared memory segment … No space left on device (parallel worker)`. It ran
  in one transaction, so nothing was written and the server did not restart. *Cause:* Docker
  gives a container 64 MB of `/dev/shm` by default; PostgreSQL parallel queries build their
  shared hash tables there. *Resolution:* `shm_size: "2gb"` on the PostgreSQL service.
  *Verified:* `/dev/shm` reports 2.0 G; the same run then completed in 783 s.
- Test-only: one new test hard-coded a character position that I had counted wrong (53
  instead of 54); the code was right. The test now computes the position.

**Not done.** Proposals are not reviewed and not split into atomic claims (M2.6). No approved
view of edges (M2.9). Mentions were extracted from archive 13's symptom statements only, as
the mapping table specifies; descriptions, causes and the 3,651 text chunks were not scanned.

### M1.12 — Raw archives in private object storage

**Handoff clauses applied** (checked before writing code):

- `docs/01` §4: four storage zones, the first being "raw immutable objects".
- `docs/01` §6: "Object storage: S3-compatible private buckets, versioning and encrypted
  backups. Raw ZIPs, manifests, model artifacts; no public medical files."
- `docs/04`: every file → "retain the original byte object". `docs/03`: "keep artifacts/data
  outside tracked source; store URI/checksum manifests in the repo". `docs/05` M0: Compose
  with "private object storage"; M1: "register immutable source versions".

**Checked before designing.** The Compose file from M0.3 named `minio/minio`. Pulling it
failed: "repository does not exist". It is not on Quay either. Images that can be pulled
today: SeaweedFS, Garage, versitygw, RustFS. versitygw v1.11.0 (built 2026-11-06, 35 MB) was
read from its own `--help` output and then proven in a throwaway container with real
requests: versioning could be enabled; two writes to one key kept two versions and the first
came back byte-identical; anonymous requests and a wrong secret returned 403; the only access
grant was the owner's. The probe container and its volumes were removed afterwards.

**Impact analysis before editing.** `main` of the ingestion CLI (modified): LOW.
`sha256_file` and `verify_all` (called only): **CRITICAL**; reported to the owner and left
unchanged. Not covered by the code graph: `infra/docker-compose.yml`, `pyproject.toml` /
`uv.lock` (new dependency `boto3` 1.44.4), a new migration, `.env.example`.

**Implemented.**

- `infra/docker-compose.yml`: the `objectstore` service is now versitygw, pinned by digest,
  on `127.0.0.1:9010`, with a data volume and a versions volume and a health check. Start it
  with `docker compose -f infra/docker-compose.yml --profile storage up -d objectstore`.
- Migration `0005`: table `source_archives` (archive name, SHA-256, size, bucket, key, version,
  URI, stored and verified times). The API's database role has no access to it.
- `pipelines/ingestion/feeltriva_ingestion/objectstore.py` and the command
  `uv run python -m feeltriva_ingestion store-archives`. It checks the local files against
  the manifest first; creates the bucket and turns versioning on; stores each archive under a
  key that contains its SHA-256; refuses to overwrite a key that holds other bytes; downloads
  every stored archive again and hashes it; requests each object with no credentials and
  fails if that succeeds; stores a copy of the ingestion manifest; registers each archive.
- Source records keep their logical locator (`zip://<archive>#<member>:row=N`); the registry
  maps the archive name to the stored object, so 1.37 million rows did not need rewriting.

**Result** (2026-11-17, 2 s):

| Archive | Bytes | Stored and re-read | Anonymous request |
|---|---:|---|---|
| `archive(11).zip` | 2,400,742 | verified | HTTP 403 |
| `archive(12).zip` | 3,927,259 | verified | HTTP 403 |
| `archive(13).zip` | 1,544,071 | verified | HTTP 403 |
| `archive(14).zip` | 373,982 | verified | HTTP 403 |
| `archive(15).zip` | 17,195,290 | verified | HTTP 403 |
| `archive(16).zip` | 2,925,505 | verified | HTTP 403 |
| **Total** | **28,366,849** | 6 of 6 | |

- Independent check that uses none of this code: `sha256sum` run inside the storage container
  on the six stored files gives exactly the six digests of `specs/ingestion_manifest.json`.
- A rerun reports "already stored" for all six with the same version IDs and uploads nothing.
- Bucket versioning is `Enabled`; an anonymous listing of the bucket returns 403.
- The registry holds 6 rows, all with a verification time; `feeltriva_app` cannot read it.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 38 files |
| `uv run pytest -m "not archives"` (SQLite) | 114 passed, 28 skipped |
| same on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT` set | 142 passed |
| `uv run pytest tests/ingestion/test_objectstore.py` with the real store | 6 passed |
| Migration `upgrade head` → `downgrade base` → `upgrade head` on a scratch database | 29 tables → 0 → 29; main database untouched |
| `verify` and `search-text` re-run (shared entry point) | succeed |
| `detect_changes` before commit | only `main` of the ingestion CLI among existing symbols |

The six tests: content-addressed keys; bucket creation with versioning; store, confirm
without re-upload, refuse to overwrite other content, reject altered bytes on read-back;
what an unauthenticated client receives; missing configuration refused; and against the real
store: byte-for-byte retrieval, a rerun writing no new version, tampering from outside the
loader detected while versioning still holds the original, and the registry row.

**Bugs.**

- **BUG-013 — unusable image in Compose.** The object store service written in M0.3 was
  never started, and its image no longer exists. *Found by* pulling it at the start of this
  sub-step. *Resolution:* replaced by versitygw (decision E48). *Lesson recorded:* a service
  that has never been started is not delivered; M0.3's log entry had said so, but the plan
  row was marked Done.
- **BUG-014 — command not registered.** The first real run printed "invalid choice:
  'store-archives'": my edit to the list of commands had not matched because the formatter
  had re-wrapped that list. Nothing ran. *Resolution:* added the entry; *verified* by the
  real run above.
- Process slip, no effect on data: my first migration round-trip command never created the
  scratch database because of a shell quoting error, so that run proved nothing. It was
  repeated correctly; the result above is from the repeat.

**Not done.** No backups of the object store and no encryption at rest (deployment, M0.10 and
M6.4). The object store is not part of CI: the unit tests run there with an in-memory
stand-in, and the real-store test runs locally. The Redis service in the same Compose file is
still unstarted and unverified.


### M1.13 — Ingestion completeness check; loaders refuse changed columns

**Handoff clauses applied** (checked before writing code):

- `docs/04`, "Source fields and exact target mapping": 27 rows, traced as T1 – T27 in
  `TRACEABILITY.md`. The check walks all of them.
- `docs/05` M1: "build quality flags for count mismatches, invalid joins and schema changes";
  acceptance: "all 12 CSVs and 85 text files accounted for; counts and duplicate findings
  reproduce; repeated runs are idempotent; archive-16 conflicts are retained; original
  archive-15 split is recorded and flagged".
- `docs/01` §8, ingestion tests: "... idempotent rerun, schema drift".
- Project rules: an imported zero is never stored as "absent"; case IDs are never merged across
  archives or splits; nothing is approved without a reviewer; counts are sample counts of
  rows, never prevalence.

**Impact analysis before editing.**

| Symbol | Action | Risk | Direct callers |
|---|---|---|---|
| `main` (ingestion CLI) | modified: new `completeness` command | LOW | 1 |
| `load_cases`, `load_symptom_lists`, `load_reference` | modified: layout pre-flight | LOW each | `main` |
| `_load_file` (cases), `_load_list_file` | analysed, then left unchanged | LOW | their loader |
| `read_csv_positional` | called only | **CRITICAL** (6 direct callers) | reported to the owner; unchanged |
| `_raw_cursor` | called only | **CRITICAL** (14 direct callers) | reported to the owner; unchanged |
| `test_reference_load_is_idempotent_and_everything_is_pending` | modified (BUG-015) | LOW | none |

**Implemented.**

- `uv run python -m feeltriva_ingestion completeness` (modules `completeness.py`,
  `completeness_rows.py`, `completeness_cases.py`, `verify_files.py`, each below the 32 KB
  limit of the code graph). It runs in a READ ONLY transaction.
- The rows of the mapping table are read from `docs/04_DATA_MAPPING.md` at run time. If the
  table no longer has the 27 rows the check was written for, that is reported. A row with no
  check is reported as a mismatch.
- Where the expected value comes from is printed on every line: the manifest, `audit.json`,
  the crosswalk files, a number stated in the mapping table (377, 223 and 654 positions), a
  rule (for example "0 values marked absent"), or the source file itself.
- "The file itself" means an independent recount. Each of the 12 CSV files is read once from
  its archive and, in the same pass, the stored rows are streamed from the database in row
  order and compared one by one: content hash, row locator, split, patient ID, age,
  demographic field and value, label and its lexical candidate, cluster ID. Feature values
  are counted per column from the file and compared with one grouped query over
  `case_features` (16 million rows, about two minutes). List items are compared per term.
  Statements are compared row by row with their text, type, disease, URL and attribution
  fields. Every stored chunk must equal the text of its file at the stored offsets. The
  co-occurrence proposals are recounted from the files per label and feature and compared
  pair by pair, with their denominators and frequencies.
- The recount does not reuse the loaders' counting code. It does use their ID and hash
  functions, because those define what "the same row" and "the same profile" mean.
- Work that the mapping table asks for but a later sub-step owns is printed as `later` with
  that sub-step. It is never counted as passed (decision E49).
- Every loader that reads columns now refuses a file whose columns changed, before writing
  anything (`require_layout` in `archives.py`; decision E50).

**Result of the real run** (2026-11-17, 7 min 38 s; 5 min 35 s when nothing else uses the database, exit status 0):
235 checks: **228 ok, 0 mismatches, 7 `later`**. The full output is written to
`data/derived/ingestion_completeness.txt` (not in Git). Headline values, expected = loaded:

| Row(s) | What was compared | Value |
|---|---|---:|
| T1 | Archives registered, and their stored bytes re-read from the object store | 6 / 6 |
| T1 | Source versions with the file's SHA-256 | 13 |
| T1 | Row records in 12 CSV files; every file's exact-unique row count equals the manifest | 1,368,315 |
| T1 | Rows whose stored content hash differs from the file | 0 |
| T1 | Columns with a target (feature mapping or named field) | 1,693 |
| T2, T4, T6, T20, T21, T24 | Cases whose label and lexical candidate equal the file | 1,365,363 |
| T3 | Archive 11 feature values (174 positions) | 2,852,472 |
| T5 | Archive 12 `data.csv` feature values (377 positions) | 1,316,921 |
| T6 | Archive 12 listed items (283 terms) | 1,081,459 |
| T7 – T10 | Archive 13 disease table: native IDs, categories, summaries, word counts, URLs | 85 each |
| T11 – T13 | Cause / symptom / treatment statements, each joined by native ID | 714 / 712 / 621 |
| T12 | Proposals where a feature term is mentioned in a symptom statement | 575 |
| T13 | Evidence proposals derived from a treatment statement | 0 |
| T14 | Text files; chunks; chunks whose offsets reproduce their text | 85; 3,651; 3,651 |
| T15 – T17 | Archive 14 patient IDs, ages, gender values equal to the file | 25,000 each |
| T17 | Gender value counts (sample counts) | Female 8,336, Male 8,271, Other 8,393 |
| T18 | Archive 14 listed items (28 terms) | 125,036 |
| T19, T23 | Rows whose declared symptom count differs from the parsed values | 0 |
| T21 | Archive 15 cases with ID, age, sex, label and split equal to the file | 134,529 + 475,502 |
| T21 | Profiles (label included) present in both original splits | 27,622 |
| T21 | Rows flagged as sharing a profile across the split | 85,357 |
| T22 | Archive 15 feature values (223 positions per file; `test.csv` + `train.csv`) | 2,093,631 + 7,269,777 |
| T25 | Archive 16 feature values (654 positions), conflicts included | 1,274,680 |
| T25 | Repeated headings; conflict rows stored | 37; 484,936 |
| T26, T27 | Archive 16 descriptions; `Source`, `Source_URL`, `Retrieved_Date`, `Canonical_Query` retained | 820 each |
| M1 acceptance | Repeated profiles over the case files; files equal to the audit | 166,259; 7 of 7 |
| M1 acceptance | Rows in exact-duplicate groups marked on the case | 146,966 |
| M1 acceptance | Lexical disease candidates; archive pairs with the audit's overlap | 960; 15 of 15 |
| M1 acceptance | Co-occurrence proposals; proposals differing from the files | 21,484; 0 |
| M1 acceptance | Feature values attached to a case of another source file | 0 |
| M1 acceptance | Imported items already marked approved | 0 |

The seven `later` lines:

| Row | Left to a later sub-step | Now | Sub-step |
|---|---|---|---|
| T12 | Statements split into atomic, reviewable feature relations | not started | M2.6 |
| T14 | Statements extracted from the text files after review | 0 statements | M2.6 |
| T16 | Age unit confirmed (archive 14) | not confirmed; unit left empty | M2.7 |
| T21 | Age unit confirmed (archive 15 `test.csv`, `train.csv`): 2 lines | not confirmed; unit left empty | M2.7 |
| T22 | Feature positions classified as symptom, history, risk, measurement or other (`test.csv`, `train.csv`): 2 lines | 0 of 223 | M2.7 |

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 42 files |
| `uv run pytest -m "not archives"` (SQLite) | 121 passed, 38 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 165 passed |
| same with `-m "not archives"` | 159 passed |
| `uv run pytest tests/ingestion/test_completeness.py tests/ingestion/test_schema_drift.py` | 19 passed |
| `uv run python -m feeltriva_ingestion completeness` | exit 0; 228 ok, 0 mismatches, 7 later (three runs, same result) |
| `detect_changes` before commit | `main`, `load_cases`, `load_symptom_lists`, `load_reference`, one test; new files |

What the 19 new tests prove:

- The check walks the 27 rows of the handoff table; a renamed or removed row is reported.
- Crafted archives loaded by the real loaders pass. Then the stored data is damaged inside a
  transaction that is rolled back, and the check must report it. 28 kinds of damage to case
  data are each reported (a changed patient ID, age, gender, label, split, content hash; a
  renumbered record; a deleted feature value; a value marked absent; a conflict flag removed;
  a mapping marked approved; a renamed heading; a feature value attached to a case of another
  file; removed quality flags; a changed cluster ID or duplicate status; a changed or deleted
  co-occurrence proposal; a deleted label mapping; a label origin that is not "unknown").
  Five kinds of damage to narrative statements and two to text chunks are reported as well.
- A crafted file that stands in for archive 15 has 3 feature positions; the check holds it to
  the 223 the mapping table states and reports the difference.
- Changed columns: the case loader refuses an added column, a removed column and a renamed
  label column; the list loader refuses a file without its list column; the reference loader
  refuses a real file whose registered layout differs. In each case nothing is written.

**Bugs.**

- **BUG-015 — a failing test that nobody ran.** `test_reference_load_is_idempotent_and_
  everything_is_pending` counted rows by ID prefix (`src_`, `rec_`, ...). The crafted tests
  added since M1.7 create rows with the same prefixes in the persistent test database (375
  sources where the test expected 13). *Found by* running the PostgreSQL suite without
  `-m "not archives"` in this sub-step. *Cause of the delay:* from M1.7 to M1.12 I ran, and gave
  the owner, the PostgreSQL command with `-m "not archives"`, which skips this test; CI has no
  archives, so it skips it too. The M1.8 – M1.12 entries above say "142 passed" and similar for
  that filtered run only. *Resolution:* the test now counts only rows that belong to the 13
  sources the loader registers. *Process change:* `CLAUDE.md` now requires the unfiltered
  PostgreSQL run in every sub-step. *Verified:* 165 passed, real archives included.
- **BUG-016 — loaders accepted or crashed on changed columns.** *Found by* writing the drift
  test the handoff asks for. A case file with an extra column was loaded by `load-cases` (only
  `load-features` refused it later, leaving cases without features). A file without its label
  or list column stopped with a bare `StopIteration`, and the reference loader with a
  `KeyError`. No real file is affected: all 12 have their registered columns (T1 above).
  *Resolution:* `require_layout` compares the number of columns with the manifest and looks for
  the columns each loader reads by name, before anything is written; the CLI prints the message
  and exits with status 2. *Verified* by `tests/ingestion/test_schema_drift.py`.
- Slips during development, none committed: the first version of `completeness_rows.py` was
  32.6 KB, above the size the code graph can parse, and was split in two; one test expected a
  crafted file to pass a line that correctly failed (the 223 positions above).

**Tool limit found.** `detect_changes` first listed `read_csv_positional`, `_h` and `source_id`
as touched and rated the change critical. Their bodies were identical to the last commit
(compared as syntax trees): I had inserted new code above them, and the tool maps the diff to
the line ranges of the old index. I moved the new code to the end of the file; the second
`detect_changes` listed only the intended symbols. Recorded in `CLAUDE.md` under the known
limits of the graph.

**Corrections to the plan and the trace.**

- **A requirement without a sub-step.** T16 says the age unit must be confirmed before clinical
  use. Nothing in the plan owned that. It is now part of M2.7.
- **Three rows moved from Done to Partial** in `TRACEABILITY.md`: T12 (atomic feature relations,
  M2.6), T14 (statements from the text files and the review itself, M2.6 and M2.5) and T16 (age
  unit, M2.7). I had marked them Done with a note about what was left; a row with work left is
  Partial. Two requirements were completed by this sub-step (the ingestion test layer and the
  M1 acceptance criteria). Net: 90 done (was 91), 63 partial (was 62).

**Not done, and limits.**

- Idempotent reruns are not checked by the command, because it is read-only. Each loader's
  tests rerun it and expect no change.
- Two expected values are recomputed with the same code the loader used, not independently:
  the number of chunks (re-chunking the files) and the 575 narrative mentions (the same phrase
  matcher over the stored statements). What is independent for the chunks is that each stored
  offset reproduces its text from the file.
- The full command is not part of CI: it needs the six archives and the loaded database.
  CI runs the parts that need neither (7 tests); the damage tests need PostgreSQL and run
  locally.
- A full run takes about six minutes, eight when other work uses the database.
- The check says the data is loaded as the mapping table requires. It says nothing about
  clinical correctness: every mapping, statement, chunk and proposal is still `pending`.

**Committed and indexed.** Code and documents committed as `1a104cc` and pushed; CI passed on
both jobs (backend, web). The code graph was re-indexed at `1a104cc`: 4,713 nodes, 9,519 edges,
272 flows, status up-to-date. This paragraph was added in a following documents-only commit,
after which the index was refreshed again.

### M2.7 — Feature meanings derived from the data

**Handoff clauses and owner decisions applied** (checked before writing code):

- `docs/01` §4: "E_* questions must be classified by clinical meaning. Do not treat a history
  question as an active symptom." "A blank matrix value, an imported zero and an explicit denial
  are different concepts. Never infer absence from silence."
- `docs/01` §3: archive 15's "feature dictionary distinguishes symptoms, history and risk factors".
- `docs/02`: the baseline read a zero as a negative "for this experiment only"; next step
  "verify zero semantics".
- `docs/04`: T22 "classify symptom/history/risk/measurement/other"; T16 "confirm unit from source
  documentation before clinical use"; T5 "zero semantics unresolved".
- Owner decisions E34 (derive meanings from the supplied data) and E41 (list what the data
  cannot settle).

**Impact analysis before editing.**

| Symbol | Action | Risk |
|---|---|---|
| `main` (ingestion CLI) | modified: new `derive-meanings` command | LOW |
| `_features` (completeness check) | modified: one line and one label | LOW |
| `case_file_rows`, `_reference` (completeness check) | **HIGH**; reported to the owner and **not modified** | unchanged |
| `read_csv_positional`, `_raw_cursor` | called only | CRITICAL, unchanged |

**What the files themselves show** (measured before designing; counts are rows in files):

- **Archive 12 holds the same cases twice.** All 192,715 rows of `final_symptoms_to_disease.csv`
  (254 labels) exist one for one in `data.csv` with the same label and the same set of affirmed
  terms. The list file can only name what is affirmed, so a zero in `data.csv` is a term that
  was not listed. The two files must count as one set of cases when data is split (M4.3).
- **15 archive-15 columns are not yes/no answers.** `E_204` (travel) is 1 in all 610,031 rows.
  Six pain-detail columns (`E_54` – `E_59`) are 1 in exactly the same 476,586 rows, which is
  6,235 more rows than the yes/no question "do you have pain somewhere" (`E_53`). Six rash
  columns are 1 in the same 119,013 rows. For these a 1 says only that an answer was recorded;
  the answer itself is not in the file.
- **The archive-15 question text is cut off in the file** after about five words
  ("have you ever had a"). The full question list was not supplied.
- **Ages are whole numbers**, 1 to 90 in archive 14 and 0 to 109 in archive 15.
- Archive 16: 48 columns are never affirmed; its columns do not split into separate blocks.

**Implemented.**

- `meanings.py`: the rules, with no file or database access. Kind: an ordered list of eight
  wording rules (relatives, exposure or lifestyle, a body measure, the past, a known condition,
  treatment, then three symptom rules), a rule for a question that names a term which at least
  two other archives present as a symptom, and the source's own statement (a `symptom_` column
  prefix, a `Symptoms` list column, a file named for symptoms). "Do you have ..." alone settles
  nothing, because it also introduces diagnoses. Zero: five evidence rules; none can yield a
  denial. Age unit: proposed only when whole numbers span a human lifetime.
- `meanings_load.py` and the command `uv run python -m feeltriva_ingestion derive-meanings`
  (about 20 s). One pass over each case file. Proposals are stored on the mapping
  (`transformation.meaning`, `zero_semantics`), the kind on the feature, the age range with the
  proposed unit on the source (`population`). Every status stays `pending`. Rows a reviewer has
  already decided are left alone. `dataset_cases.age_unit` is not written.
- The existing review API already returns `zero_semantics` and the whole `transformation` for
  each feature mapping, so a reviewer sees every proposal without an API change.
- Generated review files: `docs/review/feature_meanings.md` (summary, the non-yes/no columns,
  the age unit, the undecided list) and `docs/review/feature_meaning_proposals.csv` (all 1,962).
- Completeness check: the line about zero meanings now checks "pending, and never a denial";
  the two `later` lines now name what is actually left (the owner's review and approval).

**Result of the real run** (2026-11-17, 22 s; a second run changed 0 rows):

| File | symptom | history | exposure or lifestyle | measurement | undecided |
|---|---:|---:|---:|---:|---:|
| 11 (174 columns) | 174 | 0 | 0 | 0 | 0 |
| 12 `data.csv` (377) | 374 | 0 | 3 | 0 | 0 |
| 12 list file (283 terms) | 280 | 0 | 3 | 0 | 0 |
| 14 list file (28 terms) | 28 | 0 | 0 | 0 | 0 |
| 15 `test.csv` and `train.csv` (223 each) | 74 | 72 | 25 | 1 | **51** |
| 16 (654) | 645 | 2 | 7 | 0 | 0 |

| Meaning of zero | Mappings |
|---|---:|
| not recorded (list terms, and `data.csv`, whose cases exist as lists) | 688 |
| no answer recorded (the 15 non-yes/no columns, in two files) | 30 |
| no evidence either way (archives 11, 16 and the other archive-15 columns) | 1,244 |
| a denial | 0 |

1,962 mappings carry a proposal with a basis; 910 of 961 feature candidates got a kind and 51
stay `other`; 0 items are approved. Age unit proposed: years, for both age columns.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run mypy packages services pipelines` | no issues in 44 files |
| `uv run pytest -m "not archives"` (SQLite) | 155 passed, 40 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 201 passed |
| `uv run pytest tests/unit/test_meaning_rules.py tests/ingestion/test_meanings.py` | 36 passed |
| `uv run python -m feeltriva_ingestion derive-meanings`, twice | first run 1,962 mappings changed; second run 0 |
| `uv run python -m feeltriva_ingestion completeness` | exit 0; 235 checks, 228 ok, 0 mismatches, 7 later (10 min 38 s while tests ran) |
| `detect_changes` before commit | `main`, `_features`, one test; `roles_of` listed but identical to the last commit (code added above it) |

What the 36 tests prove: 26 real headings classify as intended, including every kind of history
question; a cut-off question is reported as cut off; a term is a symptom only when its source
says so; wording overrides a source that calls everything a symptom; no rule before the symptom
rules can propose a symptom and none proposes a sign; no combination of evidence makes a zero
a denial; the age unit is proposed only for a range that singles it out; two files count as the
same cases only when every case matches. On crafted archives in PostgreSQL: proposals are
stored pending with their basis, the unit is not written to cases, a rerun changes nothing,
and a reviewer's decision on a mapping or a feature is never overwritten.

**Bugs.** None in committed code. Slips during development, caught by running: the first rule
draft read "exercise dyspnea" as a habit and "do you ever temporarily stop" as the past, and
matched "have you had a cold" to a symptom through a term only one archive uses; all three
were corrected and are covered by tests. Two test files had the same name in different folders,
which stops pytest; one was renamed.

**Limits, stated plainly.**

- The kinds are a reading of headings by rules I wrote. They are proposals, not clinical facts.
  The rules catch wording; they do not know medicine. For example "obesity" and "recent
  pregnancy" in archive 16 stay symptoms because their source calls them symptoms and their
  wording has no marker.
- 51 archive-15 headings are undecided, most because the question is cut off in the file.
- For 1,244 columns the data cannot say what a zero means. The owner's decision D-Z1 covers it.
- The value-pattern rules need the file to show the pattern; a non-yes/no question that
  happens not to be answered as a block and has no "what/where/how" wording is not detected.

**Raised by the owner during this sub-step.** Standard vocabularies ICD-11, LOINC and SNOMED CT
are to be used (decision E51); planned as the new sub-step M2.11. The owner supplied a WHO ICD
API key (stored in the local `.env`, not in Git) and the LOINC 2.83 release (in `data/raw/`,
not in Git). Neither was used in M2.7.

**Committed and indexed.** Committed as `1f4b4e9` and pushed; CI passed on both jobs (backend,
web). The code graph was re-indexed at `1f4b4e9` and reports up-to-date. For M2.11: the WHO ICD
API key is in the local `.env` as `ICD_API_CLIENT_ID` and `ICD_API_CLIENT_SECRET`; the LOINC
release is `data/raw/Loinc_2.83.zip`. Both are outside Git. This paragraph was added in a
following documents-only commit, after which the index was refreshed again.

### M2.12 — Archive-15 source release: origin traced, question dictionary, kinds settled

**Why this sub-step exists.** M2.7 left 51 archive-15 questions undecided because the file cuts
each question off. The owner then supplied the release that archive 15 resembled, downloaded
from its publisher, said the data are real and asked for that to be checked, and asked for the
meaning of zeros to be understood from the data as well.

**Handoff clauses and owner decisions applied.** `docs/01` §3: archive 15's "feature dictionary
distinguishes symptoms, history and risk factors"; §4: "E_* questions must be classified by
clinical meaning. Do not treat a history question as an active symptom"; §7: "Confirm use
rights and document data provenance, label origin, populations and feature meanings". `docs/04`
T22: "Preserve full question text and raw value". Decisions E34, E53, E54.

**Impact analysis before editing.** `derive`, `derive_meanings` and the CLI `main`: LOW each,
one caller each. New modules call `read_csv_positional`, `_raw_cursor`, `sha256_file`
(CRITICAL, unchanged).

**What was checked, and how.**

- **The file.** `data/raw/22687585.zip`, SHA-256 `edf2cc50…5834`, 178,758,020 bytes, registered in
  `specs/supplementary_sources.json`. Its five members have the names and sizes the publisher's
  record lists. It was read in memory; nothing was unpacked to disk.
- **The publisher's record** (figshare API, DOI 10.6084/m9.figshare.22687585.v2) and its
  documentation (`github.com/mila-iqia/ddxplus`, README): title "DDXPlus Dataset (English)",
  licence CC BY 4.0, and: "The dataset contains patients synthesized using a proprietary medical
  knowledge base and a commercial rule-based AD system." Field descriptions: `AGE`: "the age of
  the synthesized patient"; `EVIDENCES`: "list of evidences experienced by the patient";
  `default_value`: "If this value is used to characterize the evidence, then it is as if the
  evidence was not synthesized"; `is_antecedent`: "whether the evidence is an antecedent or a
  symptom". Only the DOI and repository name were sent to those services; no project data.
- **The rows.** Each row of our files and of the release was reduced to age, sex, condition and
  the set of answered question codes, and our rows were matched to the release as runs in file
  order.

**Result of the real run** (`load-release`, 28 s; a second run changed 0 rows):

| Our file | Rows | In the release |
|---|---:|---|
| `test.csv` | 134,529 | test set, rows 1 – 134,529 |
| `train.csv` rows 1 – 310,850 | 310,850 | train set, rows 1 – 310,850 |
| `train.csv` rows 310,851 – 343,054 | 32,204 | train set, rows 330,223 – 362,426 |
| `train.csv` rows 343,055 – 475,502 | 132,448 | the whole validation set |

610,031 of 610,031 rows traced; 0 not found. The release holds 1,025,602 train, 132,448
validation and 134,529 test patients; ours uses 343,054 of its train rows. 223 of 223 columns
have a dictionary entry and all 223 cut-off headings are the beginning of their question.
The dictionary: 110 symptoms and 113 antecedents; 208 yes/no questions, 10 with one answer
out of several and 5 with several answers: the same 15 columns M2.7 had found from the data
alone.

**Conclusions.**

- **Archive 15 is the publisher's DDXPlus release, rendered as 0/1 columns, and its patients are
  simulated** (decision E55). The owner's statement that the data are real (E30) does not hold
  for this archive.
- **Zeros in archive 15:** for the 208 yes/no questions a 0 is the source's documented "no"
  (stored as `no_per_source`, still not `absent`, which only an approval may set). For the 15
  other questions the file keeps only that an answer is listed.
- **Its `train.csv` contains the publisher's validation set.** Recorded on the source for M4.3.

**Meanings re-derived** (`derive-meanings`, rule set `meanings-2`; a second run changed 0 rows):
archive 15 now has 110 symptom, 86 history, 26 exposure or lifestyle, 1 measurement, 0
undecided. The proposals of the other archives are unchanged (0 of 1,516 differ).

**How good were M2.7's wording rules?** Of the 172 questions they had decided, 169 agree with
the publisher on symptom or not. Three do not: `E_16` ("Do you feel anxious?", an antecedent
for the publisher, a symptom for my rule), `E_128` and `E_42`. The 51 they could not decide
are 35 symptoms, 15 history and 1 exposure. The same rules still serve the other archives,
where they mostly confirm what the source says.

**Implemented.** `specs/supplementary_sources.json`; `release.py` and the command
`load-release`; `meanings.py` (two functions for a documented source) and `meanings_load.py`
(the dictionary is used where a mapping carries one). The origin, licence and publisher's
statement are on the sources (`origin_url`, `licence`, `population.origin`), still `pending`.
`README.md` credits the publisher as the licence requires.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 45 files |
| `uv run pytest -m "not archives"` (SQLite) | 158 passed, 42 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 206 passed |
| `uv run pytest tests/ingestion/test_release.py tests/unit/test_meaning_rules.py` | 39 passed |
| `load-release` and `derive-meanings`, each run twice | second runs change 0 rows |
| `uv run python -m feeltriva_ingestion completeness` | exit 0; 235 checks, 228 ok, 0 mismatches, 7 later; T22 now reads "223 of 223 have a proposed kind; none is approved" |
| `detect_changes` before commit | `main`, `derive`, `derive_meanings`, the regenerated review files |

The new tests use a crafted release with the real layout and a crafted archive built like the
real one (train rows, a gap, then the validation set). They prove the runs are found, a row
the release lacks is reported, a changed release file is refused, the dictionary reaches the
mappings, an antecedent is never proposed as a symptom, and a documented zero is not `absent`.

**Bugs.** None in committed code. A slip in an exploration script of mine (never committed)
rebuilt a large table once per row and ran past ten minutes; it was stopped and corrected.

**Not done, and limits.**

- The answers to the 15 non-yes/no questions and the publisher's per-condition knowledge
  (symptoms, antecedents, severity, ICD-10) are in the release but not loaded: new sub-step
  M2.13, no go-ahead yet.
- The release file is not in the object store; it is registered by checksum only.
- The 550,099 train rows of the release that archive 15 does not use are not loaded.
- For archives 11, 12, 14 and 16 nothing new is known: no origin, no documentation.
- Everything stored here is `pending`.

**Committed and indexed.** Committed as `9a42446` and pushed; CI passed on both jobs. The code
graph was re-indexed at `9a42446` and reports up-to-date. This paragraph was added in a
following documents-only commit, after which the index was refreshed again.

**Noticed, not acted on.** Three untracked items appeared under `.claude/` on 2026-11-17 at 17:13
(`CLAUDE.md`, `settings.json`, `hooks/`), written by an editor tool named vexp (v3.5.1). They
were not created by this work and are not committed; the owner decides whether they are kept.

### M2.11 — Candidate links to ICD-11 and LOINC

**Why this sub-step exists.** Owner decision E51 (2026-11-17): use standard vocabularies for
diseases, symptoms, history and lifestyle items and measurements. The owner supplied a WHO ICD
API key and the LOINC 2.83 release, and agreed to decide on SNOMED CT from this result.

**Handoff clauses applied.** `docs/01` §4: "Do not force ICD/MONDO/HPO IDs when no verified
mapping exists"; reviewer-approved content only in serving. Project rule: no user health data to
outside services.

**Checked before designing** (official sources, read for this sub-step):

- WHO ICD API documentation and its Swagger reference (v2.6.0): token at
  `icdaccessmanagement.who.int/connect/token` with client credentials and scope
  `icdapi_access`; search at `/icd/release/11/{releaseId}/mms/search`; headers `API-Version: v2`
  and `Accept-Language`. One live call confirmed the reply format; the latest release is 2026-01.
- WHO terms of use, read in full: licence CC BY-ND 3.0 IGO; code, title and URI must be kept
  together (1.2.3); mappings between ICD and other classifications or terminologies need a
  separate written agreement (1.2.4); citation required (1.3).
- LOINC licence 5.8 (inside the release): free use; the LOINC notice must accompany its content.

**Impact analysis before editing.** CLI `main`: LOW (one new command). New migration `0006`
(shared area `migrations/`, no existing object changed). New module calls `_raw_cursor` and
`sha256_file` (CRITICAL, unchanged).

**Implemented.** Migration `0006` (`terminology_links`, not readable by the API role);
`vocabulary.py`; command `link-vocabularies`; LOINC registered in
`specs/supplementary_sources.json`; key placeholders in `.env.example`; credits in `README.md`.
Rules (decision E56): a link only for an exact name match; a close result is written to the
review file, never stored as a link; question sentences are not sent; no table relating ICD-11
to another vocabulary; link lists stay outside Git (`data/derived/review/vocabulary_links.csv`).

**What was sent to the WHO API:** 1,698 terms (960 disease labels and 738 feature names), each
as plain text, one request each, over one connection. No case row, no count, no question
sentence. Answers are cached in `data/derived/icd_cache/`.

**Result of the real run** (ICD-11 release 2026-01):

| Items | Looked up | Exact ICD-11 name (link stored) | Close result, for a person (best score 0.9 or more) | Weak result or none |
|---|---:|---:|---:|---:|
| Disease labels | 960 | 405 | 332 | 223 |
| Named symptom, history and exposure terms | 738 | 166 | 99 | 473 |
| Archive-15 questions (sentences) | 223 | not sent | | |

571 ICD-11 links and 10 LOINC links stored; all `pending`; every one has code, title and URI;
no item has more than one exact ICD-11 entity. Of the 166 linked symptom terms, 111 are in
ICD-11's chapter for symptoms and signs and 55 are filed in a body-system chapter (for example
"muscle pain" under musculoskeletal diseases); that is a hint for the kind review, not a
verdict. LOINC: one measurement item (the BMI question, `39156-5`) and nine symptom terms whose
whole LOINC name equals ours. A second run made 0 API calls and stored 0 new links (9 s).

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 46 files |
| `uv run pytest -m "not archives"` (SQLite) | 163 passed, 43 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 212 passed |
| `uv run pytest tests/ingestion/test_vocabulary.py` | 6 passed, no network |
| Migration `0006` on a scratch database: head, down to `0005`, head, base, head | 31, 30, 31, 1, 31 tables; scratch database dropped |
| `link-vocabularies` on the real data, then again | 581 links; second run 0 API calls, 0 new links |
| `detect_changes` before commit | `main` only among existing symbols |

The tests replace the ICD API by a local stand-in: one token with the documented request;
answers cached and reused; an expired token renewed; a dropped connection retried and a dead
one ended with a plain message; only an exact name is a match; the question sentence is never
sent; links stored pending with code, title and URI; the API role cannot read them.

**Bugs** (all found by the real run, none by the stand-in tests):

- **BUG-017 — no retry on a dropped connection.** The first run died after a minute on a TLS
  timeout. The client retried error replies but not connection failures. *Resolution:* five
  attempts with a growing wait, then a plain message saying the run can be repeated; a test.
- **BUG-018 — a new connection per request, inside a transaction.** The second run managed about
  six terms a minute: the route to the WHO servers was unstable (one connection attempt in six
  hung for 30 s) and each request made a new one. The lookups also ran inside an open database
  transaction. *Resolution:* one kept-open connection per host with a 20 s limit; terms are read
  in a short transaction, looked up with none open, then stored. The run then held about one
  term a second. It stopped once more when the owner's internet connection dropped and resumed
  from the cache, as designed.
- **BUG-019 — wrong-sense LOINC match.** Matching our term to a LOINC component alone linked
  "fever" to "Fever in Mother". *Found by* reading the twelve LOINC links. *Resolution:* the
  whole LOINC name must equal ours; the twelve pending candidates were deleted and ten correct
  ones stored; a test.

**Limits, stated plainly.**

- An exact name match is a candidate, not a clinical judgement, and nothing is approved.
- 42% of disease labels and 22% of feature terms have an exact ICD-11 name. Many of our terms
  are everyday phrases ("pus in sputum") that ICD-11 does not name. The close results need a
  person; SNOMED CT would likely cover more (decision D-T1).
- LOINC fits measurements, and our data hold exactly one measurement item.
- The links are not published, and no ICD-11 crosswalk to another vocabulary exists (E56).
- The completeness check was not rerun: this sub-step adds a table and changes no data it reads.

**Committed and indexed.** Committed as `9dc5c0a` and pushed; CI passed on both jobs. The code
graph was re-indexed at `9dc5c0a` and reports up-to-date. This paragraph was added in a
following documents-only commit, after which the index was refreshed again.
