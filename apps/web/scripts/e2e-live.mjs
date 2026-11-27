// End-to-end browser test of the web app against the RUNNING FastAPI service (fixture mode).
// Unlike `pnpm smoke` (mock adapter), every step here goes through the real REST API.
//
// Usage:
//   backend:   uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000   (repo root)
//   frontend:  pnpm dev:api     (apps/web, port 5173: the one web port; stop `pnpm dev` first)
//   test:      pnpm e2e:live
//
// Environment:
//   E2E_BASE_URL  default http://localhost:5173
//   E2E_OUT_DIR   optional directory for screenshots
//   E2E_CHANNEL   Chrome channel for playwright-core, default "chrome"
//
// The backend's fixture vocabulary is deliberately nonmedical ("alpha", "beta", ...).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { chromium } from 'playwright-core';

const BASE = (process.env.E2E_BASE_URL ?? 'http://localhost:5173').replace(/\/+$/, '');
const OUT = process.env.E2E_OUT_DIR ?? null;
const CHANNEL = process.env.E2E_CHANNEL ?? 'chrome';
const ALLOWED_STORAGE_KEYS = ['feeltriva.ui.navCollapsed'];

if (OUT) mkdirSync(OUT, { recursive: true });

let passed = 0;
const failures = [];
function check(name, ok, detail = '') {
  if (ok) {
    passed += 1;
    console.log(`PASS  ${name}`);
  } else {
    failures.push(name);
    console.log(`FAIL  ${name}${detail ? `  — ${detail}` : ''}`);
  }
}

const browser = await chromium.launch({ channel: CHANNEL, headless: true });

