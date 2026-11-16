# Feeltriva — product and engineering specification

Version 1.0 • 16 November 2026 • Implementation handoff for Claude

## 1. Name and product definition

**Feeltriva** (feel-TREE-vah). Working tagline: **Understand your symptoms. Know your next step.** This is a coined working name: exact-name searches in two search engines did not return an exact match during this task. This is not trademark, domain, app-store or company-name clearance. Complete those checks before adopting the brand publicly.

Feeltriva is a conversational symptom-assessment and care-navigation product. A person describes what they feel; the system extracts and confirms observations, asks relevant follow-up questions, checks urgency and provides provisional possible explanations with an appropriate next step. The application maintains an auditable assessment record. It does not establish a diagnosis, prescribe medication or promise a cure.

The problem: users describe symptoms informally, lack context on urgency, struggle to identify useful details, and receive fragmented or overconfident information from searches. Clinicians receive incomplete histories. The solution is structured questioning plus traceable evidence and explicit uncertainty, not a disease-name generator.

### Users and business model

- Primary hypothesis: adults in India seeking help understanding non-emergency symptoms; English text at first. Geography, language and age are proposed v1 scope decisions, not properties proven by the datasets.
- Secondary: clinicians reviewing a user-approved consultation summary. Caregiver/minor assessment is outside initial validated scope.
- Suggested rollout: internal evaluation → clinician-supervised pilot → controlled consumer release only after evidence and regulatory review.
- Business hypothesis: clinic intake SaaS and consumer longitudinal symptom tracking. Do not monetize emergency guidance or let commercial referrals alter candidate ranking or urgency.
- Differentiate through evidence-backed questions, continuity, correction handling, source traceability and a useful clinician handoff.

### Outcomes and measures

Measure: clinically appropriate next-step rate on adjudicated cases, under-triage and over-triage rates, useful-summary rate, completion without repetitive questions, correction rate, accessibility, latency and cost/session. Disease top-k recall is a secondary offline measure. Session duration or conversion alone must not override safety. No current clinically validated performance claim exists.

## 2. Functional specification

| ID | Capability | Required behaviour / acceptance criterion |
|---|---|---|
| FR01 | Consent and scope | Explain intended use and data handling; allow an assessment without a named account; identify unsupported age/scope without claiming the complaint is harmless. |
| FR02 | Free-text intake | Capture raw wording, normalize candidate features and preserve negation, time, uncertainty and who is experiencing the symptom. |
| FR03 | Confirmation | Allow users to edit the interpreted symptom list. Every extraction references the message span; speculative features remain unconfirmed. |
| FR04 | Urgency screening | Run approved rules on every new/corrected message, before general candidate ranking. Never require questionnaire completion before escalation. |
| FR05 | Relevant context | Ask age; request clinically relevant sex-related factors only when applicable. Preserve self-described gender separately. Include unknown/prefer-not-to-answer. |
| FR06 | Adaptive questions | Select approved questions by safety priority, missing essentials, information value and burden. Ask one concise question at a time; avoid repeats. |
| FR07 | Candidate assessment | Return supported possible explanations, supporting/conflicting observations, unknowns, scope status and evidence IDs. Abstain when insufficient. |
| FR08 | Results | Show urgency/next step first, then up to three provisional explanations when appropriate. Do not show uncalibrated probability percentages. |
| FR09 | Revisions | Changes invalidate stale assessments; recompute from current confirmed observations and retain an audit of the change. |
| FR10 | Summary | Create a user-previewed summary with symptoms, relevant negatives, onset/duration, context, answers, missing facts and care guidance. Sharing requires explicit user action. |
| FR11 | History and deletion | Optional saved history; delete sessions, derived summaries and related retrieval traces according to the retention policy. No automatic training consent. |
| FR12 | Review console | Clinician/data reviewer can approve mappings, evidence, questions and rules; publish immutable versions; rollback faulty releases. |
| FR13 | Error recovery | Timeout/error must produce an explicit incomplete-assessment state. It cannot produce reassurance or a fabricated result. |
| FR14 | MCP surface | Authorized clients can submit observations and request assessments through the same service used by the web app; no bypass of scope, safety or access controls. |

### Conversation states

`consent_pending → intake → clarifying → assessing → result_ready` with branches to `urgent_handoff`, `out_of_scope`, `insufficient_information`, `system_unavailable`, `closed`. An observation correction moves a completed result back to `assessing`. Record `observation_version` on every question and assessment. Reject stale answers or assessments with HTTP 409 and require a refresh.

