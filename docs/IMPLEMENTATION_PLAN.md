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

## Execution order

`M0 → M1 → M2 (API) → M3 (service, REST, MCP, web) → C (conversations on Cassandra) → M3.7 (web
against the live API) → M2.4 – M2.6 → M4 → M5 → L (continuous learning) → M6 → M7`, with step G
(GitNexus) applied to every change. Steps C and L were added on 2026-11-16 on the owner's
instruction.

## Step M0 — bootable project and contracts

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M0.1 | Repository scaffold | Monorepo layout from `docs/03`; handoff docs, specs, audit crosswalks and experiments copied in unchanged; `.gitignore`, `.env.example`, `CLAUDE.md`; source ZIPs verified and moved to ignored `data/raw/` | `shasum -a 256 data/raw/*.zip` equals `specs/ingestion_manifest.json`; `git check-ignore .env data/raw` | Done |
| M0.2 | Python toolchain | Python 3.12 pinned, `uv.lock`, ruff / mypy / pytest configuration | `uv sync && uv run ruff check . && uv run pytest tests/unit` | Done |
| M0.3 | Local stack | Compose: PostgreSQL 18 + pgvector, optional MinIO and Redis profiles, least-privilege `feeltriva_app` login, separate test database, ports on 127.0.0.1 | `docker compose -f infra/docker-compose.yml up -d postgres` then `pg_isready` | Done |
| M0.4 | Database migrations | `0001` = `specs/schema.sql` statement for statement; `0002` constraints, indexes, reviewer notes; `0003` application role grants and forced row-level security | `uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head` on a disposable database | Done |
| M0.5 | Auth and configuration guards | Bearer auth: dev-only mock tokens and a JWT/JWKS verifier; settings refuse mock auth, missing encryption key or raw prompt logging outside development; clinical mode off by default | `uv run pytest tests/unit tests/api/test_guards.py` | Done |
| M0.6 | Health, errors, request IDs | `/healthz`, `/readyz`; one error envelope (`code`, `message`, `retryable`, `request_id`); validation errors never echo input; private responses `no-store` | `curl localhost:8000/readyz`; `uv run pytest tests/api` | Done |
| M0.7 | Typed frontend API client | Types generated from `specs/openapi.json` into the web app, deterministic regeneration | `pnpm --dir apps/web gen:api && git diff --exit-code apps/web/src/api/generated` | Done |
| M0.8 | CI and repository hygiene | GitHub Actions: lint, unit, PostgreSQL suite with migrations, web typecheck/test/build, contract-generation diff; Dependabot; PR and bug templates; security policy | CI run green on the pushed commit | Done — backend and web jobs (web job added with M3.6) |

## Step M1 — reproducible ingestion

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M1.1 | Archive verification and ZIP safety | SHA-256 check of all six archives against the manifest; entry validation (path traversal, size and compression-ratio limits, allowed types) before anything is read | `uv run python -m feeltriva_ingestion verify`; `uv run pytest tests/ingestion` | Done |
| M1.2 | Positional audit | Streams every CSV by column position (duplicate headings survive); reproduces row, column, label, exact-duplicate, repeated-profile and duplicate-column-conflict counts; accounts for all 12 CSVs and 85 text files | `uv run python -m feeltriva_ingestion audit` reports zero differences from `specs/ingestion_manifest.json` and `data_audit/audit.json` | Done |
| M1.3 | Reference load: sources and crosswalks | Immutable source versions; 960 lexical disease candidates and 958 feature candidates plus their mappings loaded as `pending` under one mapping release; repeated-header columns flagged | `uv run python -m feeltriva_ingestion load` then row counts in the log | Done |
| M1.4 | Archive-13 narrative adapter | `diseases_main` and causes / symptoms / treatments joined on the native `disease_id`; redundant names checked; statements stored `pending` with source record, URL and row locator | Statement counts 85 / 714 / 712 / 621; join mismatches reported as quality flags | Done |
| M1.5 | Archive-16 descriptions | 820 descriptions as `pending` statements with supplied provenance columns | Statement count 820 | Done |
| M1.6 | Idempotent rerun | Loading twice changes nothing | Second `load` reports 0 inserted; `uv run pytest tests/ingestion -m postgres` | Done |
| M1.7 | Row-level case load and profile clustering | `source_records`, `dataset_cases`, `case_labels`, `case_features` for the matrix files (about 1.4 M rows) with exact-content and profile cluster IDs and split namespaces | Counts equal the audit; archive-15 split recorded and flagged | Partial — all 1,365,363 case rows loaded with content hashes, profile clusters, duplicate status and split flags, matching the manifest; cell-level `case_features` not loaded (E23) |

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
| M3.6 | Web application | The interface in `docs/06_LOVABLE_FRONTEND_PROMPT.md`: all routes, states and the ten demo scenarios; typed mock and HTTP service adapters | `pnpm --dir apps/web typecheck && pnpm --dir apps/web test && pnpm --dir apps/web build` | Done — built and verified; review findings BUG-007 to BUG-010 open (see log) |
| M3.7 | Web against the live API | Browser run of intake → confirm → follow-up → result → correction → summary → delete with the HTTP adapter against FastAPI | Playwright end-to-end run | Done — 43/43 live browser checks; not yet part of CI |

