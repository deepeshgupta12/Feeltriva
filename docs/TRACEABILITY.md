# Requirements traceability

Every requirement in the handoff, traced on 2026-11-16 to what exists in this repository and to
the plan sub-step that covers what is missing. Sources walked: `docs/01` – `docs/06`,
`docs/SOURCES.md`, `specs/schema.sql`, `specs/openapi.json`, `specs/ingestion_manifest.json`,
`data_audit/`, `experiments/`, `figures/` (see `FIGURES_CROSSCHECK.md`), and the owner's later
instructions.

Status words:

- **Done** — implemented and verified by a test or a recorded run.
- **Partial** — some of it exists; the "What exists / what is missing" column says which part.
- **Missing** — nothing exists yet.
- **External** — cannot be completed by engineering alone; needs the owner, a clinician or a
  legal/data decision.
- **Decided** — the requirement was a decision and the owner has made it; nothing is built for
  it (see `DECISIONS.md`).

"Fixture" means it works with the synthetic, nonmedical release only. Sub-step IDs refer to
`IMPLEMENTATION_PLAN.md`; IDs marked *new* were added by this trace.

## Summary

Last updated after sub-step M3.13 (2026-11-27).

| Area | Done | Partial | Missing | External | Decided |
|---|---:|---:|---:|---:|---:|
| Functional requirements | 7 | 10 | 1 | 0 | 0 |
| Data | 44 | 11 | 5 | 0 | 0 |
| Architecture | 11 | 15 | 8 | 0 | 0 |
| Model training and testing | 5 | 5 | 12 | 2 | 1 |
| Test and evaluation layers | 1 | 8 | 2 | 0 | 0 |
| Contracts and repository | 10 | 6 | 4 | 0 | 0 |
| Backlog milestones | 3 | 1 | 5 | 0 | 0 |
| Frontend prompt | 9 | 6 | 0 | 0 | 0 |
| Other requirements | 1 | 1 | 4 | 2 | 3 |
| **Total** | **91** | **63** | **41** | **4** | **4** |

Of 203 traced requirements, 91 are done and 4 were closed by an owner decision. (M1.13 completed two requirements and moved three data rows, T12, T14 and T16, from Done back to Partial: the completeness check showed that each still has work owned by a later sub-step.) The largest missing blocks are model training and testing (section 4), retrieval and language-model work (sections 3 and 5), and the knowledge-review steps that turn pending content into approved releases.

## 1. Functional requirements (`docs/01` §2)

| Ref | Requirement | Status | What exists / what is missing | Sub-step |
|---|---|---|---|---|
| FR01 | Consent and scope: explain use and data handling; no named account needed; unsupported age/scope identified without calling the complaint harmless | Partial | Consent step, anonymous session, minor and caregiver states in the web app; API requires a consent version; age < 18 → out of scope (fixture rule). Consent and privacy wording are drafts; scope rules are not clinically approved | M3.3, M3.6; M6.1 |
| FR02 | Free-text intake preserving negation, time, uncertainty and who has the symptom | Partial | Raw wording stored encrypted; mock extractor handles negation and uncertainty with exact spans. Time is not extracted; experiencer is always "self"; vocabulary is synthetic | M3.2; M5.1 |
| FR03 | Confirmation: user edits interpreted list; every extraction references its message span; speculative items stay unconfirmed | Done | Span stored per observation; confirm / edit / remove in API and web; tested | M3.3, M3.6 |
| FR04 | Urgency screening on every new or corrected message, before ranking, never waiting for a questionnaire | Partial | Mechanism done and tested (runs on unconfirmed details too). No approved urgency rules exist | M3.1, M3.3; M2.5, M6.1 |
| FR05 | Relevant context: age; sex-related factors only when applicable; self-described gender kept separately; prefer-not-to-answer | Partial | Age (optional) and gender identity captured. Nothing asks sex-related clinical factors when applicable | M3.3; **M3.9 new** |
| FR06 | Adaptive questions by safety priority, missing essentials, information value and burden; one at a time; no repeats | Partial | One at a time, no repeats, applicability rules. Selection is a fixed priority order | M3.1; M3.8 |
| FR07 | Candidate assessment with supporting/conflicting observations, unknowns, scope status, evidence IDs; abstain when insufficient | Partial | Contract and abstention done; candidates come only from rule-matched fixture definitions | M3.3; M4, M5 |
| FR08 | Results: next step first, up to three provisional explanations, no uncalibrated percentages | Done | API caps at three; web order verified in a browser; no score field exists | M3.4, M3.6, M3.7 |
| FR09 | Revisions invalidate stale assessments; recompute from confirmed observations; keep an audit | Done | Append-only corrections, 409 on stale version, audit events; tested on PostgreSQL | M3.3 |
| FR10 | Summary previewed by the user with symptoms, negatives, onset/duration, context, answers, missing facts, guidance; sharing is explicit | Done | API summary; web blocks export until reviewed; nothing auto-shared | M3.3, M3.6 |
| FR11 | Optional saved history; delete sessions, summaries and retrieval traces per retention policy; no automatic training consent | Partial | Deletion of primary data with honest receipt. No saved history (no list endpoint; web keeps it in memory). No retention policy | M3.3; **M3.10 new**, C8, L1 |
| FR12 | Review console: approve mappings, evidence, questions, rules; publish immutable versions; rollback | Partial | The review service records a decision, with a note and the reviewer's name, on mappings, features, diseases, statements, single claims, text chunks, evidence, sources, vocabulary links, suggested matches, rules, questions, rule sets and response texts (M2.1, M2.5, M2.17, M2.4b). Rule, mapping and knowledge releases are published as versions that cannot be changed, and rolled back by making an earlier one current (M2.5b, M2.5c2, M2.5c3). The live web workspace reads the stored data and records through the service, in plain words (M2.4a to M2.4d). Not yet: publishing and rollback from a screen (service only); screens for follow-up questions and text chunks; deciding many rows at once; a real reviewer sign-in Since M2.4h to M2.4j the review workspace publishes a version of a list and puts an earlier one back in use, shows every remaining list, and decides all rows shown at once. Duplicates are counted by kind and condition names that are one condition are merged by rule (M2.18, E101). An approval a reviewer gives for whole lists is entered row by row with its note, only on rows that say one thing on their own (M2.19, E102): on the real data 46,873 rows are approved under the doctor named by the owner and 5,835 stay pending with the reason; nothing of it is published. By the owner's instruction the approval was also entered on 1,154 suggested matches, where a name has one suggested entry in a list (M2.19a, E103). Two names for one symptom or other item are merged like two condition names, and published lists read a merged name through the kept item (M2.20, E105): 28 names merged into 26 items on the real data. | M2.1; M2.4, M2.5; M2.4h, M2.4i, M2.4j; M6.4a |
| FR13 | Timeout or error gives an explicit incomplete state, never reassurance | Done | 503 with nothing concluded; state `system_unavailable`; tested | M3.3 |
| FR14 | MCP surface on the same service, no bypass of scope, safety or access control | Partial | Nine tools over stdio with parity tests. No remote authenticated transport | M3.5; **M3.11 new** |
| States | `consent_pending → intake → clarifying → assessing → result_ready` plus urgent, out of scope, insufficient, unavailable, closed; version on every question and assessment | Done | Enforced in service and database check constraint | M3.3, M0.4 |
| Attributes | Presence, onset, duration, location, severity, pattern, triggers, relieving factors | Partial | Contract carries presence, onset, duration, severity only | **M3.12 new** |
| Targets | WCAG 2.2 AA; rule evaluation p95 < 300 ms; turn p95 < 8 s at pilot load | Missing | Not measured; accessibility only by automated checks | **M3.15 new**, M6.5 |
| Exclusions | No autonomous diagnosis, dosing, emergency monitoring, image interpretation, children, pregnancy-specific flows, impersonation, booking | Done | None of these exist; minors are routed out of scope | — |