async function newPage() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const problems = [];
  const api = [];
  // Each request is marked with the phase it was sent in, so that a check after a reload can count only what
  // the reloaded page sent: an answer to a request of the page before can still arrive afterwards.
  const phase = { now: 0 };
  const sentIn = new WeakMap();
  page.on('request', (request) => sentIn.set(request, phase.now));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console: ${m.text().slice(0, 200)}`);
  });
  page.on('pageerror', (e) => problems.push(`pageerror: ${String(e).slice(0, 200)}`));
  page.on('response', (r) => {
    const url = new URL(r.url());
    if (url.port === '8000') {
      api.push({
        method: r.request().method(),
        path: url.pathname.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/, ':id'),
        status: r.status(),
        idempotencyKey: r.request().headers()['idempotency-key'] ?? null,
        authorization: r.request().headers()['authorization'] ?? null,
        phase: sentIn.get(r.request()) ?? phase.now,
      });
    }
  });
  return { context, page, problems, api, phase };
}

const mainText = async (page) => (await page.locator('main').innerText()).replace(/\s+/g, ' ');
const shot = async (page, name) => {
  if (OUT) await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
};

async function startCheck(page, text, age = '34') {
  await page.goto(`${BASE}/start`);
  await page.getByRole('checkbox').first().check();
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('radio', { name: /I’m an adult/ }).check();
  await page.getByLabel('Age in years').fill(age);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.locator('textarea').first().fill(text);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.waitForURL(/\/assess\/[0-9a-f-]{36}$/, { timeout: 15000 });
}

/** The conversation has rendered once the first interpreted detail can be confirmed. */
async function waitForInterpretation(page) {
  await page
    .getByRole('button', { name: /^That’s right: / })
    .first()
    .waitFor({ timeout: 15000 });
}

async function answerCurrent(page, wording, act) {
  await page.getByRole('heading', { name: wording }).waitFor({ timeout: 15000 });
  await act();
  await page.getByRole('button', { name: 'Send answer' }).click();
}

// ----------------------------------------------------------------------------
// Flow 1: intake -> confirm -> four follow-ups -> provisional result -> evidence
//         -> correction -> stale -> refreshed result -> summary -> delete
// ----------------------------------------------------------------------------
{
  const { context, page, problems, api, phase } = await newPage();
  await startCheck(page, 'I have alpha');
  await waitForInterpretation(page);
  let text = await mainText(page);
  check('intake: the typed text is shown as the user’s message', text.includes('You said: I have alpha'));
  check('intake: extracted detail is listed and awaits confirmation', /alpha Please confirm/.test(text));
  check('intake: nothing the user did not mention is listed as not present', !/Not present.*beta/i.test(text));

  await page
    .getByRole('button', { name: /^That’s right: / })
    .first()
    .click();
  await page.getByText('You confirmed this').first().waitFor({ timeout: 15000 });
  check('confirm: detail is marked as confirmed by the user', true);

  await answerCurrent(page, /is fixture signal beta also present/, () =>
    page.getByRole('radio', { name: 'Yes' }).check(),
  );
  await answerCurrent(page, /best describes fixture signal gamma/, () =>
    page.getByRole('radio', { name: 'None of these' }).check(),
  );
  await answerCurrent(page, /fixture measurement delta/, () => page.getByRole('textbox', { name: 'Number' }).fill('5'));
  await answerCurrent(page, /how long has fixture signal alpha/, async () => {
    await page.getByRole('textbox', { name: 'How long' }).fill('3');
    await page.getByLabel('Unit of time').selectOption({ label: 'Days' });
  });
  await page.getByRole('heading', { name: /all the questions for now/ }).waitFor({ timeout: 15000 });
  text = await mainText(page);
  check('questions: asked one at a time and finished (yes/no, choice, number, duration)', true);
  check(
    'questions: the context question is not asked when the detail its rule names was not reported (M3.9)',
    !/context factor zeta/i.test(text),
  );
  check('questions: explicit "None of these" is recorded under Not present', /Not present .*signal gamma/i.test(text));
  // M3.14: what the service stored is shown in the person's words, and once.
  check(
    'questions: "None of these" is shown in its own words, not as the stored value (BUG-009)',
    /signal gamma \(sample\)\s+None of these/i.test(text) && !/signal gamma \(sample\)\s+none\b/.test(text),
    text.match(/signal gamma[^\n]*\n?[^\n]*/i)?.[0] ?? '',
  );
  check('questions: a duration is shown once (BUG-008)', text.includes('3 days') && !/3 days\s*·\s*3 days/.test(text));
  await shot(page, 'live-assess-complete');

  await page.getByRole('button', { name: 'See your next step' }).click();
  await page.waitForURL(/\/results\//, { timeout: 15000 });
  await page.getByRole('heading', { name: 'Possible explanations' }).waitFor({ timeout: 15000 });
  text = await mainText(page);
  const order = [
    'What to do next',
    'What we understood',
    'Possible explanations',
    'What is still uncertain',
    'Your consultation summary',
    'Sources',
  ].map((h) => text.indexOf(h));
  check(
    'result: sections are in the required order',
    order.every((v, i) => v >= 0 && (i === 0 || v > order[i - 1])),
    order.join(','),
  );
  check(
    'result: backend candidate is shown as a labelled possibility',
    text.includes('Illustrative possibility A') && text.includes('POSSIBLE EXPLANATION'),
  );
  check(
    'result: urgency "not assessed" is not presented as low urgency',
    text.includes('Urgency not assessed') && /does not mean your situation is low urgency/i.test(text),
  );
  check('result: backend next-step text is rendered verbatim', text.includes('Sample next step (synthetic fixture)'));
  check('result: no percentage or probability is shown', !/\d\s?%/.test(text) && !/probabilit/i.test(text));
  check('result: sample marker is visible', text.includes('Design demo · Sample result'));
  await shot(page, 'live-result');

  await page.getByRole('button', { name: 'View supporting information' }).click();
  const drawer = page.getByRole('dialog');
  await drawer.waitFor({ timeout: 10000 });
  check(
    'evidence: the citation returned by the API opens',
    (await drawer.innerText()).includes('Synthetic fixture source (sample)'),
  );
  await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'hidden', timeout: 10000 });

  // Correction: beta was wrong. The old result must become stale, then be recomputed.
  await page.getByRole('button', { name: 'Remove or correct: Fixture signal beta (sample)' }).click();
  const editor = page.getByRole('dialog');
  await editor.getByRole('radio', { name: /I don’t have this/ }).check();
  await editor.getByRole('button', { name: 'Save change' }).click();
  await page.getByText('This result needs updating').waitFor({ timeout: 15000 });
  text = await mainText(page);
  check('correction: earlier result is labelled as needing an update', text.includes('This result needs updating'));
  await shot(page, 'live-result-stale');
  await page.getByRole('button', { name: 'Update result' }).click();
  await page.getByText('This result needs updating').waitFor({ state: 'hidden', timeout: 15000 });
  text = await mainText(page);
  check(
    'correction: recomputed result no longer shows the possibility that depended on beta',
    !text.includes('Illustrative possibility A'),
  );
  check(
    'correction: incomplete result is not reassurance',
    /not a sign that everything is fine/i.test(text) && !/Routine/.test(text),
  );
  check('correction: beta now appears under Not present', /Not present .*signal beta/i.test(text));
  await shot(page, 'live-result-refreshed');

  check('flow 1: no console errors or page errors', problems.length === 0, problems.join(' | '));
  const mutations = api.filter((c) => c.method !== 'GET' && c.method !== 'OPTIONS');
  check(
    'api: every mutation carried an Idempotency-Key',
    mutations.length > 0 && mutations.every((c) => c.idempotencyKey),
    `${mutations.length} mutations`,
  );
  check(
    'api: idempotency keys are unique per operation',
    new Set(mutations.map((c) => c.idempotencyKey)).size === mutations.length,
  );
  const tokens = new Set(api.filter((c) => c.method !== 'OPTIONS').map((c) => c.authorization));
  check(
    'api: dev bearer token is used and stable for the page',
    tokens.size === 1 && /^Bearer dev:/.test([...tokens][0] ?? ''),
  );
  const bad = api.filter((c) => c.status >= 400);
  check(
    'api: no error responses in the normal flow',
    bad.length === 0,
    bad.map((c) => `${c.method} ${c.path} ${c.status}`).join(' | '),
  );
  check(
    'api: next-question 204 was received and treated as "no more questions"',
    api.some((c) => c.path.endsWith('/next-question') && c.status === 204),
  );

  // Reload: identity and session state live in memory only, so a reload must not bring the
  // conversation back. The API answers 404 for the new identity (same as "does not exist").
  phase.now += 1;
  await page.reload();
  await page.waitForTimeout(2500);
  text = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  const afterReload = api.filter((c) => c.phase === phase.now && c.method === 'GET');
  check(
    'reload: no health detail survives a page reload',
    !/signal beta|Illustrative possibility|alpha/i.test(text),
    text.slice(0, 160),
  );
  check(
    'reload: the API refuses the session to the new identity with 404',
    afterReload.some((c) => c.status === 404) && afterReload.every((c) => c.status === 404 || c.status === 204),
    afterReload.map((c) => `${c.path} ${c.status}`).join(' | '),
  );
  check(
    'reload: the page explains the session is unavailable and offers a restart',
    /start a new|new symptom check|couldn’t find|not available|has ended/i.test(text),
    text.slice(0, 260),
  );
  await shot(page, 'live-after-reload');
  await context.close();
}

// ----------------------------------------------------------------------------
// Flow 2: summary and deletion without leaving the page (state is in memory only)
// ----------------------------------------------------------------------------
{
  const { context, page, problems, api } = await newPage();
  await startCheck(page, 'I have alpha but no beta');
  await waitForInterpretation(page);
  let text = await mainText(page);
  check(
    'negation: "no beta" is listed under Not present, awaiting confirmation',
    /Not present .*beta Please confirm/.test(text),
  );
  for (let i = 0; i < 2; i += 1) {
    await page
      .getByRole('button', { name: /^That’s right: / })
      .first()
      .click();
    await page.waitForTimeout(700);
  }
  await page.getByRole('button', { name: 'Conversation options' }).click();
  await page.getByRole('menuitem', { name: 'Consultation summary' }).click();
  await page.waitForURL(/\/summary\//, { timeout: 15000 });
  await page.getByLabel('Consultation summary document').waitFor({ timeout: 15000 });
  text = await mainText(page);
  check('summary: text comes from the API and is marked as sample information', text.includes('SAMPLE INFORMATION'));
  check('summary: explicit negative is listed separately', /Explicitly not present.*beta/i.test(text));
  check('summary: states it is not a diagnosis', /not a diagnosis/i.test(text));
  await page.getByRole('button', { name: 'Print or save as PDF' }).click();
  check(
    'summary: export is blocked until the user confirms the review',
    (await mainText(page)).includes('Tick the box to confirm you’ve reviewed the summary first.'),
  );
  await page.getByRole('checkbox', { name: /I’ve reviewed this summary/ }).check();
  check(
    'summary: review acknowledgement can be given',
    await page.getByRole('checkbox', { name: /I’ve reviewed this summary/ }).isChecked(),
  );
  await shot(page, 'live-summary');

  await page.goBack();
  await page.waitForURL(/\/assess\//, { timeout: 15000 });
  await page.getByRole('button', { name: 'Conversation options' }).click();
  await page.getByRole('menuitem', { name: /Delete/ }).click();
  await page.getByRole('button', { name: 'Delete assessment' }).click();
  await page.getByText('Deletion scheduled').waitFor({ timeout: 15000 });
  text = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  check(
    'delete: receipt shows the status the API returned (scheduled, not completed)',
    text.includes('Deletion scheduled') && !text.includes('Deletion completed'),
  );
  check('delete: receipt id from the API is shown', /del_[0-9a-f]{8}/.test(text));
  await shot(page, 'live-delete-receipt');
  const del = api.find((c) => c.method === 'DELETE');
  check('delete: DELETE was sent and succeeded', del?.status === 200);

  const storage = await page.evaluate(() => ({
    local: Object.keys(localStorage),
    session: Object.keys(sessionStorage),
  }));
  check(
    'privacy: no health data in browser storage',
    storage.session.length === 0 && storage.local.every((k) => ALLOWED_STORAGE_KEYS.includes(k)),
    JSON.stringify(storage),
  );
  check('privacy: page title carries no symptom text', !/alpha|beta/i.test(await page.title()));
  await context.close();
  check('flow 2: no console errors or page errors', problems.length === 0, problems.join(' | '));
}

// ----------------------------------------------------------------------------
// Flow 3: urgent state comes from the API and stops routine questions
// ----------------------------------------------------------------------------
{
  const { context, page, problems } = await newPage();
  await startCheck(page, 'alpha and the escalation marker');
  await page.waitForTimeout(2500);
  const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ');
  check(
    'urgent: backend urgent text is shown',
    text.includes('Urgent-state preview (synthetic fixture)'),
    text.slice(0, 300),
  );
  check(
    'urgent: no follow-up question is asked',
    !text.includes('FOLLOW-UP QUESTION') && (await page.getByRole('button', { name: 'Send answer' }).count()) === 0,
  );
  check('urgent: no possible explanation is shown', !text.includes('POSSIBLE EXPLANATION'));
  check('urgent: no emergency number is invented by the client', !/\b(911|112|108|999)\b/.test(text));
  await shot(page, 'live-urgent');
  await context.close();
  check('flow 3: no console errors or page errors', problems.length === 0, problems.join(' | '));
}

// ----------------------------------------------------------------------------
// Flow 4: a question about clinically relevant context is asked only because the detail its
//         rule names was reported, and declining it is an answer (M3.9)
// ----------------------------------------------------------------------------
{
  const { context, page, problems } = await newPage();
  await startCheck(page, 'I have alpha and epsilon');
  await waitForInterpretation(page);
  // Two details were found in the text; each is confirmed before the questions start.
  for (let done = 0; done < 2; done += 1) {
    await page
      .getByRole('button', { name: /^That’s right: / })
      .first()
      .click();
    await page.getByText('You confirmed this').nth(done).waitFor({ timeout: 15000 });
  }
  await answerCurrent(page, /is fixture signal beta also present/, () =>
    page.getByRole('radio', { name: 'Yes' }).check(),
  );
  await answerCurrent(page, /best describes fixture signal gamma/, () =>
    page.getByRole('radio', { name: 'None of these' }).check(),
  );
  await page
    .getByRole('heading', { name: /does fixture context factor zeta apply to you/ })
    .waitFor({ timeout: 15000 });
  check('context: the question is asked once the detail its rule names was reported', true);
  check(
    'context: "Prefer not to answer" is offered beside yes, no and not sure, and nothing is chosen',
    (await page.getByRole('radio', { name: 'Prefer not to answer' }).count()) === 1 &&
      (await page.getByRole('radio', { checked: true }).count()) === 0,
  );
  await page.getByRole('radio', { name: 'Prefer not to answer' }).check();
  await page.getByRole('button', { name: 'Send answer' }).click();
  await page.getByRole('heading', { name: /fixture measurement delta/ }).waitFor({ timeout: 15000 });
  const text = await mainText(page);
  check(
    'context: declining is accepted, shown as the answer, and the conversation goes on',
    text.includes('Prefer not to answer') && !/context factor zeta[^.]*Not present/i.test(text),
  );
  await shot(page, 'live-context');
  await context.close();
  check('flow 4: no console errors or page errors', problems.length === 0, problems.join(' | '));
}

// ----------------------------------------------------------------------------
// Flow 5: the terms come from the API and are agreed to before anything starts; the choice
// about improving the product is a separate box that is never ticked for the person (M3.16)
// ----------------------------------------------------------------------------
{
  const { context, page, problems, api } = await newPage();
  await page.goto(`${BASE}/start`);
  await page.getByRole('heading', { level: 2, name: 'Before you start' }).waitFor({ timeout: 15000 });
  const text = await mainText(page);
  check(
    'terms: the text of the service is shown, with how long a conversation is kept and how to take the agreement back',
    api.some((call) => call.method === 'GET' && call.path === '/v1/consent' && call.status === 200) &&
      text.includes('We keep a conversation for 30 days and then delete it') &&
      text.includes('Taking back your agreement') &&
      text.includes('These terms are a draft'),
  );
  const agree = page.getByRole('checkbox', { name: /I have read this and agree/ });
  const improve = page.getByRole('checkbox', { name: /You may also use my conversation/ });
  check('terms: neither box is ticked for the person', !(await agree.isChecked()) && !(await improve.isChecked()));
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByText('Tick the box to confirm you’ve read this').waitFor({ timeout: 5000 });
  check(
    'terms: there is no step further without the agreement, and nothing was started',
    !api.some((call) => call.method === 'POST'),
  );
  await agree.check();
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('radio', { name: /I’m an adult/ }).check();
  await page.getByLabel('Age in years').fill('34');
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.locator('textarea').first().fill('alpha for a while');
  const starting = page.waitForResponse(
    (response) => response.request().method() === 'POST' && new URL(response.url()).pathname === '/v1/sessions',
  );
  await page.getByRole('button', { name: 'Continue' }).click();
  const response = await starting;
  const sent = response.request().postDataJSON();
  const session = await response.json();
  check(
    'terms: the session starts with the version that was shown, the time of the agreement and the separate choice as "no"',
    response.status() === 201 &&
      sent.consent_version === session.consent_version &&
      sent.training_consent === false &&
      session.training_consent === false &&
      !Number.isNaN(Date.parse(session.consent_accepted_at)),
  );
  await page.waitForURL(/\/assess\/[0-9a-f-]{36}$/, { timeout: 15000 });
  await context.close();
  check('flow 5: no console errors or page errors', problems.length === 0, problems.join(' | '));
}

await browser.close();
console.log(`\n${passed} passed, ${failures.length} failed (${passed + failures.length} checks)`);
if (failures.length > 0) {
  for (const name of failures) console.log(`  FAILED: ${name}`);
  process.exit(1);
}
