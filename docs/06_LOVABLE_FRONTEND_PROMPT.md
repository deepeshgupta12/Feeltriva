# Feeltriva — detailed Lovable frontend design prompt

Paste everything between START PROMPT and END PROMPT into Lovable. Attach `specs/openapi.json` and the product specification if the interface allows it. This prompt is self-contained for the design prototype. Build the frontend first; Claude will implement the backend from the companion handoff.

## START PROMPT

Build a polished, responsive, interactive frontend for **Feeltriva**, a conversational symptom-assessment and care-navigation product.

Tagline: **Understand your symptoms. Know your next step.**

The main user arrives thinking, “I don't feel well, and I don't know what details matter or what to do next.” Feeltriva helps them describe symptoms, review what the system understood, answer relevant follow-ups and understand a provisional next step. It also produces a useful consultation summary. The design must communicate care, clarity and uncertainty without creating fear or implying a confirmed diagnosis.

Create the full application experience described below, with working interactions and reusable components. Use your currently supported React + TypeScript project template. Keep its native router/build setup. Use Tailwind and accessible components where supported. Do not force a framework migration. This frontend will eventually consume an external FastAPI REST API. Build a typed mock service adapter now, with a clean replacement boundary for the real API.

### 1. Product and prototype boundaries

The first delivery is an **interactive design demo**. Keep a discreet but persistent banner: “Design demo · Sample scenarios · Not a medical assessment.” Place the same demo label on exports and result previews. Ask users to try the sample scenario rather than entering private health information into a shared preview.

Keep clinical mode disabled. Do not connect a general-purpose AI model to generate diagnoses or clinical advice. Do not build a symptom-to-disease ruleset in the frontend. A demo scenario selector may change UI states deterministically; typed symptoms must not secretly produce medical predictions.

The production service will provide approved questions, urgency, possible explanations, evidence and next actions. The frontend renders and validates these responses. It does not calculate disease probabilities, triage, treatment eligibility or question priorities.

Use plain patient-facing language. Technical terms such as MCP, RAG, embeddings, model confidence, vector database and dataset IDs belong in internal development/review views only.

### 2. Visual direction and design tokens

Create a calm, contemporary health product with generous spacing, clear typography and compact useful information. Emphasize the conversation and the next action. Use a light theme for v1.

| Token | Value / usage |
|---|---|
| Page background | `#F5F8F7` |
| Surface | `#FFFFFF` |
| Primary ink | `#17352F` |
| Secondary text | `#526760` |
| Muted supporting text | `#64736D`; verify contrast at actual size |
| Primary action | `#087F74`; white text; darker hover `#06685F` |
| Soft teal surface | `#E8F4F0` |
| Border | `#D9E4DF` |
| Focus ring | `#2563EB` with visible offset |
| Informational | `#245F9E` on `#EFF6FD` |
| Attention | `#8A4A0A` on `#FFF6E5` |
| Urgent/error | `#A62B32` on `#FFF0F0` |

Use Manrope for headings and Inter for body if available, with sensible system fallbacks. Body 16px/1.55, small supporting text 14px minimum, headings 24–36px inside the app. Landing hero may use 48–56px desktop and 34–40px mobile. Avoid tiny medical/legal text.

Spacing follows an 8px system with 4px for small adjustments. Cards use 16–20px radius and a subtle border; fields/buttons 10–12px. Use restrained shadows only for floating layers. Use line icons consistently, with accessible labels where needed. A simple wordmark and abstract two-part conversation/leaf mark can establish the identity. Avoid implying certification through medical seals or badges.

Primary buttons are 48px high. Interactive targets are at least 44×44px. Use a clear primary action per section. Status must have a text label and icon as well as colour. Teal is the brand colour, not proof a medical situation is safe. Keep motions short, approximately 150–200ms, and respect reduced motion.

### 3. Information architecture and routes