## 2. Data (`docs/01` §3–4, `docs/04`, `docs/02` source audit)

### 2.1 Combination policy and deduplication rules

| Ref | Requirement | Status | What exists / what is missing | Sub-step |
|---|---|---|---|---|
| Union | Full union with provenance; every source record kept; no forced ICD/MONDO/HPO IDs | Done | Every row kept as a record; feature values of the matrix files (M1.8) and every listed symptom of the list files (M1.9) kept; no external IDs forced: ICD-11, HPO and MONDO identifiers are candidate links pending review, stored beside the provisional IDs and never replacing them (M2.11, M2.14) | M1.7, M1.8, M1.9 |
| D1 | Fingerprint ZIPs and files; namespace versions and split names | Done | SHA-256 per archive and file; split names namespaced by archive | M1.1, M1.3, M1.7 |
| D2 | Parse by position so duplicate headings survive | Done | Positional reader; tested | M1.1 |
| D3 | Raw rows immutable; exact-content hashes; all member references kept | Done | Content hash per row; duplicates marked, never removed | M1.7 |
| D4 | Lexical normalisation only for disease labels; subtypes preserved; suggested synonyms to review | Done | 960 lexical groups, never merged. 467 suggestions in the review queue (118 possible synonyms, 349 possible subtypes), each with both terms and its reasons; an added word is never treated as a synonym (M2.8; 47 of the synonym suggestions come from two labels sharing one HPO or MONDO term, M2.14 and M2.15). Acting on an accepted suggestion is M2.5 | M1.3, M2.8; M2.5 |
| D5 | Feature prefixes stripped only as candidates; `E_*` classified by clinical meaning; history never treated as an active symptom | Partial | All 223 `E_*` questions have a proposed kind taken from the publisher's own dictionary (110 symptom, 86 history, 26 exposure or lifestyle, 1 measurement; M2.12); an antecedent is never proposed as a symptom. **Missing:** approval | M1.3, M2.7, M2.12; M2.5 |
| D6 | Repeated feature columns merged only after review; conflicts explicit; never OR-ed | Done | Each position kept. Where positions disagree for a case, every position is stored with its raw value and `conflict = true` (242,468 case-header conflicts, 484,936 rows); counts per header equal the handoff's audit | M1.3, M1.8 |
| D7 | Narrative statements de-duplicated within disease/type/source keeping every attribution; atomic claims only into a review queue | Done as pending claims | Done for statements (no duplicates found). 8,742 single claims, each a span of its statement, stored `pending` in `statement_claims` (M2.6, M2.6a, M2.6b, M2.6c); nothing is written to evidence before review | M1.4, M2.6; M2.5 |
| D8 | Feature-profile clusters before splitting; cross-source near-duplicates need comparable semantics | Partial | Clusters per archive and layout done. No cross-source comparison (correct until semantics are reviewed) | M1.7; M4.3 |
| D9 | Conflicting labels on equivalent profiles preserved as ambiguity | Done | 985 archive-15 profiles carry more than one label; nothing voted | M1.7 |
| D10 | Immutable mapping version, split manifest, source hashes, audit report; only approved content published | Partial | Pending mapping working set, hashes, audit. What is approved can be published as an immutable, numbered mapping release with the SHA-256 of its sources and the count of what is still undecided, with rollback (M2.5c2); the owner approved the 85 features the urgency rules name (M2.5c2a), and mapping release 1 with them is published (M2.5c4). No split manifest | M1.2, M1.3, M2.5c2, M2.5c2a, M2.5c4; M4.3 |
| Demog. | Sex/gender counts are row counts, never combined as priors; identity, case ID, clinical sex context and gender identity kept separate | Done | Stored as supplied with the original field name; counts equal the handoff | M1.7 |
| Zones | Four storage zones: raw immutable objects, normalised relational data, reviewed serving knowledge, private session data | Partial | Raw objects (M1.12), relational data and session data exist. No reviewed serving knowledge yet | M1.12; M2.5; C |

