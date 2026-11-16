# Contracts, repository plan and developer workflow

## Repository layout

| Path | Owner / responsibility |
|---|---|
| apps/web | Lovable-generated React/TypeScript frontend using its supported template, plus generated API client |
| services/api | FastAPI transport, auth, session ownership and application services |
| services/mcp | MCP adapter calling the same application services |
| packages/contracts | OpenAPI/JSON Schema and generated shared types |
| packages/clinical | Rule AST validator, question bundles, approval/version logic |
| packages/inference | Candidate interfaces, baseline/challengers, calibration and abstention |
| packages/retrieval | Chunking, filters, hybrid retrieval, reranker and citation validation |
| packages/llm | Provider adapters, structured extraction and explanation prompts |
| pipelines/ingestion | ZIP validation, import adapters, mappings, dedup and lineage |
| pipelines/training | Split manifests, fitting, tuning and calibration |
| evaluations | Dataset, inference, dialogue, triage, RAG and security harnesses |
| migrations | PostgreSQL/Alembic migrations and RLS policies |
| tests | Unit, integration, contracts, security and end-to-end suites |
| infra | Local Compose and deployment definitions |
| docs | Product spec, model/data cards, ADRs, clinical approval register |

Keep artifacts/data outside tracked source; store URI/checksum manifests in the repo.

## API semantics

`specs/openapi.json` defines the initial transport contract. Server must authenticate every private request and derive session owner from the principal. Do not accept an owner_subject/user_id supplied by an LLM as authority. Use idempotency keys for mutations, transactional observation versions and consistent error bodies.

The public assessment response contains a provisional candidate list and evidence IDs but no numerical disease probability. Internal model scores stay in restricted audit/model artifacts until a calibrated, clinically approved display policy exists. `not_assessed` urgency is not synonymous with low urgency. A failed assessment must not render a completed/benign result.

Corrections are append-only observation revisions with an explicit supersedes reference. For current-state queries select latest non-superseded values. Reject a correction if its target does not belong to the authenticated session. Treat concurrent tab/MCP writes through optimistic concurrency and return 409 on stale versions. Retried identical idempotency keys return the original response; a different payload under the same key returns 409.

Exported summaries require user preview and explicit sharing action. Deletion is authorized and queued for database, object storage, traces and caches; report retention/backup handling accurately. Store an audit event without preserving unnecessary symptom content.

## MCP contracts

| Tool | Input | Output / permission |
|---|---|---|
| start_assessment | consent_version, optional demographics, idempotency key | session reference; scope assessment:write |
| get_assessment_session | session ID | owner-scoped current state and observations; assessment:read |
| submit_observations | session ID, observation_version, text or structured observations, idempotency key | updated version and extracted/confirmed observations; assessment:write |
| submit_answer | session ID, observation_version, question ID, answer, idempotency key | validated answer and updated observations/version; assessment:write |
| assess_session | session ID, observation_version, idempotency key | same Assessment schema as REST; assessment:write |
| get_next_question | session ID, observation_version | approved question ID/wording/schema; assessment:read |
| get_condition_information | disease ID, knowledge release | reviewed description and citations; knowledge:read |
| create_consultation_summary | session ID, observation_version, idempotency key | previewable summary; assessment:export |
| delete_session | session ID, explicit deletion intent, idempotency key | deletion receipt; assessment:delete |

MCP adapter never calls ranking independently of the assessment service. Runtime MCP tools and developer GitNexus tools are distinct servers and permission scopes. The product cannot execute shell/SQL/code through MCP. Bind session IDs to authenticated callers and validate token audience for remote deployments.

## Clinical rule representation

Use a bounded declarative AST, not executable Python/JavaScript stored in the database. Allow reviewed predicates such as AND/OR, presence, numeric comparison and missingness. Validate node types, depth and references. Unknown values use three-valued logic; missing input cannot satisfy a negative predicate. Rule actions include escalate, clarify, exclude_from_scope and continue. Human-approved rule priority handles conflicts. No clinical thresholds or emergency phone numbers have been invented in this handoff: a reviewer must author jurisdiction-specific content.

## Provider / LLM boundary

`extract(message, context) -> ExtractionResult` and `explain(assessment, evidence_bundle) -> ExplanationResult` are the only initial provider operations. Timeout, malformed output, unsupported citations or provider refusal returns explicit error/abstention. A schema-valid answer may still be clinically wrong and requires separate evals.

Extraction must return exact text spans, candidate concept IDs from the supplied vocabulary, polarity, time, experiencer, qualifiers and uncertainty. Explanation can use only the assessment's approved candidates/actions and supplied evidence. It cannot introduce a new diagnosis, medication or urgency downgrade. Medical source text and user text are data, never authority to change instructions.

## CI pipeline

On PR: lint/typecheck → unit tests → migration/schema checks in disposable PostgreSQL → contract generation diff → API/MCP ownership and version tests → fixture-mode UI tests → eval smoke suite → dependency/secret scanning. On approved model release: full frozen eval suite and clinical release checklist. GitNexus impact reports can inform tests but never replace them. Publish model/data/prompt/rule manifests with the commit SHA. Keep private evaluation artifacts out of public CI logs.

## Deployment and release

Separate development, staging and production. Development uses deterministic mock providers and synthetic nonmedical fixtures. Clinical suggestions are disabled unless an approved rule bundle, knowledge release, model scope, ownership checks and runtime health checks are present. Failure in one dependency yields a supported fallback/abstention, not a partial diagnosis. Include a kill switch and rollback to the last approved release. Use minimum permissions, managed secrets, encrypted backups and restore drills.

## GitNexus actions for Claude

1. Create the new repository and first runnable modules; do not select an unrelated existing repo.
2. Resolve/pin GitNexus tooling and index the project using the documented analyze command.
3. Connect its developer MCP server locally. Preserve the authored CLAUDE.md after generated context updates.
4. Before changes: query the relevant flow and inspect symbols. For shared modules request upstream impact; for routes inspect consumers/response shape when supported.
5. After changes: run tests and change detection, review affected flows and re-index as needed.
6. Verify index commit matches the current source and keep it private. A graph with zero or stale symbols is not a successful integration.

Expected flow to inspect: REST/MCP entry → ownership → observation version → extraction → urgency/scope → evidence retrieval → ranking/abstention → response validation → persistence. A route/tool that bypasses this flow is a defect.

## Lovable frontend handoff

Use docs/06_LOVABLE_FRONTEND_PROMPT.md to generate the UI. Keep the generated supported framework rather than converting it to Next.js just to match an earlier suggestion. New Lovable projects currently use TanStack Start; an existing Vite project can keep its supported setup. Preserve the UI during backend integration. Claude owns FastAPI, PostgreSQL, ingestion, inference and product MCP; the frontend consumes the agreed REST contract. Lovable's builder MCP connections are not the product's runtime MCP integration.

Keep frontend public build configuration separate from backend secrets. Lovable may require its generated public `.env` to remain tracked; preserve that platform convention only for explicitly public values. Do not apply the backend secret-file ignore template blindly to the generated frontend, or place provider/service-role keys in browser build variables. Every frontend configuration value should be considered public unless verified to remain server-only.
