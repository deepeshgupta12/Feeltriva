# Implementation backlog and acceptance gates

Each milestone ends in runnable code, a short validation report and an updated decision register. Engineering can proceed in mock/fixture mode while clinical/data decisions remain open. The order below is intentional.

## M0 — bootable project and contracts

- Create monorepo directories from docs/03; copy/adapt CLAUDE.md, environment and ignore templates.
- Select and lock supported Python/Node/dependency versions; add format/lint/typecheck commands.
- Add Docker Compose with PostgreSQL, private object storage and optional Redis/worker; create health endpoints.
- Translate schema.sql into reviewed Alembic migrations. Add constraints, ownership/RLS policies and indexes justified by query patterns.
- Generate a typed frontend API client from OpenAPI and keep generation deterministic.
- Add mock auth and mock LLM/embedding providers for local use; never enable mock auth in production configuration.
- **Accept:** a clean checkout starts locally with documented commands; migration up/down works on a disposable DB; contract references resolve; secrets are absent; clinical mode is off.

## M1 — reproducible ingestion

- Verify all six archive SHA-256 values and register immutable source versions.
- Validate ZIP entries against traversal, maximum sizes/compression ratios and allowed content types before importing.
- Implement positional matrix adapter, symptom-list adapter and archive-13 narrative/native-FK adapter.
- Preserve unknown columns, original values, file/row locators, hashes and duplicate headings.
- Load lexical/positional crosswalks as pending; build quality flags for count mismatches, invalid joins and schema changes.
- Add exact-content and profile clustering with split namespaces; keep raw rows and all source links.
- **Accept:** all 12 CSVs and 85 text files accounted for; counts and duplicate findings reproduce; repeated runs are idempotent; archive-16 conflicts are retained; original archive-15 split is recorded and flagged.

## M2 — reviewable knowledge model

- Build internal review screens for disease aliases, feature semantics, category anomalies and conflicting values.
- Implement atomic statement extraction into pending status, with source spans and URLs.
- Add disease redirects, merge/split history, reviewer identity and immutable mapping/knowledge releases.
- Implement reviewed-only serving queries and rights/applicability filters.
- Define bounded clinical rule and question schemas; build validators and release workflow without fabricating medical contents.
- **Accept:** pending content cannot enter clinical serving; every displayed claim has a source; conflicting records remain inspectable; releases can be rolled back.

## M3 — fixture-mode vertical slice

- Implement consent/session creation, raw message storage, structured extraction interface and observation confirmation.
- Add versioned updates/corrections, idempotency replay and stale-write rejection; enforce owner checks on every path.
- Build deterministic assessment state machine; rule/question provider; candidate/retrieval interfaces; abstention/error states.
- Implement follow-up answers, provisional result rendering, previewable summary and deletion receipt.
- Build web chat and MCP adapters against the same service; add MCP submit_answer and approved question validation.
- Use clearly synthetic nonmedical test concepts to exercise escalation, contradiction, missingness and unsupported scope.
- **Accept:** end-to-end flow works with no paid provider; unauthorized cross-session access fails; stale answers return 409; errors never render completed reassurance; corrections invalidate old assessments; REST/MCP results match.

## M4 — reproducible modelling

- Reproduce the supplied archive-11 benchmark and preserve its failure result.
- Verify labels, feature semantics and permitted use before choosing eligible modelling sources.
- Create source/patient/profile-group split manifests, with separate validation, calibration and untouched test partitions.
- Compare majority/retrieval baseline, regularized linear model and boosted model; fit all transforms on training only.
- Track feature masks, source shift, rare-class support, subgroup coverage, calibration and abstention.
- Export model/data cards, confidence intervals, per-class results, calibration/risk-coverage plots and inspected failure sets.
- **Accept:** no detected grouped leakage; experiment reproducible from hashes/seed/config; unsupported metrics marked unavailable; no promotion based only on global accuracy.

## M5 — grounded retrieval and LLM adapters

- Implement provider-neutral extraction/explanation schemas with deadlines, retries and schema rejection.
- Add approved-corpus hybrid search, metadata filters, reranking and bounded graph expansion.
- Return claim-level evidence IDs and validate support, review state, relevance and citation existence.
- Add prompt injection fixtures, revoked/outdated evidence tests, contradiction cases and provider outage fallbacks.
- Measure extraction precision/recall by polarity/time/experiencer, retrieval recall/nDCG, groundedness and clinician-rated usefulness.
- **Accept:** missing evidence yields abstention; explanation cannot change approved urgency or introduce a new candidate; no raw private text in telemetry; external data processing remains explicitly configured.

## M6 — clinical and operational pilot

- Appoint clinical owner, finalize intended use and establish jurisdiction-specific clinical/regulatory review.
- Source representative adjudicated cases and urgency labels; assess coverage and disagreement between reviewers.
- Freeze release versions and evaluate clinical errors, subgroup differences and under-/over-triage.
- Validate privacy/retention/deletion, model-provider terms, access controls, restore and rollback.
- Load test the declared pilot concurrency, set latency/cost budgets and rehearse outages/incident response.
- **Accept:** documented release decision with evidence and residual risks; clinical suggestions remain off if criteria are unmet.

## M7 — expansion after evidence

Add longitudinal histories, clinician feedback, multilingual extraction or FHIR integrations individually. Each capability gets a separate data contract, consent decision, scope, eval set and rollback plan. Do not add a GNN, transformer or RL question selector simply because it is labelled advanced.

## GitNexus work items

- G1: after first runnable modules, pin the official package and index the correct new repository.
- G2: configure developer MCP access and verify an actual API-to-service call chain appears in query/context results.
- G3: test impact analysis on a shared contract change and review affected routes/tools; run the real tests.
- G4: record indexed commit and exclusions; re-index after substantive changes; preserve custom CLAUDE.md content.
- G5: inspect generated files for private-data inclusion before sharing. Do not automatically publish an index or wiki.

## Decision register

| Decision | Proposed starting point | When it must be resolved |
|---|---|---|
| Product intended use | Adult symptom assessment and care navigation | Before clinical content/pilot |
| Initial geography/language | India, English text | Before jurisdiction-specific guidance |
| Age and unsupported populations | Adults; children/pregnancy-specific diagnosis outside v1 scope | Before live scope routing |
| Responsible clinical reviewer | Not assigned in supplied material | Before clinical rules/knowledge approval |
| Dataset licence and origin | Unknown pending documentation | Before serving/training use approval |
| Brand/domain/trademark | Feeltriva working name | Before public branding |
| Hosting and model vendor | Managed private services, provider-neutral adapter | Before external health-data processing |
| Data retention/deletion | No duration invented in this package | Before collecting live health data |
| Evaluation thresholds | Set by clinical protocol and target population | Before pilot/release decision |
| Budget and load | Measure per-turn/session cost and expected concurrency | Before production sizing |
| Commercial offering | Clinic intake SaaS / consumer tracking hypothesis | During customer discovery |

Cost worksheet: monthly infrastructure + storage/backup + search/reranker + model token usage + monitoring + clinical review/support. Per-session model cost = sum over calls of input_tokens × current input unit price + output_tokens × current output unit price, plus embedding/retrieval costs. Measure observed calls/session and tail retries. No vendor prices or revenue projections have been invented.
