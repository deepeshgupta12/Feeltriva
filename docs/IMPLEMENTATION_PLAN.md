# Feeltriva — implementation steps and sub-steps

This is the working plan for building Feeltriva from the handoff in this repository
(`docs/01_PRODUCT_AND_BUILD_SPEC.md`, `docs/05_IMPLEMENTATION_BACKLOG.md`). Each step is a
backlog milestone; each sub-step is one reviewable unit that lands as its own commit and push.

How to use it:

- **Status** is one of `Done`, `Partial` (what is missing is stated) or `Not started`.
- **Verify** is the exact command or check that proves the sub-step. Results of actually
  running them, and every bug found with its resolution, are in
  [`ENGINEERING_LOG.md`](ENGINEERING_LOG.md) under the same ID.
- Decisions made along the way, and decisions still open, are in [`DECISIONS.md`](DECISIONS.md).
- Before changing shared code, run the GitNexus dependency check described in `CLAUDE.md`.

Nothing here is a clinical claim. Clinical mode is off; all served content is a synthetic,
nonmedical fixture until a clinical owner approves a real release.

## Step M0 — bootable project and contracts

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M0.1 | Repository scaffold | Monorepo layout from `docs/03`; handoff docs, specs, audit crosswalks and experiments copied in unchanged; `.gitignore`, `.env.example`, `CLAUDE.md`; source ZIPs verified and moved to ignored `data/raw/` | `shasum -a 256 data/raw/*.zip` equals `specs/ingestion_manifest.json`; `git check-ignore .env data/raw` | Done |
| M0.2 | Python toolchain | Python 3.12 pinned, `uv.lock`, ruff / mypy / pytest configuration | `uv sync && uv run ruff check . && uv run pytest tests/unit` | Done |
| M0.3 | Local stack | Compose: PostgreSQL 18 + pgvector, optional MinIO and Redis profiles, least-privilege `feeltriva_app` login, separate test database, ports on 127.0.0.1 | `docker compose -f infra/docker-compose.yml up -d postgres` then `pg_isready` | Done |
| M0.4 | Database migrations | `0001` = `specs/schema.sql` statement for statement; `0002` constraints, indexes, reviewer notes; `0003` application role grants and forced row-level security | `uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head` on a disposable database | Done |
| M0.5 | Auth and configuration guards | Bearer auth: dev-only mock tokens and a JWT/JWKS verifier; settings refuse mock auth, missing encryption key or raw prompt logging outside development; clinical mode off by default | `uv run pytest tests/unit tests/api/test_guards.py` | Done |
| M0.6 | Health, errors, request IDs | `/healthz`, `/readyz`; one error envelope (`code`, `message`, `retryable`, `request_id`); validation errors never echo input; private responses `no-store` | `curl localhost:8000/readyz`; `uv run pytest tests/api` | Done |
| M0.7 | Typed frontend API client | Types generated from `specs/openapi.json` into the web app, deterministic regeneration | `pnpm --dir apps/web gen:api && git diff --exit-code apps/web/src/api/generated` | Not started |
| M0.8 | CI and repository hygiene | GitHub Actions: lint, unit, PostgreSQL suite with migrations, web typecheck/test/build, contract-generation diff; Dependabot; PR and bug templates; security policy | CI run green on the pushed commit | Not started |

## Step M1 — reproducible ingestion

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M1.1 | Archive verification and ZIP safety | SHA-256 check of all six archives against the manifest; entry validation (path traversal, size and compression-ratio limits, allowed types) before anything is read | `uv run python -m feeltriva_ingestion verify`; `uv run pytest tests/ingestion` | Done |
| M1.2 | Positional audit | Streams every CSV by column position (duplicate headings survive); reproduces row, column, label, exact-duplicate, repeated-profile and duplicate-column-conflict counts; accounts for all 12 CSVs and 85 text files | `uv run python -m feeltriva_ingestion audit` reports zero differences from `specs/ingestion_manifest.json` and `data_audit/audit.json` | Done |
| M1.3 | Reference load: sources and crosswalks | Immutable source versions; 960 lexical disease candidates and 958 feature candidates plus their mappings loaded as `pending` under one mapping release; repeated-header columns flagged | `uv run python -m feeltriva_ingestion load` then row counts in the log | Done |
| M1.4 | Archive-13 narrative adapter | `diseases_main` and causes / symptoms / treatments joined on the native `disease_id`; redundant names checked; statements stored `pending` with source record, URL and row locator | Statement counts 85 / 714 / 712 / 621; join mismatches reported as quality flags | Done |
| M1.5 | Archive-16 descriptions | 820 descriptions as `pending` statements with supplied provenance columns | Statement count 820 | Done |
| M1.6 | Idempotent rerun | Loading twice changes nothing | Second `load` reports 0 inserted; `uv run pytest tests/ingestion -m postgres` | Done |
| M1.7 | Row-level case load and profile clustering | `source_records`, `dataset_cases`, `case_labels`, `case_features` for the matrix files (about 1.4 M rows) with exact-content and profile cluster IDs and split namespaces | Counts equal the audit; archive-15 split recorded and flagged | Not started |

