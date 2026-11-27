# Contracts

`openapi.json` is the contract of the assessment API as the product serves it: the contract the handoff
supplied (`specs/openapi.json`, which is not edited) with the product's additions. A test
(`tests/api/test_contract.py`) checks that every supplied operation and field is in it unchanged, that every
operation in it is served under the same `operationId`, and that real answers of the service match its shapes.

Additions so far:

| Since | Addition |
|---|---|
| M3.12 | `ObservationRecord.display_name` and `value_label`: the item's name and the stored answer in words, beside the internal values |
| M3.12 | `location`, `pattern`, `triggers`, `relieving_factors` on an observation, sent and returned |
| M3.12 | `GET /v1/sessions/{session_id}/assessment` (`getCurrentAssessment`) |
| M3.12 | `GET /v1/conditions/{disease_id}` (`getConditionInformation`), served since M2.9 and now in the contract |

`openapi.internal.json` lists the routes of the review workspace (`/internal/v1/review/…`) as the service itself
describes them. It is written by `uv run python -m feeltriva_api.contract` and a test checks that it is current.
These routes are for reviewers only; their answers carry no declared shape yet.

The web app's types are generated from `openapi.json`:

```bash
cd apps/web
pnpm gen:api
```

Nothing in a user-facing shape carries a code of an outside vocabulary (decision E63).
