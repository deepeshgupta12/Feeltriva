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
| BUG-020 | M2.8 | Two labels that share only a catch-all ICD-11 code were suggested as synonyms (chronic and diabetic kidney disease) | Fixed before commit |
| BUG-021 | M2.11 / M2.14 | The self-check of `link-vocabularies` reported any link that was not `pending` as a difference, so the command would fail as soon as a reviewer decided one link | Fixed |
| BUG-022 | M2.16 / M2.17 | Where the name search already held the ICD-11 code that MONDO leads to, the note on that row did not keep the foundation entity MONDO names | Fixed |
| BUG-023 | M2.6 | The sentence rule read the letters that end a token of letters and digits ("794f", "2a") as a single-letter word or an abbreviation, so a sentence ending in such a token was not ended. Found by CI on the M2.6 commit: the test sentence ends in a random tag | Fixed |
| BUG-024 | M2.5c1 | Two merge or split events written within one second came back in the wrong order on SQLite, because the history was ordered by a time the database filled in | Fixed before commit |
| BUG-025 | M1.11, M1.13 / M2.5c3, M2.5d1 | The self-checks of `load-evidence` and `completeness` reported every row that was not `pending`, so both commands would fail as soon as a reviewer decided a row (the fault of BUG-021, left in two more commands). Shown by the test suite in M2.5c3 | Fixed in M2.5d1 |
| BUG-026 | M1.10 / M2.5f | A test of the chunk loader searched the shared test database for words every run stores, with a limit of 50, and expected its own row among the results; once more than 50 runs had left their rows it failed depending on the order | Fixed in M2.5f: the test searches for its own run's word |
| BUG-027 | M2.1 / M2.4a | Two notes recorded on one item within a second came back in either order on SQLite, and every note of one transaction carried the same time on PostgreSQL, because the database filled the time in | Fixed in M2.4a: a note's time is set by the code, to the microsecond |

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

### M2.8 — Synonym and subtype suggestions

**Handoff clauses applied.** `docs/01` §4, deduplication rule 4: "Use casefold/trim/collapse-whitespace
only for initial disease labels. Preserve subtype, acuity and severity distinctions. Suggested
synonyms go to review." `docs/05` M2: review screens for disease aliases; redirects and merge
history (the acting part, M2.5). Owner's confirmed order: M2.8 after M2.7.

**Impact analysis before editing.** `record_review`, `overview`, `create_app` and the ingestion
CLI `main`: LOW each, one caller each. Shared files touched: `models.py` (one class appended),
`review.py`, `main.py`, a new migration.

**Implemented.**

- Migration `0007`: `relation_suggestions`. The API role may read and decide rows only inside a
  reviewer transaction (row-level security), and may change only `status` and `reviewer`.
- `relations.py` and the command `suggest-relations`. Possible synonym: same words under other
  punctuation, other order or number, British or American spelling, or a candidate link to
  the same specific standard code. Possible subtype: one label is the other plus one or two
  words; the narrower label is stored on the left. Question sentences are not compared.
- Review API: `GET /internal/v1/review/relation-suggestions` (filters: status, relation,
  subject type, text). Decisions go through the existing `POST /internal/v1/review/decisions`
  with target type `relation_suggestion`: the reviewer, the note and an audit event are
  recorded. The overview now counts suggestions by status.
- A pair that already has a row keeps it, whatever was decided, so a rejection is remembered.
- Accepting a suggestion records the decision only. Creating the redirect is M2.5.

**Result of the real run** (1 s; a second run added 0):

| Candidates | Possible synonyms | Possible subtypes |
|---|---:|---:|
| 960 disease labels | 18 | 175 |
| 738 named feature terms | 53 | 174 |

Reasons among the 71 synonym suggestions: same words under other punctuation 32, same specific
standard code 33, other order or number 14, spelling 1 (a pair can have a code reason and a
wording reason). All 420 are `pending`. Examples: "typhoid fever" as a subtype of "typhoid";
"acute rhinosinusitis" and "acute sinusitis" (one ICD-11 code); "pain in gums" and "gum pain".
The broader terms with most suggested subtypes: swelling 25, cancer 24, weakness 18.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 47 files |
| `uv run pytest -m "not archives"` (SQLite) | 170 passed, 44 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 220 passed |
| `uv run pytest tests/unit/test_relations.py tests/api/test_review_suggestions.py` | 8 passed |
| Migration `0007` on a scratch database: head, down to `0006`, head, base, head | 32, 31, 32, 1, 32 tables |
| Live API after restart: the new route as a reviewer, and without the role | 200 with 18 disease synonyms; 403 |
| `detect_changes` before commit | intended: `main`, `create_app`, `overview`, `record_review`; also listed but identical to the last commit (code added above them): `get_condition_information`, `KnowledgeService`, `review_decision`, `app_factory` |

The tests prove: each kind of likeness is found with its reason; an added word gives a subtype
and never a synonym; three added words give nothing; one identity per pair; the route is for
reviewers only and shows both terms; a rejection is stored with the reviewer; a rerun suggests
nothing twice and keeps the rejection; no disease is redirected by a suggestion; outside a
reviewer transaction the rows can be neither read nor changed.

**Bugs.**