| Route | Purpose |
|---|---|
| `/` | Product introduction with a direct start action |
| `/start` | Intended use, consent and basic context |
| `/assess/:sessionId` | Conversation, follow-up questions and editable observations |
| `/results/:sessionId` | Provisional results, uncertainty and next step |
| `/summary/:sessionId` | Consultation summary preview and export |
| `/history` | Optional saved assessment history |
| `/conditions/:diseaseId` | Reviewed condition information opened from evidence/results |
| `/settings/privacy` | Data/history preferences, deletion and privacy details |
| `/review` | Internal reviewer workspace, separate navigation and role |
| `/review/data` | Internal dataset/mapping inventory and conflicts |

In the design demo, expose review screens through a labelled “Reviewer preview” switch in the demo toolbar. This is not real authorization. Document that production requires backend roles and route protection. Never present a hidden navigation item as a security control.

### 4. Public introduction screen

Build a focused landing page whose first fold helps someone start.

- Header: Feeltriva wordmark, “How it works”, “About your data”, and “Start symptom check”. On mobile use a compact menu.
- Hero headline: “Tell us how you're feeling.”
- Supporting copy: “Organize your symptoms, answer useful questions and prepare for the next step.”
- Primary CTA: “Try a sample assessment”. In production this becomes “Start symptom check” only after clinical mode is approved.
- Secondary link: “See how it works”.
- Right side on desktop: a refined sample conversation card with “What have you been feeling?”, an example input, and an editable observation chip. Label it “Example conversation”. Stack it below the introduction on mobile.
- Three short steps below: “Describe what you feel”, “Clarify the important details”, “Review your next step”.
- Explain the output in a concise section: symptom summary, provisional explanations when supported, and consultation-ready notes.
- A short intended-use statement: “Feeltriva does not confirm a diagnosis. A health professional may need to examine you or arrange tests.”
- Footer: About, Privacy, Terms and Contact placeholders that open real informational pages/modals with clearly marked draft content.

Do not invent testimonials, physician endorsements, hospital logos, user counts, accuracy percentages, compliance certification or claims that the service detects every disease. The measured research baseline is internal evaluation material, not a marketing statistic.

### 5. Start and consent screen

Use a centred card, maximum 640px, with a simple three-part progress label: “About this check”, “A little context”, “Your symptoms”. This indicates completed steps, not a clinical completion percentage.

Step 1 explains intended use and data handling in short paragraphs. Provide an unchecked acknowledgement control and a link to privacy details. Do not bundle training consent into use consent. In demo mode explain that sample scenarios reset and no real account is created.

Step 2 asks:

- Age in years, with an explicit “Prefer not to answer” option. Do not default to a guessed age.
- Optional gender identity with inclusive options and self-description. Explain that clinically relevant sex-related information may be asked later when applicable. Do not infer anatomy or pregnancy from gender.
- Initial scope is adult self-assessment. Show an unsupported-scope state for caregiver/minor flows rather than silently treating them as adults. Clinical eligibility comes from the backend.

Step 3 provides a large textarea labelled “What have you been feeling?” Placeholder: “Describe what feels different, when it started, and anything that makes it better or worse.”

Offer sample input chips such as “Try an example conversation”; clicking loads a labelled demo. Do not automatically submit a symptom because a user focuses or selects a chip. Show input validation inline, keep entered text on a recoverable error, and support back navigation.

### 6. Main conversation workspace — the primary product screen

At desktop widths of 1280px and above, create three regions:

1. A 224px left navigation with “New symptom check”, “This conversation”, “Saved summaries” and “Privacy”.
2. A flexible central conversation area with a comfortable text measure, approximately 560–760px.
3. A 300–320px context rail titled “What you've shared”.

Use a maximum content width around 1440px and 24–32px outer spacing. The central column must remain usable as the viewport narrows. At tablet widths, collapse navigation and move the context rail into a drawer. On mobile, show one column with a compact header, a “Your details” button and an accessible sheet for the context. Keep the composer visible above the mobile keyboard without covering messages or action buttons.

Conversation header: title, current state label, and a menu for summary, restart and delete. Avoid showing a real person's name in the prototype.

Assistant messages use white cards with small brand icon and readable text. User messages use a soft teal surface. Keep long text wrapped. Do not show chain-of-thought or simulated medical reasoning. A temporary label such as “Preparing the next question…” is sufficient.

