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
| BUG-005 | M1.7 | PostgreSQL crashed during the first full case load (one transaction per file) | Mitigated — batched, resumable loader completed the full load; root cause not proven |
| BUG-006 | M1.7 | Formatter re-wrapped two already-applied migrations | Fixed — reverted before commit |
| BUG-007 | M3.6 | Web: keyboard focus is not returned to the footer button after its dialog closes | Open |
| BUG-008 | M3.6 | Web: a duration answer is displayed twice ("3 days · 3 days") | Open |
| BUG-009 | M3.6 | Web: an explicit "None of these" answer shows the raw option value "none" under the detail | Open |
| BUG-010 | M3.6 / M3.3 | "Not sure" on multiple-choice and free-text questions is sent in a form the API does not treat as uncertain (latent: no such question in the fixture) | Open |

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
