# Feeltriva

**Understand your symptoms. Know your next step.**

Feeltriva is a conversational symptom-assessment and care-navigation product. A person describes
how they feel, confirms what the system understood, answers relevant follow-up questions and
gets a provisional next step plus a consultation-ready summary.

> **Status: engineering prototype in fixture mode.** Clinical mode is disabled. Everything the
> service returns today is a synthetic, nonmedical fixture ("Illustrative possibility A").
> Feeltriva does not confirm a diagnosis, has not been clinically validated and is not
> production-ready. The datasets it was scoped from have unknown origin and licence.

## What is in this repository

| Path | Contents |
|---|---|
| `apps/web` | React + TypeScript web app (mock and HTTP service adapters) |
| `services/api` | FastAPI transport, auth, ownership and the assessment application service |
| `services/mcp` | Product MCP adapter calling the same application service |
| `packages/clinical` | Bounded rule AST, answer validation, release bundles, synthetic fixture |
| `packages/llm`, `packages/inference`, `packages/retrieval` | Provider boundaries (mock / bundle-backed implementations only) |
| `pipelines/ingestion` | Archive verification, positional audit, reference loaders |
| `migrations` | Alembic migrations including row-level security |
| `infra` | Local Docker Compose stack |
| `tests` | Unit, API, PostgreSQL, MCP and ingestion suites |
| `specs`, `data_audit`, `experiments`, `figures` | Handoff contracts, measured audit and baseline results (unchanged) |
| `docs` | Product spec, plan, engineering log, decisions |

## Quick start (backend, fixture mode)

Requirements: Docker, [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 if needed).

```bash
cp .env.example .env                                         # local, non-secret development values
docker compose -f infra/docker-compose.yml up -d postgres    # PostgreSQL 18 + pgvector on 127.0.0.1:5440
uv sync                                                      # install locked dependencies
uv run alembic upgrade head                                  # schema, constraints, row-level security
uv run python -m feeltriva_api.seed                          # register the synthetic fixture release
uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000
```

Then, in another terminal:

```bash
curl -s localhost:8000/readyz
# {"status":"ready","database":"up","clinical_mode":false,"release":"fixture-rules-0","synthetic_release":true}

AUTH='Authorization: Bearer dev:local-user'      # mock auth exists only in development/test
curl -s -X POST localhost:8000/v1/sessions -H "$AUTH" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-1' -d '{"consent_version":"demo-1","demographics":{"age_years":34}}'
```

The fixture vocabulary is deliberately nonmedical: try the text `I have alpha but no beta`
(`escalation marker` triggers the urgent-state preview, `scope marker` the out-of-scope one).
Interactive API docs are at `http://localhost:8000/docs` in development.

## Quick start (web app)

Requirements: Node 22.22 or newer and pnpm.

```bash
cd apps/web
pnpm install
pnpm dev        # http://localhost:5173  design demo: in-memory sample scenarios, no backend needed
pnpm dev:api    # http://localhost:5174  live mode: every action goes through the API on :8000
```

In the design demo, **Demo tools** (top right) switches between the ten scenarios and turns on
the reviewer preview. In live mode, type the fixture vocabulary (`I have alpha but no beta`,
`escalation marker`). Identity and session state are held in memory only, so reloading the page
starts fresh by design.

```bash
pnpm typecheck && pnpm lint && pnpm test && pnpm build
pnpm smoke      # real Chrome against :5173 — routes, ten scenarios, four viewports
pnpm e2e:live   # real Chrome against :5174 + the API — intake to deletion through REST
```

### Tests

```bash
uv run ruff check . && uv run mypy packages services pipelines
uv run pytest                                    # SQLite; PostgreSQL-only tests are skipped
TEST_DATABASE_URL=postgresql+psycopg://feeltriva_app:feeltriva_app_dev@127.0.0.1:5440/feeltriva_test \
TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://feeltriva:feeltriva_dev@127.0.0.1:5440/feeltriva_test \
  uv run pytest                                  # same suite plus row-level security and concurrency
```