### 2.2 Source-to-target mapping table (`docs/04`)

| Ref | Source field → target | Status | What exists / what is missing | Sub-step |
|---|---|---|---|---|
| T1 | All files → `sources`, `source_records`, original byte object retained | Done | 13 sources and every row as a record; the six original ZIPs are stored unchanged in a private, versioned bucket and registered with their SHA-256 in `source_archives` | M1.3, M1.7, M1.12 |
| T2 | 11 `disease` → mappings, `case_labels` | Done | | M1.3, M1.7 |
| T3 | 11 `symptom_*`, `rare_symptom_*` → `feature_mappings`, `case_features` | Done | 2,852,472 values loaded | M1.3, M1.8 |
| T4 | 12 `data.csv` `diseases` | Done | | M1.3, M1.7 |
| T5 | 12 `data.csv` 377 columns → mappings, `case_features` | Done | 1,316,921 values loaded; zero meaning stays `unknown` | M1.3, M1.8 |
| T6 | 12 `final_symptoms_to_disease.csv` → labels, records, parsed `case_features` | Done | 1,081,459 listed items parsed into 283 terms, all linked to existing candidates; rows never aligned with `data.csv` | M1.7, M1.9 |
| T7 | 13 `id`, `name` → `original_id`, `original_label` | Done | 336 mappings carry the native ID | M1.3 |
| T8 | 13 `category` → record metadata / review queue | Done | Kept as supplied on every chunk as `source_category_unreviewed` and beside the description statement; the 85 disease-table records are flagged for review. Example: asthma is still labelled "Mental Health" | M1.10 |
| T9 | 13 `summary` → `statements(description)` | Done | 85 | M1.4 |
| T10 | 13 `word_count`, `url` → raw metadata, `source_url` | Done | URL kept; `word_count` recorded beside the description statement and on each chunk; it equals the measured word count of the body in all 85 files | M1.4, M1.10 |
| T11 | 13 `causes.csv` joined on native ID, name checked | Done | 714; no mismatch | M1.4 |
| T12 | 13 `symptoms.csv` → statements; proposed `disease_feature_evidence` | Partial | 712 statements; 575 pending proposals where a known feature term is mentioned, each tied to its statement with the text span. A mention is not an assertion. The 712 statements are split into 727 sentences and 352 list items, all pending; 113 list items are exactly the name of one feature and carry it as a proposal (M2.6). **Missing:** review and approval, which turn a claim into evidence | M1.4, M1.11, M2.6; M2.5 |
| T13 | 13 `treatments.csv` → statements, never cure or eligibility | Done | 621 as `treatment`, pending | M1.4 |
| T14 | 13 text files → records; statements and chunks after review, with offsets | Partial | 85 files → 3,651 section-bounded chunks with exact character offsets, URL, extraction version and attribution, under a `pending` knowledge release. Not reviewed, so not served. A reviewer can now list and decide each chunk, and an approved chunk becomes a statement with its place in the file (M2.5e1). **Missing:** the review itself: no chunk is decided | M1.3, M1.10, M2.5e1 |
| T15 | 14 `Patient_ID` scoped to source | Done | | M1.7 |
| T16 | 14 `Age` numeric; unit to be confirmed before clinical use | Partial | Value kept exactly as supplied; unit left empty on the cases. A proposed unit (years) with its basis is stored on the source (M2.7). **Missing:** the owner's confirmation; no source documentation states the unit | M1.7, M2.7; owner review, M2.5 |
| T17 | 14 `Gender` kept as Male/Female/Other | Done | 8,271 / 8,336 / 8,393 | M1.7 |
| T18 | 14 `Symptoms` → raw record, parsed `case_features` | Done | 125,036 items parsed into 28 terms (25 existing candidates, 3 new pending ones); original row stays in the archive | M1.9 |
| T19 | 14 `Symptom_Count` → comparison | Done | Compared with the parsed list for all 25,000 rows: 0 mismatches; a mismatch would be flagged on the record. Not stored as a feature | M1.9 |
| T20 | 14 `Disease` | Done | | M1.7 |
| T21 | 15 `PATIENT_ID`, `AGE`, `SEX`, `DISEASE` with split | Done | | M1.7 |
| T22 | 15 `E_*` (223) → mappings, `case_features`, classified by kind | Partial | 9,363,408 values loaded; every mapping carries the full question text and a proposed kind (M2.12). The answers themselves for the 15 questions that are not yes/no are loaded from the source release: 7,026,873 answers in 4,361,917 cells, each with its release row (M2.13a). **Missing:** approval | M1.8, M2.7, M2.12, M2.13a; M2.5 |
| T23 | 15 `SYMPTOM_COUNT` → consistency check | Done | Equals the number of affirmed `E_*` columns in all 610,031 rows: 0 mismatches. Not treated as ground truth | M1.9 |
| T24 | 16 matrix `diseases` | Done | | M1.7 |
| T25 | 16 654 positions → mappings, `case_features`, conflicts explicit | Done | 1,032,212 values loaded; repeated headers kept per position with explicit conflicts | M1.3, M1.8 |
| T26 | 16 descriptions → statements | Done | 820 | M1.5 |
| T27 | 16 `Source`, `Source_URL`, `Retrieved_Date`, `Canonical_Query` | Done | Kept with each statement source | M1.5 |