Symptoms require presence (`present`, `absent`, `uncertain`, `not_asked`), onset, duration, location, severity, pattern, triggers and relieving factors where applicable. A blank matrix value, an imported zero and an explicit denial are different concepts. Never infer absence from silence.

### UX screens

1. Welcome, intended use, consent and privacy options.
2. Chat with editable interpreted observations, accessible answer choices and contextual progress (no fabricated percentage completion).
3. Immediate escalation panel when an approved rule requires it.
4. Result: next step, possible explanations, uncertainty, evidence and summary export.
5. Optional history with correction/delete controls.
6. Internal review console with mapping conflicts, source permissions, question/rule approvals and release history.

Proposed engineering targets: WCAG 2.2 AA; keyboard/screen-reader support; visible loading/error states; API writes idempotent; local structured rule evaluation p95 under 300 ms and complete conversational turns p95 under 8 s at the declared pilot load. These are targets to test, not measured SLAs.

### Excluded from v1

Autonomous diagnosis, medication dosing/prescribing, emergency monitoring, interpretation of scans/lab images, children, pregnancy-specific diagnostic flows, clinician identity impersonation and autonomous appointment booking. An out-of-scope user still receives approved escalation/navigation text; exclusion does not mean safety checks are disabled.

## 3. What the supplied datasets actually provide

Use `data_audit/audit.json` as the machine-readable measured inventory. There are 12 CSV files and 85 disease text files across the six ZIPs. There are **960 disease-label groups after case/whitespace normalization**, not 960 clinically distinct diagnoses. Clinical synonym reconciliation remains unapproved.

| Archive | Files / measured coverage | Intended mapping |
|---|---|---|
| 11 | 100,000 rows; 46 labels; 174 binary feature columns | Source records, disease mappings, positional feature mappings, dataset cases, case features |
| 12 | data.csv: 246,945 rows / 713 labels / 377 features; text file: 192,715 rows / 254 labels | Separate source representations; disease and feature mappings; no presumed one-to-one row alignment |
| 13 | 85 main disease rows + 85 texts; 712 symptom statements / 82 diseases; 714 causes / 85; 621 treatments / 84 | Disease metadata and provenance-linked narrative statements; native FK `disease_id → diseases_main.id` |
| 14 | 25,000 rows / 30 labels; age, Gender, symptom list, Patient_ID | Dataset cases and case features; Gender vocabulary Male/Female/Other retained |
| 15 | 475,502 train + 134,529 test rows / 49 labels / 223 E_* columns | Cases with source split and AGE/SEX; feature dictionary distinguishes symptoms, history and risk factors |
| 16 | 190,672 matrix rows / 820 labels / 654 positional columns; 820 descriptions with provenance columns | Cases/features plus descriptions; 37 repeated header names require conflict handling |

Important observed limitations: archive 13 includes questionable category labels (Asthma labelled Mental Health); extracted sentences are not a clinically validated fact set. Archive 12 and 16 share 674 normalized disease labels, which is overlap in labels, not proof of duplicate patients. Archives 14/15 do not establish population prevalence. Original dataset origin, collection process, licences and real/synthetic status have not been established by the supplied files.

### Final combination policy

The final design is a full union with provenance, not a concatenated training CSV. Preserve every source record in the raw layer. Normalize lexical labels to provisional IDs; retain original spellings and local IDs. Reviewer-approved semantic merges can later redirect provisional IDs without deleting source history. Preserve unmatched records. Do not force ICD/MONDO/HPO IDs when no verified mapping exists.

The deliverable contains an actual lexical disease crosswalk and positional feature-column crosswalk. It does not claim completed clinical semantic deduplication. Exact row duplicates are measured per file. Repeated patient profiles are flagged, not assumed to be duplicate people. Final unique-patient count is unknown.

### Deduplication rules, in order

1. Fingerprint original ZIPs and files; namespace source versions and split names.
2. Parse columns by position, not dict keys, so duplicate headings survive.
3. Keep raw rows immutable. Build exact-content hashes and retain all member references.
4. Use casefold/trim/collapse-whitespace only for initial disease labels. Preserve subtype, acuity and severity distinctions. Suggested synonyms go to review.
5. For features, strip known prefixes and normalize separators only as candidate mapping. E_* questions must be classified by clinical meaning. Do not treat a history question as an active symptom.
6. For repeated feature columns: merge only after semantics are verified and values agree; preserve an explicit conflict otherwise. Do not silently OR contradictory values.
7. For narrative statements: deduplicate normalized text within disease/type/source while keeping every attribution. Extract atomic claims only into a review queue.
8. Create feature-profile clusters before splitting ML data. Cross-source near duplicates require comparable feature semantics, not matching names alone.
9. Preserve conflicting disease labels on equivalent profiles as ambiguity; do not vote a diagnosis into truth.
10. Produce immutable mapping version, split manifest, source hashes and audit report. Publish only approved mappings/evidence to clinical serving.

