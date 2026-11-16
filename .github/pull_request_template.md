## What and why

<!-- Plan sub-step ID (docs/IMPLEMENTATION_PLAN.md) and a short description. -->

## Checks

- [ ] `uv run ruff check . && uv run mypy packages services pipelines`
- [ ] `uv run pytest` (SQLite) and the PostgreSQL suite
- [ ] Web: `pnpm --dir apps/web typecheck && pnpm --dir apps/web test && pnpm --dir apps/web build` (if touched)
- [ ] GitNexus `impact` run and reviewed **before** editing any code (every change, see `CLAUDE.md`); HIGH/CRITICAL results reported; `detect_changes` reviewed before commit; MCP adapter and `tests/mcp` checked by hand for service changes
- [ ] Plan status, engineering log (tests run, bugs and resolutions) and README updated
- [ ] No raw data, secrets, model artifacts or session data added
- [ ] No new clinical rule, threshold, emergency number or medical claim without an approved source
