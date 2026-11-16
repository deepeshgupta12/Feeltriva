# Feeltriva — Claude coding handoff

Version 1.0 · 16 November 2026

**Product:** conversational symptom assessment and care navigation. A user describes how they feel, confirms interpreted symptoms, answers relevant follow-up questions and receives provisional explanations and an appropriate next step. Working name: **Feeltriva**. Brand clearance remains a launch task.

**Feasibility:** the six supplied datasets support a research prototype, ingestion pipeline and starting knowledge corpus. They do not, by themselves, establish a clinically reliable diagnostic product. The package makes engineering work possible now while keeping unreviewed clinical suggestions disabled.

## What is delivered

| Requested deliverable | File |
|---|---|
| 1–2. Product name, positioning, users and requirements | `docs/01_PRODUCT_AND_BUILD_SPEC.md` |
| 3. Relationships between all supplied datasets | `docs/04_DATA_MAPPING.md`, `figures/data-relationships.png` |
| 4. Advanced product/model progression | Product specification, section 5 |
| 5. Combined data architecture and deduplication | `specs/schema.sql`, `specs/ingestion_manifest.json`, `data_audit/` |
| 6. FE/BE/database/AI/ML/RAG/LLM/evals/tests | Product specification sections 6–8; `docs/03_CONTRACTS_AND_REPOSITORY.md`; `specs/openapi.json` |
| 7. Actual train/test results and failure images | `docs/02_MEASURED_RESULTS.md`, `experiments/results/`, `figures/` |
| 8. Implementation steps, substeps and acceptance criteria | Product specification section 9; `docs/05_IMPLEMENTATION_BACKLOG.md` |
| 9. GitNexus repository integration | Product specification section 10; contracts document; `repo_templates/CLAUDE.md` |
| Missing launch/operational requirements | Product specification section 11; implementation decision register |
| Detailed Lovable frontend design prompt | `docs/06_LOVABLE_FRONTEND_PROMPT.md` |

## Important measured findings

- Six ZIPs contain 12 CSV files and 85 narrative text files.
- Disease names collapse to **960 lexical groups** after case/whitespace normalization. These are provisional IDs, not a medically reconciled ontology.
- Archive 12 has 57,305 exact repeated matrix rows and 28,988 exact repeated text rows.
- Archive 15's original train/test files share **27,622 distinct profiles** after excluding patient ID. This is a leakage warning, not proof of repeated people.
- Archive 16 has **37 repeated header names**, each with at least one disagreement between its columns. Positional ingestion is essential.
- The executed archive-11 baseline achieved **15.71% test top-1 accuracy**, below **20.56%** for predicting the training-majority class. This baseline must not be promoted to clinical serving.

## Read and build order

Read this file, the product specification, measured results, mapping document and contracts. Then review the SQL and OpenAPI before starting the backlog. Copy the repo templates into the new product repository and adapt them deliberately. The templates do not constitute a runnable application.

For the frontend, paste the complete prompt from `docs/06_LOVABLE_FRONTEND_PROMPT.md` into Lovable. Give Claude the resulting frontend code as well as this handoff. Preserve its React/TypeScript design and supported framework; connect the typed service adapter to FastAPI. The initial frontend is a clearly labelled interactive demo, not a live clinical assessment service.

The original six ZIPs are **not included** in this handoff. Supply `archive(11).zip` through `archive(16).zip` separately, unchanged. Their SHA-256 hashes are in the ingestion manifest. Do not download or scrape more MalaCards records as a prerequisite for the first engineering milestone. The MalaCards pilot/HTML and a separate duplicate CSV upload are outside this six-ZIP audit; any future import needs its own source contract and provenance.

## Paste this instruction into Claude

```text
Build Feeltriva using the attached handoff as the implementation specification.
First read README_START_HERE.md, all docs/, specs/schema.sql,
specs/openapi.json and repo_templates/CLAUDE.md. Inspect the six source ZIPs
and verify their checksums against specs/ingestion_manifest.json.

Start with milestones M0–M3 in docs/05_IMPLEMENTATION_BACKLOG.md:
create the monorepo, local Compose environment, typed API contracts,
database migrations, positional source ingestion, source audit and
reviewable disease/feature mappings. Implement a runnable fixture-mode
vertical slice of intake, observations, follow-up, assessment, correction
and summary. Connect the product MCP adapter to the same application
service as REST. Use synthetic nonmedical fixtures to test workflow.
If Lovable frontend code is supplied, preserve its design, components
and supported framework and replace its mock service adapter with the
typed API integration. Read docs/06_LOVABLE_FRONTEND_PROMPT.md.

Keep clinical mode disabled by default. Do not invent medical rules,
approve unreviewed sources, call raw dataset frequencies population
prevalence, treat unasked symptoms as absent or expose the experimental
baseline as a diagnostic probability. Do not merge patients across
sources. Preserve provenance, duplicate-column conflicts and unknowns.

Use mock LLM/embedding adapters until provider settings are configured.
Pin supported dependencies and verify their installed-version APIs.
Add meaningful ingestion, auth/ownership, concurrency, contract and
end-to-end tests. Integrate GitNexus only into this new repository,
excluding raw data, secrets and health/session artifacts. Keep developer
GitNexus separate from the product MCP server and clinical evidence graph.

Work through the backlog in order. For each milestone report changed
files, runnable commands, tests performed, unresolved decisions and the
next milestone. Make routine engineering decisions and record them.
Do not claim clinical approval, deployment or validated model performance
without evidence. Missing clinical content must not block infrastructure
and fixture-mode implementation.
```

## Reproduce the analysis

Use Python 3.12 and a dedicated environment. The measured run used NumPy 2.3.5 and Pillow 13.0.0. Install `experiments/requirements.txt`, then run:

```bash
python -m unittest discover -s experiments -p 'test_*.py'
python experiments/audit_and_baseline.py --sources /absolute/path/to/six-zips
python experiments/render_figures.py
```

The audit/model run reads the archives and overwrites this package's generated audit/result files. It does not modify source ZIPs. Training uses NumPy, not an undocumented external model service. The renderer requires an installed TrueType font; see its header for overrides.

## Delivery status

Completed: source inspection, lexical/positional crosswalks, duplicate audit, reproducible baseline experiment, measured charts and failure exports, product/design specifications, draft SQL/OpenAPI, implementation backlog and GitNexus integration instructions.

Not completed or claimed: clinically reviewed semantic merging, a fully materialized combined clinical database, trained advanced models, clinical validation, a deployed chatbot, a product repository or a generated GitNexus product index. The SQL and API describe the coding target; Claude must implement and integration-test them.

The package includes a reproducibility/verification report and `SHA256SUMS.txt`. Its measured results and the proposed build design are deliberately identified separately throughout.