### Demographics

Archive 14 totals: Male 8,271; Female 8,336; Other 8,393. Archive 15 totals: M 296,145; F 313,886. These are row counts, not prevalence and not verified unique people. Do not combine these as population priors. Preserve original field meaning and raw value. Separate patient identity, source case ID, sex-related clinical context and gender identity.

## 4. Logical data model

The PostgreSQL schema is specified in `specs/schema.sql`; it is a proposed initial migration, not an already deployed database. Clinical content review status defaults to pending. RLS / API ownership checks and encryption are implementation obligations, not established by having tables.

The central entities are disease, feature and evidence statement. Many diseases relate to many features through individually sourced assertions. Disease → care statement is one-to-many for narrative treatment/cause/management statements. Imported case → feature is many-to-many. Current user sessions have separate observations and assessments; they are not training cases by default.

Use four storage zones: raw immutable objects; normalized relational source data; reviewed serving knowledge; private live session data. Graph traversal can initially use relational joins. The medical evidence graph and GitNexus's code graph must never be confused or mixed.

Do not store an unqualified `cure` column. Use `statement_type = treatment | management | prevention | cause | description | symptom` plus evidence, applicability and review status. A drug indication or treatment mention is not proof of cure or personalized eligibility.

## 5. Product progression and advanced intelligence

### Phase A — controlled conversational prototype

Build data audit, clinician authoring, observation extraction, deterministic workflow, candidate retrieval, grounded explanations, evidence display and summary export. Unreviewed data is visible only in development/research views. A feature flag keeps diagnostic suggestions off by default until the serving corpus and clinical logic are approved.

### Phase B — validated candidate ranking

Compare transparent baseline, regularized logistic regression and gradient-boosted tabular models on the same leakage-controlled splits. Input = observed features, explicit absence, missingness masks and clinically justified context. Do not include diagnosis names, IDs, post-diagnosis treatment or source-specific label leakage as predictors. Evaluate source-specific models before pooled models. Any stacking uses out-of-fold predictions, never in-sample predictions.

Calibrate on a distinct calibration partition. Evaluate top-k recall, macro F1, rare-condition recall, subgroup calibration, selective risk and out-of-distribution handling. More complex models must beat the simpler baseline on independent data and safety metrics. Clinical priors require relevant epidemiology; dataset class frequency is not automatically a deployment prior.

### Phase C — adaptive assessment

A proposed question selector balances urgency, expected reduction in candidate uncertainty, answerability and burden. Urgency questions outrank information gain. Estimate information gain only from reviewed rules or validated likelihood models; do not manufacture it from unvalidated counts. Evaluate question policies offline and with clinicians before a supervised trial. Never explore experimental clinical questions on live users through unconstrained reinforcement learning.

Bayesian networks can model conditional relationships if suitable evidence supports parameters. Conformal candidate sets are an optional research direction with explicit exchangeability and calibration assumptions; they do not guarantee coverage under population shift. Heterogeneous graph neural networks or tabular transformers are optional research, not required architecture. No evidence currently justifies using them by default.

### Phase D — longitudinal / clinical workflow product

After separate consent and evaluation: symptom timeline, clinician-verified outcomes, follow-up adherence, teleconsult handoff, multilingual input, validated vitals/lab integrations and FHIR interoperability. Every new population/modality requires a new evaluation scope. Do not self-train on chatbot-generated diagnoses or user agreement with a suggestion.

## 6. Technical architecture

