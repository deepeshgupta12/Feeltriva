# Feeltriva web

Frontend for Feeltriva, a conversational symptom-assessment and care-navigation product.

**Status: design demo.** Clinical mode is disabled. Every screen carries the banner
“Design demo · Sample scenarios · Not a medical assessment.” The app has not been clinically
validated and is not production-ready. It contains no symptom-to-disease logic: it renders
what an assessment service returns, and in the demo that service is an in-memory mock with
visibly synthetic content (“Sample symptom A”, “Illustrative possibility A”).

The specification this implements is `docs/06_LOVABLE_FRONTEND_PROMPT.md`; the REST contract
is `specs/openapi.json`.

## Stack

| Concern    | Choice                                                                                   |
| ---------- | ---------------------------------------------------------------------------------------- |
| Build      | Vite 8, TypeScript 5.9 (strict)                                                          |
| UI         | React 19, react-router 8 (declarative routes), Tailwind CSS 4                            |
| Primitives | Radix UI dialog and dropdown menu (focus trap, Escape, focus return), lucide-react icons |
| Fonts      | Manrope (headings) and Inter (body), self-hosted via `@fontsource`. No font CDN.         |
| API types  | Generated from `specs/openapi.json` with `openapi-typescript`                            |
| Tests      | Vitest, Testing Library, jsdom; Playwright-driven smoke test against real Chrome         |
| Tooling    | pnpm 11, ESLint 10 (typescript-eslint, react-hooks, jsx-a11y), Prettier                  |

Dependency versions are pinned exactly in `package.json`, and `pnpm-lock.yaml` is committed.
TypeScript stays on 5.9 because `openapi-typescript` and `typescript-eslint` do not support
TypeScript 7 yet. `eslint-plugin-jsx-a11y` declares ESLint ≤ 9 as its peer; it runs correctly
under ESLint 10 here, which is why `pnpm install` prints one peer-dependency warning.

## Commands

Run from `apps/web`. Node ≥ 22.22 and pnpm are required.

