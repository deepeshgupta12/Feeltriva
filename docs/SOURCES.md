# Sources and provenance

## Primary project evidence

The six user-supplied archives are the authoritative inputs for the measured inventory and experiment. Archive checksums are in `specs/ingestion_manifest.json`. `data_audit/audit.json` and `experiments/results/metrics.json` are generated evidence; the scripts describe how they were computed. The data sources' clinical validity, original licences and real/synthetic status remain unverified.

## Technical and clinical-AI design references

These primary references informed the proposed design. Check installed-version documentation when implementing; this package does not assert that example CLI/SDK behaviour is permanent.

- [WHO: ethics and governance guidance for large multimodal models](https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models) — governance, human oversight and evaluation context for health AI.
- [MCP official repository](https://github.com/modelcontextprotocol/modelcontextprotocol) — protocol architecture, authorization and security documentation. MCP is a tool/application interface, not a medical model.
- [GitNexus official repository](https://github.com/abhigyanpatwari/GitNexus) — developer code graph, analyze CLI and MCP integration.
- [scikit-learn: common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) — data leakage and train-only preprocessing.
- [scikit-learn: cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html) — grouped and other evaluation splits.
- [scikit-learn: probability calibration](https://scikit-learn.org/stable/modules/calibration.html) — calibration evaluation and reliability plots.
- [pgvector official repository](https://github.com/pgvector/pgvector) — PostgreSQL vector retrieval implementation.
- [FastAPI official documentation](https://fastapi.tiangolo.com/) — typed backend/API implementation.
- [LangGraph official overview](https://docs.langchain.com/oss/python/langgraph/overview) — optional stateful orchestration; not mandatory for the initial implementation.
- [Lovable: supported project template](https://docs.lovable.dev/features/upgrade-to-tanstack-start.md) — current TanStack Start template and older React/Vite projects.
- [Lovable: connectors and APIs](https://docs.lovable.dev/integrations/introduction.md) — distinction between builder context connectors and published-app integrations.
- [Lovable: secrets](https://docs.lovable.dev/features/secrets.md) — backend secrets versus browser-exposed configuration.

Architecture choices, backlog and product scope are recommendations/inferences, not facts established by those sources. No clinical rules, epidemiological priors, emergency numbers, treatment protocols or regulatory determinations are supplied as validated content.