| Component | Recommended v1 implementation | Responsibilities |
|---|---|---|
| Frontend | Lovable-generated React + TypeScript using its supported project template (currently TanStack Start for new projects); accessible UI primitives; TanStack Query | Chat, evidence panels, corrections, consent and summary; never store provider secrets |
| API/backend | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic | Auth, ownership, typed APIs, versioned observations, assessment service |
| Orchestration | Explicit state machine; LangGraph only where persistence/branching adds value | Deterministic gates around extraction, assessment and explanation |
| Database | PostgreSQL + pgvector + PostgreSQL full-text search | Canonical data, evidence, hybrid retrieval; separate restricted session schema |
| Object storage | S3-compatible private buckets, versioning and encrypted backups | Raw ZIPs, manifests, model artifacts; no public medical files |
| Jobs/cache | Redis + worker queue, initially one worker service | Ingestion, embeddings, model training, report generation; not authoritative session state |
| AI gateway | Provider-neutral interface; Anthropic SDK adapter first, optional second provider | Structured extraction and evidence-limited explanation; model ID via config, pinned after eval |
| ML | NumPy baseline; scikit-learn and gradient boosting for validated experiments | Ranking/calibration/abstention; never bypass rule engine |
| Data pipeline | Python/pandas or Polars, Parquet, validation contracts, versioned manifests | Positional import, lineage, review queues and model-ready views |
| Tracking | MLflow or equivalent artifact/experiment registry | Dataset/model/prompt/rule versions, reproducibility and promotion |
| Observability | OpenTelemetry, redacted application logs, metrics/traces | Latency, failures, token use, evidence availability; no raw symptoms in routine logs |
| MCP | Official supported SDK, remote authenticated transport | Same assessment service as REST; tenant/session scopes; read/write tools explicitly separated |
| Delivery | Docker Compose locally; managed PostgreSQL/object store + container services for pilot | Migrations, least privilege, health checks, secrets, rollback |
| Code intelligence | GitNexus developer-only index | Dependency and execution-flow analysis; never holds user health data |

Use stable supported versions resolved at project creation and committed in lockfiles. Do not let a coding assistant guess API syntax from this blueprint. Check selected SDK documentation, generate typed clients from OpenAPI and run integration tests. Kubernetes, a separate graph database and multiple vector stores are unnecessary for the initial product.

### Request pipeline

1. Authenticate principal; derive owner scope from verified session/token, never model-supplied user ID.
2. Enforce consent, rate limits, idempotency and observation version.
3. Run high-priority approved complaint screening; extract structured candidates without inventing negatives. Extraction failure is an incomplete assessment, not negative evidence.
4. Confirm ambiguous entities, apply observation changes transactionally and invalidate stale results.
5. Run reviewed urgency and population-scope rules. An urgent result bypasses ordinary ranking and questioning.
6. Retrieve evidence and candidates only from approved serving releases; determine coverage.
7. Rank candidates and select the next approved question or abstain; ranking scores are internal.
8. Compose structured output using cited evidence; validate every cited ID and scope.
9. Verify no contradiction with urgency/action. Fall back to reviewed template on failure.
10. Persist assessment version and redacted audit event. Return the result and render it accessibly.

### Advanced RAG design

Ingest licensed and reviewed clinical references separately from raw dataset text. Chunk along clinical section boundaries, with disease IDs, feature IDs, population, source URL, publication/review dates, permissions and text offsets. Maintain parent document links. Re-embedding or retirement is versioned.

At query time: normalize complaint → filter by approved release/locale/population/permissions → retrieve lexical and dense candidates → fuse rankings → rerank with a validated cross-encoder → optionally expand one bounded hop through reviewed disease-feature evidence → assemble a small evidence bundle. Do not follow arbitrary URLs in retrieved content. Contradictory evidence remains distinguishable. If context is missing, the generator abstains.

Generation returns claim-to-evidence IDs, not invented citations. Verify citation existence, support and review status before rendering. Use citation retrieval tests, clinician review and deterministic validators; an LLM judge alone is insufficient. Graph retrieval supports evidence navigation, not causal proof. Retrieval similarity is not disease probability. Cache only public reviewed knowledge, never another user's clinical session.

### Security and privacy

Require session ownership checks on every read/write/export. For remote MCP use supported OAuth authorization, token audience validation and least-privilege scopes; do not pass arbitrary client tokens downstream. Isolate credentials server-side. Tool arguments are untrusted even when produced by an LLM. No tool may run arbitrary SQL, shell or URL fetches supplied by the user.

Encrypt transport, database storage, raw data and backups. Redact/disable provider tracing by default. Document provider retention/residency terms before sending health text. Do not use assessment data for training without separate explicit consent and governance. Proposed retention settings must be chosen before launch and tested through backup expiry; do not promise instant erasure from immutable backups. Prompt injection in source text, uploaded documents and user messages must not override rules or expose another session. Maintain incident response and access audit trails.

## 7. Model training, test design and measured graphs