| Command                    | What it does                                                                                              |
| -------------------------- | --------------------------------------------------------------------------------------------------------- |
| `pnpm install`             | Install dependencies                                                                                      |
| `pnpm dev`                 | Dev server on http://localhost:5173 (mock mode unless configured otherwise)                               |
| `pnpm build`               | Type-check, then build to `dist/`                                                                         |
| `pnpm preview`             | Serve the production build on port 4173                                                                   |
| `pnpm typecheck`           | `tsc -b --noEmit`                                                                                         |
| `pnpm lint`                | ESLint, zero warnings allowed                                                                             |
| `pnpm test`                | Unit, flow, component and route tests                                                                     |
| `pnpm format`              | Prettier (`pnpm format:check` to verify only)                                                             |
| `pnpm gen:api`             | Regenerate `src/api/generated/schema.ts` from `../../specs/openapi.json`                                  |
| `pnpm gen:review-fixtures` | Regenerate reviewer audit fixtures from `../../data_audit/`                                               |
| `pnpm smoke`               | Browser smoke test. Needs `pnpm dev` running and Google Chrome installed (see [Smoke test](#smoke-test)). |

## Configuration

Public Vite variables only. **Everything here is compiled into the browser bundle and is
public. Never put a secret, provider key or service credential in a `VITE_` variable.** Copy
`.env.example` to `.env.local` to change them.

| Variable            | Default                 | Meaning                                                                                                                                 |
| ------------------- | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_SERVICE_MODE` | `mock`                  | `mock`: in-memory demo scenarios, no network. `http`: call the FastAPI service.                                                         |
| `VITE_API_BASE_URL` | `http://localhost:8000` | API base URL, used in `http` mode.                                                                                                      |
| `VITE_DEV_AUTH`     | `false`                 | `true` sends `Authorization: Bearer dev:<uuid>` (local development only).                                                               |
| `VITE_DEMO_TOOLS`   | on in mock mode and dev | Forces the demo tools (scenario switcher, reviewer preview) on or off. By default they are off in production builds that use http mode. |

## Routes

| Route                    | Purpose                                                                           |
| ------------------------ | --------------------------------------------------------------------------------- |
| `/`                      | Introduction with a direct start action                                           |
| `/start`                 | Intended use and acknowledgement, basic context, first description                |
| `/assess/:sessionId`     | Conversation, one follow-up question at a time, editable “What you’ve shared”     |
| `/results/:sessionId`    | Provisional result in the required order (see below)                              |
| `/summary/:sessionId`    | Consultation summary: review, print / save as PDF, copy text                      |
| `/history`               | Saved summaries (in memory), rename, delete with receipt                          |
| `/conditions/:diseaseId` | Reviewed condition information; sections without content are hidden               |
| `/settings/privacy`      | History preference, retention (draft), export preview, deletion, training consent |
| `/review`                | Internal review overview                                                          |
| `/review/data`           | Data quality: the 37 repeated header names, with notes and demo actions           |
| `/review/…`              | `diseases`, `features`, `evidence`, `rules`, `releases`, `evaluation`             |

Results are always ordered: What to do next → What we understood → Possible explanations →
What is still uncertain → Your consultation summary → Sources.

Private routes set a generic document title and a `noindex` robots tag. Symptoms never appear
in a title, URL query string or metadata.

### Reviewer preview is not authorization

`/review` is shown when “Reviewer preview” is switched on in the demo tools. That switch is a
preview convenience. It is not a security control, and hiding a navigation item never is.
Production must enforce reviewer roles on the backend and protect these routes and their data
server-side before any real review data is served.

## Demo scenarios

Open **Demo tools** in the banner. Choosing a scenario resets the in-memory demo and loads
sample data. Typed text never changes an outcome: the mock does not interpret what you write.

| #   | Scenario                        | Lands on   | What to look at                                                                 |
| --- | ------------------------------- | ---------- | ------------------------------------------------------------------------------- |
| 1   | Normal sample assessment        | `/start`   | Acknowledge → load the example → confirm details → answer → result → summary    |
| 2   | Correct an earlier answer       | `/results` | Edit or remove a detail → “This result needs updating” → “Update result”        |
| 3   | Urgent-state preview            | `/assess`  | High-priority panel, placeholder action text, no questions, no explanations     |
| 4   | Insufficient information        | `/results` | What is missing, “Urgency not assessed”, the next approved question             |
| 5   | Unsupported scope               | `/results` | Limitation screen, summary still available                                      |
| 6   | Backend unavailable and offline | `/results` | “We couldn’t complete this assessment”; “Service outage” and “Simulate offline” |
| 7   | Empty history                   | `/history` | Empty state → sample → summary → delete → receipt (scheduled, then completed)   |
| 8   | Evidence missing                | `/results` | The unsupported explanation is withheld; result marked incomplete               |
| 9   | Concurrent update               | `/assess`  | Send an answer → “Your details changed. Refreshing this assessment…” → resend   |
| 10  | Internal reviewer               | `/review`  | Open a repeated header, add a note, save (“Demo change”)                        |
| +   | Session expired                 | `/assess`  | Session-ended state with a safe restart                                         |

The demo tools also have switches for “Simulate offline”, “Service outage”, “Simulate an
update from another tab”, “Reviewer preview”, and “Reset demo”.

## Architecture

```
src/
  api/
    generated/schema.ts        Generated from specs/openapi.json (do not edit)
    types.ts                   Aliases of the generated types + session states + answer schema
    assessmentService.ts       AssessmentService interface: the UI/backend boundary
    http/HttpAssessmentService.ts   REST adapter      http/auth.ts   token provider boundary
    mock/MockAssessmentService.ts   In-memory scripted stand-in for the API
    idempotency.ts  errors.ts  validate.ts
    conditionInfoService.ts  reviewService.ts   Fixture-backed (no REST endpoints yet)
  fixtures/                    All sample content and scenario scripts (never in components)
  state/
    AssessmentController.ts    One session's view state; the only caller of AssessmentService
    SessionRegistry.ts         In-memory index of sessions opened since page load
    selectors.ts               Pure presentation helpers (grouping, staleness, evidence check)
  demo/runScenario.ts          Loads scenarios through the public service API
  components/  routes/         UI
  lib/                         Answer drafts, summary model, formatting, error copy
```

- **One boundary.** Components never call `fetch` and never hold sample data. They read an
  `AssessmentController` snapshot and call its methods. The controller is the only caller of
  `AssessmentService`, which has `startSession`, `getSession`, `submitObservations`,
  `submitAnswer`, `assessSession`, `getNextQuestion`, `createSummary` and `deleteSession`.
- **UI state is separate from server state.** `Session.state` (`intake`, `clarifying`,
  `assessing`, `result_ready`, `urgent_handoff`, `out_of_scope`, `insufficient_information`,
  `system_unavailable`, `closed`) is only ever what the server reported. Loading flags live
  beside it and never change it. `consent_pending` exists only in the browser before a session
  is created. An unrecognised state renders a neutral “can’t show this step” panel.
- **No clinical logic in the browser.** The app does not compute urgency, rank explanations,
  pick questions or infer absence. The one presentation rule it applies defensively is that an
  explanation is rendered only with evidence that actually exists in the response.

## Connecting the FastAPI backend

Set `VITE_SERVICE_MODE=http` and `VITE_API_BASE_URL`. `createAppServices` in
`src/state/services.ts` then builds `HttpAssessmentService` instead of the mock; nothing else
changes. The adapter targets `specs/openapi.json`:

| Method               | Request                                                     |
| -------------------- | ----------------------------------------------------------- |
| `startSession`       | `POST /v1/sessions`                                         |
| `getSession`         | `GET /v1/sessions/{id}`                                     |
| `submitObservations` | `POST /v1/sessions/{id}/observations`                       |
| `submitAnswer`       | `POST /v1/sessions/{id}/answers`                            |
| `assessSession`      | `POST /v1/sessions/{id}/assessments`                        |
| `getNextQuestion`    | `GET /v1/sessions/{id}/next-question?observation_version=N` |
| `createSummary`      | `POST /v1/sessions/{id}/summary`                            |
| `deleteSession`      | `DELETE /v1/sessions/{id}`                                  |

**CORS.** The browser sends `Authorization`, `Content-Type` and `Idempotency-Key`, so the API
must allow the web origin (for example `http://localhost:5173`), the methods `GET, POST,
DELETE, OPTIONS` and those request headers. Requests use `credentials: 'omit'` (bearer token,
no cookies) and `cache: 'no-store'`. Expose `Retry-After` if 429 responses use it.

**Auth.** With `VITE_DEV_AUTH=true` the adapter sends `Authorization: Bearer dev:<subject>`,
where `<subject>` is a random UUID created once per page load and held in memory only. It is
anonymous and gone on reload. Otherwise the adapter takes a token-provider function. Real
authentication is a marked `TODO(auth)` in `src/api/http/auth.ts` and is deliberately not
faked: without dev auth no `Authorization` header is sent, a protected API answers 401, and the
UI shows its session-ended state.

**Idempotency.** Every mutation carries an `Idempotency-Key` (UUID). The same key is reused
when the same payload is retried after an indeterminate failure (network error, timeout, 429,
5xx). A new key is used for a new operation, including after a definitive answer such as 409 or 422. An identical mutation that is still in flight is not sent twice, and the controller
ignores repeat submits while one is pending.

**Versions and conflicts.** Observation-dependent requests carry `observation_version`. An
answer is sent with the `question_id` and version of the question the user actually saw. On
**409** the controller shows “Your details changed. Refreshing this assessment…”, re-reads the
session with `GET`, keeps the unsent text or answer, fetches the question for the new version
and requires the user to send again. A retained answer is dropped, with a visible notice, if
the current question is a different one. A result is stale whenever
`assessment.observation_version !== session.observation_version`.

**Responses.** `204` from next-question means “no question”. Errors are read from the `Error`
schema (`code`, `message`, `retryable`, `request_id`) and mapped as follows:

| Status    | Handling                                                                                 |
| --------- | ---------------------------------------------------------------------------------------- |
| 401       | Session-ended screen, safe restart                                                       |
| 403       | Permission-denied screen                                                                 |
| 404       | “We couldn’t find this assessment”                                                       |
| 409       | Version conflict flow above (`code` containing `idempot` is treated as a key collision)  |
| 400 / 422 | Inline validation message using the server `message`; input kept                         |
| 429       | “Too many requests”, honouring `Retry-After`; retry reuses the key                       |
| 503 / 5xx | “We couldn’t complete this assessment”; retry and summary offered; no result is invented |
| network   | Offline handling; unsent text kept                                                       |
| bad 2xx   | Rejected as `invalid_response` rather than rendered partially                            |

**Question answers.** `Question.answer_schema` is parsed as
`{ type, options?, allow_not_sure?, unit?, units?, min?, max?, earliest?, latest?, help_text? }`
with `type` one of `yes_no_unsure`, `single_choice`, `multiple_choice`, `number`, `duration`,
`date`, `free_text`. For a date question `earliest` and `latest` are a date written `YYYY-MM-DD`
or the word `today`.
`help_text` is the only source of the “Why this question?” disclosure, which is hidden when it
is absent. An unrecognised schema shows an “unsupported question” state.

| Type              | `answer` sent                                                           |
| ----------------- | ----------------------------------------------------------------------- |
| `yes_no_unsure`   | `"yes"`, `"no"` or `"not_sure"`                                         |
| `single_choice`   | option `value`, or `"not_sure"` when allowed                            |
| `multiple_choice` | `string[]` of option values, or `"not_sure"` when allowed               |
| `number`          | `{ "value": number, "unit": string \| null }`, or `"not_sure"`          |
| `duration`        | `{ "value": number, "unit": "hours" \| "days" \| "weeks" \| "months" }` |
| `date`            | `{ "date": "YYYY-MM-DD" }`, or `"not_sure"` when allowed                |
| `free_text`       | `string` of up to 2,000 characters, or `"not_sure"` when allowed        |

**Observations.** “That’s right”, “Edit” and “Remove/correct” post
`observations: [{ feature_id, presence, confirmed: true, supersedes: <observation_id>, … }]`.
Free text posts `text`. Names shown are `raw_phrase` when present, otherwise a humanised
`feature_id` (`fx.signal_alpha` → “Signal alpha”).

### Assumptions that go beyond the written contract

These are the places where the frontend had to choose. Please confirm or correct them.

1. **“Not sure” is one value.** When `allow_not_sure` is true the UI sends the string
   `"not_sure"` for every type of question, and the service reads it as “not sure” for every
   type (settled in M3.14; before that the UI sent `["not_sure"]` for `multiple_choice`, which
   the service refused, and the service read `"not_sure"` on a free-text question as the
   person’s own words).
2. **`Session.observations` may include superseded revisions.** The UI hides any record whose
   id appears in another record’s `supersedes`. If the API returns only current records this
   is a no-op.
3. **Records with `feature_id: null`** (allowed by `ObservationRecord`, not by `Observation`)
   cannot be confirmed or corrected structurally, so they are shown as “Saved as a note”
   without edit actions.
4. **`conflicting_observation_ids`** are displayed under “Details that need clarification”.
5. **There is no “get assessment” endpoint**, so a result is obtained with
   `POST …/assessments` when the results page opens without one in memory, and after each
   successful assessment the session is re-read to pick up its new `state`.
6. **`urgent_handoff` and `out_of_scope`.** When a session reports either state, the UI
   requests one assessment for that version to obtain the service’s `next_action.text`. It
   never writes its own urgent instructions.
7. **`next_action.question_id`** is not fetched by id; “Answer the next question” returns to
   the conversation, which asks `next-question` for the current version.
8. **`consent_version`** is sent as `demo-consent-0` (`src/config/consent.ts`).
9. **Deletion status** cannot be polled (no endpoint), so the receipt shows exactly the status
   returned by `DELETE`. “Deletion scheduled” is never upgraded to “completed” by the client.
10. **History.** There is no endpoint that lists a user’s sessions, so “Saved summaries” only
    lists sessions created since the page loaded.

### Not backed by REST yet

`/conditions/:diseaseId` and `/review/*` have no endpoints in the OpenAPI document. They run on
fixtures behind `ConditionInfoService` and `ReviewService` so HTTP implementations can replace
them later. The reviewer figures are real audit facts from `data_audit/` (six source archives,
960 lexical disease candidates, 37 repeated header names, 27,622 shared archive-15 train/test
profile signatures), labelled “Imported dataset audit”. The model-evaluation tab shows only the
measured archive-11 research baseline, labelled research-only and “Baseline rejected for
clinical serving”, with clinical validation shown as “Not evaluated”.

## Privacy rules enforced in code

- Health information is held in memory only and is cleared on reload. Nothing about a session
  is written to `localStorage`, `sessionStorage`, IndexedDB, a service worker or an HTTP cache.
- The single stored value is `feeltriva.ui.navCollapsed` (`true`/`false`), written by
  `src/state/preferences.ts`. ESLint forbids every other use of browser storage.
- No analytics, no third-party requests, no external fonts.
- Summaries are never emailed, auto-shared or given a public URL. Printing and copying happen
  only after the review acknowledgement and an explicit click.

## Tests

`pnpm test` runs:

- `src/state/assessmentFlows.test.ts`: mock service flows through the controller (normal flow,
  correction → stale → refreshed, version conflict, urgent stops questioning, insufficient
  information, evidence missing, outage and offline, idempotency replay, deletion).
- `src/api/http/HttpAssessmentService.test.ts`: the HTTP adapter with a stubbed `fetch`
  (paths, auth header, idempotency-key reuse and renewal, in-flight de-duplication, 204,
  401/403/404/409/422/429/503 mapping, invalid bodies).
- `src/routes/routes.test.tsx`: the whole app in jsdom (demo banner on every route, results
  order, stale result, no reassurance when information is insufficient, withheld explanation,
  urgent state, conflict, start validation, nothing written to storage, summary export guard,
  history deletion receipt, reviewer console, condition page).
- `src/components/components.test.tsx`, `src/lib/answers.test.ts`,
  `src/state/selectors.test.ts`: answer inputs, observation chips, source links, selectors.

### Smoke test

`pnpm smoke` drives installed Google Chrome (through `playwright-core`; no browser download)
against a running dev server in mock mode. It walks all ten scenarios, checks every route at
320, 390, 768 and 1440 px for horizontal overflow, and fails on console errors, page errors,
failed or third-party requests, broken focus return and anything written to browser storage.
Set `SMOKE_OUT_DIR` to keep screenshots and the printed summary PDF.

## Accessibility and responsive behaviour

- Layout: 224px navigation rail and a 320px “What you’ve shared” rail from 1280px; below that
  the navigation is a drawer and the details open in a sheet (bottom sheet on phones, right
  drawer from 768px). Content is capped at 1440px. The page never scrolls sideways; wide review
  tables scroll inside a focusable region.
- One `h1` per page, landmarks, a skip link, visible focus (`#2563EB` ring), labelled fields,
  inline validation, and focus moved to the page heading on navigation. Dialogs and sheets trap
  focus and return it to the control that opened them.
- The conversation is a polite live region. The urgent panel is announced once as an alert.
- Status is always an icon plus text, never colour alone. No gauges, probabilities, confetti or
  reward effects on results.
- Motion is 150–200ms and removed under `prefers-reduced-motion`.
- The summary has a print stylesheet; the demo label is part of the printed document.

## Known gaps

- **Date answers.** The specification mentions date/duration answers. The agreed
  `answer_schema` has `duration` but no date type, so only duration is implemented.
- **Mobile keyboard.** The composer is sticky with safe-area padding, and the banner and
  conversation header stop being sticky on very short viewports. This has been checked in
  desktop Chrome at phone sizes only, not on physical iOS or Android devices.
- **Screen readers and 200% zoom** have not been tested manually. Roles, names and focus
  behaviour are covered by automated checks only.
- **Real authentication, saved history, deletion status, condition information and review
  data** need backend support that does not exist yet (see above).
- **The HTTP adapter** is tested against a stubbed `fetch` and the OpenAPI types, not yet
  against the running FastAPI service.