## Step M2 — reviewable knowledge model

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M2.1 | Review API | Reviewer-role endpoints: overview, disease mappings, feature mappings (with repeated-header conflicts), statements; decisions with attributed notes and audit events | `uv run pytest tests/api/test_review.py` | Done |
| M2.2 | Reviewed-only serving | Condition information returns approved diseases and approved, unexpired, sourced statements only; pending content is unreachable | `uv run pytest tests/api/test_review.py -k serving` | Done |
| M2.3 | Bounded rule and question schemas | Declarative rule AST with three-valued logic, depth and node limits, reference validation; answer-schema validator; bundle loader that refuses unapproved or synthetic content in clinical mode | `uv run pytest tests/unit` | Done |
| M2.4 | Review console wired to the API | The web reviewer screens read and write through the review API instead of mock state | Playwright flow: inspect duplicate column, save note | Not started |
| M2.5 | Redirects, merge/split history, immutable releases, rollback | Disease redirects with history; publish and roll back mapping and knowledge releases; serving pinned to a release | Release cannot be edited after publish; rollback test | Not started |
| M2.6 | Atomic statement extraction queue | Narrative statements split into atomic claims with text spans, all `pending` | Every claim has a span and source | Not started |

## Step M3 — fixture-mode vertical slice

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M3.1 | Rule engine, answers and release bundle | `packages/clinical`: rule evaluation, urgency/scope screening, one-at-a-time question selection, answer validation, synthetic nonmedical fixture release | `uv run pytest tests/unit` | Done |
| M3.2 | Provider boundaries | `packages/llm` extraction interface with a deterministic mock (negation, uncertainty, exact spans, never invents absence); `packages/inference` candidates; `packages/retrieval` evidence | `uv run pytest tests/unit` | Done |
| M3.3 | Assessment application service | Sessions, encrypted messages, versioned observations and corrections, idempotent mutations, optimistic concurrency, ownership on every path, state machine, abstention, summary, deletion receipt, redacted audit | `uv run pytest tests/api` (SQLite) and with `TEST_DATABASE_URL` (PostgreSQL) | Done |
| M3.4 | REST transport and contract tests | All eight operations in `specs/openapi.json`; responses validated against the contract schemas | `uv run pytest tests/api/test_contract.py` | Done |
| M3.5 | Product MCP adapter | MCP tools calling the same service as REST, including `submit_answer` and approved-question validation; REST/MCP parity | `uv run pytest tests/mcp` | Partial — stdio transport only; remote OAuth transport not implemented |
| M3.6 | Web application | The interface in `docs/06_LOVABLE_FRONTEND_PROMPT.md`: all routes, states and the ten demo scenarios; typed mock and HTTP service adapters | `pnpm --dir apps/web typecheck && pnpm --dir apps/web test && pnpm --dir apps/web build` | Not started |
| M3.7 | Web against the live API | Browser run of intake → confirm → follow-up → result → correction → summary → delete with the HTTP adapter against FastAPI | Playwright end-to-end run | Not started |

## Step M4 — reproducible modelling

| ID | Sub-step | Status |
|---|---|---|
| M4.1 | Reproduce the supplied archive-11 baseline and keep its failing result (15.71 % top-1 vs 20.56 % majority) | Not started |
| M4.2 | Verify labels, feature semantics and permitted use before choosing modelling sources | Not started |
| M4.3 | Source / patient / profile-group split manifests with separate validation, calibration and untouched test partitions | Not started |
| M4.4 | Majority/retrieval baseline vs regularised linear vs boosted model, transforms fitted on training only | Not started |
| M4.5 | Calibration, abstention, feature masks, source shift, rare-class and subgroup reporting | Not started |
| M4.6 | Model and data cards, confidence intervals, plots, inspected failure sets | Not started |

## Step M5 — grounded retrieval and LLM adapters

| ID | Sub-step | Status |
|---|---|---|
| M5.1 | Real provider adapter behind the extraction/explanation interfaces with deadlines, retries and schema rejection | Not started |
| M5.2 | Approved-corpus hybrid search, metadata filters, reranking, bounded graph expansion | Not started |
| M5.3 | Claim-level evidence IDs with support, review-state and citation-existence validation | Not started |
| M5.4 | Prompt-injection, revoked-evidence, contradiction and provider-outage fixtures | Not started |
| M5.5 | Extraction, retrieval and groundedness measurement | Not started |

## Step M6 — clinical and operational pilot

| ID | Sub-step | Status |
|---|---|---|
| M6.1 | Clinical owner, intended use, jurisdiction-specific regulatory review | Not started |
| M6.2 | Adjudicated cases and urgency labels; reviewer agreement | Not started |
| M6.3 | Frozen-release evaluation: clinical errors, subgroups, under- and over-triage | Not started |
| M6.4 | Privacy, retention, deletion (including backups), provider terms, access control, restore and rollback drills | Not started |
| M6.5 | Load test, latency and cost budgets, outage and incident rehearsal | Not started |

## Step M7 — expansion after evidence

Longitudinal history, clinician feedback, multilingual extraction, FHIR: each one separately,
with its own data contract, consent decision, scope, evaluation set and rollback plan.
Not started.

## Step G — GitNexus code intelligence (developer tool, separate from the product)

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| G1 | Index this repository | GitNexus index of source, schemas, tests and docs; raw data, secrets, build output and dependencies excluded | `gitnexus status` shows this repo at the current commit with a non-zero symbol count | Not started |
| G2 | Developer MCP access | The GitNexus MCP server answers queries for this repo; the REST → service call chain is visible | Context query on `AssessmentService` lists the REST and MCP callers | Not started |
| G3 | Dependency check before critical changes | Written rule in `CLAUDE.md` and the PR template: impact analysis before changing shared modules, change detection before commit, tests always | Recorded impact report for one real shared change in the engineering log | Not started |
| G4 | Index provenance | Indexed commit and exclusions recorded; re-index after substantive changes | Entry in the engineering log | Not started |
| G5 | Privacy inspection | Generated files inspected for private data before sharing; index never published | `.gitnexus/` ignored; inspection noted in the log | Not started |