### 2.3 Entity relationships

| Ref | Relationship | Status | Sub-step |
|---|---|---|---|
| R1 | Source → source record | Done | M1.3, M1.7 |
| R2 | Disease → source aliases, scoped by release | Done | M1.3 |
| R3 | Feature → positional and list term mappings | Done (1,651 column mappings and 311 list-term mappings) | M1.3, M1.9 |
| R4 | Source record → imported case | Done | M1.7 |
| R5 | Case ↔ disease | Done | M1.7 |
| R6 | Case ↔ feature | Done (16,013,976 rows: 14,807,481 from matrix files, 1,206,495 from lists) | M1.8, M1.9 |
| R7 | Disease ↔ feature evidence | Done as pending proposals (22,947 rows: 575 narrative mentions, 888 questions the DDXPlus release lists per condition as symptoms or antecedents (M2.13b), 21,484 per-source co-occurrence counts with denominators; none approved). A reviewer can decide an evidence row, and approved rows enter a knowledge release (M2.5c3) | M1.11, M2.5c3; M2.5e, M2.9 |
| R8 | Disease → narrative statements | Done | M1.4, M1.5 |
| R9 | Statement ↔ source record | Done | M1.4, M1.5 |
| R10 | Knowledge release → evidence chunks | Done (pending knowledge set `knowledge-import-0` with 3,651 chunks). Approved statements and evidence can be published as an immutable knowledge release (M2.5c3); none is published. The chunks have no review status and are in no release | M1.10, M2.5c3; M2.5e |
| R11 | Session → observations, answers, assessments | Done (moving to Cassandra) | M3.3; C |
| R12 | Assessment → model, rules, knowledge releases | Partial (IDs recorded; no real releases) | M3.3; M2.5, L9 |

### 2.4 Serving and ML exports

| Ref | Export / view | Status | Sub-step |
|---|---|---|---|
| X1 | `reviewed_disease_catalog` | Done as a view over the current mapping release (IDs, names, other names, definitions, merged labels); empty until a disease is approved and published | M2.9 |
| X2 | `reviewed_disease_feature_edges` | Done as a view over the current knowledge release, restricted to approved evidence of approved sources; empty until evidence is approved and published | M1.11, M2.9 |
| X3 | `reviewed_care_statements` | Done as a view (statements about treatment, management and prevention), beside `reviewed_condition_statements` with all statements of a condition, which the condition endpoint reads; no clinician has reviewed a statement, so both are empty | M2.2, M2.9 |
| X4 | `model_cases` | Missing | M4.3 |
| X5 | `model_observations` (unknown is not false) | Missing | M1.8; M4.3 |
| X6 | `retrieval_corpus` | Missing (chunks exist with full-text vectors; the approved-only export does not) | M1.10; M5.2 |
| X7 | `session_summary` | Done | M3.3 |
| X8 | No combined male/female prevalence export | Done (none exists) | — |

## 3. Architecture (`docs/01` §6, `figures/technical-architecture.png`)

| Ref | Component / rule | Status | What exists / what is missing | Sub-step |
|---|---|---|---|---|
| A1 | Frontend: React + TypeScript, accessible primitives | Done | Built here, not by Lovable (E22) | M3.6 |
| A2 | API: Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic | Done | | M0, M3.3 |
| A3 | Explicit state machine | Done | | M3.3 |
| A4 | PostgreSQL + **pgvector** + **full-text search** | Partial | PostgreSQL in use; full-text search vectors now populated for the narrative chunks (M1.10). Vector extension not enabled; no embeddings | M1.10; M5.2 |
| A5 | Private object storage with versioning and encrypted backups | Partial | Private, versioned S3-compatible bucket running in the local stack and holding the six archives (versitygw, decision E48). No backups and no encryption at rest configured | M1.12; M0.10, M6.4 |
| A6 | Redis + worker queue for ingestion, embeddings, training, reports | Missing | Redis defined, never started; loaders run as commands | L7 |
| A7 | Provider-neutral AI gateway, Anthropic adapter first | Partial | Interface and mock only | M5.1 |
| A8 | ML: scikit-learn and gradient boosting for validated experiments | Missing | | M4.4 |
| A9 | Data pipeline with Parquet, validation contracts, versioned manifests | Partial | Streaming loaders and manifest checks. No Parquet exports | M1; M4.3 |
| A10 | Experiment tracking (MLflow or equivalent) | Missing | | M4.4, L7 |
| A11 | Observability: OpenTelemetry, redacted logs, metrics | Missing | Request IDs and redacted audit events only | **M0.9 new** |
| A12 | MCP on the official SDK, remote authenticated transport | Partial | stdio only | M3.5; **M3.11 new** |
| A13 | Delivery: Compose locally; containers and managed services for pilot | Partial | Compose for PostgreSQL only; API and web are not containerised | **M0.10 new**, M6 |
| A14 | GitNexus developer index | Done | Version noted, not pinned in the repository | G; **G6 new** |
| P1 | Pipeline 1: authenticate, owner from token | Done | | M3.3 |
| P2 | Pipeline 2: consent, **rate limits**, idempotency, version | Partial | Rate limits per verified caller since M3.13. Consent is taken as a version string and not yet as the full consent step | M3.16 |
| P3 | Pipeline 3: complaint screening and extraction; failure is incomplete, not negative | Done (fixture) | | M3.3 |
| P4 | Pipeline 4: confirm, apply transactionally, invalidate stale results | Done | | M3.3 |
| P5 | Pipeline 5: urgency and scope rules; urgent bypasses ranking | Done (fixture) | | M3.3 |
| P6 | Pipeline 6: evidence and candidates only from approved releases | Partial | Enforced for clinical mode at load time. The serving bundle is assembled only from the current rule release, the current mapping release and the approved response texts, and at start the loaded bundle must be exactly that (M2.5f). It holds no candidates and no citations yet | M3.1, M2.5f; M2.9 |
| P7 | Pipeline 7: rank and choose next question or abstain; scores internal | Partial | Rule match and fixed-priority questions | M4, M3.8 |
| P8 | Pipeline 8: compose with cited evidence; validate every cited ID and scope | Partial | Citation existence validated; no composed explanation | M3.3; M5.1, M5.3 |
| P9 | Pipeline 9: check no contradiction with urgency/action; fall back to reviewed template | Missing | No generated explanation yet, so nothing to check | M5.3 |
| P10 | Pipeline 10: persist assessment version and redacted audit | Done | | M3.3 |
| RAG | Chunking by clinical section, filters, hybrid retrieval, rerank, one bounded hop, claim-to-evidence IDs, abstain without context | Partial | Section-bounded chunks with offsets, disease IDs, source URL and parent-document link exist (M1.10), with a review-only full-text search. No filters by approved release, no vectors, reranking, graph hop or claim validation | M1.10; M5.2, M5.3 |
| S1 | Ownership checks on every read, write, export | Done | Service + forced row-level security; tested | M3.3, M0.4 |
| S2 | Remote MCP: OAuth, audience validation, least-privilege scopes | Missing | | **M3.11 new** |
| S3 | Tool arguments untrusted; no SQL, shell or URL fetch | Done | | M3.5 |
| S4 | Encrypt transport, database storage, raw data, backups | Partial | Free text encrypted before storage. No TLS, disk or backup encryption (deployment) | M3.3; M0.10, M6.4 |
| S5 | Provider tracing off by default; provider terms documented before sending health text | Partial | No provider is called. Terms not documented | M5.1 |
| S6 | No training on assessment data without separate consent | Partial | Nothing is trained on. Consent model not built | L1 |
| S7 | Retention chosen and tested through backup expiry; no promise of instant erasure | Missing | Decided by the owner: 30 days (E33). Not built; receipt wording is already honest | C8, M6.4 |
| S8 | Prompt injection cannot override rules or expose another session | Missing | No LLM in the loop yet; no fixtures | M5.4 |
| S9 | Incident response and access audit trails | Partial | Audit events exist. No incident plan | **M6.6 new** |