See `experiments/results/metrics.json`, `docs/02_MEASURED_RESULTS.md` and `figures/` for actual baseline results. The executed experiment uses **archive 11 only**, a fixed Bernoulli Naive Bayes baseline with Laplace smoothing. It does not measure the full product, conversational correctness, triage or clinical diagnosis. No trained advanced model or clinical performance is claimed.

### Production experiment protocol

1. Confirm use rights and document data provenance, label origin, populations and feature meanings.
2. Normalize/review mappings; form exact and near-duplicate clusters; group by verified patient/source identities where available.
3. Keep original archive 15 test untouched until the final frozen evaluation. Audit overlap first; report any contaminated original-test result separately from a rebuilt group-held-out benchmark.
4. Use development train, tuning validation, separate calibration and untouched test partitions. Fit preprocessing, feature selection and imputation on training only. Keep identical profiles/verified patients together.
5. Add leave-source-out and external clinician-adjudicated tests. Single-source random splits do not test generalization to other datasets or free-text users.
6. Model selection uses validation only. Calibrator and abstention thresholds use their designated partition. Freeze code/data/model/rules/prompts before final test.
7. Report class support and cluster-bootstrap confidence intervals. Mark sparse slices inconclusive; do not conceal them in a global score.
8. Evaluate urgency separately using adjudicated urgency labels. Existing disease labels cannot be used as surrogate urgency truth.

Required plots: train/validation learning curves; normalized confusion matrix; per-class precision/recall and support; reliability diagrams; risk-coverage curves; performance by source/age/sex/missingness; clinically adjudicated under-/over-triage; retrieval recall/nDCG and citation support; latency/cost distributions. Plot unavailable metrics as unavailable, not zero. Random feature masking tests robustness but does not simulate realistic conversational disclosure.

### Release gates

Engineering gates can be implemented immediately: zero detected split overlap; all responses match contracts; all source claims trace to records; ownership tests pass; stale observation versions rejected; incomplete backend state never becomes reassurance; unapproved rules cannot run in clinical mode; no secrets/raw sessions in public artifacts.

Clinical gates require a named clinical owner, representative cases and an agreed protocol: escalation sensitivity/specificity, candidate coverage, subgroup performance, calibration and acceptable residual risk. No invented universal percentage threshold is sufficient. A zero-failure small sample is not proof of safety. Public clinical mode stays disabled until these gates are documented and met.

## 8. Tests and evaluation layers

| Layer | Required tests |
|---|---|
| Ingestion | Zip traversal/size controls, checksums, malformed rows, duplicate headings, Unicode, missing values, idempotent rerun, source schema drift |
| Mapping | Synonyms versus subtypes, ambiguous mappings, stable IDs, merge redirects, conflict preservation, full-union retention |
| ML | Split leakage, predictor/target leakage, train-only transforms, label coverage, calibration isolation, OOD, partial observations, per-source and subgroup metrics |
| Rules | Clinician-approved fixtures, boundary ages, unknown inputs, contradictory/corrected answers, precedence and missing rule bundle |
| Conversation | Negation, temporality, experiencer, uncertainty, mixed complaints, repeated answers, unknown values, non-English scope, correction/revision |
| RAG | Gold relevant passages, outdated/revoked evidence, incompatible populations, contradiction, citation existence and claim support |
| API/MCP | Auth/owner isolation, malformed JSON, idempotency conflict, stale version, rate limit, timeout, tool parity and transport auth |
| Frontend | Keyboard, screen reader, mobile, reconnect, cancellation, correction, expired session, urgent-state visibility |
| Security | Prompt injection, cross-tenant access, SSRF, secret leakage, export authorization, retention/deletion, dependency scanning |
| Operations | Provider outage, queue failure, DB restore, model rollback, kill switch, stale index, migration rollback |

Use pytest, contract tests, Playwright and a redacted eval harness. Prefer deterministic pass/fail checks for structural safety. Clinician adjudication remains necessary for clinical correctness. Track prompt/model/knowledge versions in every eval.

## 9. Implementation steps and completion criteria