With the six archives in `data/raw/` the second command also runs the tests that read the real
files (about one minute longer). Add `TEST_OBJECT_STORAGE_ENDPOINT=http://127.0.0.1:9010` to
include the test against the running object store.

### Source data (optional)

The six source archives are not in the repository. Place `archive(11).zip` … `archive(16).zip`
unchanged in `data/raw/`, then:

```bash
uv run python -m feeltriva_ingestion verify      # SHA-256 against the manifest + ZIP safety checks
uv run python -m feeltriva_ingestion audit       # positional audit; must reproduce data_audit/audit.json
uv run python -m feeltriva_ingestion load        # pending crosswalks and statements into PostgreSQL
uv run python -m feeltriva_ingestion load-cases     # 1.37 M case rows in 20,000-row batches (about 35 min, 1.7 GB)
uv run python -m feeltriva_ingestion load-features  # 14.8 M feature values (zeros are not stored; 15 – 60 min, 3.3 GB)
uv run python -m feeltriva_ingestion load-lists     # 1.2 M listed symptoms + declared-count checks (about 12 min)
uv run python -m feeltriva_ingestion load-chunks    # 85 narrative files -> 3,651 pending chunks (seconds)
uv run python -m feeltriva_ingestion search-text "night cough wheezing"   # review search over pending text
uv run python -m feeltriva_ingestion load-evidence  # pending disease–feature proposals (about 13 min)
docker compose -f infra/docker-compose.yml --profile storage up -d objectstore   # private S3-compatible store on 127.0.0.1:9010
uv run python -m feeltriva_ingestion store-archives # the six ZIPs, unchanged, verified, in a versioned bucket (seconds)
uv run python -m feeltriva_ingestion completeness   # read-only check of everything above against the handoff's mapping table (6 – 8 min)
uv run python -m feeltriva_ingestion load-release    # trace archive 15 to its source release; store the publisher's question dictionary (about 30 s)
uv run python -m feeltriva_ingestion derive-meanings # proposed kind and zero meaning per column, pending review (about 20 s)
uv run python -m feeltriva_ingestion load-answers    # the answers behind archive 15's questions that are not yes/no, from the source release (first run about 80 min)
uv run python -m feeltriva_ingestion load-conditions # what the source release lists per condition: symptoms, antecedents, severity, ICD-10; all pending (1 – 3 min)
uv run python -m feeltriva_ingestion link-vocabularies # candidate ICD-11 and LOINC codes (first run about 40 min; later runs seconds)
uv run python -m feeltriva_ingestion link-ontologies   # candidate HPO and MONDO terms from two local files; nothing leaves this machine (about 15 s)
uv run python -m feeltriva_ingestion import-identifiers # SNOMED CT and ICD-11 identifiers that MONDO marks equivalent (first run about 4 min; later runs seconds)
uv run python -m feeltriva_ingestion suggest-relations # possible synonyms and subtypes for review; nothing is merged (seconds)
uv run python -m feeltriva_ingestion extract-claims    # every statement split into single claims with exact spans, pending review (seconds); add --remake after a change of the rules
uv run python -m feeltriva_api.rule_drafts             # the draft urgency rules checked against the feature vocabulary and stored pending (nothing approved, nothing served)
```

`link-vocabularies` needs a WHO ICD API key in `.env` (`ICD_API_CLIENT_ID`, `ICD_API_CLIENT_SECRET`; see `.env.example`) and
the LOINC release (`Loinc_2.83.zip`) in `data/raw/`. It sends only term text (a column heading or a disease label) to the
WHO API. `load-release` needs the DDXPlus release (`22687585.zip`, registered in `specs/supplementary_sources.json`) in `data/raw/`.
`link-ontologies` needs `hp.json` (HPO) and `mondo.owl` (MONDO) in `data/raw/`; each is read only when its checksum and release
are the registered ones. It writes every name's outcome to `data/derived/review/ontology_links.csv`, outside Git. Labels that
are abbreviations (`gerd`, `copd`) are linked only through `specs/confirmed_readings.json`, where a named person has confirmed
the full name each stands for. `import-identifiers` takes, for every label with a MONDO link, the SNOMED CT and ICD-11
identifiers MONDO marks equivalent; it sends only ICD-11 entity numbers to the WHO API, to fetch official titles and codes.
No code of any vocabulary is shown to a user: the links are for the internal database (`docs/DECISIONS.md` E63).
Reviewers can list the links at `GET /internal/v1/review/terminology-links` and approve or reject one through
`POST /internal/v1/review/decisions` with the target type `terminology_link`; a decision carries the reviewer's name and a note.