## Step C — user conversations on Apache Cassandra

Owner's decisions (2026-11-16): **everything in a user conversation is recorded in Cassandra;
PostgreSQL is not used for conversations.** There are two sources of truth and they are never
mixed: **PostgreSQL for data** (datasets, diseases, features, aliases, statements, evidence,
rules, releases, review state) and **Cassandra for conversations** (messages, answers,
interpreted observations and corrections, assessments, summaries, replay bodies). Conversation
records point at PostgreSQL entities by ID and release version; they never copy or redefine
them. Today the conversation data is still in PostgreSQL from M3.3; this step moves it.

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| C1 | Data boundary and data model | Boundary confirmed by the owner: everything in a conversation moves; PostgreSQL keeps all reference and knowledge data. Design in `CASSANDRA_CONVERSATION_STORE.md`: one partition per `(owner_subject, session_id)`, session state as static columns, turns and records as clustering rows, lightweight-transaction version checks, replay records inside the session batch, consistency levels, what stays relational (audit events without content) | Owner confirmed the boundary on 2026-11-16; every `AssessmentService` operation is mapped in the design | Done |
| C2 | Cassandra in the local stack and CI | Cassandra service in Compose with health check, keyspace and tables created by versioned, repeatable CQL migrations; driver pinned in `uv.lock`; settings and `.env.example` entries; CI service container | `docker compose up -d cassandra`; migration applies twice without change; driver connects | Not started |
| C3 | Conversation store interface | A storage port (`ConversationStore`) used by `AssessmentService`, with an in-memory adapter for unit tests, so service logic no longer depends on SQLAlchemy session tables | Existing API, MCP and contract suites pass unchanged on the in-memory adapter | Not started |
| C4 | Cassandra adapter: transcript | Every user and assistant turn written to Cassandra, content encrypted before it leaves the service; `session_messages` no longer written in PostgreSQL | Transcript round-trips; ciphertext only at rest; nothing new appears in `session_messages` | Not started |
| C5 | Cassandra adapter: session state and records | Sessions, observations, corrections, answers, assessments and summaries in Cassandra. Observation-version check with lightweight transactions (`IF observation_version = ?`) in a single-partition conditional batch; append-only corrections | Six concurrent writers on one version → exactly one succeeds; stale version → 409; correction chain cannot fork | Not started |
| C6 | Idempotency on Cassandra | Replay records keyed by `(owner_subject, key)` with `INSERT … IF NOT EXISTS`, encrypted response, TTL; same replay and conflict semantics as today | Identical retry replays once; different payload → 409; five concurrent retries apply once | Not started |
| C7 | Ownership without row-level security | Cassandra has no RLS: the owner is part of every partition key, every query is built by the store from the verified principal, and the application role is limited to the conversation keyspace | Another caller gets 404 on every path; a query without the owner cannot address a partition; role cannot read other keyspaces | Not started |
| C8 | Deletion, expiry and retention | Session TTL and per-row TTLs, deletion of a whole partition, tombstone and compaction behaviour documented, honest deletion receipt; backup/snapshot handling stated | Deleted session unreadable on every path; expired rows disappear; receipt wording matches what was actually removed | Not started |
| C9 | Remove conversation tables from PostgreSQL | Alembic migration dropping `sessions`, `session_messages`, `session_observations`, `session_answers`, `assessments`, `idempotency_keys` and their policies once C4 – C8 pass; data migration or explicit reset of development data | `alembic upgrade head` / `downgrade` round trip; no conversation table left in PostgreSQL | Not started |
| C10 | REST/MCP parity and contract on Cassandra | Full API, MCP parity and OpenAPI contract suites running against Cassandra in CI | CI green with the Cassandra service | Not started |
| C11 | Operations | Replication strategy and factor, `LOCAL_QUORUM` reads/writes, repair, snapshot backups and restore drill, capacity estimate per session, metrics | Restore drill recorded in the engineering log | Not started |
| C12 | Reference integrity across the two stores | Cassandra has no foreign keys to PostgreSQL: the service validates every feature, question and disease ID before writing, each record stores the release versions it was written under, and a scheduled check reports any ID in Cassandra that no longer resolves in PostgreSQL | Check finds a deliberately orphaned ID; a retired entity is reported, not silently dropped | Not started |

