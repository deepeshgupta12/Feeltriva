# Feeltriva — engineering log

One entry per sub-step in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md): what was
implemented, the tests that were actually run with their real results, and every bug found
with its cause and resolution. Newest entries are at the bottom. Figures are copied from
command output, not estimated.

## Bug index

| Bug | Sub-step | Summary | Status |
|---|---|---|---|| BUG-001 | M3.3 | Every authenticated endpoint returned 422 `query.who: Field required` | Fixed |
| BUG-002 | M0.4 | `uv run alembic upgrade head` failed on a checkout that only had `.env` | Fixed |

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
- Full suite after this change: see the count in the next entry's table.

**Bugs.** None in the adapter. Note: the SDK's own argument-validation errors echo the
offending value, so tools take loosely typed arguments and validate them with the API's
schemas, which report locations only.

**Not done.** Remote (streamable HTTP) transport with OAuth, token-audience validation and
per-tool scope metadata. Only stdio with an environment-supplied token exists.