Composer: multiline textarea, send action, Enter to send and Shift+Enter for newline on desktop. Keep mobile behaviour predictable. Include a text alternative for icon buttons. Do not add a microphone or attachment action in v1 unless implemented and scoped; voice and medical document analysis are future capabilities.

Show one follow-up question at a time. Support yes/no/not-sure, single choice, multiple choice, number with unit, date/duration and free-text answers. Choices must not be preselected. Include “I'm not sure” when the question schema allows it. A small “Why this question?” disclosure displays backend-provided explanatory copy. Do not invent clinical reasoning in this disclosure.

The context rail contains grouped, editable observations: “Reported”, “Not present”, and “Needs clarification”. “Not present” appears only after explicit denial; silence is unknown. Each row can show feature wording, onset/duration and confirmation status. Unconfirmed interpretations display “Please confirm”. Actions: “That's right”, “Edit” and “Remove/correct”. Do not use a green tick to imply a confirmed diagnosis.

The user can correct an earlier answer. Show a brief revision notice, invalidate the previous assessment and request a new backend result. If a server returns an observation-version conflict, show “Your details changed. Refreshing this assessment…” and refresh the authoritative state. Never silently attach an old answer to a new question.

### 7. Results screen and content hierarchy

The order is essential:

1. **What to do next** — backend-provided action and urgency, with a clear primary action.
2. **What we understood** — a concise editable summary of confirmed observations and relevant context.
3. **Possible explanations** — zero to three cards only when supported by the backend.
4. **What is still uncertain** — missing information, scope limits and follow-up considerations.
5. **Your consultation summary** — preview/export action.
6. **Sources** — accessible, expandable source details.

A possibility card includes name, brief explanation, “Details that fit”, “Details that need clarification” and “View supporting information”. Do not show numerical disease probabilities, ranking progress bars or “You have X”. The card heading should read “Possible explanation”, not “Diagnosis confirmed”.

Use neutral, visibly fictional labels such as “Illustrative possibility A” in prototype result cards, with a prominent sample marker. Do not build a realistic-looking unverified disease recommendation for typed user input. Production cards use approved backend content and citations.

Sources open in a right drawer on desktop and bottom sheet/full screen on mobile. Display title, excerpt, source URL when supplied and the knowledge-release context in internal detail only. External links need an accessible label and safe link behaviour. A citation must actually exist in the response; do not decorate generated content with invented reference numbers.

The “Add or correct details” action returns to the conversation while preserving context. A result rendered for an old observation version displays “This result needs updating” and its action buttons cannot imply it remains current.

### 8. Urgent, incomplete and unsupported states

Implement each as a first-class design state selectable from the demo toolbar:

| State | Required UI |
|---|---|
| Urgent handoff | Full-width high-priority panel; clear action first; pause routine questioning; no diagnosis cards or celebratory effects |
| Insufficient information | Explain what is missing; offer the next approved question or a summary; never show a normal/low-risk badge |
| Out of scope | Clear limitation and backend-provided navigation; preserve summary access where appropriate |
| Backend/provider unavailable | “We couldn't complete this assessment”; retry and summary options; retain recoverable input; no fallback medical guess |
| Offline | Distinguish unsent text from saved observations; reconnect action; no “assessment complete” state |
| Session expired | Explain that the session ended; safe restart and reauthentication where needed |
| Version conflict | Refresh authoritative state; retain unsent draft; require resubmission against the new question/version |
| No evidence available | Withhold unsupported explanation; show an incomplete result |
| Empty history | Useful explanation and “Start a sample assessment” |
| Deletion pending/completed | Accurate receipt status; do not claim completed deletion while still queued |

In the urgent demo, say “Urgent-state preview” and use generic placeholder action text identified as a sample. Actual emergency instructions, contact numbers and location-dependent services must come from approved backend content. Do not hardcode a country emergency number or pretend a call was placed.

### 9. Consultation summary

