# Feeltriva — decision register

Engineering decisions made while implementing the handoff, and the product, clinical and
data decisions that are still open. The open items come from the handoff's own register
(`docs/05_IMPLEMENTATION_BACKLOG.md`); none of them has been decided on anyone's behalf.

## Engineering decisions made

| # | Decision | Why | Revisit when |
|---|---|---|---|
| E1 | One Python distribution (`pyproject.toml` at the root) whose packages live in the monorepo paths from `docs/03` | Keeps the documented layout without a multi-project workspace; one lockfile | A package needs its own release cycle |
| E2 | Python 3.12, dependencies resolved by `uv` and pinned in `uv.lock`; Node dependencies pinned in `apps/web/pnpm-lock.yaml` | Spec requires locked, supported versions | Routine upgrades via Dependabot |
| E3 | Synchronous SQLAlchemy with psycopg 3; FastAPI runs handlers in its thread pool | Simple transactional code; concurrency correctness comes from the database, verified by tests | Measured latency requires async |
| E4 | Migrations are hand-written SQL in Alembic, `0001` copied statement for statement from `specs/schema.sql` | The spec asks for reviewed migrations; autogeneration would hide differences from the reviewed SQL | — |
| E5 | The API connects as `feeltriva_app`, a non-owner, non-superuser role; private tables use forced row-level security keyed on a per-transaction `app.owner_subject` | Ownership holds even if a query forgets its filter; superusers bypass RLS, so the app must not be one | — |
| E6 | Service logic is also unit-tested on in-memory SQLite; the same suite runs on PostgreSQL in CI | Fast feedback without services; PostgreSQL-only guarantees (RLS, row locks, partial unique index) have their own tests | — |
| E7 | Session free text (messages, quoted phrases, idempotent replay bodies) is encrypted with Fernet before storage | Schema specifies encrypted columns; key comes from `SESSION_ENCRYPTION_KEY`, with a built-in non-secret key allowed only in development/test | Managed KMS / key rotation before any live data |
| E8 | Mock bearer tokens (`dev:<subject>`, `dev-reviewer:<name>`) exist only when `AUTH_MODE=mock`, which settings refuse outside development/test | Local use without an identity provider; cannot be enabled in production configuration | Real identity provider chosen |
| E9 | Fixture mode serves one synthetic, nonmedical release (`fx.*` concepts, "Illustrative possibility A") shipped in `packages/clinical` | Exercises escalation, scope, contradiction, missingness and missing evidence without inventing medical rules | A reviewed clinical release exists |
| E10 | Clinical mode refuses to start with the mock extractor, a synthetic bundle or any unapproved item | "Unapproved rules cannot run in clinical mode" enforced at load time, not by convention | — |
| E11 | Urgency and scope rules run on every observation change and use unconfirmed details too; candidates use confirmed details only | FR04: escalation must never wait for confirmation or a questionnaire; explanations must not rest on unconfirmed interpretations | Clinical owner reviews this policy |
| E12 | Fixture results report urgency `not_assessed` unless an escalation rule fires | There is no approved urgency content; `not_assessed` is not "low" | Approved urgency rules exist |
| E13 | A candidate is returned only if every evidence ID it cites resolves; otherwise it is withheld and reported as an unknown | "No evidence, no claim" | — |
| E14 | An answer is accepted only for the question the server would ask now; otherwise 409 | Prevents attaching an old answer to a new question | — |
| E15 | A structured observation for a concept that already has a current observation must supersede it; an observation can be superseded once (database unique index) | Corrections form an auditable chain, never a fork | — |
| E16 | Provider failure during assessment returns 503 and is not stored against the idempotency key | A failure must not become the permanent replay for that key, and must never look like a result | — |
| E17 | Deletion removes messages, observations, answers, assessments and earlier replay bodies in one transaction, keeps a tombstone, and returns `deletion_scheduled`, not `deleted` | No backup, trace or object-store purge exists yet, so completion is not claimed | Retention policy and purge job exist |
| E18 | Missing, deleted and not-owned sessions all return the same 404 | Existence of another caller's session is not disclosed | — |
| E19 | Session lifetime is `SESSION_TTL_MINUTES` (default 1440); expired sessions return 403 `session_expired` and can still be deleted | A technical session timeout, not a data-retention policy | Retention decision |
| E20 | `GET /v1/conditions/{disease_id}` and `/internal/v1/review/*` are additions beyond `specs/openapi.json` | Needed for M2 (review workspace, reviewed-only serving); the supplied contract file is left unchanged | Contract owner extends the OpenAPI |
| E21 | Rate limiting (HTTP 429) is not implemented | Needs the declared pilot load and an infrastructure choice | Before any shared deployment |
| E22 | Web app is Vite + React + TypeScript + Tailwind in `apps/web`, built here from `docs/06_LOVABLE_FRONTEND_PROMPT.md` rather than generated by Lovable | No Lovable output was supplied; the prompt allows any supported React + TypeScript template | Lovable-generated code is supplied |
| E23 | Matrix rows (about 1.4 M rows × up to 654 columns) are audited by streaming but not yet loaded row by row into `case_features` | That table would hold hundreds of millions of rows; storage layout (PostgreSQL vs Parquet) should be chosen deliberately | M1.7 |
| E24 | GitHub repository is public (owner's instruction, 2026-11-16; it was created private first) | Owner decision. Raw archives, `.env`, model artifacts and session data are ignored and were never pushed. The tracked `data_audit/` crosswalks and `experiments/results/` are derived from datasets whose origin and licence are still unknown | Data rights are documented; a software licence is chosen |
| E25 | User conversations are stored in Apache Cassandra, not PostgreSQL (owner's instruction, 2026-11-16) | Owner decision. Planned as step C; until C is implemented the M3.3 PostgreSQL tables are still in use | C1 fixes the exact boundary |
| E26 | The product and its models learn, retrain and evolve continuously (owner's instruction, 2026-11-16) | Owner decision. Planned as step L: automated feedback capture, retraining, evaluation gates, shadow/canary promotion, drift-triggered runs | D-L1 below |

## Open decisions (owner needed)

| Decision | Proposed starting point in the handoff | Needed before |
|---|---|---|
| Product intended use | Adult symptom assessment and care navigation | Clinical content / pilot |
| Initial geography and language | India, English text | Jurisdiction-specific guidance |
| Age and unsupported populations | Adults; children and pregnancy-specific diagnosis out of scope | Live scope routing |
| Responsible clinical reviewer | Not assigned | Any clinical rule or knowledge approval |
| Dataset licence and origin | Unknown | Serving or training use; making the repository public |
| Brand, domain, trademark | "Feeltriva" working name, not cleared | Public branding |
| Hosting and model vendor | Managed private services, provider-neutral adapter | External health-data processing |
| Data retention and deletion | No duration set | Collecting live health data |
| Evaluation thresholds | Set by clinical protocol | Pilot / release decision |
| Budget and load | Measure per-session cost and concurrency | Production sizing, rate limits |
| Commercial offering | Clinic intake SaaS / consumer tracking hypothesis | Customer discovery |
| D-C1 Conversation boundary in Cassandra | Proposed: all conversation content (messages, answers, observations, assessments, summaries, replay bodies) moves; PostgreSQL keeps reference, review and imported-case data | Starting C3 |
| D-L1 How automatic is promotion to live users | Proposed: fully automatic up to shadow/canary; serving clinical suggestions to users still needs the recorded approval the handoff requires (clinical owner). Fully unattended promotion would override the handoff's release gates | L9 |
| D-L2 Training consent | Handoff: separate from use consent and off by default; nothing is learned from a session without it | L1 |
| Software licence for this repository | None chosen (all rights reserved by default) | Sharing the code |
