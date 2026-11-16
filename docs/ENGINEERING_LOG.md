# Feeltriva — engineering log

One entry per sub-step in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md): what was
implemented, the tests that were actually run with their real results, and every bug found
with its cause and resolution. Newest entries are at the bottom. Figures are copied from
command output, not estimated.

## Bug index

| Bug | Sub-step | Summary | Status |
|---|---|---|---|

## Entries

### M0.1 — Repository scaffold

**Implemented.** Monorepo directories from `docs/03_CONTRACTS_AND_REPOSITORY.md`. The handoff
package (`docs/`, `specs/`, `data_audit/`, `experiments/`, `figures/`) copied in unchanged so
its relative links still resolve. `.gitignore` and `.env.example` adapted from the handoff
templates; `CLAUDE.md` keeps the authored instructions and adds this repository's working
agreement. The six source ZIPs were moved, unmodified, from the project root to `data/raw/`
(ignored by Git). `Feeltriva_Claude_Handoff.zip` stays at the root, also ignored.

**Checks run.**

- `shasum -a 256 -c SHA256SUMS.txt` inside the extracted handoff: 0 mismatches.
- `shasum -a 256 data/raw/*.zip`: all six digests equal `specs/ingestion_manifest.json`
  (`92be3363…`, `6f81c9c4…`, `fbe1d4b7…`, `19ff1f13…`, `9e21f94b…`, `61749286…`).
- `git check-ignore`: `.env`, `data/raw/*.zip`, the handoff ZIP and `*.npy` are ignored.
- Text search of everything staged for personal details or credentials: none found.

**Bugs.** None.