Known trade-offs to settle in C1 (stated now so they are not a surprise): Cassandra gives
per-partition atomicity only, so the idempotency record and the session write are two steps
that must be ordered and recoverable; there is no database-enforced ownership as with
PostgreSQL row-level security; and deletes are tombstones that disappear only after
compaction. PostgreSQL foreign keys from conversation rows to features and questions are
replaced by validation in the service.

## Step M4 — model training and testing (reproducible modelling)

This is where the first models are trained and tested. Nothing here is started. Two inputs
already exist: the handoff's measured archive-11 baseline in `experiments/` (15.71 % top-1
against a 20.56 % majority comparator, so it is rejected), and the profile clusters from M1.7
that make leakage-free splits possible. After this step, retraining over time is step L.

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M4.1 | Reproduce the supplied baseline | Re-run `experiments/audit_and_baseline.py` on archive 11 (Bernoulli Naive Bayes) in this repository's environment and keep its failing result on record | `python -m unittest discover -s experiments -p 'test_*.py'` passes; test top-1 15.71 %, majority 20.56 %, top-3 39.67 %, 39 of 46 labels present — equal to `experiments/results/metrics.json` | Not started |
| M4.2 | Training-data eligibility | Per source: label origin, feature meanings (symptom vs history vs risk factor), meaning of zero, permitted use. Sources without documented rights or semantics are excluded from training | A data card per source; the training configuration refuses an ineligible source (test) | Not started |
| M4.3 | Train / validation / calibration / test splits | Split manifests built from profile clusters so identical profiles never straddle partitions; a separate calibration partition; an untouched final test partition; archive 15's original split reported separately as contaminated; manifests identified by content hash and seed | Test: zero `profile_cluster_id` shared between any two partitions; the same seed reproduces the same manifest | Not started |
| M4.4 | Model training | Majority and nearest-profile baselines, regularised logistic regression and gradient-boosted trees on identical splits; all preprocessing, feature selection and imputation fitted on the training partition only; one model per source before any pooled model; unknown stays unknown (missingness masks), never false | One command trains each model; same seed and data hash give identical metrics; a test fails if any transform sees validation or test rows | Not started |
| M4.5 | Model testing | Top-k recall, macro F1, rare-class recall, calibration (reliability diagram, expected calibration error) on the calibration partition, abstention and risk-coverage, robustness to missing features, results per source and subgroup with cluster-bootstrap confidence intervals. Model selection uses validation only; the final test partition is used once | Evaluation report generated by one command; metrics that cannot be computed are reported "unavailable", not zero; the test partition is read exactly once (logged) | Not started |
| M4.6 | Model cards, failure review and promotion decision | Model and data cards, learning curves, confusion matrix, reliability and risk-coverage plots, a reviewed sample of failures, and a recorded decision. A model is a candidate only if it beats the simpler baseline on independent data and on the safety metrics; otherwise it is rejected like the archive-11 baseline. No score is shown to users as a disease probability | Cards exist for every trained model; promotion is refused without the baseline comparison (test) | Not started |