| Stage | Steps and substeps | Completion artifact |
|---|---|---|
| 0. Product foundation | Confirm intended use, adult scope, launch market, clinical owner, data rights, retention, name clearance and budgets | Signed scope/decision register; clinical mode remains off |
| 1. Repo foundation | Create monorepo; pin toolchains; configure lint/typecheck/tests; secrets/env templates; Compose; auth skeleton; GitNexus | Local build and CI pass; code index reflects current commit |
| 2. Source ingestion | Register hashes; import all 12 CSVs and 85 texts positionally; preserve raw; produce quality/dedup reports | Reproducible source manifests and audit matching supplied counts |
| 3. Canonical mapping | Load lexical crosswalks; review aliases/subtypes; classify features; resolve duplicate columns; attach provenance | Versioned disease/feature mapping release with unresolved queue |
| 4. Knowledge curation | Verify source licences; review atomic statements; add clinical guidelines; author question and urgency bundles | Approved serving corpus and rule/question release, or development-only mode |
| 5. Assessment backend | Session/observation state, ownership, idempotency, structured extraction adapter, rule executor, candidate retrieval and abstention | API contracts and integration tests pass; no provider needed for fixture mode |
| 6. First UI and MCP | Build intake/chat/corrections/results/summary; expose MCP tools sharing backend; add accessibility and scopes | End-to-end fixture flows through web and MCP |
| 7. Baselines | Reproduce supplied experiment; build logistic/boosted challengers; source/group splits; calibration; missingness and OOD | Reproducible model cards, plots, failure reports and frozen artifacts |
| 8. RAG and dialogue | Build filtered hybrid retrieval/rerank; grounded output schema; citation validation; adaptive question policy | Retrieval and dialogue eval results against reviewed test cases |
| 9. Supervised pilot | Clinician-adjudicated external cases; bias and safety evaluation; load/privacy/security tests; red-team failures | Pilot report, risks, fixes and documented release decision |
| 10. Controlled release | Feature flags, staged deployment, monitoring, rollback, feedback adjudication and incident drills | Auditable release with approved clinical scope |
| 11. Advanced product | Add longitudinal, multilingual and clinical integrations one scope at a time | Separate validation for each expanded capability |

Indicative planning only: 12–16 weeks for a constrained supervised pilot with two full-stack/backend engineers, one ML/data engineer, product/design support and a responsible clinical reviewer, assuming timely data access. This is not a delivery commitment; clinical data acquisition/review may dominate the schedule.

## 10. GitNexus integration

GitNexus indexes code symbols, dependencies and execution flows. It is a developer tool, separate from the medical graph. Existing connected indexes were inspected; none was a repository for this new product. No product code graph has been generated or installed yet.

After creating the repository, use the upstream documented CLI flow: `npx gitnexus analyze` in the project root; `npx gitnexus mcp` for the developer MCP server. Resolve and pin the package in development dependencies rather than using unpinned downloads in CI. Verify commands against the installed release. Preserve authored CLAUDE.md instructions if indexing generates context files.

For Claude coding: query execution flows before changing modules; inspect symbol context; use impact analysis before shared-code changes; use API impact/route maps when supported; use change detection before commit. Review fuzzy results and run real tests. Re-index after substantive changes and record indexed commit. Code-graph analysis is not proof of correctness or clinical validation.

Index only source, schemas, tests and documentation. Exclude raw ZIPs, patient/session data, model binaries, secrets, exports, build folders and dependencies. Never publish an index or generated wiki automatically. Use the connected tools only against this new repo, not the user's unrelated existing repositories.

## 11. Additional requirements not in the initial list

- Named clinical owner, intended-use statement, launch-country regulatory assessment and incident reporting plan.
- Dataset rights, source provenance and synthetic/real-data determination.
- Clear target population, supported conditions and language coverage.
- Consent, retention, deletion, residency and model-provider data handling.
- Gold clinical test set, urgency labels and adverse-event/near-miss review.
- Accessibility, understandable uncertainty and unsupported-user behaviour.
- Cost model, observability, version rollback, release gates and operational ownership.
- Outcome feedback that distinguishes clinician-confirmed outcomes from user agreement.
- Business incentives that do not bias care suggestions or referral urgency.
- Name/domain/trademark clearance and security threat modelling.

Cost planning: cost/session = extraction calls + explanation calls + embeddings/reranking + infrastructure allocation + clinical review allocation. Log token/model usage without medical content. Benchmark real request traces before setting a price or cost budget. No vendor price assumptions are embedded here.

## 12. Status at handoff

Measured: six ZIP inventories, lexical disease/feature crosswalks, per-file exact duplicate audits, repeated-profile findings, one offline archive-11 baseline and corresponding charts. Designed: product flows, data schema, contracts, architecture, evals, GitNexus workflow and delivery steps. Not completed: clinical semantic deduplication, population validation, a production app/repository, live integrations, clinical rules, advanced ML training or a clinical release approval.