## 4. Model training and testing (`docs/01` §7, `docs/02`)

| Ref | Requirement | Status | What exists / what is missing | Sub-step |
|---|---|---|---|---|
| E0 | Supplied baseline preserved as a reproducible benchmark and rejected for serving | Partial | Results stored and checked against the figures; not re-run here; not wired into serving | M4.1 |
| E1 | Confirm rights, provenance, label origin, populations, feature meanings | Partial | Archive 15: origin, licence (CC BY 4.0) and nature (simulated patients) established and recorded (E55). The other archives: owner's statement only (E30), no written provenance. A reviewer's decision on the rights of each source can be recorded (M2.5c3); the owner approved all 14 on 2026-11-24 (E87, M2.5c4), with no licence verified. Feature meanings proposed, pending review. Label origin unknown for archives 11 – 14 and 16 (D-O1); for archive 15 the label is the simulator's condition | M2.7, M2.12, M4.2 |
| E2 | Review mappings; exact and near-duplicate clusters; group by identity where available | Partial | Exact and profile clusters done | M1.7; M2.5, M4.3 |
| E3 | Archive 15 original test kept untouched; overlap audited; contaminated result reported separately | Partial | Overlap audited and flagged (27,910 shared profiles) | M1.7; M4.3 |
| E4 | Train, validation, separate calibration and untouched test; transforms fitted on training only; clusters kept together | Missing | | M4.3, M4.4 |
| E4b | **A fresh untouched test set**: the archive-11 test split is "now exposed" (`docs/02`) | Missing | Was not in the plan | M4.3 (widened) |
| E5 | Leave-source-out and external clinician-adjudicated tests | Missing / External | | M4.5 (widened), M6.2 |
| E6 | Selection on validation only; calibration and abstention on their own partition; freeze before final test | Missing | | M4.5 |
| E7 | Class support and cluster-bootstrap confidence intervals; sparse slices marked inconclusive | Missing | Baseline has none | M4.5 |
| E8 | Urgency evaluated separately with adjudicated labels | External | No urgency labels exist. Urgency rules will be drafted by the assistant on the owner's instruction (E39), which is not the same as adjudicated labels. The draft exists since M2.10 (20 rules, pending); it has not been tried on any case, because no urgency labels exist | M2.10, M6.2 |
| N1 | Next experiment: verify zero semantics and label origins | Partial | Archive 15: a 0 on a yes/no question is the source's documented "no" (M2.12); 15 questions are not yes/no. Archive 12: a zero is a term not listed. Archives 11 and 16: the files give no evidence; the owner's decision E53 applies. Label origin known for archive 15 only | M2.7, M2.12, M4.2 |
| N2 | Next: inspect feature relationships and source artefacts (accuracy rises when features are hidden; falls with more data) | Missing | | M4.2 |
| N3 | Next: regularised linear baseline and boosted challenger on controlled splits | Missing | | M4.4 |
| N4 | Next: evaluate missingness explicitly | Missing | | M4.5 |
| N5 | Next: separately adjudicated external case set | External | Owner will supply it; split once into training and held-out parts (E35) | M4.3, M6.2 |
| N6 | Next: calibrate and test abstention on dedicated partitions; study error families before adding complexity | Missing | | M4.5, M4.6 |
| Plots | Learning curves, confusion matrix, per-class precision/recall/support, reliability, risk-coverage, by source/age/sex/missingness, under/over-triage, retrieval recall/nDCG, latency/cost; unavailable shown as unavailable | Missing | Only the handoff's baseline charts exist | M4.6, M5.5, M6.3 |
| G1 | Gate: zero detected split overlap | Missing | | M4.3 |
| G2 | Gate: all responses match contracts | Done | | M3.4 |
| G3 | Gate: all source claims trace to records | Done | Every statement has a source record; served statements require one | M1.4, M2.2 |
| G4 | Gate: ownership tests pass; stale versions rejected; incomplete never reassurance | Done | | M3.3 |
| G5 | Gate: unapproved rules cannot run in clinical mode | Done | Refused at load time; tested | M3.1 |
| G6 | Gate: no secrets or raw sessions in public artefacts | Done | Ignore rules, CI check, secret scanning | M0.8 |
| G7 | Clinical gates: named owner, representative cases, protocol, thresholds | Decided | Owner decision E36: no clinical gates or thresholds, a single release. The evaluation is still shown to the owner before go-live (E40) | M6.3, M6.7 |
| Self-learning | Product and models learn and evolve (owner, 2026-11-16) | Missing | Planned | L |