## Step M5 — language-model and retrieval adapters, and their testing

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| M5.1 | Real extraction / explanation provider | A provider adapter behind the existing `Extractor` and explanation interfaces with deadlines, retries and rejection of malformed output; disabled unless credentials and `ALLOW_EXTERNAL_HEALTH_DATA_PROCESSING` are set | Stubbed-provider tests: timeout, malformed output and refusal each end in an explicit incomplete state; no network call is made when not configured | Not started |
| M5.2 | Retrieval over the approved corpus | Lexical + vector search in PostgreSQL (full-text and pgvector), filters for release, population and permissions, reranking, one bounded hop through reviewed disease–feature evidence | Gold-passage retrieval tests; pending, retired or expired evidence is never returned | Not started |
| M5.3 | Claim-level evidence validation | Every generated claim carries evidence IDs that are checked for existence, support and review state before rendering | A claim with a missing or unsupported citation is withheld (test) | Not started |
| M5.4 | Adversarial fixtures | Prompt injection in user text and in source text, revoked or outdated evidence, contradictions, provider outage | Each fixture passes: no instruction override, no cross-session data, abstention on outage | Not started |
| M5.5 | Testing the language and retrieval parts | Extraction precision and recall by polarity, time and experiencer on a labelled gold set; retrieval recall and nDCG; groundedness of explanations; latency and cost per turn | Evaluation harness report with prompt, model and knowledge versions recorded | Not started |

## Step L — continuous learning: the product and its models train and evolve

Owner's decisions (2026-11-16): **the product and the model learn from user conversations,
retrain and evolve.** What is learned flows one way between the two sources of truth: learning
reads conversations from Cassandra, and **anything new it discovers about the data — a new
symptom or feature term, a new alias, a new disease label — is written to PostgreSQL as a new
record**, because PostgreSQL is the source of truth for data. A **named person approves** before
a new model's suggestions reach real users in clinical mode; everything before that step
(capture, retraining, evaluation, shadow and canary trials) is automatic, and fixture/demo mode
is automatic end to end.

This step stays inside the rules of the handoff this repository treats as its specification:
training uses consented data; labels come from user corrections and verified outcomes, never
from the system's own unverified suggestions or from a user merely agreeing with one.