Create a clean, print-friendly page with date, reported symptoms, explicit relevant negatives, timing/context, confirmed answers, unresolved questions and backend-provided next step. Separate user-reported information from provisional explanations. Include an “Edit details” action and a user-review acknowledgement before export.

Implement print/save-as-PDF using the browser print flow and a working copy-text action after explicit user click. The document header/footer must say “Design demo · Sample information” in prototype mode. Do not auto-email, auto-share or create a public health-data URL. A share button can open a preview/options modal; unavailable integrations should be labelled clearly rather than faking delivery.

Do not put private symptoms into the page title, URL query string, analytics event or public Open Graph metadata. Private routes need noindex and must not render sensitive data before authorization in production.

### 10. History and privacy screens

History is optional. In the demo, use in-memory sample sessions and a clear reset control. Cards show date, user-selected title, completed/incomplete status and available summary. Avoid presenting a previous provisional explanation as a confirmed medical history item.

Privacy settings include saved-history preference, explanation of current retention, export preview and delete controls. Display draft-policy status until real policies are supplied. Training consent is separate, off by default and has no effect in the demo. Do not promise immediate removal from all backups.

Keep live health information out of localStorage, sessionStorage, IndexedDB, service-worker caches and persistent client query caches. In-memory prototype state should reset on reload. Persist only non-sensitive preferences such as whether the navigation is collapsed. Production history comes from the authenticated backend.

### 11. Condition information view

This is a reviewed information page reached from a result/source link. Layout: condition name, plain-language overview, symptoms, causes/risk context, management information, questions to ask a clinician and sources. Hide sections when no reviewed content exists. Do not fill missing clinical text with generated guesses.

Treatment content is educational and source-linked. Do not add personalized dosing, a cure promise, an “order medicine” CTA or a paid referral that changes the assessment. The prototype may show clearly labelled placeholders for these sections.

### 12. Internal reviewer console

Use a denser layout with separate navigation: Overview, Disease mappings, Feature mappings, Evidence, Questions/rules, Releases and Data quality. Keep it visually related to the consumer app but clearly labelled “Internal review”.

Overview cards can show these actual audit facts with “Imported dataset audit” labels: six source archives, 960 lexical disease candidates, 37 repeated header names requiring review, and 27,622 shared archive-15 train/test profile signatures. Do not describe these as clinically approved conditions or unique patients.

Mapping table columns: source, original term, proposed canonical term, mapping method, review status, conflicts, last reviewed. Support search, status filter, detail drawer and reviewer notes. Preserve source term and column position. Review actions operate only on mock state and show “Demo change”; they do not approve medical content for live serving.

Evidence detail shows original statement, source URL/locator, proposed atomic claim, applicability, status and reviewer notes. Release view shows version, included sources/mappings/rules, pending items and a disabled publication control with a reason until real permissions/approval exist.

Do not invent live clinical metrics. If adding a model-evaluation tab, use only the supplied measured archive-11 values with an explicit research-only label: test accuracy 15.71%, majority comparator 20.56%, top-3 accuracy 39.67%, 39/46 test labels represented. State “Baseline rejected for clinical serving.” Empty clinical-validation fields should say “Not evaluated”, not 0%.

### 13. Components and state architecture

Create reusable components for: AppShell, DemoBanner, ConversationHeader, MessageCard, Composer, FollowUpQuestion, AnswerOptions, ObservationChip, ObservationEditor, ContextPanel, NextActionCard, PossibilityCard, UncertaintyPanel, EvidenceDrawer, SummaryPreview, HistoryCard, StatusPanel, ConfirmDialog, ReviewTable and ReleaseBadge.

Use a typed state model with consent_pending, intake, clarifying, assessing, result_ready, urgent_handoff, out_of_scope, insufficient_information, system_unavailable and closed. Keep UI state separate from server assessment state. A loading animation must never change clinical status.

Create a typed AssessmentService interface with startSession, getSession, submitObservations, submitAnswer, assessSession, getNextQuestion, createSummary and deleteSession. Provide mock and HTTP implementations. Mock fixtures live separately from UI components. Do not scatter simulated diagnoses or API calls across components.