## 5. Test and evaluation layers (`docs/01` §8)

| Layer | Required | Status | Missing part | Sub-step |
|---|---|---|---|---|
| Ingestion | Traversal/size, checksums, malformed rows, duplicate headings, Unicode, missing values, idempotent rerun, schema drift | Done | Every loader that reads columns now refuses a file whose columns changed, before writing anything (`tests/ingestion/test_schema_drift.py`); text outside ASCII is covered in the archive, list and narrative tests | M1.1 – M1.13 |
| Mapping | Synonyms vs subtypes, ambiguous mappings, stable IDs, redirects, conflict preservation, full union | Partial | Synonym and subtype suggestions are tested (M2.8); merges, splits and redirects are tested (M2.5c1), and a published mapping release resolves a merged label to the kept one (M2.5c2). Missing: ambiguity tests | M2.5, M2.8 |
| ML | Split leakage, target leakage, train-only transforms, coverage, calibration isolation, OOD, partial observations, per-source and subgroup | Missing | All | M4 |
| Rules | Approved fixtures, boundary ages, unknown inputs, contradictions, precedence, missing bundle | Partial | Clinician-approved fixtures | M3.1; M6.2 |
| Conversation | Negation, temporality, experiencer, uncertainty, mixed complaints, repeats, unknowns, non-English, correction | Partial | Temporality, experiencer, non-English | M5.1, M5.5 |
| RAG | Gold passages, revoked evidence, incompatible populations, contradiction, citation existence and support | Missing | All except citation existence | M5 |
| API/MCP | Owner isolation, malformed JSON, idempotency conflict, stale version, rate limit, timeout, tool parity, transport auth | Partial | Rate limit, remote transport auth | M3.11, M3.13 |
| Frontend | Keyboard, screen reader, mobile, reconnect, cancellation, correction, expired session, urgent visibility | Partial | Screen reader, real devices, one focus defect | M3.14, M3.15 |
| Security | Prompt injection, cross-tenant, SSRF, secret leakage, export authorisation, retention/deletion, dependency scanning | Partial | Prompt injection, export-scope test, retention | M5.4, C8 |
| Operations | Provider outage, queue failure, restore, model rollback, kill switch, stale index, migration rollback | Partial | All except provider outage and migration rollback | M6.4, M6.5, L9 |
| Harness | pytest, contract tests, Playwright, redacted evaluation harness | Partial | `evaluations/` is empty | **M5.6 new** |

## 6. Contracts and repository (`docs/03`)

| Ref | Requirement | Status | What exists / what is missing | Sub-step |
|---|---|---|---|---|
| L1 | Repository layout (15 paths) | Partial | `packages/contracts`, `pipelines/training`, `evaluations` are empty; contract lives in `specs/`, generated types in `apps/web` | M3.12, M4, M5.6 |
| API1 | Authenticate every private request; owner from principal | Done | | M3.3 |
| API2 | Idempotency keys, transactional versions, one error shape | Done | | M3.3 |
| API3 | No numerical probability; `not_assessed` is not low; failed assessment is not benign | Done | | M3.3, M3.7 |
| API4 | Append-only corrections; latest non-superseded; reject cross-session targets; 409 on concurrent writes | Done | | M3.3 |
| API5 | Same key replays; different payload under the same key is 409 | Done | | M3.3 |
| API6 | Summary needs preview and an explicit sharing action | Done | | M3.6 |
| API7 | Deletion queued for database, object storage, traces, caches; reported accurately | Partial | Database only; receipt says "scheduled" | M3.3; C8 |
| API8 | Audit event without symptom content | Done | | M3.3 |
| MCP1 | Nine tools with the listed inputs, outputs and scopes | Done | | M3.5 |
| MCP2 | Remote deployments: sessions bound to callers, token audience validated | Missing | | **M3.11 new** |
| RULE1 | Declarative AST: AND/OR, presence, numeric comparison, missingness; validated; three-valued | Done | | M3.1 |
| RULE2 | Actions escalate, clarify, exclude from scope, continue; human-approved priority | Partial | `clarify` and `continue` are defined but unused; rules live in a bundle file, not `clinical_rules` | M3.1; M2.5 |
| LLM1 | `extract(message, context)` and `explain(assessment, evidence_bundle)` only | Partial | `extract` exists without context; `explain` does not exist | M5.1 |
| LLM2 | Extraction returns spans, concept IDs, polarity, time, experiencer, qualifiers, uncertainty | Partial | No time or qualifiers | M5.1 |
| LLM3 | Explanation cannot add a diagnosis, medication or lower urgency | Missing | | M5.3 |
| CI1 | Lint/types → unit → migrations on disposable PostgreSQL → contract diff → ownership/version tests → UI tests → eval smoke → dependency/secret scanning | Partial | No evaluation smoke suite; browser tests not in CI | M0.8; M5.6 |
| CI2 | On model release: full frozen evaluation suite and clinical checklist | Missing | | L8 |
| DEP | Separate development, staging, production; kill switch; rollback; managed secrets; encrypted backups; restore drills | Missing | Development only | **M0.10 new**, M6.4 |
| GN | GitNexus actions 1 – 6 | Done | | G |