| ID | Sub-step | What it delivers | Verify | Status |
|---|---|---|---|---|
| L1 | Learning data contract and consent | Which signals may be learned from and under which consent; training consent stored separately from use consent and off by default; de-identification and retention rules; event schema from the Cassandra conversation log to the learning store | Records without training consent never appear in a training snapshot (test) | Not started |
| L2 | Feedback capture | Signals the product already produces — "that's right", edits and removals of interpreted observations, not-sure answers, abandoned questions — captured as labelled learning events; explicit result feedback; intake of clinician-verified outcomes (`assessment_feedback`, `clinically_verified`) | Each signal produces one event with provenance; user agreement and verified outcome are distinguishable | Not started |
| L3a | Entity discovery from conversations | From consented sessions in Cassandra: phrases the extractor could not match and mappings users corrected are aggregated into candidates — new symptom/feature term, new alias of an existing feature, new disease label. Normalised with the same lexical rule as the dataset crosswalk; a candidate is raised only above a minimum number of distinct sessions (D-L3). Only the normalised term and counts leave Cassandra: no sentence, session ID or identity | A phrase seen in fewer sessions than the threshold raises nothing; one above it raises exactly one candidate; a candidate row contains no user text beyond the term | Not started |
| L3b | Write-back to PostgreSQL as new records | Each candidate becomes a **new PostgreSQL record** (`features`, `diseases` or an alias entry) with status `pending`, in one transaction with a provenance row (`entity_discoveries`: support count, first/last seen, discovering model and extractor version, de-duplication decision). Idempotent. A term that already exists (any status) links to the existing record instead of creating a second one. An approved record is never modified by discovery | Rerun creates nothing new; an existing term gains provenance, not a duplicate; approved rows are byte-identical before and after; every discovered record has a provenance row | Not started |
| L3c | Review, release and use | Discovered records appear in the review workspace with their provenance; approval puts them in a mapping/knowledge release; only then are they served and used by the extractor, and new conversation records refer to them by PostgreSQL ID | A pending discovered entity is never served or used for extraction; after approval and release it is | Not started |
| L4 | Extraction model learning | Training and evaluation sets built from confirmed and corrected spans; scheduled retraining or prompt revision of the extractor; scored by polarity, time and experiencer against a frozen gold set | New version must beat the current one on the gold set to become a candidate | Not started |
| L5 | Ranking model learning | Scheduled retraining on leakage-controlled splits (profile clusters from M1.7) plus verified outcomes; calibration on its own partition; champion vs challenger | Reproducible from data hash, seed and config; no shared cluster across splits | Not started |
| L6 | Question-policy learning | Offline estimates of each question's information value and burden from logged dialogues; policy candidates evaluated offline and in a supervised trial. No unconstrained reinforcement learning on live users | Offline evaluation report; fewer questions for equal or better coverage | Not started |
| L7 | Automated training pipeline | Scheduler and worker (Redis queue), dataset snapshots by content hash, experiment tracking and a model registry, one command or trigger per run | A run is fully reproducible from the registry entry | Not started |
| L8 | Automated evaluation gates | Every candidate is scored on frozen test sets, safety metrics (under- and over-triage once labels exist), subgroups and regression thresholds; a failed or missing metric blocks the candidate | A deliberately worse model is rejected automatically | Not started |
| L9 | Promotion, shadow mode and rollback | Registry stages: candidate → shadow (runs beside the champion, results not shown) → canary → champion. Automatic up to canary. **Go-live of clinical suggestions requires a recorded approval by a named person** (owner decision E29); fixture/demo mode promotes automatically. Automatic rollback and kill switch; every served result records its model, rule and knowledge versions (already in the contract) | Shadow results logged but never returned; promotion without an approval record is refused in clinical mode; rollback restores the previous version in one step | Not started |
| L10 | Drift and quality monitoring | Input drift, correction rate, abstention rate, calibration drift and unmatched-phrase rate; thresholds that trigger retraining (L7) | Synthetic drift raises an alert and queues a run | Not started |
| L11 | Knowledge evolution | Scheduled refresh, retirement and re-ingestion of sources; versioned re-embedding; superseded evidence stops being served | Retired evidence disappears from results; old release can be restored | Not started |
| L12 | Learning governance | Model and data cards generated per version; audit trail of what data trained what; guard tests that the system's own outputs and unverified agreement are excluded from labels | Guard tests fail if a forbidden label source is added | Not started |

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
| G1 | Index this repository | GitNexus index of source, schemas, tests and docs; raw data, secrets, build output and dependencies excluded | `gitnexus status` shows this repo at the current commit with a non-zero symbol count | Done |
| G2 | Developer MCP access | The GitNexus MCP server answers queries for this repo; the REST → service call chain is visible | Context query on `AssessmentService` lists the REST and MCP callers | Done — REST edges resolve; MCP tool edges do not (see log) |
| G3 | Dependency check before critical changes | Written rule in `CLAUDE.md` and the PR template: impact analysis before changing shared modules, change detection before commit, tests always | Recorded impact report for one real shared change in the engineering log | Done |
| G4 | Index provenance | Indexed commit and exclusions recorded; re-index after substantive changes | Entry in the engineering log | Done |
| G5 | Privacy inspection | Generated files inspected for private data before sharing; index never published | `.gitnexus/` ignored; inspection noted in the log | Done |
