## What and why

<!-- Plan sub-step ID (docs/IMPLEMENTATION_PLAN.md) and a short description. -->

## Checks

- [ ] `uv run ruff check . && uv run mypy packages services pipelines`
- [ ] `uv run pytest` (SQLite) and the PostgreSQL suite
- [ ] Web: `pnpm --dir apps/web typecheck && pnpm --dir apps/web test && pnpm --dir apps/web build` (if touched)
- [ ] Critical change (contract, `service*.py`, `schemas.py`, `models.py`, `auth.py`, `db.py`, `packages/`, `migrations/`, `apps/web/src/api`): GitNexus `impact` reviewed before editing and `detect_changes` before commit; MCP adapter and `tests/mcp` checked by hand
- [ ] Plan status, engineering log (tests run, bugs and resolutions) and README updated
- [ ] No raw data, secrets, model artifacts or session data added
- [ ] No new clinical rule, threshold, emergency number or medical claim without an approved source