## 7. Backlog milestones (`docs/05`): acceptance criteria

| Milestone | Acceptance | Status | Missing part | Sub-step |
|---|---|---|---|---|
| M0 | Clean checkout starts with documented commands; migrations up/down; contract references resolve; no secrets; clinical mode off | Done | Mock embedding adapter does not exist | M0; M5.2 |
| M1 | All 12 CSVs and 85 texts accounted for; counts and duplicate findings reproduce; reruns idempotent; archive-16 conflicts retained; archive-15 split recorded and flagged | Done | `uv run python -m feeltriva_ingestion completeness` checks four of the five criteria against the files and the audit (235 checks, 0 mismatches). Idempotent reruns cannot be checked by a read-only command; each loader's tests rerun it and expect no change | M1.1 – M1.13 |
| M2 | Pending content cannot enter serving; every displayed claim has a source; conflicting records inspectable; releases can be rolled back | Partial | The four parts hold in the service: pending content cannot enter a release or the serving views (M2.2, M2.5, M2.9); a served statement keeps its source records (M2.9); repeated columns, conflicting links and the names without a link can be inspected and decided on screens (M2.4a to M2.4g); the three kinds of release are published, and rolled back by making an earlier one current (M2.5b, M2.5c2, M2.5c3). Not yet: the web page of a condition reads sample fixtures (M2.9a); publishing and rollback have no screen (M2.4h); nine review lists of the service have no screen (M2.4i). No knowledge release has been published, so nothing is served from reviewed knowledge: that waits for review decisions on about 52,800 pending rows, not for code After M2.19 most stored rows are approved by a list approval of the doctor named by the owner (E102); no version of a list was made from them, so serving is unchanged. Still open: the rows set aside, merging of item names (M2.20), the reviewer's own sign-in (M6.4a). After M2.20 every sub-step of M2 in the plan is done. Still open, and not sub-steps of the build: the rows left pending for a person (E102, E103, E105), and making new versions of the lists from what is approved, which is the owner's step. | M2.9a, M2.4h, M2.4i |
| M3 | End-to-end without a paid provider; cross-session access fails; stale answers 409; errors never reassure; corrections invalidate; REST and MCP match | Done | Follow-on gaps listed under FR05, FR06, FR11, FR14 | M3.8 – M3.15 |
| M4 | No grouped leakage; reproducible; unsupported metrics unavailable; no promotion on accuracy alone | Missing | All | M4 |
| M5 | Missing evidence abstains; explanation cannot change urgency or add a candidate; no private text in telemetry | Missing | All (abstention on missing evidence is done) | M5 |
| M6 | Documented release decision with evidence and residual risks | Missing | Reshaped by owner decisions E36, E37, E45: one go-live decision by the owner; not going live for now | M6.1 – M6.7 |
| M7 | Each expansion with its own contract, consent, scope, evaluation, rollback | Missing | | M7 |
| Cost | Cost worksheet per session and per month | Missing | | M6.5 |

## 8. Frontend prompt (`docs/06`, 15 sections)

| § | Section | Status | Missing part | Sub-step |
|---|---|---|---|---|
| 1 | Prototype boundaries, demo banner, no AI diagnosis in the browser | Done | | M3.6 |
| 2 | Visual tokens, type, spacing, 44 px targets, reduced motion | Partial | Colour contrast not measured | M3.15 |
| 3 | Ten routes; reviewer preview is not authorisation | Done | | M3.6 |
| 4 | Landing page, draft footer pages, no invented claims | Done | | M3.6 |
| 5 | Start and consent in three steps; no guessed age; unsupported scope state | Done | | M3.6 |
| 6 | Conversation workspace, answer types, "Why this question?", editable observations, version conflict | Partial | All the answer types of the handoff are there since M3.14, the date type included; BUG-008 fixed; BUG-009 fixed for the visit in which the question was asked. Missing: the words of a stored option after a reload, which need the contract | M3.12 |
| 7 | Results hierarchy, possibility cards, sources drawer, stale result | Done | | M3.6, M3.7 |
| 8 | Ten urgent/incomplete/unsupported states | Done | | M3.6 |
| 9 | Print-friendly summary, review acknowledgement, no auto-share | Done | | M3.6 |
| 10 | History and privacy screens; nothing sensitive in browser storage | Partial | History is in-memory only | M3.10 |
| 11 | Condition information page from reviewed content | Partial | The service answers from the reviewed serving views (`GET /v1/conditions/{disease_id}`, M2.2 and M2.9). In live mode the web page reads that route (M2.9a) and shows only what is published; today that is nothing, so it says that no reviewed information is available. The design demo shows labelled placeholders | M2.9a |
| 12 | Reviewer console with real audit facts | Partial | In live mode the workspace shows the stored data and records notes and decisions through the service (M2.4a to M2.4d). The design demo (`pnpm dev`) still runs on fixtures, by design; its review screens use the same plain wording (M2.4g) | M2.4 |
| 13 | Twenty components, state model, service interface, OpenAPI types, idempotency | Done | BUG-010 (latent) | M3.6; M3.14 |
| 14 | Responsive 320 – 1440, 200 % zoom, keyboard, screen reader, focus restore | Partial | Zoom and screen reader untested; BUG-007 | M3.14, M3.15 |
| 15 | Ten demo scenarios and README | Done | | M3.6 |