`completeness` prints, for each of the 27 rows of the source-to-target table in
`docs/04_DATA_MAPPING.md`, the loaded value next to the expected one and exits with status 1 on
any mismatch. It confirms that the data is loaded as the handoff requires. It is not a clinical
check: everything it looks at is still pending review.

### MCP

```bash
FEELTRIVA_MCP_BEARER_TOKEN=dev:local-user uv run python -m feeltriva_mcp     # stdio transport
```

The product MCP server exposes the same assessment service as the REST API. It is unrelated to
GitNexus, the developer code-intelligence index described in `CLAUDE.md`.

## Progress

| Step | State |
|---|---|
| M0 Bootable project and contracts | Backend, migrations, auth, generated web client, CI (backend and web jobs) done |
| M1 Reproducible ingestion | Verification, audit, reference load, 1,365,363 case rows, 16,013,976 feature rows, 3,651 narrative chunks, 22,059 pending evidence proposals, the six raw archives in a private, versioned object store, and a completeness check of all of it against the handoff's mapping table (235 checks, 0 mismatches) done. Everything loaded is still `pending` review |
| M2 Reviewable knowledge model | Review API and reviewed-only serving done. Feature meanings proposed from the data for all 1,962 column and list-term mappings, each with its basis, pending review ([`docs/review/feature_meanings.md`](docs/review/feature_meanings.md)); archive 15 is traced row for row to its source release, whose own question dictionary settles all 223 of its questions; for its 15 questions that are not yes/no the answers themselves are loaded from that release (7,026,873 answers), and what the release lists for each of its 49 conditions is stored as pending source-provided evidence (888 rows) and ICD-10 links (49). Candidate ICD-11 codes for 405 of 960 disease labels and 166 of 738 named symptom terms, and 10 LOINC codes, stored pending review. Candidate HPO and MONDO terms for 625 of 960 disease labels and 246 of 738 named terms (1,167 links, 25 of them through the owner's confirmed readings of abbreviated labels), stored pending review; counting ICD-11 as well, 680 disease labels and 300 named terms have at least one candidate. 467 synonym and subtype suggestions in the review queue (`GET /internal/v1/review/relation-suggestions`), none merged. Through those MONDO links, 527 SNOMED CT identifiers and 218 further ICD-11 links (official WHO titles) are stored pending review; 475 of 960 disease labels now have an ICD-11 candidate and 501 a SNOMED CT identifier. Vocabulary links can be decided through the review API; 11 of 2,493 have been (5 approved, 6 rejected by the owner). The SNOMED CT release itself could not be obtained. The 2,952 narrative statements are split into 8,742 single claims with exact spans, pending review. A first urgency rule set is drafted from published warning signs and stored pending: 20 rules, unreviewed and not served (review document: [`docs/review/urgency_rules_draft.md`](docs/review/urgency_rules_draft.md); the finished text awaiting approval: [`docs/review/urgency_rules_final.md`](docs/review/urgency_rules_final.md)). The owner approved all 20 rules and the rule set on 2026-11-23, recorded through the review API under the owner's name; no doctor has reviewed them. An approved rule set can be published as an immutable, numbered release with rollback, and clinical mode starts only on the current release; release 1 of the urgency rules was published on the owner's instruction on 2026-11-23; nothing is served. Release publishing, serving views and review UI wiring not started |
| M3 Fixture-mode vertical slice | Service, REST, contract tests, stdio MCP and the web app done; web verified against the live API in a browser (43 checks) |
| C User conversations on Apache Cassandra (replaces the PostgreSQL session tables) | Planned, not started |
| M4 – M5 Modelling, retrieval and LLM adapters | Not started |
| L Continuous learning: automated retraining, evaluation gates, promotion | Planned, not started |
| M6 – M7 Pilot, expansion | Not started |
| G GitNexus code intelligence | Indexed; dependency check documented |

Every handoff requirement is traced to its status and sub-step in
[`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) (203 requirements; the current count is at the top of that file).

Work follows [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md): steps and sub-steps with
a verification command and status each. Test results, bugs and resolutions per sub-step are in
[`docs/ENGINEERING_LOG.md`](docs/ENGINEERING_LOG.md); decisions made and still open are in
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Data sources and attribution

Archive 15 is the **DDXPlus** dataset: Arsene Fansi Tchango, Rishab Goel, Zhi Wen, Julien Martel, Joumana Ghosn,
*DDXPlus Dataset (English)*, [doi:10.6084/m9.figshare.22687585.v2](https://doi.org/10.6084/m9.figshare.22687585.v2),
licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Its files here are a 0/1 rendering of that release
(every row is traced to it; see `docs/DECISIONS.md` E55). Its patients are **simulated**: the publisher states that they were
"synthesized using a proprietary medical knowledge base and a commercial rule-based AD system". Question headings and
question texts from that release appear in `docs/review/` and `data_audit/`.

The origin of the other five archives is not documented; see `docs/DECISIONS.md` E30.

Candidate codes come from four vocabularies. The link lists themselves are kept in the private database, not in
this repository (`docs/DECISIONS.md` E56). The SNOMED CT release could not be obtained (`docs/DECISIONS.md` E60); on the
owner's decision (E62) the SNOMED CT concept identifiers and ICD-11 entity numbers that MONDO lists as equivalent to its
terms are stored as internal candidates. No SNOMED CT name, description or hierarchy is held.

- **ICD-11:** International Classification of Diseases, Eleventh Revision (ICD-11), World Health Organization (WHO) 2019,
  <https://icd.who.int/browse11>. Licensed under the Creative Commons Attribution-NoDerivatives 3.0 IGO licence
  (CC BY-ND 3.0 IGO).
- **LOINC:** This material contains content from LOINC (http://loinc.org). LOINC is copyright © Regenstrief Institute, Inc.
  and the Logical Observation Identifiers Names and Codes (LOINC) Committee and is available at no cost under the license at
  http://loinc.org/license. LOINC® is a registered United States trademark of Regenstrief Institute, Inc.
- **HPO:** This product is using the Human Phenotype Ontology (release 2026-09-01). Find out more at
  http://www.human-phenotype-ontology.org. Sebastian Köhler, Sandra C Doelken, Christopher J. Mungall, Sebastian Bauer,
  Helen V. Firth, et al., *The Human Phenotype Ontology project: linking molecular biology and disease through phenotype
  data*, Nucl. Acids Res. (1 January 2014) 42 (D1): D966-D974, doi:10.1093/nar/gkt1026. Its terms are stored unchanged:
  identifier, label and address.
- **MONDO:** Mondo Disease Ontology, release 2026-11-03, licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). *Mondo: integrating disease terminology across communities*,
  Genetics, <https://doi.org/10.1093/genetics/iyaf215>. Its terms are stored unchanged: identifier, label and address.

## Safety boundaries that the code enforces

- Clinical mode is off by default and refuses to start with synthetic or unapproved content.
- Unmentioned symptoms are unknown, never absent. An imported zero is not a denial.
- No numerical disease probability is exposed. The offline baseline scored below the majority
  comparator and is rejected for serving.
- A failed or incomplete assessment never renders as a completed or reassuring result.
- Raw datasets, secrets, model artifacts and session data stay out of Git and the code index.

## Documentation

Start with [`docs/HANDOFF_README.md`](docs/HANDOFF_README.md), then
[`docs/01_PRODUCT_AND_BUILD_SPEC.md`](docs/01_PRODUCT_AND_BUILD_SPEC.md),
[`docs/03_CONTRACTS_AND_REPOSITORY.md`](docs/03_CONTRACTS_AND_REPOSITORY.md) and
[`docs/04_DATA_MAPPING.md`](docs/04_DATA_MAPPING.md).