- **BUG-020 — synonyms from a catch-all code.** The first real run suggested "chronic kidney
  disease" and "diabetic kidney disease", and "Gaucher disease" and "Niemann-Pick disease", as
  possible synonyms, because each pair carries one residual ICD-11 code ("unspecified", "other
  specified"). *Found by* reading a sample of the stored suggestions. *Resolution:* residual codes
  are no reason to suggest (decision E58); the 440 pending rows were deleted and 420 generated;
  a test with a specific and a residual code.
- Also corrected before commit: the singular form cut "virus" to "viru" and would have cut
  "arthritis"; endings "us" and "is" are now left alone.

**Limits, stated plainly.**

- Wording and shared codes are the only evidence. A suggestion is a question for a reviewer.
- Synonyms with no word in common ("heart attack", "myocardial infarction") are found only
  when both have a link to the same specific code, and only 42% of disease labels and 22% of
  terms have an ICD-11 link.
- The 349 subtype suggestions include loose ones ("neck cramps or spasms" under "cramps").
- The review screens do not show suggestions yet (M2.4); they are reachable through the API.

**Committed and indexed.** Committed as `01ee0c8` and pushed; CI passed on both jobs. The code
graph was re-indexed at `01ee0c8` and reports up-to-date. The API on port 8000 was restarted so
that it serves the new route. This paragraph was added in a following documents-only commit,
after which the index was refreshed again.

### Maintenance — dependency alert on `minimatch` resolved (2026-11-18)

Asked for by the owner after GitHub's Dependabot alert 1 was reported. Not a plan sub-step; no
product code changed.

**The alert.** GHSA-g3hv-75wg-m249 (CVE-2026-118764, medium): `minimatch` versions 7.0.0 up to
but not including 11.0.1 can be made to use excessive time on a crafted pattern. Scope:
development only, in `apps/web/pnpm-lock.yaml`.

**Where it came from.** The lockfile held four copies of `minimatch`:

| Copy | Pulled in by | In the affected range |
|---|---|---|
| 10.2.6 | `eslint` 10.14.0 and `@typescript-eslint/typescript-estree` 8.72.2 | yes |
| 11.0.8 | `@eslint/config-array` | no (fixed) |
| 5.1.9 | `openapi-typescript` through `@redocly/openapi-core` | no (below 7.0.0) |
| 3.1.5 | `eslint-plugin-jsx-a11y` | no (below 7.0.0) |

All four belong to lint and type-generation tools. None is in the built web app or the API.

**Change.** Two pinned development dependencies in `apps/web/package.json`, checked against the
registry before choosing: `eslint` 10.14.0 → 10.15.0 (declares `minimatch ^11.0.5`) and
`typescript-eslint` 8.72.2 → 8.73.0 (its `typescript-estree` declares `minimatch ^11.0.1`). The
lockfile was regenerated. No override was needed, so no package is forced outside the range its
publisher declares. In the lockfile only `eslint`, the `typescript-eslint` family and `minimatch`
changed; copy 10.2.6 is gone.

**Impact analysis.** `impact` on `apps/web/eslint.config.js`, upstream: 0 dependents, risk LOW.
A search of `apps/web` found no other use of these packages. `detect_changes` before commit:
2 files, 0 symbols, 0 flows, risk low.

**Tests actually run.**

| Command | Result |
|---|---|
| `pnpm install --frozen-lockfile` | already up to date |
| `pnpm typecheck` | clean |
| `pnpm lint` (before and after the change) | clean both times, with `eslint` 10.15.0 after |
| A probe file using `localStorage` and an unused variable, linted, then deleted | 2 errors, as required: the storage rule and the unused-variable rule still fire |
| `pnpm test` | 118 passed in 6 files |
| `pnpm build` | built |
| `pnpm gen:api` and `git diff --exit-code src/api/generated` | no difference |
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 47 files |
| `uv run pytest` (SQLite, nothing deselected) | 173 passed, 47 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 220 passed |

**Limits, stated plainly.**

- Copies 3.1.5 and 5.1.9 remain. This advisory does not list them; they were not changed.
- `pnpm` reports one unmet peer: `eslint-plugin-jsx-a11y` 6.10.2 declares support for `eslint`
  up to version 9, and the project uses version 10. This was already so before the change; lint
  runs and its rules fire. Left as it is.

**Committed and indexed.** Committed as `172838b` and pushed; CI passed on both jobs. GitHub
rescanned the branch and marked alert 1 as fixed (2026-11-18 08:15 UTC). The code graph was
re-indexed at `172838b` and reports up-to-date. This paragraph was added in a following
documents-only commit, after which the index was refreshed again.

**A second alert, seen at the same rescan, not fixable today.** Alert 2: GHSA-fc5q-39xc-vjpf
(high, development scope), `picomatch` 4.0.7 and every earlier version; no fixed release exists
(4.0.7 is the newest published). GitHub dismissed it automatically under its rule for
development-only dependencies. The package was in the lockfile before this change, unchanged by
it, and is used by `vite`, `vitest`, `tinyglobby` and `fdir` to match file names from this
repository's own configuration; it is not in the built web app. To be updated when a fixed
release is published.

**Alert 2 re-examined at the owner's request ("fix this"), 2026-11-18. It cannot be fixed yet.**

What was checked, with results:

| Question | Finding |
|---|---|
| Is there a fixed release? | No. The registry's newest `picomatch` is 4.0.7 (published 2026-08-24); the advisory covers 4.0.7 and everything earlier and names no patched version |
| Is a repair on its way? | The advisory points to pull request 194 in the `picomatch` repository. It is open and unmerged, written by an outside contributor, last updated 2026-11-09 |
| Can the package be removed or avoided? | No. The newest `vite` (8.3.8), `vitest` (5.1.1), `tinyglobby` (0.2.17) and `fdir` (6.5.0) all still require `picomatch` 4 |
| Is the weakness real in the installed copy? | Yes. The advisory's pattern `+(*a)` took 9 ms against 20 letters, 36 ms against 22, 149 ms against 24 and 546 ms against 26: about four times longer for every two letters |
| Can it be reached in this project? | Not found. It needs a file pattern of that special kind to be supplied to the tool. The only pattern this project writes is `src/**/*.test.{ts,tsx}` (0.11 ms on a long path); no configuration file or script contains such a pattern; the source uses no `import.meta.glob`; the development server listens on this machine only (`[::1]:5173`); the built app in `dist/` does not contain the package |

Not done, and why:

- **The unmerged repair was not applied as a local patch.** It is 160 changed lines in the
  pattern parser, not reviewed or accepted by the package's maintainers. The same parser decides
  which test files `vitest` finds, so a subtle error could make tests silently not run. GitHub's
  alert would also stay as it is, because the version number would not change.
- **No override was added.** Every published version is affected, so there is nothing to pin to.

Correction to what was reported to the owner earlier the same day: GitHub did not dismiss the
alert because no fix exists. Its preset rule dismisses certain low-impact kinds of weakness (this
one is recorded as CWE-1333, inefficient regular expression) in npm packages used only for
development. GitHub's documentation does not say whether a fix will then arrive as an automatic
pull request, so the item is tracked in the plan (M0.8) with the command to re-check.

### M2.14 — Candidate links to HPO and MONDO, in place of SNOMED CT

Owner's go-ahead: 2026-11-18, with the order of decision E59. The owner could not obtain the
SNOMED CT release and supplied `hp.json` (HPO, release 2026-09-01) and `mondo.owl` (MONDO,
release 2026-11-03) in `data/raw/`.

**What was built.**

- `ontologies.py` (reads two files, no database): `read_hpo`, `read_mondo`, `read_vocabulary`
  (checksum and release must be the registered ones), `lookup` and `nearest`. `mondo.owl` is
  255 MB and is read as a stream; both files are read in about 15 seconds.
- `ontology_links.py`: `link_ontologies`, `summarise`, `check`, `write_review`.
- New command `python -m feeltriva_ingestion link-ontologies`. Offline: nothing leaves the machine.
- `vocabulary.py`: the subject query and the link insert of `link_vocabularies` moved into
  `read_subjects` and `store_links`, used by both link commands, so both look up the same items
  and store a link the same way.
- `specs/supplementary_sources.json`: both files registered with SHA-256, size, release, licence.
- No migration: the links go into `terminology_links` (M2.11). No API or web change.

**The rule for a link (decision E60).** A `pending` link only when our whole name equals the
label or an exact synonym of a current term that may be linked. Not through an abbreviation, a
related, broad or narrow synonym, an obsolete term or a disease of animals. None when several
terms carry the name. Every other name gets a recorded reason and up to three nearest terms.

**Facts measured on the real files before the rules were fixed** (read-only scripts):

| Fact | Consequence |
|---|---|
| Our label "scar" equals MONDO's abbreviation SCAR ("severe cutaneous adverse reaction"); our symptom "cold" equals COLD, its abbreviation for chronic obstructive pulmonary disease | An abbreviation is not a name: no link, listed for review |
| "ards" and "multiple myeloma" also name a dog disease and a "non-human animal" variant; 8,319 of MONDO's 32,137 current terms are animal diseases | Only terms under "human disease" or "injury" are linked |
| "frostbite", "burn" and "head injury" stand under MONDO's separate root "injury" | "injury" is linkable |
| "mood swings", "hypersomnia", "vertigo" and 9 more equal only obsolete terms; "diabetes mellitus type 1" equals only a term of the branch "disease susceptibility" | Such terms are indexed so that the reason can be stated; never linked |
| 45 of our names equal only a related, broad or narrow HPO synonym ("dizziness" is a related synonym of "Vertigo") | Looser synonyms never link |
| After these rules no real name is carried by several linkable terms | The "several terms" rule is covered by tests only |

**Real run** (`link-ontologies`, 11 seconds):

| | HPO 2026-09-01 | MONDO 2026-11-03 |
|---|---:|---:|
| Terms in the file | 20,482 | 36,168 |
| Current / obsolete | 19,894 / 588 | 32,137 / 4,031 |
| Entries of other vocabularies, counted and not read | 50 | 27,627 |
| Terms that may be linked | 19,845 | 23,285 |
| Labels / exact synonyms / looser synonyms read | 19,894 / 23,665 / 2,595 | 32,137 / 71,027 / 22,487 |
| Exact synonyms that are abbreviations or otherwise not names | 593 | 6,116 |
| Parent links | 24,436 | 46,770 |

| Outcome | Disease labels (960): HPO | MONDO | Feature terms (961): HPO | MONDO |
|---|---:|---:|---:|---:|
| Linked: our name is the term's label | 257 | 420 | 147 | 23 |
| Linked: our name is an exact synonym | 67 | 121 | 92 | 15 |
| Equals only an abbreviation | 8 | 15 | 0 | 1 |
| Equals only a looser synonym | 33 | 12 | 12 | 6 |
| Only terms that may not be linked | 0 | 9 | 2 | 2 |
| No term with this name; nearest listed | 264 | 210 | 218 | 116 |
| No term with this name or near it | 331 | 173 | 267 | 575 |
| Not looked up: a question sentence | | | 223 | 223 |

Every column adds up to its total. Stored: 563 HPO and 579 MONDO links, all `pending`
(`terminology_links` now holds 1,723: 571 ICD-11, 10 LOINC, 563 HPO, 579 MONDO).

| Coverage | Before (ICD-11 only) | HPO or MONDO | Any of the three |
|---|---:|---:|---:|
| Disease labels with a candidate link (of 960) | 405 | 607 | 662 |
| Named terms with a candidate link (of 738) | 166 | 246 | 300 |
| Case labels whose label has a link (of 1,365,363) | 608,438 | 847,340 | 923,332 |

Links by branch: MONDO human disease 576 (2 of them also "disease susceptibility"), injury 3;
HPO phenotypic abnormality 556, past medical history 5, clinical modifier 2. Synonym links by
the kind the vocabulary states: HPO layperson 89, plain 63, plural form 5, UK spelling 2; MONDO
plain 134, UK spelling 1, historic 1.

**Reading the stored links.** The 95 synonym links whose label shares no word with our name
were read one by one: they are lay names against technical names ("heart attack" and
"Myocardial infarction", "bunion" and "Hallux valgus", "whooping cough" and "pertussis"). For a
reviewer to judge, because the vocabulary's own exact synonym is broader or narrower in everyday
use: "sweating" and "Hyperhidrosis", "fainting" and "Loss of consciousness", "cushing syndrome"
and HPO's "Increased circulating cortisol level", "gestational diabetes" and HPO's "Maternal
diabetes" (a history item about a pregnancy).

**Effect on the suggestions of M2.8.** `suggest-relations` was rerun: 36 new possible synonyms
(22 disease pairs, 14 feature pairs) from two of our names carrying one HPO or MONDO term, all
read ("influenza" and "flu", "hematuria" and "blood in urine", "typhoid fever" and "typhoid").
456 suggestions are pending; nothing is merged.

**Impact analysis.** `main` (command dispatcher): 1 caller, LOW. `link_vocabularies`: 1 caller
(`main`) and its tests, LOW. `load_supplementary`: 2 callers, each choosing its entry by kind,
LOW. `suggest_relations`: 1 caller, LOW (affected through the data only). `check` of
`vocabulary.py`: 1 caller, LOW. `detect_changes` before commit: intended `main` and
`link_vocabularies`; summary risk "high" because `main` is the first step of eight flows.
Investigated by comparing every function body with the last commit: in `vocabulary.py` only
`check` and `link_vocabularies` differ (`write_review` and the variables it listed are
identical: the known line-shift artefact); in `main` exactly one command branch was added and
none of the 14 existing branches differs. `verify`, `search-text`, `link-vocabularies` and
`suggest-relations` were run after the change.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 49 files |
| `uv run pytest -m "not archives"` (SQLite) | 179 passed, 45 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 231 passed |
| `tests/unit/test_ontologies.py` (8), `tests/ingestion/test_ontology_links.py` (3) | 11 passed |
| `link-ontologies` on the real files, twice | 1,142 links, then 0 new; exit 0 both times |
| `link-vocabularies` after the change (answers cached, no network) | 0 new calls, 0 new links, exit 0 |

The tests prove: every entry of a file is counted and placed in a branch; synonym kinds are
read (HPO from the synonym, MONDO from its annotation); a parent given as a restriction is not
a parent; label and exact-synonym links; no link through an abbreviation, a looser synonym, an
obsolete term, a frequency term, a susceptibility or an animal disease; none when several terms
carry the name, the label winning when there is exactly one; nearest terms ranked and never an
abbreviation; a file is refused when its checksum, its release or its layout is not the expected
one; links stored `pending` with code, label, address, branch and matched text; a question
sentence is not looked up; the review file has one row per item and vocabulary, a reason
wherever there is no link, and no ICD-11 code; a rerun stores nothing; a reviewer's decision
survives; on the real files the known hazards ("scar", "cold", "ards", "gerd") get no link and
"multiple myeloma" is linked to the human disease only.

**Bugs.**

- **BUG-021 — a reviewed link made `link-vocabularies` fail.** Its self-check counted every
  link in the table that was not `pending` and reported it as a difference. Nothing had been
  reviewed when M2.11 was written, so it never fired. *Found by* the new test in which a
  reviewer's decision survives a rerun: it left one decided link in the test database and the
  M2.11 test then failed. *Resolution:* a decided link is expected; what is reported is a link
  decided without a reviewer's name (`decided_without_reviewer`), in both link commands; tests
  for both cases. *Same pattern, not changed here:* the self-checks of `load-evidence` and
  `completeness` report any row that is not `pending`; recorded on the M2.5 row of the plan,
  where approvals begin.
- Two expectations in the new unit tests were wrong (six exact synonyms in the invented file,
  not five; the shorter name is the nearer one). The code was right; the tests were corrected.

**Limits, stated plainly.**

- A link is a match of names. Nothing is approved, and no disease or feature ID is replaced.
- 19 names equal only an abbreviation and have no link in either vocabulary: 39,842 case rows,
  among them `gerd` (15,831), `psvt` (10,994), `sle` (7,023) and `copd` (2,872). Most of these
  are probably right; "scar" and "cold" are not, and the rule cannot tell them apart.
- 298 disease labels and 438 named terms have no candidate in ICD-11, HPO or MONDO. Many are
  compound or misspelt labels ("possible nstemi / stemi", "larygospasm").
- "Nearest terms" are found by shared words only (at least half). They are a starting point
  for a person, and some are poor ("sweating" and "gustatory sweating").
- The 223 question sentences of archive 15 are not looked up as names.
- The nearest terms and reasons live in a file outside Git, not in the database; the review
  screens (M2.4) will need them loaded.
- Identifiers of other vocabularies inside MONDO (ICD-11, SNOMED CT) were not read (D-T2).
- The two files are not copied into the object store, as with the other supplied releases.

**Committed and indexed.** Committed as `ef750d4` and pushed; CI passed on both jobs. The code
graph was re-indexed at `ef750d4` and reports up-to-date; both new modules are below the 32 KB
limit and their call edges are present. Note for later changes: the graph now rates the shared
functions `store_links` and `read_subjects` HIGH, because both link commands depend on them.
The API and the web app were not restarted: this sub-step changes neither. This paragraph was
added in a following documents-only commit, after which the index was refreshed again.

### M2.15 — Readings of abbreviated labels confirmed by the owner

Owner's review of 2026-11-18. M2.14 left 19 names without a link because they equal only an
abbreviation. The owner confirmed that the 14 readings marked "looks right" are right, wrote out
what COPD, PACs, OCD and CIDP mean, and said that "scar" and "cold" are ordinary words that can
be symptoms. In the same exchange the owner decided that the SNOMED CT and ICD-11 identifiers
inside MONDO are to be imported (decision E62); that is sub-step M2.16 and was not started here.

**What was built.**

- `specs/confirmed_readings.json`: 19 readings, each with the label, the full name it stands
  for (or `plain_word`), who confirmed it, when, and on what basis.
- `ontologies.py`: `load_readings` (refuses an unclear file) and `lookup_as_read`; `Outcome`
  gained the field `read_as`. `lookup` itself is unchanged.
- `ontology_links.py`: `link_ontologies` applies the readings; a link made through one records
  `read_as`, `our_name`, `reading_confirmed_by` and `reading_confirmed_on`; the review file has a
  column `read_as`; `check` reports a reading that fits none of our names.
- `link-ontologies` prints how many readings are in the file and how many fit a name.

**The rule (decision E61).** A confirmed full name is looked up in place of the label by the
unchanged exact-name rule. The abbreviation match itself is never accepted.

**Why the full name is looked up, and not the abbreviation match as shown** (read-only check
before any code): for 15 of the 17 readings the full name finds exactly the terms that were shown
to the owner. For two it corrects them:

| Label | The abbreviation match shown in the M2.14 report | What the owner's full name finds |
|---|---|---|
| `ocd` | MONDO "obsessive-compulsive personality disorder" | MONDO "obsessive-compulsive disorder" (its label); HPO "Compulsive behaviors", which HPO lists under that exact synonym |
| `cidp` | two MONDO terms sharing the abbreviation | the one whose exact synonym is the owner's wording, "chronic inflammatory demyelinating polyradiculoneuropathy" |

Two links were not shown before and follow from the full name: `adhd` to MONDO "attention
deficit-hyperactivity disorder" and `als` to HPO "Amyotrophic lateral sclerosis".

**Real run** (`link-ontologies`, 17 seconds; a second run added nothing):

| | Before | After |
|---|---:|---:|
| HPO links / MONDO links | 563 / 579 | 573 / 594 |
| Disease labels with an HPO or MONDO link (of 960) | 607 | 625 |
| Disease labels with a link in ICD-11, HPO or MONDO | 662 | 680 |
| Case labels whose label has a link (of 1,365,363) | 923,332 | 963,174 |
| Suggestions pending (after `suggest-relations`) | 456 | 467 |

All 25 new links were read: 21 are the label of the term, 4 an exact synonym (`gerd`, `copd`
and `ocd` in HPO, `cidp` in MONDO). The 11 new possible synonyms pair an abbreviated label with its
written-out label ("copd" and "chronic obstructive pulmonary disease", "ibs" and "irritable
bowel syndrome").

**"scar" and "cold".**

- `scar` (a disease label, 347 cases): read as "scarring", which is HPO's name of the finding;
  linked to HPO "Scarring". The owner said it is a symptom to be mapped; the wording "scarring"
  was chosen by the assistant, and the file says so. MONDO: no link.
- `cold` (a symptom, affirmed in 43 cases): recorded as an ordinary word, so MONDO's
  abbreviation COLD is ruled out. No full name yet. The data: swine flu 12, influenza 10, common
  cold 7, sinusitis 6, measles 5, allergy 3, which points to "a cold", not "feeling cold". HPO
  has no finding of that name; MONDO has the disease "common cold". Left for the owner.

**Impact analysis.** `lookup`: 1 direct caller (`link_ontologies`), LOW; it was in the end left
unchanged. `link_ontologies`, `write_review`, `check` of `ontology_links.py`: 1 caller each
(`main`), LOW. `main`: 1 caller, LOW (measured for M2.14 the same day). `detect_changes` before
commit: `main`, `_link`, `link_ontologies`, `summarise`, `check`, `write_review`, all intended;
summary risk "high" because `main` and `link_ontologies` are the first step of 13 flows.
Compared with the last commit function by function: in `ontologies.py` only `Outcome` differs
(one field) and two functions are new; in `main` only the `link-ontologies` branch differs, the
other 14 are identical. `verify` and `link-vocabularies` were run after the change.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 49 files |
| `uv run pytest -m "not archives"` (SQLite) | 183 passed, 46 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 237 passed |
| `tests/unit/test_ontologies.py` (12), `tests/ingestion/test_ontology_links.py` (5) | 17 passed |
| `link-ontologies` on the real files, twice | 25 links, then 0 new; exit 0 both times |

The tests prove: a confirmed full name is looked up by the same rule and the link records who
confirmed it; a full name that no term carries gives no link and a reason; a "full name" that is
itself only an abbreviation still gives no link; an ordinary word is never linked through an
abbreviation and gets the nearest terms; an unclear readings file is refused (both or neither
kind, no name, no confirmer, no date, a label twice); the committed file is valid; a link through
a reading is stored `pending` with no reviewer; a reading that fits no name is reported; on the
real files the 19 readings lead to exactly 25 links, `ocd` to the disorder and not to the
personality disorder, `cidp` to one term, `scar` to HPO only, `cold` to none.

**Bugs.** None in committed code. A read-only data query written during the work was slow (four
minutes for a count over 16 million rows; `case_features` has no index on the mapping alone) and
one of its three parts had a SQL error; it changed nothing and its first part gave the figures
for "cold" above.

**Limits, stated plainly.**

- A reading is the owner's statement about a name. The links stay `pending`; nothing is approved.
- The readings apply to HPO and MONDO only. The ICD-11 name search of M2.11 was not repeated
  with the full names; M2.16 will bring ICD-11 identifiers for these labels through MONDO.
- `cold` has no link. `scar` rests on a wording the owner has not seen.
- `nash` is read as MONDO's present name of the condition ("metabolic dysfunction-associated
  steatohepatitis"), which is what was shown to and confirmed by the owner.

**Committed and indexed.** Committed as `9c904d9` and pushed; CI passed on both jobs. The code
graph was re-indexed at `9c904d9` and reports up-to-date. The API and the web app were not
restarted: this sub-step changes neither. This paragraph was added in a following documents-only
commit, after which the index was refreshed again.

### M2.16 — SNOMED CT and ICD-11 identifiers taken from MONDO

Owner's instruction of 2026-11-18 (decision E62): "We do not need any license for the same,
import them and map them correctly, for the deduplication, keep the most accurate nomenclature".
Before the work the owner confirmed how deduplication is to be read, accepted that a SNOMED CT
link shows the number and MONDO's name, confirmed "scar" as "Scarring", and added a standing rule:
no code of any vocabulary is shown to a user (decision E63, now in `CLAUDE.md`).

**What was built.**

- `mondo_identifiers.py` (one file, WHO, no database): `read_identifiers` (streams `mondo.owl`
  after its checksum and release are confirmed), `grade`, `resolve_icd`.
- `identifier_links.py`: `import_identifiers`, `summarise`, `check`, `write_review`.
- New command `python -m feeltriva_ingestion import-identifiers`.
- No migration: links go into `terminology_links`. No API or web change.
- `specs/confirmed_readings.json`: the basis of "scar" now records the owner's confirmation.

**The rules.**

- Basis: every label with a MONDO link that no reviewer has rejected (594).
- Only an identifier MONDO marks `MONDO:equivalentTo`, and not as obsolete, may become a link.
  When MONDO marks several identifiers of one vocabulary equivalent for a term, none is chosen.
- SNOMED CT: the concept number, the address `http://snomed.info/id/<number>`, and as title
  MONDO's name of the equivalent disease, with a note saying so. No SNOMED CT name is held.
- ICD-11: MONDO gives foundation entity numbers. WHO is asked for the entity's official title
  and for where the MMS linearization codes it. If the MMS entity is that same entity, the link
  is its MMS code (the kind M2.11 stores). If WHO codes it under another entity, the link is the
  foundation entity itself and the MMS code is recorded beside it, not linked.
- One row per label and code. Each link names the MONDO term, release and marks it came through.

**WHO's API, checked before use.** The official OpenAPI document (`id.who.int/swagger`) gives
`GET /icd/entity/{id}` and `GET /icd/release/11/{releaseId}/{linearizationname}/lookup` with
`foundationUri`; a linearization entity carries `code`, `title` and `source` (the foundation
entity it derives from). One real call per endpoint with WHO's documented example (cholera)
confirmed it. Only entity numbers are sent.

**Real run** (`import-identifiers`; the dry run before it made 568 WHO calls in four minutes,
all cached, so the run itself took 9 seconds and a rerun adds nothing):

| In `mondo.owl` | SNOMED CT | ICD-11 |
|---|---:|---:|
| Identifiers listed for current MONDO terms | 9,026 | 4,569 |
| Marked equivalent | 8,985 | 4,565 |
| Other marks | 41 | 4 |

| Outcome for our 594 labels with a MONDO link | SNOMED CT | ICD-11 |
|---|---:|---:|
| Linked | 527 | 278 as an MMS code |
| Linked to the foundation entity (WHO codes it only under a sub-code) | | 46 |
| MONDO lists no identifier | 61 | 263 |
| Several identifiers marked equivalent, none chosen | 5 | 5 |
| No identifier marked equivalent | 1 | 1 |
| WHO does not know the entity | | 1 |

Stored: 527 SNOMED CT, 172 ICD-11 MMS and 46 ICD-11 foundation links, all `pending`
(`terminology_links` now holds 2,493 rows).

**Deduplication against the name search of M2.11**, for the 278 MMS codes MONDO leads to:

| Case | Labels | What was done |
|---|---:|---|
| The name search had stored the same code | 106 | No second row; the existing row is noted as also reached through MONDO |
| The name search had stored only the "unspecified" or "other specified" sub-code of the same category | 121 | The category is added; the sub-code row is noted with the category. Both stay as candidates |
| The name search had stored a different code | 5 | Both stay as candidates; listed for review |
| The name search had no code | 46 | New row |

The 121 show how the two routes differ: asked for a bare category name, WHO's search codes it as
a coder would, as "Lyme borreliosis, unspecified" (`1C1G.Z`); MONDO leads to the category itself
(`1C1G`). The 5 real differences were read: "eczema" (our label is linked to MONDO's "atopic
eczema"), "indigestion" as a disease label and as a symptom (dyspepsia against functional
dyspepsia), "stye" (hordeolum against hordeolum externum) and "valley fever" (coccidioidomycosis
against its acute pulmonary form).

| Coverage | Before | After |
|---|---:|---:|
| Disease labels with an ICD-11 candidate (of 960) | 405 | 475 |
| Disease labels with a SNOMED CT identifier | 0 | 501 |
| Case labels whose label has an ICD-11 candidate (of 1,365,363) | 608,438 | 735,746 |
| Case labels whose label has a SNOMED CT identifier | 0 | 725,473 |
| Suggestions pending (after `suggest-relations`) | 467 | 467 |

No new suggestion: the imported codes are shared only by labels that already share the MONDO term.

**Impact analysis.** `main`: 1 caller, LOW. `IcdClient.get`: LOW; called unchanged.
`store_links`: **HIGH** (two commands depend on it). Reported to the owner before any code was
written, with the plan: the function is called and not changed. Confirmed after the work by
comparing every function with the last commit: `vocabulary.py` (22 functions, `store_links`
among them), `ontologies.py`, `ontology_links.py` and `relations.py` are identical; in `main`
one command branch was added and the other 15 are identical. `link-vocabularies` and
`link-ontologies` were rerun and pass. `detect_changes` before commit: `main` and the test
fixture `write_mondo`, both intended; `_hp` and four variables are the known line-shift artefact;
summary risk "high" because `main` is the first step of seven flows.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 51 files |
| `uv run pytest -m "not archives"` (SQLite) | 187 passed, 48 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 244 passed |
| `tests/unit/test_mondo_identifiers.py` (3), `tests/ingestion/test_identifier_links.py` (4) | 7 passed |
| `import-identifiers` on the real data, twice | 745 links, then 0 new and 0 WHO calls; exit 0 both times |

The tests prove: only SNOMED CT and ICD-11 identifiers are read, with MONDO's marks, and all are
counted; an obsolete term's identifiers are not read; the one identifier marked equivalent is
chosen, none when there are several, none when it is broader, related or equivalent to an
obsolete concept; WHO is asked for the official title and the MMS code, only numbers are sent and
an answer is not asked for twice; an entity WHO does not know gives no link; a link is stored
`pending` with no reviewer, names its MONDO term and marks, and a SNOMED CT link says whose name
its title is; a code the name search already stored is not stored again and is noted; the
unspecified sub-code is recognised as the same category; a different code stays beside the new
one; a rejected MONDO link is not used, and pending links that rest on one are reported.

**Bugs.**

- Found by the new database test before any real data was written: the note written onto an
  existing ICD-11 row merged two sets of fields that both have a `code` and a `title`, so MONDO's
  code replaced the ICD-11 code in the note. The two are now kept apart (`icd_code`, `via`).
- The first version reported the 121 unspecified sub-codes as "a different code". The dry run on
  the real data showed what they are; the command now recognises them by WHO's own address of a
  residual sub-code, with a test.

**Limits, stated plainly.**

- Every link here rests on two steps that are both candidates: our label's match to a MONDO term
  (a match of names) and MONDO's statement of equivalence. Nothing is approved.
- If a reviewer rejects a MONDO link, the SNOMED CT and ICD-11 links taken through it are not
  removed by this command; it reports them and fails until M2.5 handles the case.
- SNOMED CT links carry MONDO's name as their title, not SNOMED CT's. The release is not held.
- Of the 594 labels, 67 have no SNOMED CT link and 270 no ICD-11 link through MONDO. Most of
  these are terms for which MONDO lists no identifier (61 and 263); the other 13 cases are listed
  for review in `data/derived/review/mondo_identifiers.csv` (two equivalents, none equivalent,
  or unknown to WHO).
- 388 labels and terms with a link in another vocabulary have no MONDO link and so get nothing here.
- The licence question was decided by the owner (E62). The lists are in the private database and
  a file outside Git, not in the repository.
- `cold` still has no full name: the owner has not answered whether it is "common cold".

**Committed and indexed.** Committed as `e3aaa10` and pushed; CI passed on both jobs. The code
graph was re-indexed at `e3aaa10` and reports up-to-date; both new modules are below the 32 KB
limit. The API and the web app were not restarted: this sub-step changes neither. This paragraph
was added in a following documents-only commit, after which the index was refreshed again.

### M2.17 — Vocabulary links in the review path; the owner's review recorded

Owner's "apply now" of 2026-11-18, for the five labels where the two routes of M2.16 gave
different ICD-11 codes (decision E64). With it the owner gave a written note on how the 121
"unspecified" sub-codes are to be handled and three checks to run first (decision E66).

**What was built.**

- Migration `0008`: the API's database role may read `terminology_links` and change `status` and
  `reviewer`, inside a reviewer transaction only (row-level security). No other column, no
  insert, no delete.
- `models.py`: `TerminologyLink` (appended). `review.py`: the target type `terminology_link`,
  the reviewer set on a decision, a count in the overview, and `list_terminology_links`
  (appended). `main.py`: `GET /internal/v1/review/terminology-links`.
- `identifier_links.py`: the note on a row the name search already held now keeps the foundation
  entity, and a note written by an earlier run is brought up to date (BUG-022).
- `__main__.py`: the closing line of `link-vocabularies` no longer says every link is pending.

**Why the API role now has access, and what guards it.** A decision is recorded through the
review API, which runs as the application role. Before this sub-step that role had no access to
the table. Decision E63 (no code is shown to a user) is kept by row-level security: a
transaction that is not a reviewer's sees no row. `CLAUDE.md` said "has no access; keep it so",
written one sub-step earlier; it now states the real rule.

**The owner's review, recorded** through `POST /internal/v1/review/decisions` as
`dev-reviewer:owner`, each with a note that names decision E64 and says the assistant entered
it on the owner's instruction:

| Label | Approved | Rejected |
|---|---|---|
| eczema | `EA8Z` Dermatitis or eczema, unspecified | the MONDO link to "atopic eczema"; `EA80` Atopic eczema taken through it |
| indigestion (symptom) | `MD92` Dyspepsia | `DD90.3` Functional dyspepsia |
| indigestion (disease label) | `MD92` Dyspepsia | `DD90.3` Functional dyspepsia |
| stye | `9A01.2` Hordeolum | `9A01.20` Hordeolum externum |
| valley fever | `1F25` Coccidioidomycosis | `1F25.00` Acute pulmonary coccidioidomycosis |

11 decisions: 5 approved, 6 rejected. The listing of "indigestion" as a disease is flagged by a
note on its four mappings; no status was changed by it. `terminology_links`: 2,482 pending,
5 approved, 6 rejected. After the decisions `link-vocabularies`, `link-ontologies`,
`import-identifiers` and `suggest-relations` were rerun: no difference reported, nothing
inserted, and `import-identifiers` reports the eczema link as "rejected by a reviewer and not used".

**The three checks of the owner's note on the 121 sub-codes** (read-only script; 108 WHO calls,
entity numbers only):

| Check | Result |
|---|---|
| (a) The hierarchy, from WHO's own parent relation in the same MMS release | For all 121 WHO names the category as the parent of the stored sub-code; both rows are of release 2026-01. Nothing is inferred by cutting a "Z" |
| (b) What MONDO means by each identifier taken | All 745 rows carry `MONDO:equivalentTo`; all 481 SNOMED CT and 193 ICD-11 term and identifier pairs also carry MONDO's `skos:exactMatch`. No close, broad, narrow or related match was taken |
| (c) The foundation-to-MMS step is kept | Kept on all 172 MMS rows (foundation entity, MMS address in 2026-01) and all 46 foundation rows (43 with the MMS code they are counted under; WHO places the other 3 nowhere in MMS). **Missing** from the note on the 106 rows where the name search already had the code: BUG-022 |

**Impact analysis.** `record_review`: 1 caller (`review_decision`), LOW. `overview`: 1 caller,
LOW. `create_app`: 1 caller (`app_factory`), LOW. `import_identifiers`: 1 caller (`main`), LOW.
`main`: 1 caller, LOW. The MCP server does not use the review service. `detect_changes` before
commit rated the set **critical**: 19 symbols in 7 files, 16 flows, among them the app factory
and the review routes. Investigated statement by statement against the last commit: in the
existing functions six statements differ, all intended (`record_review`: one type added to the
reviewer check; `overview`: one count; `main`: one message; `import_identifiers`: the note and
its condition; `create_app`: one route added). The other 19 route functions, `app_factory`,
`review_decision` and all 22 functions of `vocabulary.py` are identical; `REVIEW_STATES`,
`entry`, `stored`, `on_rejected` and the other listed variables are the known line-shift artefact.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 51 files |
| `uv run pytest -m "not archives"` (SQLite) | 189 passed, 49 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 247 passed |
| `uv run pytest tests/mcp` | 5 passed |
| Migration `0008` on a scratch database: head, down to `0007`, head | row security on, 2 policies, readable; off, 0, not readable; on, 2, readable |
| Live API after restart: the new route as a reviewer, as a user, with no token | 200 with 2,493 links; 403; 401 |

The tests prove: links are listed for reviewers only, with our own term, and can be filtered by
vocabulary, kind, status, label, title and code; a decision is stored with the reviewer and a
note and changes nothing else on the row; a user cannot decide a link; outside a reviewer
transaction the API role sees no link and changes none; even inside one it cannot change a code
or a title, nor insert or delete a link; the note on an existing row keeps the foundation entity
and an older note is refreshed.

**Bugs.**

- **BUG-022 — the foundation entity was not kept on rows the name search already held.** M2.16
  stored it on every new row but not in the note it wrote on an existing one (106 rows), nor in
  the note on a sub-code row (121). *Found by* check (c) of the owner's note. *Resolution:* both
  notes carry `foundation_uri`; a note that differs from what the run would write is rewritten;
  a test with an older note. All 106 and 121 notes on the main database were refreshed.
- An older test asserted that the API role has no read privilege on the table. That is what this
  sub-step changes on purpose; the test now asserts the guarantee that remains (row security on,
  no write to code or title, no insert, no delete).

**Limits, stated plainly.**

- The owner's verdicts are naming decisions by the owner, with public health pages as sources
  that the assistant did not open. No clinician has reviewed them (open decision D-C2).
- "Approved" on a link means the owner accepted it as the label's code in that vocabulary. It
  serves nothing to a user: links are internal (E63).
- Rejecting the eczema MONDO link also meant rejecting, by hand, the ICD-11 code taken through
  it. That a rejection carries over by itself is still M2.5.
- The 121 sub-code rows and their categories are all still pending; the owner's rule (E66) says
  which is the identity, and approval is M2.5.
- The pending suggestion "rift valley fever is a subtype of valley fever" is wrong (different
  diseases) and was not decided: the owner has not ruled on it.
- The decisions live in the database and in the review notes, not in a file: a rebuilt database
  would need them entered again from decision E64.

**Committed and indexed.** Committed as `c5b6f26` and pushed; CI passed on both jobs. The code
graph was re-indexed at `c5b6f26` and reports up-to-date. Migration `0008` was applied to the
main database, and the API on port 8000 was restarted so that it serves the new route. This
paragraph was added in a following documents-only commit, after which the index was refreshed
again.

### M2.13a — The answers behind archive 15's questions that are not yes/no

Owner's go-ahead of 2026-11-19 ("proceed ahead") after confirming the M2.17 tests. M2.13 was
split in two because its halves are independent and each is large; this is the first half. In
the same message the owner described Rift Valley fever; the wrong suggestion that it is a
subtype of valley fever was rejected through the review path under the owner's identity (E69).

**What was built.**

- Migration `0009`: table `case_answers` (case, question mapping, answer, the release as source,
  release split, release row). Import-only: the application role has no access.
- `release_answers.py`: `answers_in`, `load_answers`, `check`. New command
  `python -m feeltriva_ingestion load-answers`.
- `release.py` is unchanged; its `open_release`, `read_dictionary`, `release_keys`, `file_keys`
  and `trace` are reused.

**How it works.** Each of our two files is traced to the release again, exactly as in M2.12, and
the result must equal the trace `load-release` stored; otherwise nothing is written. For every
traced row the release's evidence list is read and each answer to one of the 15 questions is
stored as written (`V_112`, or a number such as `6`). The archive's 0/1 values are not touched.

**The check, against the files and not against the database.** For every row, the set of those
15 columns that hold a 1 in our file must equal the set of those questions that have an answer
in its release row; every answer must be one the publisher's dictionary lists; what is stored
must equal what was read.

**Real run** (`load-answers`, 4,722 seconds):

| | `train.csv` | `test.csv` | Both |
|---|---:|---:|---:|
| Rows (cases) | 475,502 | 134,529 | 610,031 |
| 1s in the 15 columns of our file | 3,376,591 | 985,326 | 4,361,917 |
| Of them answered in the release row | 3,376,591 | 985,326 | 4,361,917 |
| Answers stored | 5,437,674 | 1,589,199 | 7,026,873 |
| Answers that are the publisher's default | 1,013,554 | 291,931 | 1,305,485 |
| Answers not among the possible ones | 0 | 0 | 0 |

**What the answers show.** A 1 in these columns does not mean yes. "Have you traveled out of
the country in the last 4 weeks?" has a 1 for all 610,031 cases; the answer is "N" for 563,857
of them. 1,305,485 of the stored answers (18.6%) are the publisher's default: "nowhere", "N",
"NA" or 0. This is what M2.12 predicted from the dictionary and M2.7 from the data; it is now
measured. Anything that reads these columns as symptoms that are present would be wrong.

**Impact analysis.** `trace` and `open_release`: 1 caller each (`load_release`), LOW; both are
called unchanged. `main`: 1 caller, LOW. `detect_changes` before commit: `main` only, summary
risk "high" because it is the first step of seven flows; compared with the last commit, one
command branch was added, the other 16 are identical, and all 12 functions of `release.py` are
identical.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 52 files |
| `uv run pytest -m "not archives"` (SQLite) | 191 passed, 50 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 250 passed |
| `uv run pytest tests/mcp` | 5 passed |
| Migration `0009` on a scratch database: head, down to `0008`, head | table present, absent, present; never readable by the API role |

The tests prove: answers are read as written and yes/no items are left out; every kind of gap
is reported; nothing is written before the files have been traced by `load-release`; each
answer is stored with the release as its source and the split and row it came from, also where
our file takes its rows from the release's validation set; a case with two answers to one
question keeps both; the publisher's default answer is kept; no 0/1 value is stored or changed;
a second run inserts nothing.

**Bugs and what the real run taught.**

- Found by the new database test: run before `load-release`, the loader failed on a missing
  source row. It now writes nothing in that case and says which command to run first.
- **The write is slow: 79 minutes, of which about 3 are reading.** Seven million rows are
  inserted in random key order with three foreign-key checks each, and the checks run at the end
  of the statement (the table stopped growing long before the statement ended).
- **A freshly loaded table has no statistics.** A count that takes 2.6 seconds after `ANALYZE`
  ran for more than five minutes before it; three exploratory queries had to be cancelled. The
  loader now runs `ANALYZE case_answers` after its inserts. The same cause explains two slow
  queries on `case_features` earlier in this session, which was last analysed after M1.8.

**Limits, stated plainly.**

- These are answers of simulated patients (E55).
- Answers are stored as codes; what a code means (`V_10` is "N") is in the question dictionary
  on the mapping. No view yet joins the two for a reader.
- `completeness` does not cover `case_answers`; the loader's own check does.
- The archive's 1 is still stored as `present` in `case_features` for these 15 columns. Reading
  it as "symptom present" is wrong for them; modelling (M4.3) must take the answer.
- A fresh load takes about 80 minutes. Inserting in key order would likely shorten it; that was
  not tried, so that the committed code is the code that produced the data.
- The second half of M2.13 (the publisher's knowledge per condition) is not started.

**Committed and indexed.** Committed as `ea0c134` and pushed; CI passed on both jobs. The code
graph was re-indexed at `ea0c134` and reports up-to-date. Migration `0009` is applied to the main
database. The API and the web app were not restarted: this sub-step changes neither. A second
real run of `load-answers`, to confirm on the real data that a rerun adds nothing, was started
after the commit and was still in its write statement when this paragraph was written; the
crafted test proves the same on a small release. This paragraph was added in a following
documents-only commit, after which the index was refreshed again.

### M2.13b — What the source release says about each condition

Owner's go-ahead of 2026-11-19. In the same message the owner parked the medicines data (Step
D) and chose to leave the scraper repository as it is.

**What was built.**

- `release_conditions.py`: `load_conditions`, `check`. New command
  `python -m feeltriva_ingestion load-conditions`. No migration.
- `vocabulary.py`: the self-check of `link-vocabularies` asks for an address only on the
  vocabularies that command writes (one statement), because a source's own code can come
  without one.

**What is stored, and as what (decision E70).** From `release_conditions.json`, for each of the
49 conditions: a source record; a `pending` evidence row per listed question; the ICD-10 code
as a `pending` link written exactly as the publisher writes it; severity and names on the
release's source row. The publisher's README was read for the meaning of the fields: severity
is "the severity associated with the pathology. The lower the more severe"; the ICD-10 edition
is not stated.

**Real run** (`load-conditions`, 142 seconds; a second run inserted nothing):

| | Count |
|---|---:|
| Conditions, each matched to one disease candidate | 49 |
| Source records | 49 |
| Questions listed as symptoms / as antecedents | 605 / 283 |
| Evidence rows, all pending | 888 (49 diseases, 223 features) |
| ICD-10 links, all pending, no address | 49 |
| Severity level 1 / 2 / 3 / 4 / 5 | 5 / 12 / 17 / 12 / 3 |

Two listings disagree with the publisher's own dictionary and are kept as listed: question
`E_16` is listed among the symptoms of "PSVT" and of "Panic attack", and the dictionary calls
it an antecedent. One code, `g44.009`, is lower case and has a form no WHO ICD-10 code has; it
is stored as written.

**Impact analysis.** `link_vocabularies`: 1 caller (`main`), LOW. `main`: 1 caller, LOW.
`store_links`: HIGH for a change (three commands depend on it since M2.16); it is called and
not changed. `open_release`, `read_dictionary`: called unchanged. `detect_changes` before
commit: `main` and `link_vocabularies`, both intended, summary risk "high" for the number of
flows they start. Compared with the last commit: one statement of `link_vocabularies` differs,
its other 21 functions (with `store_links`) and all 12 of `release.py` are identical, and one
command branch was added to `main` while the other 17 are identical.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 53 files |
| `uv run pytest -m "not archives"` (SQLite) | 192 passed, 52 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 253 passed on the final run; see below for two earlier runs |
| `uv run pytest tests/mcp` | 5 passed |
| `load-conditions`, `link-vocabularies`, `suggest-relations` after the load | no difference reported; nothing inserted on the second run |

The tests prove: every kind of gap is reported; nothing is written before `load-release` has
registered the release; evidence rows are pending, of the one type, and point at the record of
the condition entry they came from; a question listed against the dictionary is kept as listed
and reported; a code is stored as written, with no address and no reviewer; severity and names
are kept on the release's row; a second run inserts nothing; a condition that is no label of
ours is reported and nothing is stored for it; a link that already exists is found and is no gap.

**Bugs, and two full-suite runs that did not pass.**

- Found by the new tests: conditions were looked up through `disease_mappings`, but a case's
  disease comes from its case label. The lookup now uses the labels of the described files' cases.
- **First failing full run: my own new test.** The check counted the ICD-10 links "of this
  release", but a link is one disease, one vocabulary and one code: when an earlier run had
  stored the same code, nothing new was stored and the check reported a gap. The check now looks
  for the links themselves; a test covers a link that already exists.
- **Second failing full run: `tests/mcp/test_mcp_parity.py::test_full_flow_gives_identical_results_over_rest_and_mcp`,
  once.** It passed alone four times (with and without this sub-step's changes) and in the next
  full run. The database was under heavy load from another job at the time. Its error text was
  not captured. Recorded as an intermittent failure to watch, not as fixed.

**Limits, stated plainly.**

- These lists were written to generate simulated patients. They are stored as a source's
  statement and are not reviewed knowledge.
- Severity is the publisher's label. It is not used anywhere and is not an urgency rule.
- The ICD-10 links have no address and no official title; the edition is not known.
- The second real run of `load-answers` (M2.13a), started to confirm that a rerun adds nothing,
  was still in its write after more than an hour: a rerun of that loader costs about as much as
  the first load. Its result is reported when it ends.
- `__main__.py` is now 27 KB; the code index cannot read a file above 32 KB, so the next
  command should go with a split of that file.

**Committed and indexed.** Committed as `a349397` and pushed; CI passed on both jobs. The code
graph was re-indexed at `a349397` and reports up-to-date. The API and the web app were not
restarted: this sub-step changes neither. The second real run of `load-answers` had finished its
larger file and was writing the smaller one when this paragraph was written. This paragraph was
added in a following documents-only commit, after which the index was refreshed again.

**M2.13a, the second real run of `load-answers`: result.** Finished with exit 0 after 5,740
seconds (96 minutes; other work was using the database for part of that time). Inserted 0 for
`train.csv` and 0 for `test.csv`; stored totals unchanged (5,437,674 answers in 3,376,591 cells
of 475,502 cases, and 1,589,199 in 985,326 of 134,529); the self-check passed. So a rerun adds
nothing on the real data, and it costs as much as the first load: every one of the 7 million
answers is offered to the table again and refused one by one. Left as it is. If the loader is
to be rerun routinely, it should first compare what is stored with what it read and skip the
write when they agree; that is a change of its own and has not been made.

### M2.6 — Single claims from the narrative statements, in the review queue

Owner's go-ahead of 2026-11-19 ("proceed with M2.6").

**What the handoff asks, checked before the work.** "Extract atomic claims only into a review
queue" (`docs/01`); for the symptom statements "narrative claim first; extract atomic feature
relations into review queue" (`docs/04`); "atomic statement extraction into pending status,
with source spans and URLs" (`docs/05`); the reviewer's view shows "original statement, source
URL/locator, proposed atomic claim, applicability, status" (`docs/06`). The figures cross-check
had assigned the empty applicability to this sub-step.

**What was built.**

- `claims.py` (pure rules): `sentences`, `list_items`, `cues`, `split`, `item_name`.
- `claims_load.py`: `extract_claims`, `check`, `report`. New command
  `python -m feeltriva_ingestion extract-claims`.
- Migration `0010`: table `statement_claims` (statement, kind, the two offsets, the text, the
  rule, wording cues, a proposed feature, applicability, review status). Import-only.
- Completeness check: `_claims` recomputes the claims of the symptom statements by the rules and
  compares them with what is stored; the line that said "not started" became two checks. The
  remaining narrative item (statements from the text files, after their review) is now listed
  under the approval workflow.

**What a claim is (decision E71).** A piece of a stored statement between two offsets, never new
wording: every sentence, and each item of a sentence that is plainly an enumeration with a
lead-in. A list item of a symptom statement that is exactly the name of one feature carries
that feature as a proposal. No language model is used. Nothing is written to the evidence table.

**The rules were set by reading real results, in three rounds of a read-only dry run:**

| Round | Enumerations | List items | What reading a sample showed, and the change |
|---|---:|---:|---|
| 1 | 806 | 3,378 | "Severe dengue is a life-threatening emergency, requiring hospitalization and ..." cut into three items. "is"/"are" now introduce a list only for a plural of listed things and not before a verb form |
| 2 | 654 | 2,818 | "red, itchy, and watery eyes" broken up; a list ending "A and B such as C or D" split at the wrong word. Two guards: a list inside the list, and an unclear end |
| 3 | 625 | 2,651 | An adverb after "are"; "as well as" at the start of an item. Two small rules |
| stored, then read again | 623 | 2,646 | "coma; death can ensue" kept as the last item; a label "B:" taken for a lead-in. A semicolon now divides the sentence; a colon needs three words before it. The 8,856 unreviewed claims were deleted and made again |

**Real run** (`extract-claims`, 3 seconds; a second run inserted nothing):

| Statement type | Statements | Sentences | Enumerations | List items |
|---|---:|---:|---:|---:|
| description | 905 | 4,120 | 487 | 2,017 |
| cause | 714 | 729 | 40 | 184 |
| symptom | 712 | 727 | 69 | 352 |
| treatment | 621 | 634 | 29 | 99 |
| all | 2,952 | 6,210 | 625 | 2,652 |

8,862 claims, all pending, each exactly its statement's text at its offsets; the sentences hold
all the text of every statement. 3,065 sentences with a comma were left whole, and why is
counted (no final "and"/"or" 1,553; no lead-in 1,250; an item too long 110; unclear end 85;
fewer than three items 38; a list inside the list 19; an item beginning like a clause 17).
Sentences carrying a wording cue: hedge 2,716, negation 654, a group of people 364. Of the 352
list items of symptom statements, 113 are exactly the name of one feature and carry it, 8 fit
several features and carry none, 231 fit none.

**Read by hand.** Of 30 stored split sentences drawn at random (before the last two rule
changes), 26 were right and 4 wrong or partly wrong; the last two rules fix 2 of those. What
remains: adjectives that share one noun ("flaky, scaly, greasy, and ... itchy and inflamed
skin") and a list nested in another ("..., such as in cataract surgery, a perforating wound or
ulcer, or congenital anomaly"). About 2 in 30.

**Impact analysis.** `gather`: 1 caller, LOW. `main`: 1 caller, LOW. `_statement_file`: **HIGH**
(1 caller, `emit`; reached from `run_completeness` and `main`; 3 flows). Reported to the owner
before editing, with the plan per caller: `emit` unchanged; the full completeness run must still
pass; `main` gets one branch. `_texts`: **HIGH** for the same reason; its one changed argument
(the owner label of an item that stays deferred) was edited before its impact analysis was run,
which was then run and is recorded here as a slip in the process. `detect_changes` before commit:
`main`, `gather`, `_statement_file` and the updated test, summary risk "high"; `_acceptance` and
the variables it listed are the line-shift artefact. Compared with the last commit: in
`_statement_file` one statement was removed and three added; in `gather` one; in `_texts` one;
in `main` one command branch was added and the other 18 are identical; `evidence.py` and
`vocabulary.py` are untouched.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 55 files |
| `uv run pytest -m "not archives"` (SQLite) | 201 passed, 54 skipped |
| `uv run pytest` on PostgreSQL, real archives and object store included | 264 passed |
| `uv run pytest tests/mcp` | 5 passed |
| Migration `0010` on a scratch database: head, down to `0009`, head | table present, absent, present; never readable by the API role |
| `completeness` on the real data, after the final rules | 236 checks, 230 ok, 0 mismatches, 6 left to later (2,257 s); claims of the symptom statements: 1,079 expected, 1,079 stored |

The tests prove: the sentences hold all the text and keep their offsets; an abbreviation, a
single letter and a full stop inside brackets do not end a sentence; an enumeration gives one
claim per item, with brackets kept in the item; the list starts at the last lead-in that leaves
three items; "is"/"are" only for a plural of listed things; every reason for leaving a sentence
whole; a semicolon divides the sentence; a short label before a colon is no lead-in; cues are
read from the wording; a list item belongs to its sentence; claims are stored pending with
span, rule, cues and source; a feature is proposed only for an exact, single name; a second run
stores nothing and a reviewer's decision stays; a claim that is no longer its statement's text
is reported; the completeness facts notice a missing claim, a changed one and an unsigned decision.

**Bugs.** None in committed code. One existing completeness test built its input by hand
without the new facts and was updated; it now also covers the two new checks.

**Limits, stated plainly.**

- The rules know nothing about medicine. About 2 in 30 split sentences are split wrongly; every
  item is pending and its whole sentence is kept beside it.
- Most sentences with a comma are left whole (3,065). That is by design: a sentence left whole
  loses nothing.
- Two-item lists ("A and B") are not split.
- Applicability is still empty everywhere: the cues say what the wording contains, and a
  reviewer decides.
- No reviewer route for claims yet: they can be read with SQL; the screens and their route are
  M2.4. Approval, and writing an approved claim to evidence, are M2.5.
- The claim rules carry a version (`claims-1`). If they change after claims have been reviewed,
  the reviewed claims stay and the completeness check will list them as not made by the rules;
  how to carry decisions across a rule change is not built.
- The full completeness check now takes 14 to 38 minutes on this machine, depending on what
  else uses the database.

**After the commit: CI failed on `8bb8039`, and why (BUG-023).** The web job passed. The backend
job failed in its PostgreSQL step: 1 failed, 253 passed, 1 skipped. The failing test was the new
`test_claims_are_stored_pending_with_their_span_their_sentence_and_a_feature_named_exactly`: it
expected two sentences from its symptom statement and got one.

- **Cause.** The test's sentence ends in a random ten-character tag, in that run `b7c75f794f`.
  To decide whether a full stop ends a sentence, `sentences` looked at the letters just before
  it. It took only the last run of letters, here the "f" after "794", for a single-letter word
  such as the "B." of a species name, and did not end the sentence. The same happened for a
  token ending in "ca" or "cf" after a digit, which are in the list of abbreviations. The rule
  was wrong, not only the test: "form 2a." or a laboratory name written with a digit and a final
  letter would also have kept two sentences together.
- **Why it was not seen locally.** The tag is random. The test fails for about one tag in four
  (a digit followed by one last letter). The local runs before the commit happened to draw other
  tags. Reproduced afterwards with CI's exact sentence: one sentence instead of two.
- **Resolution.** One pattern in `claims.py`: the word before a full stop counts only when no
  letter or digit stands directly before it. A letter standing alone and a real abbreviation
  still do not end a sentence. A unit test was added at the end of `tests/unit/test_claims.py`
  with CI's sentence, three more tokens of that shape and four cases that must stay one sentence.
  The test sentence of the loading test was then tried with 339,808 tags (every ending of one
  to four characters and 200,000 random ones): two sentences and three items every time.
- **Effect on the stored claims: none, measured before the edit.** A read-only run cut all
  2,952 stored statements by the old pattern and by the new one: 0 statements differ, 8,862
  claims either way. After the edit `extract-claims` inserted nothing (8,862 rows, all pending);
  the claims part of the completeness check gives 1,079 expected and 1,079 stored for the
  symptom statements; over all statement types the claims by the rules and the stored claims
  are the same 8,862. The rule version stays `claims-1`: no stored claim differs and none has
  been reviewed. The full completeness check (14 to 38 minutes) was not run again; its claims
  part was run directly on the real data, and nothing else it reads has changed.
- **Impact analysis.** `sentences`: **CRITICAL** (1 direct caller, `split`; 5 flows; reached from
  `extract_claims`, from `_claims` and `gather` of the completeness check, and from `main`).
  Reported to the owner before the edit with the plan per caller: no caller changes, and each
  must give the same result on the real data, which was measured as above. `detect_changes`
  before commit: risk low, one symbol listed, `_STRONG`, the pattern defined directly below
  the changed one; its text is identical in the diff (the known line-range artefact).
- **Tests actually run after the fix.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 55 files |
| `uv run pytest -m "not archives"` (SQLite) | 202 passed, 54 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 265 passed |
| the same without the object store variable | 264 passed, 1 skipped (the real-store test) |

- **A limit this shows, measured on the stored statements.** A letter standing alone before a
  full stop never ends a sentence, and neither does a listed abbreviation. That was meant for
  names such as "B. Example" and for "No. 4". Counted read-only over the 2,952 statements: a
  single letter keeps a full stop inside a sentence 8 times, and all 8 are real sentence ends
  ("types A, B, C, and D.", "vitamin C.", "mmol/L." twice, "mEq/L.", "40 °C.", "lower case d.",
  "A, B, C, D, and E."); an abbreviation does so 5 times, 3 rightly ("No. 4", "No. 202", "i.e.
  ENT") and 2 wrongly ("symptoms of MS.", "tongue, etc."). So 10 pairs of sentences out of
  6,210 sentences are kept together as one claim. Nothing is lost and all are pending. It is
  not changed here: a change would alter the stored claims of those statements, and that is the
  owner's decision (a small follow-up: a single capital or a unit before a full stop ends the
  sentence when a new sentence plainly follows; the claims of about 10 statements made again).

**Committed and indexed.** M2.6 is two commits. `8bb8039` holds the sub-step; CI failed on it
in the backend job's PostgreSQL step (BUG-023, above), the web job passed. `1aa2ef8` holds the
correction; CI passed on both jobs (run 44670136494). A pushed commit is not rewritten, so the
correction is a second commit and not an amended first one. The code graph was re-indexed at
`1aa2ef8` and reports up-to-date. The API and the web app were not restarted: this sub-step
changes neither. Migration `0010` is applied to the main database. This paragraph was added in a
following documents-only commit, after which the index was refreshed again.

### M2.6a — Sentence ends after a single letter or an abbreviation; claims made again after a rule change

Owner's go-ahead of 2026-11-20: "We will follow your recommendation" on the 10 pairs of sentences
that M2.6 measured as kept together, after the owner had run the six M2.6 tests with the
expected results.

**What changed.**

- `claims.py`: `sentences` asks a new function `_continues` whether a full stop belongs to an
  abbreviation or an initial. A single capital is taken for an initial ("J. Example") unless it
  is plainly something else: a lower-case letter, the end of a unit or label joined by "/" or
  "°", the last of a series after "and" or "or", or a label after a word that takes one
  (`_LETTERED`: vitamin, type, hepatitis, group, stage and the like). A listed abbreviation
  written all in capitals is an acronym and ends the sentence. "etc" left the list of
  abbreviations. The rules are `claims-2`.
- `claims_load.py`: `extract_claims` has a `remake` option and a helper `_earlier`. A statement
  holding a claim the rules do not give gets nothing added and is reported. With `--remake` its
  claims are deleted and made again, unless a reviewer has decided on one of them. `check`
  reports both cases; `report` prints one more line.
- `__main__.py`: the option `--remake` (28.4 KB; the index limit is 32 KB).
- Decision E72 records the rules. Nothing else in the schema, the API or the web app changed.

**The rule was set on the real data first, read-only.** The proposed rule was run beside the
stored one over all 2,952 statements: 9 statements change, covering the 10 sentence ends, and
each change was read. After the code was written, the implemented rule and the dry-run version
gave the same claims for every statement.

| Sentence end now recognised | Real case |
|---|---|
| a label after a word that takes one | "... a lack of vitamin C. Early symptoms ..." |
| the last of a series | "... types A, B, C, and D. Aquatic birds ...", "... A, B, C, D, and E. HDV is ..." |
| a unit or label joined by a sign | "... 135–145 mmol/L. Hypernatremia ...", "... above 145 mmol/L. Severe ...", "... below 120 mEq/L. Symptoms ...", "... to 40 °C. Symptoms ..." |
| a lower-case letter | "... a lower case d. It later ..." |
| an acronym in capitals | "... symptoms of MS. Roughly 65% ..." |
| "etc." before a capital | "... the lips, tongue, etc. The study ..." |

Still kept inside their sentence, all rightly: "world No. 4", "No. 202", "i.e. ENT".

**Real run.**

| Step | Result |
|---|---|
| `extract-claims` with the new rules, before any remake | inserted 0; "12 stored claims in 9 statements that the rules do not give" (9 joined sentences and 3 list items whose sentence changed); 2 differences, exit code 1, as intended |
| `extract-claims --remake` | 9 statements made again: 58 claims deleted, 80 stored; 0 differences |
| `extract-claims` again | inserted 0, nothing to make again, 0 differences |

| | Before | After |
|---|---:|---:|
| claims, all pending | 8,862 | 8,884 |
| sentences | 6,210 | 6,220 |
| list items | 2,652 | 2,664 |
| enumerations | 625 | 628 |
| list items carrying a proposed feature | 113 | 113 |

Three sentences that now stand alone are enumerations: "A | B | C | D | E" (hepatitis
viruses), "types A | B | C | D" (influenza) and "absent | mild | severe". The 80 new claims carry
`claims-2` (41 sentences, 39 list items); the other 8,804 are what `claims-2` gives too and keep
`claims-1`, the label they were made under. Checked read-only afterwards: the claims the rules
give and the stored claims are the same 8,884; no list item lies outside its own sentence; no
claim has a reviewer or a decision.

**Impact analysis.** `sentences`: **CRITICAL** (1 direct caller, `split`; 5 flows; reached from
`extract_claims`, from `_claims` and `gather` of the completeness check, and from `main`).
Reported to the owner before the edit with the plan per caller: no caller changes its code; the
results change for the 9 statements only, which is the purpose, and stored claims and rules are
compared afterwards for every statement. `extract_claims`, `check`, `report` and `main`: LOW,
one caller each. `detect_changes` before commit: 13 symbols, summary risk "high" by count (`main`
starts many flows). Compared with the last commit statement by statement: changed are `main`
(one option added, one call), `sentences`, `_ABBREVIATIONS`, `VERSION`, `extract_claims`,
`check` and `report`; added are `_continues`, `_LETTERED`, `_PREVIOUS_WORD` and `_earlier`.
`_BOUNDARY`, `started`, `entries`, `params`, `app`, `database_url` and `scope` are listed
although identical (the line-range artefact).

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 55 files |
| `uv run pytest -m "not archives"` (SQLite) | 203 passed, 55 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 267 passed |
| `completeness` on the real data, after the remake | 236 checks, 230 ok, 0 mismatches, 6 left to later (464 s); claims of the symptom statements: 1,080 expected, 1,080 stored |

The two new tests prove: each of the six kinds of sentence end, with invented sentences; an
initial and an abbreviation written as one still do not end a sentence; a series becomes a
list once its sentence ends where it should; claims of earlier rules are found by span, text
and sentence; nothing is added to a statement that holds one; `--remake` deletes and stores
again; a statement with a reviewer's decision is left, also with `--remake`; a claim the newer
rules give unchanged keeps its label; a further run changes nothing.

**Bugs.** None found in this sub-step.

**Limits, stated plainly.**

- The words after which a letter is a label are a short list. A sentence ending in a capital
  letter after another word ("... called plan B. Then ...") is still joined to the next one;
  none is in the stored statements.
- A person's initial after "and" or "or" ("... and J. Example ...") would now end a sentence
  wrongly. None is in the stored statements.
- "No." before a capital or a digit never ends a sentence, so "... the answer was no. Then ..."
  stays joined. None is in the stored statements.
- The wrong splits of M2.6 remain (about 2 in 30 split sentences), for example "Legionella may
  occur with abdominal pain | diarrhea | confusion". This sub-step changed sentence ends only.
- `--remake` never touches a reviewed statement, so after reviews begin a rule change leaves
  such statements on the earlier rules and the command reports them as a difference each run.
  Carrying a decision over is M2.5 (added to its row).

**Committed and indexed.** Committed as `f5f3528` and pushed; CI passed on both jobs (run
44675052520). The code graph was re-indexed at `f5f3528` and reports up-to-date. The API and
the web app were not restarted: this sub-step changes neither. No migration. This paragraph was
added in a following documents-only commit, after which the index was refreshed again.

### M2.6b — Wrong lists and the remaining sentence ends corrected

Owner's instruction of 2026-11-20 on the two limits reported after M2.6a: "Fix these" (the wrong
splits; the sentence ends the rule still got wrong). Done as one sub-step because both change
the claim rules and need one remake.

**Every stored list was read, not a sample.** M2.6 had estimated "about 2 in 30" from a
hand-read of 30. All 628 stored lists were written out with their items marked in place and
read. 59 were plainly wrong (9%), so the estimate was too low. What was found:

| What was wrong | Example (items between bars) | Lists |
|---|---|---:|
| An item only goes on with the item before it | heart failure \| due to dilated cardiomyopathy \| cardiac arrest | 13 |
| Describing words that share the noun of the last item | a red \| warm \| swollen \| painful leg | 9 |
| The last item runs on into the rest of the sentence | ... \| feeling tired may develop | 9 |
| A middle item only says more about the item before it | fever \| often greater than 40 °C (104 °F) \| cough | 7 |
| An item is a whole clause | Legionella may occur with abdominal pain \| diarrhea \| confusion | 4 |
| An item begins with a preposition or "to" among items that do not | difficulty walking \| speaking \| with sensations | 6 |
| "between ... and", "either ... or" read as the end of a list | the valve between the stomach \| the duodenum | 4 |
| An item is only a joining word | fever \| and \| less commonly \| seizures | 3 |
| The list began at a lead-in inside an item | (a round red face due to) facial plethora \| a fat lump ... | 2 |
| An unclosed bracket; a remark after a dash | artificial UV radiation (e.g | 2 |

**What changed in `claims.py`.**

- `_enumeration`: the last "and"/"or" after "between", "either", "both" or "whether" is no list
  end; "is"/"are" is no lead-in in a sentence that opens with "although", "though", "while" or
  "whereas"; the first lead-in that gives a list is taken, and the list after a lead-in inside
  an item is preferred when there is one; the items are tested by the new `_checked`.
- `_checked` (new, with `_clause_at` and `_words`): the tests of the table above, each with a
  closed word list. The last item ends before a remark after a dash, and before the verb that
  follows a list which can be the subject of its sentence (after "such as", "including",
  "which includes"). After "include" or "are" a verb after the last item refuses the list.
- `_continues` and `sentences`: the text after the full stop is looked at too. A single capital
  ends the sentence before a word that opens a sentence and is never a name ("plan B. Then"),
  after a common word in lower case ("plan B. Aquatic ..."), and as the last of a series of
  letters; it does not after "by", "of", "from" and the like, after "and"/"or" when no series
  stands before ("Smith and J. Example"), or beside another initial. "No." is the abbreviation
  only before a digit.
- The rules are `claims-3`. The module is 25.1 KB; the index limit is 32 KB, so the next change
  to these rules should come with a split into two modules.

**The rules were corrected twice after reading what they did, before any data was touched.**
A read-only run compared the new rules with the stored claims for every statement and wrote
out every list that was dropped, changed or added; all were read.

- The first version refused "is"/"are" as a lead-in after any opening "If", "When" or
  "Although". That dropped a right list ("If this progresses to severe dengue the symptoms are
  ..."). Narrowed to "although", "though", "while", "whereas".
- The first version cut a verb after the last item of every list. That added two wrong lists:
  "Symptoms include eye pain, eye redness, floaters and blurred vision, and ophthalmic
  examination may show ..." made "ophthalmic examination" a symptom. The cut is now made only
  where the list can be the subject of the sentence.
- One existing unit test pinned "the list starts at the last lead-in". Its case (an item holding
  one example, "a scarf such as wool") still gives the same list; the comment was corrected.

**Real run.**

| Step | Result |
|---|---|
| `extract-claims`, before any remake | 26 list items added to 7 statements whose stored claims all still hold (7 new lists); "193 stored claims in 61 statements that the rules do not give"; 1 difference, exit code 1, as intended |
| `extract-claims --remake` | 61 statements made again: 531 claims deleted, 355 stored; 0 differences |
| `extract-claims` again | inserted 0, nothing to make again, 0 differences |

| | Before | After |
|---|---:|---:|
| claims, all pending | 8,884 | 8,734 |
| sentences | 6,220 | 6,220 |
| list items | 2,664 | 2,514 |
| lists | 628 | 585 |
| list items carrying a proposed feature | 113 | 106 |

Of the 628 lists: 48 wrong ones are no longer split (the sentence stays whole), 11 are corrected
(9 last items shortened, 2 lists now begin where they should), 2 mostly right ones are no longer
split, and 7 right ones are new. Checked read-only afterwards: the claims the rules give and
the stored claims are the same 8,734; none of 47 marker texts of the wrong lists is stored any
more; no list item lies outside its own sentence; no claim has a reviewer or a decision. The
sentences of all 2,952 statements are the same as before: the new sentence-end rules change
none of the stored statements. 381 claims in 68 statements carry `claims-3`; the others are
what `claims-3` gives too and keep the label they were made under.

**Impact analysis.** `_enumeration`: **HIGH** (1 direct caller, `list_items`; reached from
`split`, `extract_claims` and the completeness check). `_continues`: **HIGH** (1 direct caller,
`sentences`). `sentences`: **CRITICAL**. Reported to the owner before the edit with the plan
per caller: no caller changes its code; results change only where the rules decide differently,
and every such list was read before the remake. `detect_changes` before commit: 14 symbols,
summary risk "high" by count. Compared with the last commit: changed are `VERSION`,
`_CLAUSE_START`, `_continues`, `_enumeration` and `sentences`; 29 names are new; `list_items`,
`MAX_ITEM_WORDS`, `MIN_WORDS_BEFORE_COLON` and `_NEGATION` are listed although identical (the
line-range artefact). In the test file four tests are new and no existing test changed its code.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 55 files |
| `uv run pytest -m "not archives"` (SQLite) | 207 passed, 55 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 271 passed |
| the two loader test sentences with 339,808 tag endings each | the expected sentences and items every time |
| `completeness` on the real data, after the remake | 236 checks, 230 ok, 0 mismatches, 6 left to later (697 s); claims of the symptom statements: 1,040 expected, 1,040 stored |

The four new tests prove, with invented sentences: each kind of refused list and its reason;
the look-alikes that stay lists (a frequency word before an item, a list of places, an item
with its own "that is", a list of colours, "If ... the symptoms are"); the first lead-in, and
the list after a lead-in inside an item; the last item ending before the sentence's verb or a
dash remark, and still being the statement's own text at its offsets; the new sentence ends and
the initials that do not end a sentence.

**Bugs.** None in committed code. The two faults of the first version of the rules were found
in the read-only run and corrected before the remake (described above).

**Limits, stated plainly.**

- 19 of the 585 lists are still imperfect, in ways wording alone cannot tell: 15 where the
  first item carries words the others share ("infection with viruses | bacteria | fungi |
  parasites", "injury to the tibia | femur | knee ligaments"), and 4 others (a chain of
  explanations read as a list, "certain liver | kidney | hereditary disorders", a list at the
  end of a source text that was cut off, and places listed inside one item).
- Two mostly right lists are no longer split ("... such as from lung, breast, thyroid, kidney
  and prostate"; "feeling tired, weak, short of breath, or having decreased ability to
  exercise"). Their sentences stay whole.
- The word lists are closed. New text will bring describing words, verbs after a list and
  continuing words that are not in them; such lists will be split wrongly until the lists are
  extended, and only reading finds them.
- The sentence rule still cannot tell every initial from a label: "The bacterium B. Example"
  stays one sentence only because "bacterium" is in a short list, and "Plan B. Aquatic ..." at
  the start of a sentence stays joined.
- Every item of every list is still pending, with its whole sentence beside it.

**Committed and indexed.** Committed as `5043c13` and pushed; CI passed on both jobs (run
44691863751). The code graph was re-indexed at `5043c13` and reports up-to-date. The API and
the web app were not restarted: this sub-step changes neither. No migration. This paragraph was
added in a following documents-only commit, after which the index was refreshed again.

### M2.6c — What was left of the wrong lists: fixed where wording can tell, marked where it cannot

Owner's question of 2026-11-20 on the four limits reported after M2.6b: "Are the above issues
not fixed??". They were not: they were what remained. This sub-step fixes the parts that have a
sign in the wording and marks the rest for the reviewer. M2.10 was not started.

**What each limit turned out to be.**

| Limit reported after M2.6b | What was done |
|---|---|
| Two mostly right lists no longer split | Both are lists again: "lung \| breast \| thyroid \| kidney \| prostate" and "feeling tired \| weak \| short of breath \| having decreased ability to exercise" |
| A list at the end of a source text that was cut off ("... and a family") | The cut is recognised and the fragment is not kept |
| Places listed inside one item ("fat pads along the collarbone \| on the back of the neck \| on the face") | No longer split |
| Lists whose other items share the first words of the first item ("infection with viruses \| bacteria \| fungi") | Not decidable by wording; marked for the reviewer |
| Closed word lists; "Plan B. Aquatic ..." against "John F. Example ..." | Limits of any wording rule; unchanged and said so |

**Measured before deciding.**

- Every description of `diseases_main.csv` has exactly 120 words (85 statements; 79 end without
  a full stop, 6 happen to end with one). The source cuts its texts at 120 words. No other
  stored statement has 120 words and no full stop, and the 138 other statements that end
  without a full stop are short phrases, not cut texts. So "exactly 120 words and no full stop"
  finds the cut texts and nothing else. One cut-off last sentence holds a list.
- 79 of the 585 lists had a first item that holds a preposition. "infection with viruses,
  bacteria, fungi" and "loss of appetite, nausea, vomiting" are worded alike, so no rule can
  tell which lists share the first words. M2.6b had counted 15 such lists; reading the lists
  that are now marked found 21, and 3 more that the mark does not catch. The count of 15 was
  too low.

**What changed.**

- `claims.py`, `_checked`: a preposition at the start of the first item, when no other item
  begins with one, goes with the lead-in and the item begins after it; a list whose other items
  all begin with a preposition while the first item holds one is refused ("the other items go
  on with the first item"); a describing word alone does not refuse a list whose first item
  begins with a verb form in "-ing".
- `claims.py`, `split`: the last sentence of a cut-off text gets the cue `cut_off`, and the
  last item of a list in it is not kept; the items of a list whose first item holds a
  preposition get the cue `first_item_preposition` with the prepositions found. New helpers
  `_cut_off`, `_bare`, `_first_item_cue`; new constant `CUT_OFF_WORDS = 120`.
- `claims_load.py`, `_earlier`: the cues are compared too, so a claim whose cues are not what
  the rules give is renewed by `--remake`.
- The rules are `claims-4`. Decision E74 records all of this. The plan row of M2.4 now requires
  the review screens to show both marks.
- **The sentence rules moved to `claim_sentences.py`, unchanged.** With these changes
  `claims.py` had reached 27.8 KB of the 32 KB the code index can read, and the M2.6b entry had
  said the next change must come with a split. 13 names moved (`_mask`, `sentences`,
  `_continues` and their constants); `claims.py` imports the two it uses. Proved to change
  nothing: one digest over every claim the rules give for all 2,952 statements (span, text,
  rule, sentence above, cues) is the same before and after the move, and the 13 names are
  identical to the last commit. `claims.py` is now 22.2 KB, `claim_sentences.py` 6.4 KB.

**Read before any data was touched.** The new rules were compared read-only with the stored
claims: exactly five lists change their items, all as intended (the fragment "a family"
dropped; the two lists back; the "fat pads" sentence whole; one more list recovered, "cataract
surgery | a perforating wound or ulcer | congenital anomaly"). The 78 marked lists were read.

**Real run.**

| Step | Result |
|---|---|
| `extract-claims`, before any remake | 12 list items added to 3 statements whose stored claims all still hold; "453 stored claims in 140 statements that the rules do not give" (5 with other items, the rest with new marks); 1 difference, exit code 1, as intended |
| `extract-claims --remake` | 140 statements made again: 1,505 claims deleted, 1,501 stored; 0 differences |
| `extract-claims` again | inserted 0, nothing to make again, 0 differences |

| | Before | After |
|---|---:|---:|
| claims, all pending | 8,734 | 8,742 |
| sentences | 6,220 | 6,220 |
| list items | 2,514 | 2,522 |
| lists | 585 | 587 |
| last sentences marked `cut_off` | 0 | 79 |
| lists marked `first_item_preposition` | 0 | 78 (361 items) |
| list items carrying a proposed feature | 106 | 106 |

Checked read-only afterwards: for all 8,742 claims the span, the text and the cues stored are
what the rules give; no list item lies outside its own sentence; no claim has a reviewer or a
decision; none of the fragments "a family", "from lung", "in cataract surgery" is stored.

**Impact analysis.** `split`: **CRITICAL** (4 direct callers; reached from `extract_claims`,
the completeness check and `main`). `_checked` and `_mask`: **HIGH**. `_earlier`: LOW. Reported
to the owner before the edit with the plan per caller: no caller changes its code; every list
that changes was read before the remake; the move changes no claim. `detect_changes` before
commit: 28 symbols, summary risk "high"; most are listed because the move shifted their lines.
Compared with the last commit name by name: 13 names moved and are identical; changed are
`VERSION`, `_PREPOSITION`, `_checked`, `split` and, in the loader, `_earlier`; 7 names are new;
no existing test changed its code and 4 tests are new.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 56 files |
| `uv run pytest -m "not archives"` (SQLite) | 210 passed, 56 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 275 passed |
| the loader test sentences with 339,808 tag endings | what the tests expect every time |
| `completeness` on the real data, after the remake | 236 checks, 230 ok, 0 mismatches, 6 left to later (590 s); claims of the symptom statements: 1,037 expected, 1,037 stored |

The four new tests prove, with invented sentences: the preposition after the lead-in; places
going on with the first item refused; the list after "feeling tired"; a cut-off text marked on
its last sentence only, its cut item not kept, and the same words with a full stop or in a
shorter text left whole; the mark on every item of a list whose first item holds a preposition
and on no other claim; a stored claim with other cues found, left alone without `--remake` and
renewed with it.

**Bugs.** None found in this sub-step. One count reported to the owner was wrong: the lists
whose items share the first words of the first item are about 24, not 15.

**Limits, stated plainly.**

- About 24 of the 587 lists have a first item that carries words the other items share. They
  are stored as before. 21 of them are among the 78 marked lists; 3 are not marked (the shared
  word is not a preposition: "abnormal muscle tone | reflexes | ..."). The mark does not say a
  list is wrong: by the same reading about 57 of the 78 marked lists are right.
- Two lists are still wrong with no sign in the wording: a chain of explanations read as a
  list ("Yellow fever virus (YFV) | an enveloped RNA virus ... | the type species | namesake
  ...") and "certain liver | kidney | hereditary disorders".
- The recovered list "cataract surgery | a perforating wound or ulcer | congenital anomaly"
  stands in a sentence that says "surgical removal, such as in cataract surgery": its first
  item is an example of a cause, the other two are causes.
- The 120-word limit is a fact about one source. Another source with another limit would not
  be recognised; the constant and its measurement are in the code.
- The word lists are closed, and a label or an initial after the first word of a sentence
  cannot be told apart. Unchanged.
- Nobody sees the marks yet: the review screens are M2.4.

**Committed and indexed.** Committed as `46bee9d` and pushed; CI passed on both jobs (run
44701018793). The code graph was re-indexed at `46bee9d` and reports up-to-date; both rule
modules are below the size it can read. The API and the web app were not restarted: this
sub-step changes neither. No migration. This paragraph was added in a following documents-only
commit, after which the index was refreshed again.

### M2.10 — Urgency rule set, first draft

Owner's go-ahead of 2026-11-20 ("Please proceed ahead"), after agreeing to leave the marked lists
of M2.6c to review. Owner decision E39: the assistant drafts the urgency rules.

**What the handoff asks, checked before the work.** "Run approved rules on every new/corrected
message, before general candidate ranking" (`docs/01`, FR04). "Use a bounded declarative AST ...
No clinical thresholds or emergency phone numbers have been invented in this handoff: a reviewer
must author jurisdiction-specific content" (`docs/03`). "Actual emergency instructions, contact
numbers and location-dependent services must come from approved backend content" (`docs/06`).
"Use clearly synthetic nonmedical test concepts to exercise escalation" for code tests
(`docs/05`). An out-of-scope user "still receives approved escalation/navigation text"
(`docs/01`). E39 replaces the reviewer as author with the assistant; nothing else is relaxed.

**What was built.**

- `packages/clinical/feeltriva_clinical/drafts/urgency_draft.json`: the draft, `urgency-draft-1`.
  20 rules (12 emergency, 8 urgent) over 85 features of the vocabulary; 19 sources; a list of
  warning signs it does not cover; five open points for the owner.
- `feeltriva_clinical/urgency_draft.py` (pure): the draft's form, `check_draft`, `load_draft`,
  `review_document`. A draft and its rules can only have the status `pending`.
- `services/api/feeltriva_api/rule_drafts.py`: `python -m feeltriva_api.rule_drafts` checks every
  feature of the draft against the vocabulary in the database (identifier and name) and stores
  one `rule_bundles` row and one `clinical_rules` row per rule, all `pending`. It never changes a
  rule or a bundle that a reviewer has decided. `models.py` gains `ClinicalRule` for the table
  that has existed since migration 0001; no migration was needed.
- `docs/review/urgency_rules_draft.md`: the draft as a document for the owner, generated from the
  file; a test keeps the two the same.
- Decision E75 records how the draft was made.

**How the basis was gathered.** Each page was fetched to a scratch directory outside the
repository and turned into plain text by a small script. The draft was then built by a script
that refuses to write the file unless every quoted line is found word for word in its page and
every "last reviewed" date is the page's own. The same script takes each feature from a dump of
the vocabulary and stops on an unknown identifier. Nothing about any user or case left this
machine: only public pages were requested.

| Source | Pages | Used for |
|---|---:|---|
| NHS website (England), Open Government Licence v3.0 | 16 | the warning signs and the two levels ("call 999" and "urgent appointment") |
| Kerala Police, Government of Kerala | 1 | the emergency number 112 |
| Dhubri Medical College & Hospital (Government of Assam), JIPMER | 2 | the Tele MANAS helpline 14416 |

**What could not be read.** `112.gov.in` (certificate error), `mha.gov.in` and `pib.gov.in` (HTTP
403) and `telemanas.mohfw.gov.in` (an empty page shell) refused automated reading, by both ways
tried. The numbers are therefore quoted from the three government pages above and marked in the
draft for the owner to confirm on the official pages. No readable official page states the
ambulance number 108, and it differs between states, so the draft does not use it.

**The rules.** Emergency (checked first): chest pain with signs of a heart attack; severe
breathing difficulty; signs of a stroke; seizure; loss of consciousness with other warning
signs; bleeding that is heavy or will not stop; vomiting blood with other warning signs;
coughing up blood with other warning signs; signs of a severe allergic reaction; thoughts of
suicide or self-harm; stiff neck or headache with signs of a serious infection; bleeding in
pregnancy with fainting or dizziness. Urgent: chest pain; breathing difficulty; fainting;
vomiting blood; coughing up blood; black stools or bloody diarrhoea; confusion; bleeding in
pregnancy. No rule uses a number as a threshold: each asks only whether features are present.

**Real run** (`python -m feeltriva_api.rule_drafts`, main database):

| Run | Result |
|---|---|
| first | all 85 features found under the names the draft gives; 20 rules inserted; stored: bundle `pending`, 20 rules, 20 `pending`; 0 differences |
| second | 0 inserted, 0 updated, 20 unchanged; 0 differences |

Checked afterwards: 12 emergency and 8 urgent rules, all `pending`, bundle not approved; the
API's database role gets "permission denied" when it tries to set a rule to approved; `/readyz`
still reports `clinical_mode: false`, release `fixture-rules-0`, `synthetic_release: true`. The
API and the web app were not restarted: nothing they load changed.

**Impact analysis.** New code only. It calls `validate_ast` and `evaluate` (both LOW) and adds a
model class beside `RuleBundle` (MEDIUM; not changed). No HIGH or CRITICAL symbol is touched.
`detect_changes` before commit: one tracked file changed (`models.py`, a class appended at its
end), no existing symbol touched, risk low. The code index's keyword search reported its index
missing at the start of this sub-step; it was rebuilt in full (`gitnexus analyze --force`).

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 58 files |
| `uv run pytest -m "not archives"` (SQLite) | 219 passed, 56 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 284 passed |

The nine new tests prove: the draft is whole, pending, and every rule has an NHS basis, a
reason and two levels in the right order; every rule fires on its case, stays silent on its
other case, and never fires when nothing is known or everything is merely not asked; the texts
name no number but 112 and 14416, each with its source; a draft cannot be given the status
approved; the draft file cannot be loaded as a release, and a bundle built from it is refused in
clinical mode; five kinds of broken draft are refused with their reason; the review document is
exactly what the draft generates. With an invented draft over invented features: stored pending
once; a second run changes nothing; a rule a reviewer decided is not rewritten while a pending
one is; a decided bundle is not rewritten at all; a missing feature or a feature under another
name stores nothing. The model is checked against the migration by the existing schema test.

**Bugs.** None in committed code. Found before commit: the test on telephone numbers was written
with a pattern that could never match, so it passed without checking anything; corrected, and it
now finds 112 in 20 texts and 14416 in one.

**Limits, stated plainly.**

- The assistant is not a clinician, and no clinician has seen the rules. The warning signs come
  from an English public health website, not from an Indian clinical source.
- The rules have not been tried on a single real case. No urgency labels exist, so how often
  they would fire wrongly or miss is not known. The case files cannot be used for it: a disease
  label says nothing about urgency (`docs/01`, evaluation rule 8).
- The vocabulary records that a symptom is present, not how severe or how sudden it is. Where
  that decides the level, the draft escalates; this will over-escalate.
- Several features of different archives mean the same thing and are joined with "or" inside the
  rules, because no synonym has been approved yet. A feature added later is not picked up.
- A rule fires only on features recorded as present. Free text a user types reaches a rule only
  through extraction and confirmation, which are separate steps.
- The numbers 112 and 14416 were not read on the central government's own pages. 108 is absent.
- There is no way yet to approve a rule: that, and publishing a release from approved rules, is
  M2.5. Until then the draft cannot be served, whatever its content.

**Committed and indexed.** Committed as `92c284c` and pushed; CI passed on both jobs (run
44729100873). The code graph was re-indexed at `92c284c` and reports up-to-date. The API and the
web app were not restarted: nothing they load changed. No migration. This paragraph was added in
a following documents-only commit, after which the index was refreshed again.

### M2.10a — Urgency rules: the review document enlarged and the final text for approval

Owner's instruction of 2026-11-23, after reporting the M2.10 checks as "all good": "Enhance the
urgency_rules_draft.md even more and make a final version for the same as well." M2.5 was not
started in this run: one sub-step at a time.

**How the instruction was read.** "Final version" is taken as the finished text, ready to be
approved. It cannot mean approved: no path records an approval before M2.5, and E39 allows
serving only after the owner's recorded approval. The owner had read the 20 rules, so their
conditions, levels and texts were not changed, and nothing new was added to them.

**What was built.**

- `feeltriva_clinical/urgency_documents.py` (new, pure): `review_document` and `final_document`,
  both generated from the rule file. The earlier `review_document` in `urgency_draft.py` was
  removed; its one caller, the test, uses the new module.
- `docs/review/urgency_rules_draft.md` (991 lines, was 410): an overview table of the 20 rules
  with links; how the rules behave; the two levels; the telephone numbers with their source and
  "confirmed by the owner: not yet"; the decisions the owner has to take; the weaknesses that
  remain; the warning signs not covered; for each rule its condition as a list, the text shown,
  the reason for its level, the two cases it was checked with, its quoted basis and a decision
  line; the sources with the rules resting on each; the 85 features with the rules using each;
  the history.
- `docs/review/urgency_rules_final.md` (325 lines, new): only when each rule fires and the exact
  words the person is shown, emergency rules first; the checks before approval; the numbers;
  what is not covered; what stays true after approval; an approval record naming the rule file
  by its SHA-256 fingerprint, with a row per rule. Its head says "Final means the text is
  finished and ready to be approved. It does not mean approved."
- The rule file gained three lists: `numbers` (112 and 14416, each with its basis and an empty
  date of the owner's confirmation), `limits` and `history`. One more sentence of the Kerala
  Police page is quoted for 112 ("to establish a single emergency number "112" all over the
  country ..."), found word for word in the fetched page. The open points were rewritten as
  four decisions for the owner. `check_draft` now refuses a text that names a number the file
  does not list, a number without its basis among the rule's sources, and a listed number that
  no text names.
- Decision E76 records what "final" means and that an approval is for one fingerprint.

**No rule changed.** A digest over the 20 rules (conditions, levels, texts, basis, tests) was
taken before and after editing the file: the same, `7a62112eb2187838...`.

**Real run** (`python -m feeltriva_api.rule_drafts`, main database): 0 inserted, 0 updated, 20
unchanged, 20 `pending`. The bundle's fingerprint in the database, the SHA-256 of the file and
the fingerprint printed in the final text are the same value (`3e0bedd9...9712`). `/readyz` still
reports clinical mode off and the synthetic release. The API and the web app were not restarted.

**Impact analysis.** `review_document`, `UrgencyDraft` and `check_draft`: LOW. The graph does not
trace callers across packages, so the callers were found by search: the storing command and the
two test files; each was updated or checked. `detect_changes` before commit: "medium", 48 names,
of which 26 are headings of the regenerated document. In code, compared with the last commit:
`UrgencyDraft` and `check_draft` changed, `DraftNumber`, `DraftChange` and `_NUMBER` added,
`review_document` and `_condition` removed from this module (they live in the new module).

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 59 files |
| `uv run pytest -m "not archives"` (SQLite) | 221 passed, 56 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 286 passed |

New or changed tests prove: both documents are exactly what the rule file generates; the review
document holds every rule with its text, reason, two cases, basis and decision line, every
feature and every number; the final text holds every rule's exact words in the order the rules
are checked, says it is not approved, names the file's fingerprint and the missing approval path,
and carries no working notes; a text naming an unlisted number, a number without its basis, or a
listed number nobody names is refused; neither number is marked as confirmed by the owner.

**Bugs.** None in committed code. Found while writing: a test claimed that no quoted line of the
NHS pages occurs in the final text; it failed because some texts shown use a short phrase that is
also in a quote ("your chest feels tight or heavy"). The test now checks that the final text has
no basis section, and the final text gained a line naming the NHS website and its licence.

**Limits, stated plainly.**

- Nothing about the rules is better than on 2026-11-20: no clinician has read them and they were
  tried on no real case. Only the documents changed.
- The owner's confirmation of 112 and 14416 on the official pages is not recorded: the owner
  wrote "all good" but did not say the two pages were opened. Both stay "not yet".
- The approval record in the final text is a place to write on, not a recorded approval. The
  system records nothing until M2.5.
- The documents are long because 85 features are spelled out. The final text is the short one.

**Committed and indexed.** Committed as `8df646b` and pushed; CI passed on both jobs (run
45106608805). The code graph was re-indexed at `8df646b` and reports up-to-date. The API and the
web app were not restarted: nothing they load changed. No migration. This paragraph was added in
a following documents-only commit, after which the index was refreshed again.

### M2.5a — Approval of rules, questions and bundles

Owner's go-ahead of 2026-11-23: "Proceed ahead with M2.5".

**M2.5 was split before any code.** Its plan row had collected requirements from eight earlier
sub-steps. Read as a whole it holds five separate pieces of work, so it is done in five parts
(decision E77): M2.5a approvals; M2.5b publishing a rule release, rollback and what clinical
mode loads; M2.5c mapping and knowledge releases and disease redirects; M2.5d what a decision
on a vocabulary link entails, and self-checks that accept decisions; M2.5e claims after review.
Every requirement of the old row is in one of the five new rows. Only M2.5a was done here.

**What the handoff asks, checked before the work.** "Human-approved rule priority handles
conflicts" and rules as reviewed content (`docs/03`); "author question and urgency bundles"
with the exit "approved serving corpus and rule/question release, or development-only mode"
(`docs/01`, phase 4); clinical suggestions "disabled unless an approved rule bundle ..."
(`docs/03`). E39: the urgency rules are served only after the owner approves them by name.

**What was built.**

- Migration `0011`: the API's database role may change `status` on `clinical_rules` and
  `followup_questions`, and `status`, `approved_by`, `approved_at` on `rule_bundles`, and only
  inside a reviewer transaction (row-level security). Reading is as before.
- `review.py`: `record_review` calls a guard for the target type, when one is registered,
  before it sets a status.
- `review_rules.py` (new): the review targets `clinical_rule`, `followup_question` and
  `rule_bundle`; the guards; `list_rules`.
- `main.py`: `GET /internal/v1/review/rules` (reviewers only; `bundle_id`, `status`, paging).
- Decisions use the existing `POST /internal/v1/review/decisions`. The reviewer's name is kept
  in the decision record (`review_notes`) and, for a bundle, on the bundle with the time.

**When a bundle can be approved.** Every rule and question decided and at least one rule
approved; for a bundle stored from a rule file, the file on disk has the stored fingerprint;
every telephone number of the file confirmed by the owner. Each failing condition answers 409
with its own code and writes nothing. While a bundle is approved its rules cannot be decided;
withdrawing the approval clears the name and the time.

**Real run.** Migration applied to the main database (head `0011`, six policies on the three
tables). The API was restarted, because it serves a new route. As reviewer `dev-reviewer:owner`:
the bundle `urgency-draft` is listed with its fingerprint and 20 pending rules; a user gets 403;
an attempt to approve the bundle answers `bundle_items_pending`, "20 rules or questions of this
bundle are still pending", and the database holds no decision record and an unchanged bundle.
`/readyz` still reports clinical mode off and the synthetic release.

**Impact analysis.** `record_review`: LOW (one caller, the decision route; the MCP server does
not call it, checked by search). `create_app`: LOW. `detect_changes` before commit: "medium",
four names: `create_app` (one route added), `record_review` with its class (the guard call), and
`review_decision`, the route below the new one, whose text is unchanged.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 60 files |
| `uv run pytest -m "not archives"` (SQLite) | 224 passed, 57 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 290 passed |
| Migration `0011` on a scratch database: head, down to `0010`, head | 6 policies, 0, 6 |

The four new tests prove, with an invented bundle: rules are listed for reviewers only, with
their bundle, its fingerprint and counts; a user cannot decide; a rule's decision is recorded
with the reviewer and the note and changes only its status; a bundle is refused while a rule is
pending, when the rule file is missing, when its fingerprint differs, when a number is not
confirmed, and when no rule is approved; with everything in place the approval is recorded with
name and time; an approved bundle's rule cannot be decided until the approval is withdrawn;
on PostgreSQL, a transaction that is not a reviewer's changes no row, and a reviewer's cannot
change a priority, a text or a manifest, or delete a rule.

**Bugs.** None in committed code. While writing the tests I read the error response in the
wrong shape; the tests were corrected.

**Limits, stated plainly.**

- Nothing is approved. The owner has not decided any rule, and both telephone numbers are still
  "not yet" confirmed, so the bundle could not be approved today even with every rule decided.
- A decision is made with a request to the API (or by the assistant on the owner's instruction,
  as for the vocabulary links). The review screens do not show rules yet (M2.4).
- A rule has no column for its reviewer: the name is in the decision record. The list route
  shows the last decision of each rule from there.
- An approved bundle is not yet a release. Publishing, rollback and loading in clinical mode are
  M2.5b; until then an approval changes nothing a person sees.
- The development reviewer token (`dev-reviewer:<name>`) is accepted only with mock
  authentication. In production the reviewer's identity comes from the verified token.

**Committed and indexed.** Committed as `7934502` and pushed; CI passed on both jobs (run
45110331677). The code graph was re-indexed at `7934502` and reports up-to-date. Migration `0011`
is applied to the main database. The API was restarted for the new route; the web app was not,
because nothing it loads changed. This paragraph was added in a following documents-only commit,
after which the index was refreshed again.

### M2.5a1 — The owner's approval of the urgency rules recorded

Owner's statement of 2026-11-23, in reply to the limit "Nothing is approved. No rule is decided
and both phone numbers are still unconfirmed": "This is decided by me and approved. 20 rules are
approved." Then: "please proceed ahead". Recording the approval is one sub-step; M2.5b was not
started.

**What was recorded, and how.**

1. Rule file: both telephone numbers marked confirmed by the owner on 2026-11-23; the label now
   says the rules were approved by the owner without a doctor's review; the history holds the
   owner's words; the open points are reduced to the two that are still open (no doctor's
   review; 108 not used). No rule changed: the digest over the 20 rules is the same before and
   after (`7a62112eb2187838...`).
2. `python -m feeltriva_api.rule_drafts`: the bundle, still pending, took the new fingerprint;
   20 rules unchanged.
3. Through `POST /internal/v1/review/decisions` as `dev-reviewer:owner`: 20 times
   `clinical_rule` from `pending` to `approved`, then `rule_bundle` `urgency-draft` to
   `approved`. Every note quotes the owner and says the assistant entered it on the owner's
   instruction. The bundle approval passed all conditions of M2.5a: every rule decided, the
   rule file is the stored one, both numbers confirmed.

**State afterwards.** `clinical_rules`: 20 approved. `rule_bundles`: `urgency-draft` approved by
`dev-reviewer:owner` at 2026-11-23 04:47:12 UTC; its stored fingerprint and the file's SHA-256
are both `19147c0f5df211a961bd1abcdb57d1dc60520e2165100bf82f17c8bc6abd0193`. 21 decision
records. A further attempt to decide a rule answers `bundle_already_approved`. `/readyz`:
clinical mode off, release `fixture-rules-0`, synthetic. Nothing is published or served.

**Code changed with it.**

- `urgency_documents.py`: the documents no longer print a status or say "not approved". They
  are generated from the file, which cannot know what was decided, so they now say where
  decisions are recorded, show the owner's decision in the history, name the fingerprint an
  approval is for, and list what is still open. The empty approval forms were removed. The
  numbers column reads "Confirmed by the owner".
- `rule_drafts.py`: an approved bundle whose rule file is the one approved is no longer reported
  as a difference. Before this, the command would have ended with a difference on every run
  after an approval. A changed file is still a difference. The summary counts approved rules.

**Impact analysis.** `store_draft`, `final_document`, `_banner`: LOW. `detect_changes` before
commit: "medium", 55 names, 30 of them headings of the two regenerated documents; in code
`_banner`, `_numbers`, `review_document`, `final_document`, `store_draft`, `check` and `main` of
the storing command, and the tests of both.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 60 files |
| `uv run pytest -m "not archives"` (SQLite) | 224 passed, 57 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 290 passed |

Changed tests prove: both documents are what the file generates, print no status, say where
decisions are recorded and carry the owner's words; the file records both numbers as confirmed
on 2026-11-23; a decided bundle with the same file is no difference and is not rewritten, with
another file it is a difference.

**Bugs.** One, found before it could occur: the storing command treated every decided bundle as
a difference (written in M2.10, when nothing could be decided). Corrected here.

**Limits, stated plainly.**

- The approval was given without a doctor's review, and the rules were tried on no real case.
  Both documents say so. Nothing about the rules' quality changed today.
- The owner's statement does not say that the two official pages were opened. The record holds
  the owner's words and the date, not more.
- The approval was entered by the assistant on the owner's instruction with the development
  reviewer identity, as for the vocabulary links (M2.17). In production the identity comes from
  a verified token.
- An approved bundle is not a release. Publishing, rollback and loading in clinical mode are
  M2.5b, and clinical mode stays off until the owner's go-live decision (E37, E40).

**Committed and indexed.** Committed as `72b2b23` and pushed; CI passed on both jobs (run
45114093737). The code graph was re-indexed at `72b2b23` and reports up-to-date. The API and the
web app were not restarted: the service reads the rule file from disk at each approval, and
nothing else it loads changed. No migration. This paragraph was added in a following
documents-only commit, after which the index was refreshed again.

### M2.5b — Publishing a rule release, rollback, and what clinical mode loads

Owner's go-ahead of 2026-11-23: "proceed ahead with M2.5B".

**What the handoff asks, checked before the work.** "Publish and roll back mapping, knowledge and
rule/question releases", immutable once published (plan row, from `docs/05`); clinical
suggestions "disabled unless an approved rule bundle, knowledge release, model scope, ownership
checks and runtime health" are in place (`docs/03`). The rule release is one of three kinds; the
other two are M2.5c.

**What was built.**

- Migration `0012`: table `rule_releases` (release, bundle, number, content, SHA-256, rule-file
  fingerprint, publisher, time, current). A trigger refuses every UPDATE of a published release
  except of `is_current`, and every DELETE. A partial unique index allows one current release.
  The API's role may read, insert and change `is_current`, and the last two only in a reviewer
  transaction.
- `releases.py` (new): `preview`, `publish`, `make_current`, `list_releases`, `verify_published`.
- `main.py`: `GET /internal/v1/review/releases`, `GET .../releases/preview`,
  `POST .../releases` (publish), `POST .../releases/current` (rollback). Reviewers only.
- `container.py`: in clinical mode `build_container` calls `verify_published`; the API and the
  MCP server both start through it.
- `models.py`: `RuleRelease`.

**What a release holds.** The approved rules of the bundle in the order they are checked; its
approved questions; the sources those rules name, with their quotes, page review dates and
licences, taken from the rule file; the features the rules name, with their names; the bundle's
version, the rule file's fingerprint, and who approved the bundle and when. Rejected rules are
left out. The SHA-256 is taken over this content in a fixed form.

**Real run.** Migration applied to the main database (head `0012`). The API was restarted for the
new routes. As reviewer: the preview of `urgency-draft` says `publishable: true`, no problems,
it would be release 1 with 20 rules, 0 questions, 19 sources and 85 features. No release was
published: the list is empty. A user gets 403. `verify_published` on the main database refuses
with "clinical mode requires a current published rule release; 0 releases exist and none is
current". `/readyz` still reports clinical mode off and the synthetic release.

**Not published, on purpose.** A release can never be removed again, and publishing is done
under a reviewer's own name. The owner was asked to build M2.5b, not to publish. The owner can
publish with one request, or tell the assistant to (decision E79, point 7).

**A gap in the plan, found and reported.** A published rule release is not yet what the service
loads. The bundle that clinical mode loads must also hold approved features (they belong to the
mapping release, M2.5c) and four response texts that nobody has written or approved. No sub-step
covered assembling that bundle or the texts. Added: sub-step M2.5f and open decision D-R1.

**Impact analysis.** `build_container`: LOW (callers: the API's `create_app`, the MCP server and
the test fixture). `create_app`: LOW. `detect_changes` before commit: "medium", eight names:
`build_container` (the check), `create_app` (four routes), and `_error`, `app_factory` and four
variables of `main.py`, which moved because two request models were added above them; their text
is unchanged.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 61 files |
| `uv run pytest -m "not archives"` (SQLite) | 227 passed, 58 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 294 passed |
| Migration `0012` on a scratch database: head, down to `0011`, head | table and trigger present, absent, present |

The four new tests prove, with an invented bundle: a user can neither list nor publish; an
undecided bundle previews with each obstacle named and is refused; an approved bundle publishes
as release 1 with only its approved rules, their sources and features, the publisher's name and
the rule file's fingerprint; the same content is refused a second time; after the approval is
withdrawn, a rule rejected and the bundle approved again, release 2 becomes current and release
1 keeps its three rules; a rollback makes release 1 current again and is recorded; clinical mode
accepts exactly the published rules and refuses a changed text, a missing rule and the sample
release; on PostgreSQL the schema owner cannot edit a release's content, fingerprint or
publisher, nor delete it, and a transaction that is not a reviewer's can neither publish nor
switch the current release.

**Bugs.** None in committed code. While tidying the test file I removed lint exemptions before
the lines they covered were rewritten, which left four style findings; fixed before commit.

**Limits, stated plainly.**

- Nothing is published. The approved rules are one request away from being release 1.
- Clinical mode cannot start, and will not be able to after a release is published either,
  until the serving bundle exists (M2.5f): approved features and approved response texts.
- The check at start-up compares rules. It does not yet compare questions, features or
  evidence with a release; those belong to the other kinds of release.
- A rollback changes which release is current. A service already running keeps the bundle it
  loaded until it is restarted.
- One release is current for the whole system, not one per bundle: there is one rule set.

**Committed and indexed.** Committed as `a140a27` and pushed; CI passed on both jobs (run
45115544657). The code graph was re-indexed at `a140a27` and reports up-to-date. Migration `0012`
is applied to the main database. The API was restarted for the new routes; the web app was not,
because nothing it loads changed. This paragraph was added in a following documents-only commit,
after which the index was refreshed again.

### M2.5b1 — Release 1 of the urgency rules published

Owner's instruction of 2026-11-23. Asked "Publish release 1? Run the command above, or tell me to
publish it for you. Publishing serves nothing; it only makes these rules the current release",
the owner answered "yes" (decision E80).

**What was done.** One request to `POST /internal/v1/review/releases` as `dev-reviewer:owner`,
with a note quoting the question and the answer and saying the assistant entered it on the
owner's instruction. No code changed.

**State afterwards.** `rule_releases` holds one row: `urgency-draft.r1`, number 1, current,
published by `dev-reviewer:owner` at 2026-11-23 05:08:34 UTC, SHA-256
`60998fe967cb05e59e381869ec37aa40c397d5e03d8c72f06e7d3ffc796c8358`, for the rule file
`19147c0f...0193`: 20 rules, 0 questions, 19 sources, 85 features. One decision record
(`release_published`). A second request to publish answers `release_already_published`.
`/readyz`: clinical mode off, release `fixture-rules-0`, synthetic. Nothing is served.

**Tests.** No code changed, so the suites of M2.5b stand (SQLite 227 passed, 58 skipped;
PostgreSQL 294 passed). The release tests were run again after the publication: 3 passed, 1
skipped on SQLite.

**Limits.** The release cannot be removed. It is not served: clinical mode is off, and the bundle
the service would load does not exist yet (M2.5f). No doctor has reviewed the rules it holds.

### M2.5f1 — The four response texts drafted

Owner's decision of 2026-11-23 on D-R1: "yes" to "I can draft them for your approval, as I did the
urgency rules ... you approve every word" (decision E81).

**What the handoff asks, checked before the work.** Results show "urgency/next step first, then
up to three provisional explanations"; no "uncalibrated probability percentages" (`docs/01`,
FR08); no autonomous diagnosis or medication advice (`docs/01`, excluded from v1); explanation
"cannot change approved urgency"; the frontend shows "backend-provided action" text only
(`docs/06`). The bundle format calls these "reviewer-authored response texts. The service never
composes care guidance itself."

**Where each text is shown** (read in `service_results.py` before writing): `confirm_details`
when something understood from the person's words is not yet confirmed; `provisional_next_step`
above possible explanations; `insufficient_information` when no explanation can be given;
`system_unavailable` when the assessment could not be completed.

**What was built.**

- `packages/clinical/feeltriva_clinical/drafts/response_texts_draft.json`:
  `response-texts-draft-1`, the four texts, each with when it is shown and why it is worded so,
  and four open points.
- `feeltriva_clinical/response_texts.py` (pure): the draft's form, `check_texts`,
  `load_response_texts`, `as_templates`, `review_document`. A draft can only be `pending`.
- `docs/review/response_texts_draft.md`, generated from the file; a test keeps them the same.

**What the texts do and do not say.** None names an illness, a medicine or a percentage. Three of
them end with "In an emergency call 112 or go to the nearest hospital emergency department."; 112
is the only number, and the check accepts a number only while the owner has confirmed it in the
urgency rule file. The text shown when nothing is found says "This does not mean that nothing is
wrong." The text shown on a failure says "Nothing has been concluded about your symptoms."

**Impact analysis.** New code only. It reads `Templates` and `load_draft` (both LOW) and changes
no existing symbol.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 62 files |
| `uv run pytest -m "not archives"` (SQLite) | 230 passed, 58 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 297 passed |

The three new tests prove: the draft holds exactly the four texts of a release, pending, in the
form a bundle holds them; it cannot be given the status approved; a missing text, a number the
owner has not confirmed, a diagnosis, a percentage and a missing reason are each refused; the
review document is exactly what the file generates.

**Bugs.** None.

**Limits, stated plainly.**

- Not approved. The owner has to read and decide each text.
- No doctor has read them. They give no medical advice beyond "see a doctor" and the emergency
  number.
- Nothing stores an approved text yet, and no route records the approval: that is M2.5f, with
  the serving bundle.
- English only.

### M2.5c1 — Disease redirects with merge and split history

Owner's go-ahead of 2026-11-23: "proceed ahead with M2.5c as well". M2.5c held three pieces of
work and is done in three parts (decision E82): M2.5c1 redirects with history; M2.5c2 approving
features and diseases, and the mapping release; M2.5c3 the knowledge release. Only M2.5c1 was
done here.

**What the handoff asks, checked before the work.** "Add disease redirects, merge/split history,
reviewer identity and immutable mapping/knowledge releases" (`docs/05`). "Preserve subtype,
acuity and severity distinctions. Suggested synonyms go to review" and original source rows and
names are preserved (`docs/01` §4). Owner's rules for merges (E62): the name kept is the most
accurate standard name, and every merged label is saved as a synonym of it.

**What was built.**

- Migration `0013`: table `disease_history` (merge or split, the two labels, detail, reviewer,
  reason, time), which a trigger makes append-only. The API's role may change a disease's
  `redirected_to`, `preferred_name` and `status`, and add a history row, only in a reviewer
  transaction. Reading is as before.
- `disease_merges.py` (new): `merge`, `split`, `state`.
- `main.py`: `POST /internal/v1/review/disease-merges`, `POST .../disease-splits`,
  `GET .../diseases/{id}/history`. Reviewers only.
- `models.py`: `DiseaseHistory`.

**How a merge works.** The merged label stays in the database, points at the kept label and is
marked retired. Its name is listed as a synonym of the kept label. The reviewer may give the kept
label its standard name; its former name then stays a synonym. Labels merged earlier into the
merged label follow it to the kept one, so no chain forms. A label is not merged twice, and
nothing is merged into a label that is itself merged. A split takes a merged label out again and
gives it back the status it had.

**Real run.** Migration applied to the main database (head `0013`). The API was restarted for the
new routes. As reviewer: the history of the real label "common cold" answers with the label
itself, no synonyms and no events; a user gets 403; a merge of a label into itself is refused.
Nothing was merged: 0 history rows, 0 redirected labels, the 466 suggestions still pending.

**Impact analysis.** `create_app`: LOW. `detect_changes` before commit: "medium", 14 names in
`main.py`: `create_app` (three routes added) and the names below the two new request models,
whose text is unchanged. `models.py` gained a class at its end.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 63 files |
| `uv run pytest -m "not archives"` (SQLite) | 233 passed, 59 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 301 passed |
| Migration `0013` on a scratch database: head, down to `0012`, head | table and policies present, absent, present |

The four new tests prove, with invented labels: a user can neither merge nor read the history; a
merge keeps the merged label with its own name, pointing at the kept one, and records who and
why; its name is listed as a synonym; a label is not merged twice nor into a merged label; the
kept label can take a standard name and its former name stays a synonym; a label merged earlier
follows; a split restores the label and its status and the history keeps both events; on
PostgreSQL the history cannot be changed or deleted even by the schema owner, a transaction that
is not a reviewer's changes no disease, and a reviewer's cannot rewrite a definition.

**Bugs.**

- **BUG-024 — two events in the same second came back in the wrong order.** Found by the tests
  on SQLite: the history was ordered by a time the database filled in, which SQLite keeps to the
  second. The time is now set by the code to the microsecond. Fixed before commit; the tests were
  then run three times on SQLite and once on PostgreSQL.

**Limits, stated plainly.**

- No label has been merged. Which labels are the same disease is a reviewer's decision, one
  merge at a time; the 466 suggestions only propose.
- A merge does not move mappings, evidence or links from the merged label to the kept one. They
  stay on the label they were loaded with and are reached through the redirect. Views that
  gather them under the kept label are M2.9.
- Approving a suggestion does not merge, and a merge does not mark a suggestion: the two are not
  yet connected.
- Features cannot be merged; only disease labels.
- After a split, labels that had followed the split label into the kept one stay with the kept
  label.

**Committed and indexed (M2.5b1, M2.5f1, M2.5c1).** The owner named all three in one message, so
they were done one after the other, each with its own commit: `b84ab09` (M2.5b1, documents only),
`9512eb8` (M2.5f1; CI passed on both jobs, run 45117002469) and `edd3e87` (M2.5c1; CI passed on
both jobs, run 45121017064). The code graph was re-indexed after each and reports up-to-date at
`edd3e87`. Migration `0013` is applied to the main database. The API was restarted for the new
routes of M2.5c1; the web app was not, because nothing it loads changed. This paragraph was added
in a following documents-only commit, after which the index was refreshed again.

### M2.5c2 — Approving features and diseases; the mapping release

Owner's go-ahead of 2026-11-23: "Please proceed with M2.5c2 and M2.5c3 together". The two were
done one after the other, each with its own commit. This entry is M2.5c2.

**What the handoff asks, checked before the work.** "Produce immutable mapping version, split
manifest, source hashes and audit report. Publish only approved mappings/evidence to clinical
serving" (`docs/01` §4, rule 10). "Versioned disease/feature mapping release with unresolved
queue" (`docs/01`, stage 3). "Disease → source aliases, scoped by mapping release" and the export
`reviewed_disease_catalog` (IDs, names, aliases, definitions) from an approved mapping release
(`docs/04`). "Immutable mapping/knowledge releases" (`docs/05`). Codes of outside vocabularies
are internal (E63). The split manifest belongs to the model data (M4.3) and is not part of this.

**What was built.**

- Migration `0014`: the API's role may set the status of a feature, only in a reviewer
  transaction, and no other column. Table `published_mappings` (working set, number, content,
  SHA-256, publisher, time, current), with a trigger that refuses every edit and deletion and an
  index that allows one current release. The API's role may read, publish and switch, only in a
  reviewer transaction.
- `publishing.py` (new): what the mapping release and the knowledge release share: numbering,
  fingerprint, "not twice", current, rollback, the decision record.
- `published_mappings.py` (new): `feature` and `disease` as review targets; the guard for merged
  labels; `list_features`, `list_diseases`; what a release holds; `preview`, `publish`,
  `make_current`, `list_published`.
- `main.py`: `GET /internal/v1/review/features`, `GET .../diseases`,
  `GET .../mapping-releases`, `GET .../mapping-releases/preview`, `POST .../mapping-releases`,
  `POST .../mapping-releases/current`. Reviewers only.
- `models.py`: `PublishedMapping`.

**What a mapping release holds** (decision E83). The approved features; the approved diseases
with their synonyms and the redirects of merged labels; the approved mappings of one working set
whose disease or feature is approved too; the sources of those mappings with their SHA-256; how
much was still undecided. An approved mapping whose target is not approved is held back and
counted. No code of an outside vocabulary. The only thing that refuses a release is that no
feature and no disease is approved.

**Real run.** Migration applied to the main database (head `0014`). The API was restarted for the
new routes. As reviewer: the list of features answers with the real features and their status
(968 pending); the preview of `mapping-lexical-0` says not publishable, "no feature and no disease
is approved", undecided 968 features, 960 disease labels, 3,117 and 1,962 mappings; publishing is
refused with `release_not_publishable` and writes nothing; a user gets 403. Nothing was decided
and nothing was published: 0 rows in `published_mappings`. The 85 features the urgency rules name
are all pending.

**Impact analysis.** `create_app`: LOW (one caller, `app_factory`). `record_review`: LOW; it is
not changed, the two new targets are entered in its table. `_page`: CRITICAL by count (six list
routes use it); it is called, not changed. `Feature` and `Disease`: MEDIUM; read, not changed.
`test_application_role_cannot_alter_reference_or_schema`: LOW. `detect_changes` before commit:
"medium", 8 names in 3 files. Compared with the last commit by syntax tree: changed are
`create_app` (six routes added) and the one test; `PublishedMapping` and `MappingPublish` are
new; `app_factory`, `sid`, `barrier`, `codes`, `write` and
`test_concurrent_writers_on_one_version_exactly_one_wins` are listed only because lines above
them moved.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 65 files |
| `uv run pytest -m "not archives"` (SQLite) | 237 passed, 60 skipped |
| `uv run pytest` (SQLite, archives included) | 243 passed, 63 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 306 passed |
| Migration `0014` on a scratch database: head, down to `0013`, head | table and policies present, absent, present |

The five new tests prove, with invented rows: a user can neither list nor decide; a reviewer
approves and rejects a feature and a disease and the list shows who decided; a merged label is
not decided; a release holds the approved features and diseases and not the rejected or pending
ones; the kept label carries its standard name with the merged label and the former name as
synonyms, the same as the history route gives; a mapping of a merged label keeps its own label
and says which label it resolves to; an approved mapping whose target is not approved is held
back and counted; the notes that said "pending" are not in the release; the source is listed
with its SHA-256; the same content is not published twice; on a database of its own, with
nothing approved, publishing is refused and writes nothing; a second release leaves the first
unchanged and a rollback makes the first current again, with every step recorded; on PostgreSQL
a published release cannot be edited or deleted even by the schema owner, a transaction that is
not a reviewer's can neither publish, switch nor decide a feature, and a reviewer's cannot
change a feature's name.

**An older test changed, deliberately.** The first run of the PostgreSQL suite gave 305 passed,
1 failed: `test_application_role_cannot_alter_reference_or_schema` expected "permission denied"
for `UPDATE features SET status = 'approved'` by the API's role. That was true until this
migration. A reviewer's decision on a feature is written by the API's role, so the role now has
that one permission, and row-level security lets it act only in a reviewer transaction. The test
now states the new guarantee: changing a feature's name and deleting a feature are still refused
with "permission denied", and the status update in a user's transaction changes no row. The same
change was made for diseases in migration 0013 and for rules in 0011. This widens what the API's
role can do in the database by one column, and it is the reason the role is trusted to say
"reviewer" only for a verified reviewer.

**Bugs.** None found in the code of this sub-step.

**Limits, stated plainly.**

- Nothing is approved, so no mapping release exists. Deciding 968 features and 960 disease labels
  is the reviewer's work; there is no way yet to decide many at once.
- The serving bundle does not read the mapping release yet (M2.5f). Clinical mode is off.
- Features and diseases are not scoped to a working set: a release holds every approved feature
  and disease, and the approved mappings of the one working set it is published from.
- Approved vocabulary links are not part of a release (E83, E63).
- One mapping release is current across all working sets. There is one working set.
- A feature cannot be merged into another; only disease labels can (M2.5c1).

### M2.5c3 — The knowledge release

Second of the two sub-steps the owner named on 2026-11-23 ("Please proceed with M2.5c2 and
M2.5c3 together"). Done after M2.5c2 was committed, with its own commit.

**What the handoff asks, checked before the work.** "Immutable mapping/knowledge releases"
(`docs/05`). Stage 4: "Verify source licences; review atomic statements" leading to an "approved
serving corpus" (`docs/01`). "Publish only approved mappings/evidence to clinical serving"
(`docs/01` §4). The exports `reviewed_disease_feature_edges` ("approved evidence and source use
rights") and `retrieval_corpus` ("approved knowledge release and current applicability"), and
"Knowledge release → evidence chunks" (`docs/04`). Every displayed claim needs a source.

**What was found before building.**

- Evidence rows could not be decided at all: `disease_feature_evidence` was not a review target
  and the API's role could not change it. "Approved evidence" could not exist.
- No source's rights have been decided: all 14 sources are `pending`, 11 have no licence
  recorded, `permitted_uses` is empty for all. No sub-step covered "verify source licences".
- The retrieval chunks have no review status, so none can be approved.

**What was built.**

- Migration `0015`: the API's role may set the status of an evidence row and the provenance
  status of a source, only in a reviewer transaction, and no other column. Table
  `published_knowledge` (knowledge set, pinned mapping release, number, content, SHA-256,
  publisher, time, current), immutable by trigger, one current.
- `published_knowledge.py` (new): `evidence` and `source` as review targets; `list_sources`,
  `list_evidence`; what a release holds; `preview`, `publish`, `make_current`, `list_published`.
  It uses `publishing.py` of M2.5c2 unchanged.
- `main.py`: `GET /internal/v1/review/sources`, `GET .../evidence`,
  `GET .../knowledge-releases`, `GET .../knowledge-releases/preview`,
  `POST .../knowledge-releases`, `POST .../knowledge-releases/current`. Reviewers only.
- `models.py`: `DiseaseFeatureEvidence`, `PublishedKnowledge`; `Source.status`, a second name for
  `provenance_status`, because the decision endpoint reads and sets `status` on every target.

**What a knowledge release holds, holds back and refuses** (decision E84). It holds the approved
statements that have not expired with their source records, the approved evidence rows, and the
sources with licence and SHA-256, pinned to the current mapping release. Held back and counted:
content whose source is not approved; whose disease or feature is not in the pinned mapping
release; a statement without a source; an evidence row resting on a statement that is not in the
release. Refused: no current mapping release; the current one is of another working set; nothing
would be in it.

**Real run.** Migration applied to the main database (head `0015`). The API was restarted for the
new routes. As reviewer: 14 sources listed, all pending, with the licence recorded for each (three
have one, CC BY 4.0: the DDXPlus release and the two archive-15 files traced to it; eleven have
none); the evidence list answers with real rows (888 of the type the DDXPlus
release lists); the preview of `knowledge-import-0` says not publishable, "no mapping release is
current" and "no statement and no evidence is approved", undecided 2,952 statements, 22,947
evidence rows, 14 sources; publishing is refused with `release_not_publishable` and writes
nothing; a user gets 403. Nothing was decided and nothing published: 0 rows in
`published_knowledge` and `published_mappings`; rule release `urgency-draft.r1` is still current.

**Impact analysis.** `create_app`: LOW. `Source`: MEDIUM by count (11 modules import the models
module); the change adds one attribute and alters none, and the ingestion writes sources by
column name, which the test suite on PostgreSQL confirms. `publishing.publish`: LOW; called, not
changed. `detect_changes` before commit: "medium", 7 names in 2 files. Compared with the last
commit by syntax tree: changed are `create_app` (six routes added) and `Source` (the second
name); `DiseaseFeatureEvidence`, `PublishedKnowledge` and `KnowledgePublish` are new;
`MappingPublish`, `app_factory`, `Json` and `SourceRecord` are listed only because lines above
them moved.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 66 files |
| `uv run pytest -m "not archives"` (SQLite) | 240 passed, 61 skipped |
| `uv run pytest` (SQLite, archives included) | 246 passed, 64 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 310 passed, twice in a row |
| Migration `0015` on a scratch database: head, down to `0014`, head | table and policies present, absent, present |

The four new tests prove, with invented rows: a user can neither list, decide nor publish; a
reviewer approves a source and evidence rows and the lists show it; of seven statements and six
evidence rows, one for each case, exactly two of each are published and each of the seven ways
of being held back is counted once; a statement of a merged label keeps its own label and says
which label it stands under; a statement keeps its source record; the release records the SHA-256
of its mapping release; the same content is not published twice; without a current mapping
release, and with a mapping release of another working set, publishing is refused; a second
release leaves the first unchanged and a rollback makes the first current again, with every step
recorded; on PostgreSQL a published release cannot be edited or deleted even by the schema
owner, a transaction that is not a reviewer's can neither publish, switch, nor decide a source or
an evidence row, and a reviewer's cannot change a licence or what an evidence row says.

**Found while building.**

- **The `load-evidence` self-check refuses approved evidence (rest of BUG-021).** The first full
  run on PostgreSQL gave 308 passed, 2 failed: two older tests of `load-evidence` reported
  "sample: 30 rows not pending". The rows were the invented evidence rows my new tests had
  approved and left in the shared test database. The self-check was written when nothing could
  be approved and counts every evidence row that is not pending as a difference. That is the
  part of BUG-021 already assigned to M2.5d. Done here: the new tests remove their invented
  evidence rows, and the rows left by the earlier runs were deleted from the test database. Not
  done here: the self-check itself. **Until M2.5d, `load-evidence` will report a difference as
  soon as a real evidence row is approved**, as `completeness` will for an approved disease and
  `derive-meanings` for an approved feature mapping; the M2.5d row now names all three.
- A formatter run over whole directories also re-laid two old migrations (0001, 0003). They
  were restored from the last commit before anything else was done; neither is in this commit.

**Bugs.** None new in the code of this sub-step.

**Limits, stated plainly.**

- Nothing is approved and no mapping release exists, so no knowledge release exists.
- No source's rights are decided (D-S1). Until a reviewer approves a source, every statement and
  evidence row of it is held back from every release. That decision is the owner's; nothing in
  the code makes it.
- Retrieval chunks are in no release: they have no review status (now in M2.5e).
- Claims are not in a release: what an approved claim becomes is M2.5e.
- Statements and evidence are not scoped to a knowledge set: a release holds every approved
  statement and evidence row that passes the checks.
- Nothing serves from a release yet. `get_condition_information` still reads the working tables
  (approved rows only) until the serving views (M2.9); the serving bundle is M2.5f.
- There is no way yet to decide many rows at once: 22,947 evidence rows are decided one by one.
- A rollback of a knowledge release does not move the mapping release; each knowledge release
  says whether the mapping release it is pinned to is the current one.

**Committed and indexed (M2.5c2, M2.5c3).** The owner named both in one message, so they were
done one after the other, each with its own commit: `78380cb` (M2.5c2; CI passed on both jobs,
run 45166757670) and `2853a95` (M2.5c3; CI passed on both jobs, run 45169655475). The code graph
was re-indexed after each and reports up-to-date at `2853a95`. Migrations `0014` and `0015` are
applied to the main database. The API was restarted after each for the new routes; the web app
was not, because nothing it loads changed. This paragraph was added in a following
documents-only commit, after which the index was refreshed again.

**Correction (same day).** The entry and decision E84 first said that 13 of the 14 sources have
no licence recorded. The owner-test run showed 3 with a licence and 11 without. Both texts were
corrected in a documents-only commit.

### M2.5d1 — Self-checks that accept a reviewer's decision

Owner's go-ahead of 2026-11-24: "Please proceed". M2.5d held two separate pieces of work and is
done in two parts (decision E85): M2.5d1, the self-checks; M2.5d2, what a decision on a
vocabulary link entails. Only M2.5d1 was done here. It was done before the owner's approval of
the 85 features was entered (next entry), because that approval would otherwise have made
`completeness` report a difference.

**What the plan asks, checked before the work.** "`load-evidence` and `completeness` accept a row
whose decision carries a reviewer's name (BUG-021)" and, since M2.5c2 and M2.5c3, the same for
features, diseases, evidence rows and sources, whose tables have no reviewer column. Nothing
imported is marked approved without a reviewer (`CLAUDE.md`).

**What was found by reading the code.**

- `completeness` compared a status with `pending` in eleven places, not the two the plan row
  named: sources, disease mappings, diseases, feature mappings, features, statements, both kinds
  of evidence proposal, and three counts of mappings "awaiting review".
- Approving one feature that a mapping uses was enough to make `completeness` exit with a
  mismatch ("imported items already marked approved"). The 85 features are such features.
- `derive-meanings`, which the plan row also named since M2.5c3, was already right: it leaves a
  reviewed mapping and feature alone and reports nothing for it. The plan row is corrected.

**What was built.**

- `decisions.py` (new, in the ingestion package): the standing of a row. `pending`: as imported.
  `reviewed`: its present status is the last decision a reviewer recorded on it in
  `review_notes`, or it is a disease label retired by a merge that `disease_history` records.
  Anything else was changed by no reviewer. The module only builds SQL from names fixed in it.
- `evidence.py` (`summarise`, `check`), `completeness.py` (`_reference`, `_evidence`),
  `verify_files.py` (`verify_statement_file` and its query), `completeness_cases.py`
  (`disease_mapping_rows`, `_features`, `_list`), `completeness_rows.py` (`_statement_file`,
  `_acceptance`): each reads the standing where it read the status, and reports only a row
  changed by no reviewer. Three counts are renamed to say what they count
  (`changed_by_no_reviewer`, `mentions_changed_by_no_reviewer`,
  `diseases_changed_by_no_reviewer`), and seven report lines are reworded to match.
- `__main__.py`: the closing line of the report no longer says that everything is pending.

The two working sets (`mapping_releases`, `knowledge_releases`) are still expected to be
`pending`: they are never decided as a whole (E83, E84).

**Impact analysis.** HIGH for `_reference`, `_evidence`, `verify_statement_file`,
`_statement_file` and `_acceptance`: each has one direct caller, but all are on the single path
of the `completeness` command (`gather`, `inspect_file`, `emit`, `run_completeness`, `main`).
LOW for `summarise`, `check`, `disease_mapping_rows`, `_features`, `_list` and `main`. The HIGH
result was reported to the owner before the edit with the plan for every caller: no caller is
edited; each changed function keeps the shape of what it returns; the renamed counts are changed
at every reader in the same commit; the real command is run before and after. `detect_changes`
before commit: "high", 32 names in 9 files. Compared with the last commit by syntax tree: the
eleven functions above, the query `_STATEMENT_ROWS`, three existing tests and one test fixture
are changed, and two tests are new; `_feature_rows`, `_Named` and the other names listed are
there only because lines above them moved.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 67 files |
| `uv run pytest -m "not archives"` (SQLite) | 240 passed, 63 skipped |
| `uv run pytest` (SQLite, archives included) | 246 passed, 66 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | four runs: 311 passed and 1 failed; then 312 passed three times |
| `uv run python -m feeltriva_ingestion completeness` on the main database, before the change | 236 checks: 230 ok, 0 mismatches, 6 left to a later sub-step; 489 s |
| the same command with the changed code, twice | 236 checks: 230 ok, 0 mismatches, 6 left to a later sub-step, both times; 1,472 s beside two full test suites, 672 s alone. Earlier runs of the unchanged check took between 464 s and 697 s (M2.6a to M2.6c) |

Compared line by line, the two reports differ only in the reworded lines; every expected and
loaded value is the same.

The two new tests prove, on crafted files loaded with the real loaders: for each of the six
kinds of row (source, disease, disease mapping, feature, feature mapping, evidence row), a row
approved with no decision behind it is reported, the same row with its decision recorded as the
review path records it is not, and a row whose status is not its last recorded decision is
reported; a label retired by a merge is in order once the history records the merge; an
approved evidence row with its decision passes `load-evidence`, one without is reported, and a
decision for another status does not cover it. Three existing tests were changed to the new
names and wording; one of them now also shows that an approved statement with its decision is
in order. The invented evidence rows of the knowledge-release tests are no longer removed after
each test: they stay approved with their decisions, and the `load-evidence` tests that share the
database accept them, which is the fault of M2.5c3 shown the other way round.

**The failed run.** The first of the four PostgreSQL runs failed in
`tests/mcp/test_mcp_parity.py::test_full_flow_gives_identical_results_over_rest_and_mcp`. This
sub-step changes nothing in the API or the MCP server. The test then passed five times alone and
in three more full runs, two of them under load. It is the intermittent failure first recorded
in M2.13b; this is its second sighting. Its error text was again not captured, because the run
printed only its last lines. From now on the full output of every PostgreSQL run is saved, so
that the next sighting shows the cause. Recorded as open, not as fixed.

**Bugs.**

- **BUG-025 — `load-evidence` and `completeness` reported every row that was not `pending`.**
  The fault of BUG-021 in two more commands, found in M2.5c3 when two older tests failed. Fixed
  here as described above.

**Limits, stated plainly.**

- The rule trusts `review_notes`. A note can only be written in a reviewer's transaction
  (row-level security), but whoever owns the schema can write one directly; the check cannot
  tell that from a decision made through the review path.
- A reviewer who gives a kept label its standard name at a merge changes `preferred_name`. No
  check compares that name with the imported one today; if one is added it must allow for this.
- The checks of vocabulary links, relation suggestions and claims keep their own rule (a decided
  row names its reviewer in its own column). They already accepted reviewed rows.
- `completeness` still says nothing about clinical validity, and now also passes rows a
  reviewer rejected or retired: it checks that the import is intact, not what was decided.


**Committed and indexed (M2.5d1).** Committed as `d167dcd` and pushed; CI passed on both jobs
(run 45336562825). The code graph was re-indexed and reports up-to-date at `d167dcd`. No server
was restarted: only the ingestion pipeline changed, which neither the API nor the web app loads.

### M2.5c2a — The owner's approval of the 85 features recorded

Owner decision E86 of 2026-11-24. Asked "The 85 features your urgency rules name ... Do you
approve them, and should I enter that under your name as I did for the rules?", the owner
answered: "Yes, I am approving them". No code changed in this sub-step.

**What was done.** The 85 approvals were entered through the review path
(`POST /internal/v1/review/decisions`, target type `feature`) as `dev-reviewer:owner`, each with
the note: 'Approved by the owner on 2026-11-24 ("Yes, I am approving them"): one of the 85
features the approved urgency rules name. Entered by the assistant on the owner's instruction
(decision E86).' It was done after M2.5d1, so that the self-checks accept the decided rows.

**Checked before entering.** The 85 features listed in the rule file are exactly the features
the 20 approved rules name (same set). All 85 exist in the vocabulary, all were `pending`, all
are of the kind symptom with a yes/no value.

**Result on the real data.**

| What | Value |
|---|---|
| Features approved / still pending | 85 / 883 |
| Decision records for features (`review_notes`), all by `dev-reviewer:owner`, all `approved` | 85, written 2026-11-24 05:54:51 to 05:54:52 UTC |
| Audit events for these decisions | 85 |
| Approved features without a decision record | 0 |
| Column mappings of these 85 features | 198, all still pending (not decided) |
| Diseases, mappings, statements, evidence rows, sources decided | 0 |
| Preview of the mapping working set `mapping-lexical-0` | publishable, would be release 1: 85 features, 0 diseases, 0 mappings; undecided 883 features, 960 disease labels, 3,117 and 1,962 mappings |
| Published mapping releases | 0 (not published: a release cannot be removed, and publishing is the owner's act, E79) |
| `/readyz` | clinical mode off, synthetic release |

**The self-check on data that holds decided rows.** `uv run python -m feeltriva_ingestion
completeness` after the approvals: 236 checks, 230 ok, 0 mismatches, 6 left to a later sub-step
(963 s). Its report is line for line the report of the run before the approvals. Under the rule
that M2.5d1 replaced, the same run would have reported 85 "imported items already marked
approved" and exited with a mismatch: that is the number of approved features a mapping uses.

**Tests.** No code changed, so the suites of M2.5d1 stand (SQLite 240 passed, 63 skipped;
PostgreSQL 312 passed). CI passed on `d167dcd`.

**Also recorded from the owner's message (E86).**

- The four response texts: the owner answered "yes" to the assistant's reading of "it is fine" as
  approval of the four texts as written. They are approved; the approval is entered where the
  texts are stored, in M2.5f.
- Source rights (D-S1): the owner answered "ok". Read as an acknowledgement, not as a decision.
  No source is approved and D-S1 stays open.

**Bugs.** None.

**Limits, stated plainly.**

- Approving a feature approves its name, kind and value type. It approves no mapping of a source
  column to it, no evidence and no disease. The 198 mappings of these features are undecided.
- Nothing is published and nothing is served. The serving bundle (M2.5f) needs a published
  mapping release that holds these features, and the stored response texts.
- No doctor has reviewed the rules or the features (D-C2).

**Committed and indexed (M2.5c2a).** Committed as `9024e47` (documents only) and pushed; CI
passed on both jobs (run 45341856786). The code graph reports up-to-date. No server was
restarted: no code the API or the web app loads changed in M2.5d1 or M2.5c2a. This paragraph was
added in a following documents-only commit, after which the index was refreshed again.

### M2.5c4 — The owner's decisions of 2026-11-24 entered: mapping release 1 published, the 14 sources approved

Owner decision E87. "Publish mapping release 1 - yes", and on source rights (D-S1): "All the
sources are yes from my end, I trust you". No code changed in this sub-step.

**What was done.**

- Mapping release 1 was published through the review path
  (`POST /internal/v1/review/mapping-releases`) as `dev-reviewer:owner`, with a note that the
  assistant entered it on the owner's instruction.
- The 14 sources were approved through the review path (`POST /internal/v1/review/decisions`,
  target type `source`) as `dev-reviewer:owner`, each with the note: 'Approved by the owner on
  2026-11-24 ("All the sources are yes from my end"): the content of this source may be shown
  and used. Entered by the assistant on the owner's instruction (decision E87). The assistant
  has not verified a licence for this source; the decision is the owner's.'

**Result on the real data.**

| What | Value |
|---|---|
| Published mapping release | `mapping-lexical-0.r1`, number 1, current, published by `dev-reviewer:owner` at 2026-11-24 07:04:04 UTC |
| What it holds | 85 features; 0 diseases, 0 redirects, 0 mappings, 0 sources |
| Its SHA-256 | `5f4aadbb7a283aa1a2cceda7261923e1c9e3e427cf0957d5a5381f4c566b8dd9` (the value the preview gave before publishing) |
| Still undecided, as the release records | 883 features, 960 disease labels, 3,117 and 1,962 mappings |
| A second publication of the same content | refused, `release_already_published` |
| Sources approved / pending | 14 / 0; 14 decision records by `dev-reviewer:owner`, 2026-11-24 07:18:04 to 07:18:07 UTC |
| Sources with a licence on record | 3 of 14, unchanged |
| Preview of the knowledge set `knowledge-import-0` | not publishable: "no statement and no evidence is approved"; it would be pinned to `mapping-lexical-0.r1`; undecided 2,952 statements, 22,947 evidence rows, 0 sources |
| Published knowledge releases | 0 |
| `uv run python -m feeltriva_ingestion completeness` after both | 236 checks: 230 ok, 0 mismatches, 6 left to a later sub-step; the report is line for line the earlier one (1,460 s beside the test suites) |
| `/readyz` | clinical mode off, synthetic release |

**Tests.** No code changed, so the suites of M2.5d1 stand.

**Bugs.** None.

**Limits, stated plainly.**

- The approval of the sources is the owner's judgement of the rights. The assistant verified no
  licence. Eleven sources have none on record; the statements of archive 13 name Wikipedia pages
  as their source, and Wikipedia's text is offered under a licence that asks for attribution and
  for sharing alike. Whoever is responsible for the rights of the content should look at this
  before content is shown to users.
- Approving a source publishes nothing. No statement and no evidence row is approved, so no
  knowledge release exists.
- A published release cannot be edited or deleted. A later release or a rollback only changes
  which one is current.
- Nothing is served. The serving bundle is M2.5f.

**Committed and indexed (M2.5c4).** Committed as `2b19cb1` (documents only) and pushed.

### M2.5d2 — What a decision on a vocabulary link entails

Owner's go-ahead of 2026-11-24: "Please proceed". The second part of M2.5d (decision E85).

**What the plan and the owner's decisions ask, checked before the work.** "Rejecting a MONDO link
also retires the SNOMED CT and ICD-11 links derived from it (`import-identifiers` reports such
links and fails until this is handled)" (from M2.16). "Where a label has an ICD-11 category and
its unspecified sub-code as candidates, approval keeps the category" (E62, E66: the sub-code row
is preserved with its provenance, and no case is recoded). "The general term is the default when
a label has a broader and a narrower candidate" (E64). Codes are never shown to a user (E63).

**What was built** (decision E88). One rule function for the review target `terminology_link`,
`_link_guard`, with three small helpers, at the end of `review.py`. It runs inside the reviewer's
transaction before the status is set, like the rules for rule bundles and merged labels.

- Rejecting a MONDO link retires every pending link taken through it (`detail.via.link_id`), each
  with a decision record under the reviewer's name that says why, and an audit event.
- Withdrawing the rejection makes pending again the links the rejection retired, and only those.
- While a link taken through a MONDO link is approved, rejecting that MONDO link is refused
  (`derived_links_approved`): the reviewer decides the approved link first.
- A link is not approved while the MONDO link it rests on is rejected (`basis_rejected`).
- Where a term has two ICD-11 candidates and one lies under the other, the narrower one is not
  approved while the broader one is pending or approved (`general_term_is_default`). This covers
  a category and its unspecified sub-code, and a narrower code under a general one.
- A refusal names the title and our own link ID of the other link, never a code.

`record_review`, the route and the database are unchanged; no migration.

**Real run.** The API was restarted for the rule. As reviewer on the real data:

| What | Result |
|---|---|
| Approving the ICD-11 link taken through the rejected MONDO link "atopic eczema" (E64) | refused, `basis_rejected` |
| Approving "Optic neuritis, unspecified" while its category "Optic neuritis" is a candidate | refused, `general_term_is_default` |
| Links by status before and after the two attempts | 2,531 pending, 5 approved, 6 rejected; unchanged |
| Decision records on links before and after | 11; unchanged |
| Pending links resting on a rejected MONDO link (what `import-identifiers` fails on) | 0 |
| Terms with a category and its unspecified sub-code both as candidates, now covered by the rule | 121 |
| Other pending candidates lying under another candidate of the same term | 0 (the two E64 cases of this kind, stye and valley fever, are already decided) |

**Impact analysis.** `record_review`: LOW, not changed; it calls the rule registered for the
target. `TerminologyLink`: MEDIUM by count, read and set through the columns the API's role may
already change (`status`, `reviewer`), not changed. `detect_changes` before commit: "low", no
existing name touched. Compared with the last commit by syntax tree: four functions are new in
`review.py`, four tests and a fixture are new, nothing existing changed.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 67 files |
| `uv run pytest -m "not archives"` (SQLite) | 243 passed, 64 skipped |
| `uv run pytest` (SQLite, archives included) | 249 passed, 67 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 316 passed, twice; full output saved |

The four new tests prove, with invented links: rejecting a MONDO link retires the two links taken
through it and leaves alone the link found by its own name; the retirement is recorded with the
reviewer and the reason; a link is not approved while its MONDO link is rejected; withdrawing the
rejection brings the two back; a MONDO link is not rejected while a link taken through it is
approved, and nothing is retired by the refused attempt; a narrower code and an unspecified
sub-code are not approved while the category stands, whether the relation is the recorded parent
or the code itself; the refusal names no code; approving the category changes no other row; after
the general candidate is rejected the narrower one can be approved; on PostgreSQL, a link the
reviewer retired is not brought back by a withdrawal.

**Bugs.** None found.

**Limits, stated plainly.**

- The rule sees a broader and a narrower candidate only when one code lies under the other. For
  eczema and indigestion (E64) the two candidates are not under one another in the
  classification, so choosing between them stays the reviewer's judgement.
- Where the import did not record WHO's parent, the relation is read from the code itself (a
  code that continues another). The 121 recorded pairs do not depend on this; at present no
  other pending pair exists.
- A MONDO term that is narrower than our label (the "atopic eczema" case) is not detected: the
  API does not hold MONDO's hierarchy.
- The test of "a link the reviewer retired stays retired" runs on PostgreSQL only, because the
  order of two decisions is read from recorded times and SQLite keeps them to the second.
- The review screens (M2.4) still have to show these refusals to a reviewer in words.

**Committed and indexed (M2.5c4, M2.5d2).** `2b19cb1` (M2.5c4, documents only; CI passed on both
jobs, run 45350954954) and `f92a700` (M2.5d2; CI passed on both jobs, run 45351279030). The code
graph was re-indexed and reports up-to-date at `f92a700`. The API was restarted for the rule of
M2.5d2; the web app was not, because nothing it loads changed. This paragraph was added in a
following documents-only commit, after which the index was refreshed again.

### M2.5f — The serving bundle from the current releases

Owner's instruction of 2026-11-24: "do M2.5f and M2.9". Each is done with its own commit; this
entry is M2.5f.

**What the plan asks, checked before the work.** The bundle loaded in clinical mode must hold the
rules of the current rule release, the features those rules name with an approved status from
the mapping release, and the four response texts; the sub-step "assembles that file from the
current releases and refuses when any part is missing or not approved". From M2.5c3: the bundle
is refused when the current knowledge release is pinned to a mapping release that is not the
current one. From M2.5f1 and E86: storing the approved texts and entering the approval belongs
here. Clinical mode defaults off and no external model provider is called (`CLAUDE.md`).

**What was built** (decision E89).

- Migration `0016`: table `response_text_sets` (the four texts as stored, the file's SHA-256,
  status, who approved and when). A trigger refuses any change to the texts of a decided set.
  The API's role may read, and decide only in a reviewer transaction; it cannot change a text.
- `response_text_sets.py` (new): stores the texts file (`python -m
  feeltriva_api.response_text_sets`); review target `response_texts`; approval is refused when
  the file is not the one stored or fails its checks; `list_sets` for reviewers.
- `serving_bundle.py` (new): `assemble`, `preview`, `write`, `verify_serving`, and the command
  `python -m feeltriva_api.serving_bundle`, which writes the bundle and a second file saying
  what it was built from.
- `bundle.py`: a bundle may name no knowledge release (both fields empty); it then may hold no
  candidates and no citations. `seed.py` registers no knowledge release for such a bundle;
  `feeltriva_retrieval` copes with the empty name.
- `container.py`: in clinical mode the loaded bundle must be exactly what the current releases
  give (`verify_serving`), in addition to the check of M2.5b.
- `main.py`: `GET /internal/v1/review/response-texts`, `GET /internal/v1/review/serving-bundle`.
  Reviewers only.

**Real run.** Migration applied to the main database (head `0016`). The API was restarted.

| Step | Result |
|---|---|
| The texts file stored | `response-texts-draft-1`, 4 texts, SHA-256 `272179d62ea79ac122afacdde2965530102f22077b41876e3494ce6d969a1acd`; unchanged since the commit the owner read (`9512eb8`); stored pending |
| Assembling before the approval | refused: "the response texts are not approved"; nothing written |
| The owner's approval (E86) entered through the review path as `dev-reviewer:owner` | pending to approved, with a note quoting the owner and saying that the assistant entered it |
| Assembling | bundle `urgency-draft.r1`: 20 rules, 85 features, 0 questions, 4 response texts, 0 candidates; SHA-256 `d89b006bf71a24364b89ed81640e3746de4dcdab01e0661ca9467a4e5c115821`; built from rule release `urgency-draft.r1`, mapping release `mapping-lexical-0.r1`, text set `response-texts-draft-1`, no knowledge release |
| Where | `data/derived/serving_bundle.json` (53,129 bytes) and `serving_bundle.manifest.json`; `data/` is outside Git |
| Loaded as clinical mode loads it | passes the clinical-mode checks; its rules are the current rule release; the whole bundle is what the releases give; every rule text is the text of the approved rule file |
| `/readyz` | clinical mode off, synthetic release: nothing changed in what runs |

**Impact analysis.** All LOW: `ReleaseBundle`, `validate_bundle`, `seed_release`,
`build_container`, `BundleEvidenceProvider`, `create_app`, and the changed test. The graph does
not trace readers of the bundle across packages, so they were found by search: `seed.py`,
`service_results.py` (passes both fields on; the result's `versions.knowledge` and the
assessment's knowledge column already allow an empty value), `feeltriva_retrieval`; the MCP
server reads neither field. `detect_changes` before commit: "medium", 19 names in 7 files.
Compared with the last commit by syntax tree: changed are `ReleaseBundle`, `validate_bundle`,
`BundleEvidenceProvider.__init__`, `build_container`, `seed_release`, `create_app` (two routes)
and one test with its fixture; `ResponseTextSet` is new; the rest is listed because lines moved.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 69 files |
| `uv run pytest -m "not archives"` (SQLite) | 249 passed, 65 skipped |
| `uv run pytest` (SQLite, archives included) | 255 passed, 68 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | four runs: 323 passed; 322 passed and 1 failed (BUG-026); after the fix 323 passed twice. Full output saved |
| Migration `0016` on a scratch database: head, down to `0015`, head | table and policies present, absent, present |

The seven new tests prove, on a database of their own with invented rules: every missing part is
named and nothing is written; a mapping release that lacks a feature a rule names is refused with
the feature's name; the assembled bundle holds the rules of the current rule release, the
features of the mapping release and the approved texts, names no knowledge release, passes the
clinical-mode checks and loads from its file; a bundle with an edited text, the sample bundle, a
bundle assembled before a later release, and a bundle whose texts lost their approval are each
refused at the start check; a knowledge release pinned to the current mapping release is named
in the bundle and one pinned to an earlier release refuses it; a bundle names a knowledge release
fully or not at all; the texts are stored as the file has them, approved only as stored, not
rewritten once decided, and a withdrawn approval names nobody; the two routes are for reviewers
only; on PostgreSQL the texts of a decided set cannot be changed even by the schema owner.

**Bugs.**

- **BUG-026 — a test of the chunk loader failed once the test database held more than 50 of
  its own leftovers.** One of four PostgreSQL runs failed in
  `test_chunks_are_stored_pending_searchable_and_idempotent`. The saved output showed the cause:
  the test searched the shared test database for words that every run stores, with a limit of
  50, and expected its own row among the results; 62 such rows had accumulated. Not caused by
  this sub-step. Fixed: the test's file now carries a word of its own run and the test searches
  for that. The test file is one of three that are not laid out by the formatter; only the
  changed lines were touched.
- The intermittent failure of the MCP parity test (M2.13b, M2.5d1) did not occur in these runs.

**Limits, stated plainly.**

- **Clinical mode cannot be switched on yet.** It refuses the mock extraction provider, and no
  other provider exists (M5). Switching it on is also the owner's go-live decision (E36, E45).
- The bundle holds no candidates. Served as it is, the service would screen every message for
  the 20 urgency rules and otherwise answer with the "not enough information" text.
- An urgency message does not show the source it rests on; the sources are in the rule release.
- The file must be assembled again after every new release; the start check refuses an old file.
- An assessment records the rule bundle's ID and, in its result, the rule release's ID. A column
  for the published release IDs of mapping and knowledge on the assessment is not built (R12).
- No doctor has reviewed the rules, the features or the texts (D-C2).

**Committed and indexed (M2.5f).** Committed as `02c3731` and pushed; CI passed on both jobs
(run 45354379289). The code graph was re-indexed and reports up-to-date at `02c3731`. Migration
`0016` is applied to the main database; the API was restarted.

### M2.9 — Serving views

Second of the two sub-steps the owner named on 2026-11-24 ("do M2.5f and M2.9").

**What the handoff and the plan ask, checked before the work.** The exports
`reviewed_disease_catalog` (IDs, names, aliases, definitions; from an approved mapping release),
`reviewed_disease_feature_edges` (approved evidence and source use rights) and
`reviewed_care_statements` (management, treatment and prevention descriptions with
applicability) (`docs/04`). "Restrict serving queries to approved/versioned releases. Pending data
stays research-only" (`specs/schema.sql`). Plan: a pending, rejected, retired or expired row
never appears in any view, and the views are the only objects the serving code reads.

**What was built** (decision E90).

- Migration `0017`: four views over the current published releases. `reviewed_disease_catalog`;
  `reviewed_condition_statements` (every statement of a condition, with its source records);
  `reviewed_care_statements` (of those, the statements about care); and
  `reviewed_disease_feature_edges`. The application role may select from them and nothing more.
- `review.py`: `KnowledgeService.get_condition_information` reads the catalog and the condition
  statements from the views and nothing else. Its inputs and the shape of its answer are
  unchanged, for the REST route and for the MCP tool.

**When a row is shown.** All of this must hold at the moment of reading: the row is in the
current release; the knowledge release is pinned to the mapping release that is current; the row
is still approved in the working tables; its source is still approved; a statement has not
expired. A release is the only way in. A rejection, a retirement, a withdrawn source approval or
an expiry takes a row out at once.

**Changed behaviour.** Content that is approved but not published is no longer served. Before,
an approved statement of an approved disease was served as soon as it was approved.

**Real run.** Migration applied to the main database (head `0017`). The API was restarted.

| What | Result |
|---|---|
| Rows in the four views | 0, 0, 0, 0: the current mapping release holds 85 features and no disease, and no knowledge release exists |
| `GET /v1/conditions/{id}` for two real labels and an unknown ID | 404 `condition_not_available` each |
| The application role on a view | may select; may not update |
| `/readyz`, serving-bundle preview | unchanged: clinical mode off; bundle `urgency-draft.r1` assembles as before |

**Impact analysis.** `get_condition_information`: LOW, two callers (the REST route `get_condition`
and the MCP tool), both of which pass the answer through; `services/mcp/.../server.py` was read
and `tests/mcp` run. `detect_changes` before commit: "medium", 13 names in 2 files. Compared with
the last commit by syntax tree: `KnowledgeService.get_condition_information` and its class text
changed; in the tests one test was replaced by two and one was added; `list_terminology_links`
and the other names are listed because lines above them moved.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 69 files |
| `uv run pytest -m "not archives"` (SQLite) | 250 passed, 68 skipped |
| `uv run pytest` (SQLite, archives included) | 256 passed, 71 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 326 passed, 1 skipped, twice; full output saved |
| Migration `0017` on a scratch database: head, down to `0016`, head | four views present, absent, present |

The new and changed tests prove, with invented rows: nothing decided, nothing is in any view;
approved and the mapping release published, the disease is in the catalog with its other name
and merged label, and no statement or evidence is shown without a knowledge release; with the
knowledge release, three of eight statements and two of six evidence rows are shown, and the
pending ones, the expired one, the one without a source, the one of a source that is not
approved and what stands under a label that is not approved are in no view; a statement of a
merged label stands under the label kept and carries its source record; the care view holds the
treatment statement only; the condition route gives the same statements under either label and
404 for a label that is not approved; retiring a statement removes it and the evidence row that
rests on it, at once; a statement that expires after publication, a rejected evidence row, a
retired feature, a withdrawn source approval and a rejected disease each take their rows out at
once and restoring the approval brings them back; when a later mapping release becomes current
the knowledge views are empty and the catalog is not, and a rollback shows them again; the
application role reads every view and can write through none; approved content that is not
published is not served (both databases); where the views do not exist the route answers that
nothing is available. The one skipped test on PostgreSQL is that last one, which is for SQLite.

**Bugs.** None found. The intermittent MCP parity failure did not occur.

**Limits, stated plainly.**

- All four views are empty on the real data. They fill when diseases, statements and evidence
  are approved and published; the 14 sources are approved already.
- The views unfold the current release on every read. That is fast at today's size and will need
  a stored copy per release when releases hold tens of thousands of rows.
- The views exist in PostgreSQL only. The unit tests on SQLite cannot show what they hold; those
  tests run on PostgreSQL, locally and in CI.
- Nothing reads `reviewed_disease_feature_edges` or `reviewed_care_statements` yet: candidate
  ranking and care guidance are later steps (M4, M5).
- Applicability is a column, not a filter: no statement carries any yet.
- The retrieval chunks are in no view: they have no review status (M2.5e).

**Committed and indexed (M2.9).** Committed as `3da314d` and pushed; CI passed on both jobs (run
45359559129). The code graph was re-indexed and reports up-to-date. Migration `0017` is applied to
the main database; the API was restarted for the changed condition route; the web app was not,
because nothing it loads changed. This paragraph was added in a following documents-only commit,
after which the index was refreshed again.

### M2.5e1 — Claims and text chunks in the review path; what an approval makes

Owner's instruction of 2026-11-24: "Do M2.5e and M2.4". M2.5e touches two different parts of the
system, the review path of the API and the ingestion pipeline, and is committed as M2.5e1 and
M2.5e2, both in this round. This entry is M2.5e1.

**The owner's question, answered before the work** ("Will the above be implemented in some other
step?"). The bundle has no candidates: the ranking model is M4 and retrieval is M5.2, but no
sub-step said that the assessment service takes its possible explanations from the promoted model
and the reviewed evidence with citations from the knowledge release. That was a gap in the plan;
row M5.7 is added. A bundle that carries no knowledge release: already handled; the bundle names
the knowledge release as soon as one is published. Views in PostgreSQL only: no step, by design.

**What the plan and the handoff ask, checked before the work.** "Approving a list-item claim that
carries a proposed feature turns it into evidence for that disease and feature; a reviewer sets a
claim's applicability; ... statements from the text files are made after their chunks are
reviewed" and, from M2.5c3, a reviewer's decision on a chunk. `docs/04`: "13 text files →
source_records; statements/evidence_chunks after review"; `symptoms.csv`: "extract atomic feature
relations into review queue". `docs/01` §4: statement types `treatment | management |
prevention | cause | description | symptom`, with applicability and review status. M2.4 needs a
reviewer-only route and review target for the claims.

**What was built** (decision E91).

- Migration `0018`: claims and chunks can be read and decided in a reviewer transaction only;
  `evidence_chunks` gains `status` and `reviewer`; the API's role may insert evidence,
  statements and statement sources in a reviewer transaction only; `statement_claims` gains
  `superseded_by` (used in M2.5e2).
- `review_claims.py` (new): review targets `claim` and `chunk` with their rules; `list_claims`,
  `set_applicability`, `list_chunks`.
- `main.py`: `GET /internal/v1/review/claims`, `POST .../claims/{id}/applicability`,
  `GET .../chunks`. Reviewers only.
- `models.py`: `StatementClaim`, `EvidenceChunk`.

**What an approval makes.** An approved list item that names a feature: one evidence row, made
once, retired when the approval is withdrawn. An approved part of a text: one statement with its
source record and its place in the file, its type from the source's section heading, retired
when the approval is withdrawn. A list of references is not approved.

**Real run.** Migration applied to the main database (head `0018`). The API was restarted.

| What | Result |
|---|---|
| Statements listed with their claims | 2,952 statements, 8,742 claims, all pending |
| Statements with a claim marked `cut_off` / `first_item_preposition` | 79 / 78; marked statements are listed first |
| Statements holding a list item with a proposed feature | 40 (106 such items) |
| A real statement (atherosclerosis) | six list items shown under their sentence; four name a feature (sweating, nausea, breathlessness, palpitations) |
| Text chunks listed | 3,651, all pending; 58 for the label "Alzheimer's disease", each with its section and the type it would get |
| A user on the claims route | 403 |
| Decided claims and chunks; statements and evidence rows made | 0, 0, 0, 0: nothing was decided |

**Impact analysis.** `create_app`: LOW. `published_knowledge._content`: LOW and `_counts`: HIGH
(four flows) were looked at for putting chunks into a release; neither is changed, because an
approved chunk enters a release as the statement made from it. `detect_changes` before commit:
"low", 8 names, all of them the request bodies at the end of `main.py`, listed because lines
above them moved. By syntax tree: `create_app` changed (three routes); `ClaimApplicability`,
`StatementClaim`, `EvidenceChunk` and the new module are new.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 70 files |
| `uv run pytest -m "not archives"` (SQLite) | 255 passed, 69 skipped |
| `uv run pytest` (SQLite, archives included) | 261 passed, 72 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 332 passed, 1 skipped, twice; full output saved |
| Migration `0018` on a scratch database: head, down to `0017`, head | columns and policies present, absent, present |

The six new tests prove, with invented rows: a user can neither list nor decide; a statement is
listed with its sentence and the items of its list, their marks and proposed feature, and the
filters by mark, feature and status choose statements; an approved sentence and an approved item
without a feature make nothing; an approved item that names a feature makes one evidence row
with its disease, feature, statement and its own decision record; a withdrawn approval retires
the row and a new approval approves the same row, never a second one; applicability is stored
with who said it, shown in the list, removable, and decides nothing; a part of a text is listed
with the type it would get; a list of references is refused; an approved part becomes one
statement with the file's record and the part's place in the file, retired and approved again
with its chunk; the statement made from a chunk and the evidence made from a claim enter a
published knowledge release; on PostgreSQL a user's transaction reads no claim and no chunk,
decides none and makes no evidence or statement, and a reviewer's cannot change the wording.

**Bugs.** None found.

**Limits, stated plainly.**

- Nothing is decided. 8,742 claims and 3,651 chunks are decided one at a time; there is no way
  yet to decide many at once.
- Applicability is free text. Nothing filters by it.
- A statement made from a chunk gets its type from the section heading; a reviewer cannot choose
  another type.
- A claim's evidence row and a mention proposal of M1.11 for the same disease and feature both
  exist, each with its own basis.
- After a chunk is approved, `extract-claims` has to be run to make the claims of the new
  statement.

**Committed and indexed (M2.5e1).** Committed as `f357465` and pushed. The code graph was
re-indexed and reports up-to-date at `f357465`. Migration `0018` is applied to the main database;
the API was restarted. The CI result of this commit is recorded with that of M2.5e2 below.

### M2.5e2 — Claims after a change of the rules; a source's cut-off length found by measurement

The second commit of M2.5e (owner's instruction of 2026-11-24).

**What the plan asks, checked before the work.** "How a reviewer's decision is carried over to
the claims of newer rules (E72) ... before another text source is loaded its word limit is found
by measurement (E74)". Acceptance: "a rule change does not lose a decision; a cut-off limit
other than 120 words is found". E72: a reviewer's decision is never deleted by a command; until
now a statement that held one was left out of every remake and reported each time. E74: the
120-word limit "is a fact about one source".

**What was built** (decision E92).

- `claims.py`: `split` takes the number of words at which the statement's source cuts its texts;
  left out, it is the 120 of the one source measured by hand, so every existing caller behaves
  as before. `measure_cut_off` finds that number from a source's texts: the longest length, when
  at least five texts have exactly that length and most of them end without a full stop. Rules
  `claims-5`.
- `claims_load.py`: `cut_off_limits` measures every source before its statements are split.
  `_carry_over` brings a statement that holds a reviewer's decision to the present rules: a claim
  the rules give again is the same row and keeps its decision, with the present cues and
  sentence; a decided claim the rules no longer give is kept and marked (`superseded_by`); an
  undecided one is deleted; the caller stores the new ones as pending. Only with `--remake`.
- `completeness.py`, `completeness_rows.py`: a kept claim is no fault; the claims are recomputed
  with the measured length; the line "statements extracted from the text files after review",
  left to a later step since M1.13, is replaced by two checks of the statements made from
  approved parts of the text files (M2.5e1).

**Real run.**

| Command | Result |
|---|---|
| `uv run python -m feeltriva_ingestion extract-claims` on the main database | rules `claims-5`: 2,952 statements read; inserted 0; stored 8,742 claims, all pending; 0 claims the rules do not give; 79 sentences marked `cut_off`, as before |
| What the measurement found | one source cuts its texts: `archive(13).zip/diseases_main.csv`, at 120 words. This is the value measured by hand in M2.6c; no other source shows a limit |
| `uv run python -m feeltriva_ingestion completeness` | 237 checks: 232 ok, 0 mismatches, 5 left to a later sub-step (524 s). Before: 236 checks, 230 ok, 6 left. One "later" line became two checks, both 0 of 0 |

**Impact analysis.** HIGH: `split` (five direct callers, four flows), `_cut_off`, `_claims` and
`_texts`. LOW: `extract_claims`, `_earlier`, `gather`. The HIGH result was reported to the owner
before the edit with the plan for every caller: `split`'s new argument is optional and its
default is today's value; `_cut_off` is called by `split` only; `_claims` returns the same
counts and one more; `_texts` gets its new counts from `gather` in the same commit.
`detect_changes` before commit: "high", 40 names in 8 files. Compared with the last commit by
syntax tree: `split`, `_cut_off`, `_earlier`, `check`, `extract_claims`, `report`, `_claims`,
`gather` and `_texts` changed; `measure_cut_off`, `_carry_over` and `cut_off_limits` are new;
`_acceptance`, `run_completeness`, `_bare` and the other names are listed because lines moved.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 70 files |
| `uv run pytest -m "not archives"` (SQLite) | 256 passed, 72 skipped |
| `uv run pytest` (SQLite, archives included) | 262 passed, 75 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 336 passed, 1 skipped, twice; full output saved |

The new tests prove: a limit of 63 words is found from five texts cut there, and none where too
few texts share the longest length or the texts end properly; `split` marks a text cut at the
measured length and drops its last item, and marks nothing without a limit; through the loader,
a source with six texts of 16 unfinished words gets the limit 16 and its sentences the mark
"16 words" ("a cut-off limit other than 120 words"); after a rule change, an approved item the
rules give again is still approved under its new sentence, a rejected sentence the rules no
longer give is kept and marked, the undecided item the rules dropped is deleted and made again,
and a second run changes nothing and reports nothing ("a rule change does not lose a decision");
an undecided sentence stays when a decided item stands under it; without `--remake` nothing is
added and the command says how to go on. One existing test asserted the old rule (a reviewed
statement is never remade) and was replaced by these.

**Three wrong expectations of mine, corrected before commit.** My first version of the new tests
expected the earlier rules' last list item to survive a rule change. It rightly does not: under
the earlier rules it ran on to the end of the text, so the present rules give another span. The
code was right and the tests were changed.

**Bugs.** None found in the code.

**Limits, stated plainly.**

- When the cues of a decided claim change with the rules, the decision is kept and the cues are
  updated. A reviewer is not told that a claim they decided now carries another mark.
- The measurement needs at least five texts at the longest length. A source with fewer texts cut
  at its limit is not recognised.
- It measures words. A source that cuts at a number of characters is not recognised.
- A kept claim keeps the evidence row it made.

**Committed and indexed (M2.5e2).** Committed as `2a9d1e3` and pushed. The code graph was
re-indexed and reports up-to-date at `2a9d1e3`. No server needed a restart for it: only the
ingestion pipeline changed. CI results of M2.5e1 and M2.5e2 are recorded with M2.4a below.

### M2.4a — The review screens read and write through the review API

Owner's instruction of 2026-11-24: "Do M2.5e and M2.4". M2.4 held three pieces of work, two of
which need new work in the service, and is done in three parts (decision E93): M2.4a the screens
on what the service already offers; M2.4b the close vocabulary results and the terms without a
link; M2.4c the urgency rules in words. Only M2.4a was done here.

**What the plan asks, checked before the work.** "The web reviewer screens read and write
through the review API instead of mock state"; from M2.16, links taken from MONDO shown with the
MONDO term they came through; from M2.6 and M2.6c, a statement with its claims, cues, proposed
feature and the two marks with what to check, each claim decided; codes shown to reviewers only
(E63). Acceptance: "inspect duplicate column, save note; confirm one close vocabulary result and
reject another". The close results are not in the database yet (M2.4b), so here the browser
flow approves one stored vocabulary link and rejects another.

**What was built** (decision E93).

- Service: `GET /internal/v1/review/notes` (`list_notes`), the notes and decisions on one item,
  for reviewers only, so that a saved note can be shown again.
- Web: `api/liveReview.ts`, the client for the reviewer routes; `routes/review/live/`: a drawer
  that shows an item, its notes and the form that records a note or a decision; a list page that
  searches, filters and pages through the service; the screens overview, disease mappings,
  feature mappings, data quality, vocabulary links, statements and claims, urgency rules,
  releases. `ReviewRoutes` and `ReviewShell` choose by mode: live screens in http mode, the design
  demo on fixtures in mock mode.
- Configuration: `VITE_DEV_REVIEWER` (with `VITE_DEV_AUTH`) names the development reviewer;
  `pnpm dev:review` starts the live workspace as reviewer "owner"; without a reviewer name the
  workspace says that reviewer sign-in is not configured and asks the service for nothing.
- Browser test: `pnpm e2e:review` with `apps/web/scripts/seed_review_e2e.py`, against a test
  database with invented rows.

**Real run.**

| What | Result |
|---|---|
| Browser flow (`pnpm e2e:review`) on the test database, second API on port 8001, web on 5174 | 15 of 15 checks pass |
| What it did | opened a repeated column heading, saw both positions and the 12 disagreeing rows, was refused an empty note, saved a note, saw it with the reviewer's name, saw it again after a reload; was refused the narrower vocabulary link in the service's words, rejected it and approved the general one; approved a list item with a mark and a proposed feature |
| What the service held afterwards, asked directly | the note under `dev-reviewer:e2e` with no status changed; one link approved and one rejected under that name; one evidence row made from the approved item |
| Every request to the service | carried the reviewer token and no other |
| The real API on port 8000, restarted | the notes route returns the owner's note on a real approved feature; a user gets 403; the data-quality list holds the 74 real repeated column positions |
| The two temporary servers (8001, 5174) | stopped after the run |

No decision was recorded on real data in this sub-step.

**Impact analysis.** LOW: `ReviewRoutes`, `ReviewShell`, `createAppServices`, `parseConfig`,
`create_app`. HIGH by count: `ReviewNote` (fifteen modules import the models or create notes),
changed for BUG-027; reported to the owner before the edit with the plan: no creator is edited,
none passes a time itself, the model sets it. `detect_changes` before commit: "medium", 16 names
in 12 files; in the Python files `create_app` (one route) and `ReviewNote` changed and
`list_notes` is new, the other names are listed because lines moved; in the web files the names
are the ones changed on purpose.

**Tests actually run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 70 files |
| `uv run pytest -m "not archives"` (SQLite) | 257 passed, 72 skipped, six runs in a row |
| `uv run pytest` (SQLite, archives included) | 263 passed, 75 skipped |
| `uv run pytest` on PostgreSQL with `TEST_OBJECT_STORAGE_ENDPOINT`, real archives included | 337 passed, 1 skipped, four runs; full output saved |
| `pnpm typecheck` / `pnpm lint` / `pnpm build` (apps/web) | clean |
| `pnpm test` (apps/web) | 130 passed in 8 files |
| `pnpm e2e:review` (browser, test database) | 15 of 15 |

The new web tests prove: the client asks the reviewer routes with the reviewer token and only
the filters that are set, records a note without a status and a decision with one, passes on the
service's refusal, and asks nothing without a reviewer; the data-quality screen shows a repeated
heading as stored, refuses an empty note, records a note and a decision and shows them; a
refusal of the service is shown in its words; a statement is shown with its sentence, items,
mark and proposed feature, and applicability is recorded; with no reviewer configured the
workspace asks the service for nothing. The existing tests of the design demo still pass.

**Bugs.**

- **BUG-027 — two notes recorded within a second came back in either order.** Found when the
  new test of the notes route failed in two of four SQLite runs. The time of a note was filled
  in by the database: SQLite keeps it to the second, and PostgreSQL gives every note of one
  transaction the same time. The same cause as BUG-024. Fixed: the model sets the time in the
  code, to the microsecond. Six SQLite runs and four PostgreSQL runs then passed.
- Two checks of my browser test failed on its first run because they looked before the drawer
  had read the notes again; the screen was right (seen in the screenshot). The test now waits.

**Limits, stated plainly.**

- **The close vocabulary results are not on a screen** (M2.4b): the 431 close ICD-11 results,
  the names without an HPO or MONDO link, the 13 labels without a single equivalent. The second
  half of the plan's browser flow, "confirm one close vocabulary result and reject another", is
  therefore not met yet.
- **The urgency rules are not shown in words** (M2.4c): the screen shows a rule's level, text
  and stored condition and points to the review document.
- There is no real reviewer sign-in. `pnpm dev:review` records under the name "owner", through a
  development token the service accepts only in development.
- The answers of the service are not checked field by field in the browser, as they are for the
  patient-facing screens.
- No way yet to decide many rows at once, merge labels, or publish a release from a screen.
- While a list is read again after a decision, the table is replaced by "Loading…" for a moment.
- In a development server the app-wide banner still says "Design demo · Sample scenarios" above
  the live workspace; the workspace itself says "Live review data".
- `pnpm format:check` reports one older file, `scripts/e2e-live.mjs`; it was not touched.
- The browser test is run by hand; it is not part of CI, like `pnpm e2e:live`.

**Committed and indexed (M2.5e1, M2.5e2, M2.4a).** `f357465` (M2.5e1; CI passed on both jobs, run
45362478313), `2a9d1e3` (M2.5e2; CI passed on both jobs, run 45365845875) and `fa13525` (M2.4a; CI
passed on both jobs, run 45372328021). The code graph was re-indexed after each and reports
up-to-date at `fa13525`. Migration `0018` is applied to the main database. The API on port 8000
was restarted after M2.5e1 and after M2.4a; the web app on port 5173 was not, because the design
demo it serves did not change; port 5174 was used for the browser test and stopped. This
paragraph was added in a following documents-only commit, after which the index was refreshed
again.

### Web port — one port, 5173 (owner's instruction of 2026-11-24)

The owner went to test the live review screens and found nothing on port 5174: the working
agreement had the live mode started there only for a sub-step and stopped afterwards. Their
instruction: "keep 5174 port closed, we will use 5173 only" (decision E94).

**Impact analysis.** `scripts/e2e-live.mjs` and `scripts/e2e-review-live.mjs`: LOW, no callers
(both are run from the command line). No application code is changed.

**Implemented.**

- `apps/web/package.json`: `dev:api` and `dev:review` use port 5173, as `dev` does. Each has
  `--strictPort`, so a second one refuses to start while the first holds the port.
- `scripts/e2e-review-live.mjs` starts no web server. The new script `build:e2e-review` builds
  the app in live mode (reviewer `e2e`, service on port 8001) into
  `node_modules/.cache/feeltriva-e2e-review`, outside Git, and the test hands those files to the
  browser itself under the address of port 5173. Nothing listens; a web server that is running
  on 5173 is not touched. `pnpm e2e:review` builds first, then runs the test.
- `scripts/e2e-live.mjs` expects the live mode on 5173.
- `CORS_ALLOWED_ORIGINS` in `.env.example` and in the local `.env` names 5173 only.
- `README.md` and the working agreement in `CLAUDE.md` say: one web port, three commands, one at
  a time, and every report says which one is running.

**Found on the way.** Chrome refused the calls of the page to the test service: a page handed
over from disk does not count as a page of this machine, and Chrome blocks such a page from
calling a service on this machine. The test's browser context is now given the permission
`local-network-access`. This concerns the test only; a page served by the development server
is a page of this machine.

**Tests run.**

| Command | Result |
|---|---|
| `pnpm e2e:review` against the test database, service on port 8001, web server on 5173 left running | 15 passed, 0 failed |
| Ports afterwards | 5173 answers, 5174 and 8001 do not |
| `pnpm lint` / `pnpm exec prettier --check` on the two files touched and formatted | clean |
| `pnpm test` | 130 passed (8 files) |
| `detect_changes` before commit | 8 files, risk low, no flow affected. The functions it lists in `e2e-review-live.mjs` stand below the inserted lines and are unchanged. It also lists `docs/HANDOFF_README.md` and `apps/web/README.md`, which `git status` shows unchanged: it matched the changed lines of `README.md` to the other files of that name |

**Limits, stated plainly.**

- The design demo and the live mode cannot run side by side any more. Which one is running is
  said in every report; changing takes stopping one command and starting the other.
- The browser test still needs a second copy of the service on port 8001 while it runs, on the
  test database. That is not a web port, and it is stopped when the test ends.
- `scripts/e2e-live.mjs` is still not laid out by the formatter; three of its lines changed.

### M2.4b — Close vocabulary results and names without a link, loaded for review

**What it is for.** The look-ups of M2.11, M2.14 and M2.16 store a link only for an exact name or
for the one identifier a vocabulary marks equivalent. Everything else went to three review files
outside the database: no screen could show it and no decision could be recorded. The owner
decided (E57) that the close results are confirmed or rejected in the review screens.

**Impact analysis before editing** (all LOW). `best_result`: one caller, `link_vocabularies`.
`link_vocabularies`, `link_ontologies`, `import_identifiers`: called by the command line (`main`)
and their tests only. `_link_guard` is not changed; the new rule calls it. `LiveListPage` and
`DecisionDrawer` show no callers in the graph (screen components are not traced); their real
users are the five list screens and the claims page, and both got optional additions only.

**Implemented** (decision E95).

- Migration `0019`: table `link_proposals`. A row holds our name (a disease or a feature), the
  vocabulary and its version, the kind of row, the reason in words, and either a whole term (code,
  title and address together, as the WHO terms require) with the ID of the link it would make, or
  no term. Only a reviewer's transaction can read it; the application role may change status and
  reviewer. The application role may now add a row to `terminology_links`, inside a reviewer's
  transaction only.
- `feeltriva_ingestion/proposals.py`: the row, its ID, storing, the self-check and the report
  lines. Each look-up builds its own rows and stores them in the transaction that stores its
  links: `close_results` (`vocabulary.py`), `unlinked_names` (`ontology_links.py`),
  `several_identifiers` (`identifier_links.py`). `best_result` now also returns the address of the
  entity and whether it is a residual sub-code. A stored row is never changed by a later run; a
  full run removes rows of its own kinds that it no longer gives, unless a row carries a decision
  or a note.
- `feeltriva_api/review_proposals.py`: `GET /internal/v1/review/link-proposals` (filters: status,
  vocabulary, kind, disease or feature, whether a term can be confirmed, search; the rows that can
  be confirmed come first) and the review target `link_proposal`. Confirming a row makes its link,
  approved under the reviewer, through the rules of every link (`_link_guard`); a refusal leaves
  nothing behind. A link that exists by another route is approved, not made twice. Rejecting makes
  no link. A row without a term, or with a term that cannot be linked, takes notes only.
- Web: the screen "Suggested matches" (`/review/suggestions` in live mode), written in plain
  words: why a name was not matched automatically, the suggested entry, how close it is, whether
  the match has been made. The buttons read "Confirm match" and "Reject match"; a row without a
  suggestion shows "No decision needed" and offers a note only.

**Loaded on the real data** (three commands, each exited 0 with no difference reported).

| Kind of row | Vocabulary | Rows | Names | Rows naming a term |
|---|---|---:|---:|---:|
| Close search result (score 0.9 or more, no exact name) | ICD-11 MMS | 431 | 431 | 431 |
| Only a looser synonym equals our name | HPO / MONDO | 43 / 20 | 43 / 17 | 43 / 20 |
| Nearest terms by shared words | HPO / MONDO | 799 / 550 | 484 / 326 | 799 / 550 |
| An ordinary word, not the abbreviation; nearest terms | MONDO | 3 | 1 | 3 |
| Several identifiers marked equivalent | SNOMED CT / ICD-11 MMS / ICD-11 Foundation | 8 / 7 / 3 | 4 / 5 / 3 | 8 / 7 / 3 |
| The only term with our name cannot be linked (obsolete) | HPO / MONDO | 2 / 11 | 2 / 11 | 2 / 11 (shown, not confirmable) |
| No term near our name | HPO / MONDO | 596 / 749 | 596 / 749 | 0 |
| A question sentence, not looked up | HPO / MONDO | 223 / 223 | 223 / 223 | 0 |

3,668 rows in all; 1,864 name a term a reviewer can confirm; 1,804 record only why a name has no
link. All `pending`. No link was made: `terminology_links` holds 2,542 rows as before (2,531
pending, 5 approved, 6 rejected). For 16 rows the link they would make exists already by another
route; the screen says so. `link-vocabularies` made 0 calls to WHO (all answers were cached);
`import-identifiers` made 20, each for one ICD-11 entity number, to fetch WHO's own title and code
for the identifiers of the five labels with several. `link-ontologies` reads two local files.

**Two figures of the plan do not hold on today's data, reported as found.** (1) "The 19
abbreviation matches first": none is left. They were settled in M2.15 through
`specs/confirmed_readings.json`; the order of the list still puts that kind first, should one
appear. (2) "The 13 labels without a single equivalent": today 9 label-and-vocabulary pairs have
several identifiers marked equivalent (5 for ICD-11, 4 for SNOMED CT), giving 18 rows. I could not
reproduce 13 from the stored data and have not changed anything to make it fit.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 72 files |
| `uv run pytest` (SQLite, archives included) | 273 passed, 78 skipped (before: 263, 75) |
| `uv run pytest` on PostgreSQL, real archives and object store included; full output saved | 350 passed, 1 skipped (before: 337, 1) |
| `pnpm typecheck` / `pnpm lint` / `pnpm test` / `pnpm build` | clean; 131 passed (8 files); built |
| `pnpm e2e:review` against the test database (no web port; test service on 8001, stopped afterwards) | 20 passed, 0 failed |
| Migration `0019` on the main database | applied; `alembic upgrade head` |
| `detect_changes` before commit | 18 files. Changed definitions confirmed by comparing each file with the last commit: `best_result`, `link_vocabularies`, `link_ontologies`, `import_identifiers`, the three `check` functions, `main` (three print lines), `create_app` (one route); added: `close_results`, `unlinked_names`, `several_identifiers`, `LinkProposal`. The other symbols it lists (`write_review`, `summarise`, `_link`, `link_id`, the request bodies of `main.py`) stand below inserted lines and are unchanged. Risk "critical" is by the number of flows through the three commands |

New tests: `tests/api/test_review_proposals.py` (7: reviewers only; order and filters; confirming
makes the link and rejecting makes none; the link follows its row; a row without a term is not
decided; the general-term rule refuses a confirmation and leaves nothing behind, and its message
names no code; a link from another route is approved, not made twice; outside a reviewer's
transaction no row is seen and no link is added), `tests/ingestion/test_proposals.py` (3: the
service and the look-ups name the same kinds; what a row must hold; what a full run removes and
what it never removes), and additions to the three look-up tests (rows stored, none a link, a
decision survives a rerun, a decision nobody signed is reported). The browser flow of the plan,
"confirm one close vocabulary result and reject another", is step 4 of `pnpm e2e:review`.

**A guarantee changed on purpose, and two older tests with it.** Until now two tests asserted that
the application role can never add a row to `terminology_links`, not even in a reviewer's
transaction (`test_vocabulary.py`, `test_review_links.py`). Confirming a term has to make a link,
so a reviewer's transaction now can; a user's still cannot. Both tests now assert that boundary.

**Bugs and slips.**

- While the old assertion still stood, the first PostgreSQL run of `test_review_links.py` added a
  link row in a reviewer's transaction and kept it; three other tests then failed, because their
  self-checks read the whole table and found a link without an address. The row was removed from
  the test database, and the test now undoes what it writes. No product bug.
- Two expectations in my new tests were wrong (the order of two rows of one name depends on how
  the database sorts punctuation; the recorded reviewer name carries the prefix `dev-reviewer:`).
  One test used a PostgreSQL-only cast in a check that also runs on SQLite. The code was right in
  all three; the tests were corrected.
- The first version did not let a reviewer confirm the nearest terms listed for the one name
  that is a plain word and not an abbreviation. Seen in the counts of the real run; corrected.
- Seen in the screenshot of the new screen and corrected: a rejected suggestion read "Not yet"
  under "Match made", and a row that takes no decision showed "Pending review".

**Limits, stated plainly.**

- ICD-11 results below 0.9 (239 names) and names with no ICD-11 result at all (457) are not
  loaded: the plan names the close results only. The 223 question sentences were never sent to
  the ICD-11 search and have no row for ICD-11 either.
- The rows of a kind cannot be decided together; each is opened and decided on its own.
- A reviewer who is not a clinician can confirm a match. The decision is recorded with the name;
  it is not a clinical judgement, and nothing confirmed here is shown to anyone (E63).
- The titles of SNOMED CT rows are MONDO's names, because the SNOMED CT release is not held.
- The review files in `data/derived/review/` are still written, as before; nothing reads them.

### M2.4c — The urgency rules screen in words

**What it is for.** The screen of M2.4a showed a rule's level, its text and its condition as
stored (a tree of feature identifiers) and pointed to the review document for the rest. A
reviewer should read on the screen what the document says.

**Impact analysis before editing** (all LOW). `list_rules`: one caller, the rules route in
`main.py`; tests reach it over HTTP. `review_document` is not changed: the new `rules_in_words`
stands beside it and calls the same helpers (`_when`, `_quoted`, `_names`, `_ordered`).
`LiveRulesPage`: no traced caller; it is used by the route table.

**Implemented** (decision E96).

- `feeltriva_clinical/urgency_documents.py`: `rules_in_words(draft)` gives, per rule, its number
  and title, the level and what the level means, the condition line by line with the depth of
  each line and whether it heads a group, the text shown, the reason for the level, the two cases
  it was checked with, and the basis (publisher, page, address, date reviewed, quotes).
- `feeltriva_api/review_rules.py`: each rule of `GET /internal/v1/review/rules` carries `in_words`
  and `in_words_unavailable`; each rule set carries `in_words_unavailable`. Words are given only
  when the rule file on the installation is the one the rule set was stored from (same
  fingerprint) and the stored condition and text equal the file's.
- Web: `routes/review/live/LiveRulesPage.tsx`. The list shows number and title, level, the text
  shown and who decided. Opening a rule shows: level and its meaning; when the rule applies (the
  nested condition); what the person is told; why it has this level; the two examples; what it is
  based on, quoted word for word, with a link to each page; its place in the order of checking.
- `scripts/e2e-rules-in-words.mjs` (`pnpm e2e:rules`): reads the review document, opens every rule
  on the screen and compares. It records nothing and so runs against the real rule set.

**Tests run.**

| Command | Result |
|---|---|
| `uv run ruff check .` / `uv run mypy packages services pipelines` | clean; no issues in 72 files |
| `uv run pytest` (SQLite, archives included) | 275 passed, 78 skipped (before: 273, 78) |
| `uv run pytest` on PostgreSQL, real archives and object store included; full output saved | 352 passed, 1 skipped (before: 350, 1) |
| `pnpm typecheck` / `pnpm lint` / `pnpm test` / `pnpm build` | clean; 132 passed (8 files); built |
| `pnpm e2e:rules` against the real rule set `urgency-draft` (service on 8000, live review mode on 5173) | 4 passed, 0 failed: all 20 rules are shown in the document's words; the browser sent no request that changes data |
| `pnpm e2e:review` against the test database | 20 passed, 0 failed |
| `detect_changes` before commit | 12 files, risk medium. The one changed definition of the service is `list_rules`, with the four flows of its route; `_in_words`, `_rule_words` and `rules_in_words` are new. `git status` shows the same 12 files plus the two new ones (`LiveRulesPage.tsx`, `e2e-rules-in-words.mjs`); `docs/HANDOFF_README.md` and `apps/web/README.md` are listed again though unchanged (the changed lines of `README.md` matched to the other files of that name) |

New tests: `test_every_rule_in_words_says_what_the_review_document_says` (all 20 rules: the
condition line for line in the same order, the text shown, the reason, both cases, every quote and
one line per source); `test_a_rule_is_shown_in_the_same_words_as_the_review_document` (through the
route: the words of a rule are found in the document's part about that rule; a stored rule whose
text is not the file's gets no words and the reason; when the file's fingerprint differs no rule
gets words); a component test of the screen.

**Bugs and slips.**

- An existing test (`test_a_bundle_is_approved_only_when…`) failed with a server error: it replaces
  the rule file by a stand-in that has only telephone numbers, and the list now also reads rules
  from the file. The stand-in was given the fields a rule file has. No product bug: the real file
  is checked when it is loaded.
- One count in my new unit test was wrong (it counted a line of the condition as a quote).
- The first screenshot of the check was taken while the drawer was still sliding in; the check
  now waits before the picture.

**Limits, stated plainly.**

- The words exist only for a rule set stored from the rule file that is on the installation.
  The fixture rule set (`fixture-rules`) has none and says so.
- The condition is long for some rules (rule 1 names 24 items in one group). It is shown whole,
  as the document shows it.
- The browser check needs the web app in live review mode on port 5173; it is run by hand, like
  the other browser tests, and is not part of CI.