## 9. Other requirements (`docs/01` §10–11, `docs/05` decision register)

| Ref | Requirement | Status | Sub-step |
|---|---|---|---|
| O1 | Named clinical owner, intended-use statement, regulatory assessment, incident reporting | External | Intended users decided (adults in India, English, E31). Nobody medically responsible is named (D-C2); harm reports are reviewed by the owner (E44) | M6.1, M6.6 |
| O2 | Dataset rights, provenance, real-or-synthetic determination | Decided | Owner: real, original data (E30). No written record supplied | M4.2 |
| O3 | Target population, supported conditions, languages | Decided | Owner: adults in India, English (E31). Supported conditions follow from the data | M6.1 |
| O4 | Consent, retention, deletion, residency, provider data handling | Missing | Decided by the owner, not built: consent capture (E32), 30-day retention (E33), Claude API as provider (E46), own Cassandra in this repository (E47) | M3.16, C8, M5.1, C2 |
| O5 | Gold clinical test set, urgency labels, adverse-event review | External | Owner agrees and will supply reference cases; harm reports reviewed by the owner (E44). Urgency labels do not exist | M6.2, M6.6 |
| O6 | Accessibility, understandable uncertainty, unsupported-user behaviour | Partial | M3.15 |
| O7 | Cost model, observability, rollback, release gates, operational ownership | Missing | M0.9, M6.5, L9 |
| O8 | Outcome feedback separating clinician-confirmed outcomes from user agreement | Missing | L2 |
| O9 | Business incentives must not bias suggestions or urgency | Done (no referral or commercial feature exists) | — |
| O10 | Name, domain, trademark clearance; security threat modelling | Decided | Owner: the name is Feeltriva and no clearance check will be done (E43). Threat model not written | M6.6 |
| O11 | GitNexus package pinned rather than an unpinned download | Missing | **G6 new** |

## 10. Owner's instructions after the handoff

| Ref | Instruction | Status | Sub-step |
|---|---|---|---|
| U1 | Conversations in Cassandra; everything conversational moves | Missing (design confirmed) | C1 – C12 |
| U2 | PostgreSQL is the source of truth for data; new entities learned from conversations are written there carefully | Missing | L3a – L3c |
| U3 | Product and model learn and evolve; a person approves go-live | Missing | L |
| U4 | Impact analysis before every code change | In force | `CLAUDE.md` |
| U5 | One sub-step, commit and push, report with tests for the owner, then wait for go-ahead | In force | `CLAUDE.md` |
| U6 | Backend and frontend kept running for the owner | In force | — |
| U7 | Repository public on the owner's GitHub with description, topics, CI | Done | M0.8 |
| U8 | Consent taken from users (E32) | Missing | M3.16 |
| U9 | Conversations kept 30 days (E33) | Missing | C8 |
| U10 | Feature meanings derived from the supplied data (E34) | Done as proposals; 51 headings listed for the owner | M2.7 |
| U11 | Urgency rules drafted by the assistant, approved by the owner (E39) | Approved by the owner, not published | 20 rules from published warning signs, each with its basis, stored `pending` and not served (M2.10). The finished text for approval and its approval record are in `docs/review/urgency_rules_final.md` (M2.10a). The owner approved all 20 rules and the rule set on 2026-11-23 (E78), recorded through the review path (M2.5a, M2.5a1); published as release 1 on the owner's instruction (E80, M2.5b1); the serving bundle holding them is assembled (M2.5f) and not served | M2.10, M2.10a, M2.5a, M2.5a1, M2.5b, M2.5f |
| U12 | Claude API as the language model (E46) | Missing | M5.1 |
| U13 | Cassandra self-hosted inside this repository (E47) | Missing | C2 |
| U14 | Not live for now; the whole handoff is built end to end (E45) | In force | all steps |
| U15 | External cases are also used for training, split once (E35) | Missing | M4.3 |
| U16 | Standard vocabularies ICD-11, LOINC and SNOMED CT for diseases, symptoms, history, lifestyle and measurements (E51) | Partial: ICD-11 and LOINC links stored as pending candidates (571 and 10; M2.11). SNOMED CT could not be obtained by the owner; in its place HPO and MONDO links are stored as pending candidates (573 and 594; M2.14, E60, and the owner's confirmed readings of abbreviated labels, M2.15, E61). 680 of 960 disease labels and 300 of 738 named terms have at least one candidate; none is approved, and the 223 question sentences are not looked up as names. On the owner's instruction the SNOMED CT and ICD-11 identifiers that MONDO marks equivalent were imported as pending candidates (527 SNOMED CT, 172 ICD-11 MMS, 46 ICD-11 foundation; M2.16, E62): 475 disease labels have an ICD-11 candidate and 501 a SNOMED CT identifier. No code is shown to a user (E63). Links can be decided through the review API; the owner has decided 11 (5 approved, 6 rejected; M2.17, E64) | M2.11, M2.14, M2.15, M2.16, M2.17 |

## 11. Sub-steps added by this trace

M0.9 observability · M0.10 deployable images and environment separation · M2.8 synonym and
subtype suggestions · M2.9 serving views · M3.9 clinically relevant context · M3.10 saved
history · M3.11 remote MCP transport · M3.12 contract extensions · M3.13 rate limiting ·
M3.14 open web defects · M3.15 accessibility audit · M5.6 evaluation harness · M6.6 threat
model and incident response · G6 pin GitNexus. M4.3 and M4.5 were widened.