If the supplied OpenAPI is available, generate/use its types. Expected REST operations:

- POST `/v1/sessions`
- GET/DELETE `/v1/sessions/{session_id}`
- POST `/v1/sessions/{session_id}/observations`
- POST `/v1/sessions/{session_id}/answers`
- POST `/v1/sessions/{session_id}/assessments`
- GET `/v1/sessions/{session_id}/next-question?observation_version=...`
- POST `/v1/sessions/{session_id}/summary`

Mutations include an Idempotency-Key. Observation-dependent requests include observation_version. HTTP 204 on next-question means no question, not an error. Handle 401/403, 409, 422, 429 and 503 explicitly. On retries reuse the key for the same payload; generate a new key for a new operation. Suppress duplicate submits while pending.

Runtime secrets and AI credentials stay server-side. Browser build configuration contains public values only. Do not create an alternative medical backend or automatically enable Lovable AI/Cloud for diagnosis. A narrow server adapter for secure API access may be added during integration; the FastAPI service remains the authority for assessments. Do not treat a Lovable builder MCP connector as the published product's MCP server.

### 14. Responsive, accessible and interaction requirements

Test at 390px mobile, 768px tablet and 1440px desktop; also verify 320px minimum without horizontal page overflow. Support 200% zoom, keyboard navigation and screen-reader names. Use real labels, headings, landmarks, visible focus and inline validation. Dialogs/sheets trap focus correctly and restore it on close. Announce new assistant responses politely; announce urgent states promptly without repeatedly interrupting the screen reader.

Use skeletons for structural loading and clear text for submission progress. Respect reduced motion. Keep mobile sticky controls clear of safe-area insets and the keyboard. Dates, long labels and error messages must wrap. Empty, loading, error, success, stale and permission-denied states must have intentional layouts.

Any charts appear only in internal review screens and include titles, units and textual equivalents. Patient-facing results do not use gauges that imply diagnostic confidence. Do not use decorative animation, confetti or reward streaks for medical results.

### 15. Demo scenarios and acceptance checklist

Provide a development-only scenario switcher, visually separate from the patient workflow, for:

1. Normal sample intake → confirm observations → follow-up → provisional sample result → summary.
2. Correct an earlier answer → old result becomes stale → refreshed result.
3. Urgent-state preview → routine questioning stops.
4. Insufficient information → uncertainty and a follow-up.
5. Unsupported scope → appropriate limitation screen.
6. Backend unavailable and offline → recoverable UI, no result invented.
7. Empty history → create sample → preview → delete → receipt.
8. Evidence missing → candidate explanation withheld.
9. Concurrent update/version conflict → refresh and resubmit.
10. Internal reviewer → inspect duplicate column → save demo note.

Before finishing, click through these flows, check all navigation and primary actions, and verify mobile sheets, validation, focus and print output. Run available type checks and UI tests. Fix console errors and broken layouts. Keep all sample clinical content visibly labelled.

Deliver the full frontend, reusable design tokens/components, mock data/service layer, HTTP integration boundary and a short README explaining routes, scenarios, run commands, frontend stack and how Claude should connect the backend. Do not claim the prototype is clinically validated or production-ready. Keep the product name and interface consistent throughout.

## END PROMPT

## Suggested refinement prompt after the first build

Review the implemented Feeltriva frontend against the original specification. Prioritize the assessment screen, editable observations, urgent/incomplete states, result hierarchy and mobile keyboard behaviour. Verify that every visible action works or explains its unavailable state. Preserve the visual identity and service contracts. Fix accessibility, responsive overflow, stale-result handling and demo-content labelling. Report the files changed and the flows tested; do not add new clinical logic.

## Claude integration instruction

Preserve the Lovable-generated UI and supported project framework. Implement the AssessmentService HTTP adapter against specs/openapi.json, replace mock sessions with authenticated backend sessions, and enforce all clinical permissions/versions on the server. Keep mock mode available for tests. Do not reproduce symptom ranking or urgency logic in the browser. Preserve explicit demo/prod boundaries and keep live private data out of persistent browser storage and analytics.
