// Browser smoke test for the Feeltriva demo. Drives a real Chrome through the routes and the
// demo scenarios and fails on console errors, page errors, broken flows or horizontal overflow.
//
// Usage (dev server must already be running in mock mode):
//   pnpm dev            # terminal 1
//   pnpm smoke          # terminal 2
//
// Environment:
//   SMOKE_BASE_URL  default http://localhost:5173
//   SMOKE_OUT_DIR   optional directory for screenshots and the printed summary PDF
//   SMOKE_CHANNEL   Chrome channel for playwright-core, default "chrome" (uses the installed browser)
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { chromium } from 'playwright-core';

const BASE = (process.env.SMOKE_BASE_URL ?? 'http://localhost:5173').replace(/\/+$/, '');
const OUT = process.env.SMOKE_OUT_DIR ?? null;
const CHANNEL = process.env.SMOKE_CHANNEL ?? 'chrome';
const ALLOWED_STORAGE_KEYS = ['feeltriva.ui.navCollapsed'];
const VIEWPORTS = {
  w320: { width: 320, height: 640 },
  w390: { width: 390, height: 844 },
  w768: { width: 768, height: 1024 },
  w1440: { width: 1440, height: 900 },
};

if (OUT) {
  mkdirSync(OUT, { recursive: true });
}

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  — ${detail}` : ''}`);
}

async function shot(page, name) {
  if (OUT) {
    await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
  }
}

/** Runs one flow in a fresh browser context (fresh page load = fresh in-memory state). */
async function flow(browser, name, viewport, run) {
  const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
  await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: BASE });
  const page = await context.newPage();
  page.setDefaultTimeout(10_000);
  const problems = [];
  page.on('console', (message) => {
    if (message.type() === 'error') problems.push(`console.error: ${message.text()}`);
    if (message.type() === 'warning' && /react|radix|aria/i.test(message.text()))
      problems.push(`console.warn: ${message.text()}`);
  });
  page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`));
  page.on('requestfailed', (request) => problems.push(`requestfailed: ${request.url()}`));
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.origin !== BASE) problems.push(`external request: ${request.url()}`);
  });
  try {
    await run(page);
    check(`${name}: completed`, true);
  } catch (error) {
    check(`${name}: completed`, false, String(error).split('\n').slice(0, 4).join(' | '));
    await shot(page, `FAILED-${name.replace(/[^a-z0-9]+/gi, '-')}`);
  }
  check(
    `${name}: no console errors, page errors or external requests`,
    problems.length === 0,
    problems.slice(0, 5).join(' || '),
  );
  await context.close();
}

async function noOverflow(page, label) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check(`${label}: no horizontal page overflow`, overflow <= 1, `overflow ${overflow}px`);
}

async function loadScenario(page, title) {
  await page.getByRole('button', { name: 'Demo tools' }).click();
  await page
    .getByRole('dialog', { name: 'Demo tools' })
    .getByRole('button', { name: new RegExp(title) })
    .click();
  await page.getByRole('dialog', { name: 'Demo tools' }).waitFor({ state: 'hidden' });
}

async function expectVisible(page, locator, label) {
  await locator.first().waitFor({ state: 'visible', timeout: 8000 });
  check(label, true);
}

async function expectAbsent(page, locator, label) {
  check(label, (await locator.count()) === 0);
}

const isWide = (page) => (page.viewportSize()?.width ?? 0) >= 1280;

/** Opens "What you've shared" (a sheet below 1280px, a rail above) and returns its locator. */
async function openDetails(page) {
  if (isWide(page)) {
    return { panel: page.getByRole('complementary', { name: 'What you’ve shared' }), close: async () => {} };
  }
  await page.getByRole('button', { name: /Your details/ }).click();
  const panel = page.getByRole('dialog', { name: 'What you’ve shared' });
  await panel.waitFor({ state: 'visible' });
  return {
    panel,
    close: async () => {
      await page.keyboard.press('Escape');
      await panel.waitFor({ state: 'hidden' });
    },
  };
}

async function startToAssess(page) {
  await page.goto(`${BASE}/`);
  await page.getByRole('link', { name: 'Try a sample assessment' }).click();
  await page.waitForURL('**/start');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expectVisible(
    page,
    page.getByText('Tick the box to confirm you’ve read this'),
    'start: acknowledgement is required (inline validation)',
  );
  check(
    'start: acknowledgement is unchecked by default',
    !(await page.getByRole('checkbox', { name: /I understand/ }).isChecked()),
  );
  await page.getByRole('checkbox', { name: /I understand/ }).check();
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.getByRole('heading', { level: 1, name: 'A little context' }).waitFor();
  check(
    'start: no "who is this for" option is preselected',
    (await page.getByRole('radio', { checked: true }).count()) === 0,
  );
  check('start: age is not prefilled', (await page.getByLabel('Age in years').inputValue()) === '');
  await page.getByRole('radio', { name: /Someone else/ }).check();
  await expectVisible(
    page,
    page.getByText('This check isn’t available for this situation yet'),
    'start: unsupported-scope state for caregiver flow',
  );
  await expectAbsent(
    page,
    page.getByRole('button', { name: 'Continue' }),
    'start: cannot continue in unsupported scope',
  );
  await page.getByRole('radio', { name: /Me, and I’m an adult/ }).check();
  await page.getByRole('button', { name: 'Continue' }).click();
  await expectVisible(page, page.getByText('Enter your age in years, or choose'), 'start: age validation shown inline');
  await page.getByRole('checkbox', { name: 'Prefer not to answer' }).check();
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.getByRole('heading', { level: 1, name: 'Your symptoms' }).waitFor();
  await page.getByRole('button', { name: 'Back' }).click();
  await page.getByRole('heading', { level: 1, name: 'A little context' }).waitFor();
  check(
    'start: back navigation keeps answers',
    await page.getByRole('radio', { name: /Me, and I’m an adult/ }).isChecked(),
  );
  await page.getByRole('button', { name: 'Continue' }).click();

  await page.getByRole('button', { name: 'Continue' }).click();
  await expectVisible(
    page,
    page.getByText('Describe what you’ve been feeling, or load the example'),
    'start: empty description is rejected inline',
  );
  await page.getByRole('button', { name: 'Try an example conversation' }).click();
  check('start: example chip loads text without submitting', page.url().endsWith('/start'));
  const loaded = await page.getByLabel('What have you been feeling?').inputValue();
  check('start: loaded example is labelled sample text', loaded.startsWith('Sample entry'));
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.waitForURL('**/assess/**');
}

async function answerStandardQuestions(page) {
  const send = page.getByRole('button', { name: 'Send answer' });

  await page.getByRole('heading', { name: /have you also noticed sample symptom C/ }).waitFor();
  check('question: nothing preselected', (await page.getByRole('radio', { checked: true }).count()) === 0);
  await send.click();
  await expectVisible(
    page,
    page.getByText('Choose an answer to continue.'),
    'question: selecting is required before sending',
  );
  await page
    .getByRole('button', { name: /Why this question/ })
    .or(page.getByText('Why this question?'))
    .first()
    .click();
  await expectVisible(
    page,
    page.getByText(/Sample explanation\. In the live service/),
    'question: "Why this question?" shows backend-provided copy',
  );
  await page.getByRole('radio', { name: 'No', exact: true }).check();
  await send.click();

  await page.getByRole('heading', { name: /how long have you had sample symptom A/ }).waitFor();
  await page.getByRole('textbox', { name: 'How long', exact: true }).fill('3');
  await page.getByLabel('Unit of time').selectOption('days');
  await send.click();

  await page.getByRole('heading', { name: /how much does sample symptom B affect your day/ }).waitFor();
  await expectVisible(
    page,
    page.getByRole('radio', { name: 'I’m not sure' }),
    'question: "I’m not sure" offered when the schema allows it',
  );
  await expectAbsent(
    page,
    page.getByText('Why this question?'),
    'question: disclosure hidden when no help text is supplied',
  );
  await page.getByRole('radio', { name: 'A moderate amount' }).check();
  await send.click();

  await page.getByRole('heading', { name: /which of these sample situations apply/ }).waitFor();
  await page.getByRole('checkbox', { name: 'Sample situation 1' }).check();
  await page.getByRole('checkbox', { name: 'Sample situation 3' }).check();
  await send.click();

  await page.getByRole('heading', { name: 'That’s all the questions for now' }).waitFor();
}

async function normalFlow(page, tag) {
  await startToAssess(page);
  await page.getByRole('heading', { name: /have you also noticed sample symptom C/ }).waitFor();
  await noOverflow(page, `${tag} assess`);
  await shot(page, `${tag}-assess`);

  // Confirm an unconfirmed interpretation from the context panel.
  const details = await openDetails(page);
  await expectVisible(
    page,
    details.panel.getByText('Please confirm'),
    `${tag}: unconfirmed details show "Please confirm"`,
  );
  await expectAbsent(
    page,
    details.panel.getByRole('heading', { name: 'Not present' }),
    `${tag}: "Not present" hidden before any explicit denial`,
  );
  await shot(page, `${tag}-details`);
  await details.panel.getByRole('button', { name: 'That’s right: Sample symptom A' }).click();
  await details.panel.getByText('You confirmed this').first().waitFor();
  await details.close();

  await answerStandardQuestions(page);
  const after = await openDetails(page);
  await expectVisible(
    page,
    after.panel.getByRole('heading', { name: 'Not present' }),
    `${tag}: "Not present" appears after an explicit "No"`,
  );
  await after.close();

  await page.getByRole('button', { name: 'See your next step' }).click();
  await page.waitForURL('**/results/**');
  await page.getByRole('heading', { level: 2, name: 'What to do next' }).waitFor();
  const headings = await page.getByRole('main').getByRole('heading', { level: 2 }).allTextContents();
  const expected = [
    'What to do next',
    'What we understood',
    'Possible explanations',
    'What is still uncertain',
    'Your consultation summary',
    'Sources',
  ];
  check(`${tag}: results hierarchy order`, JSON.stringify(headings) === JSON.stringify(expected), headings.join(' > '));
  await expectVisible(
    page,
    page.getByRole('heading', { name: 'Illustrative possibility A' }),
    `${tag}: illustrative possibility card shown`,
  );
  const bodyText = await page.getByRole('main').innerText();
  check(`${tag}: no percentages or "You have" in results`, !/%|You have /.test(bodyText));
  await noOverflow(page, `${tag} results`);
  await shot(page, `${tag}-results`);

  await page.getByRole('button', { name: 'View supporting information for Illustrative possibility A' }).click();
  const drawer = page.getByRole('dialog', { name: 'Supporting information' });
  await drawer.waitFor();
  await expectVisible(
    page,
    drawer.getByRole('link', { name: /Open source.*opens in a new tab/ }),
    `${tag}: source link has an accessible label`,
  );
  const rel = await drawer
    .getByRole('link', { name: /Open source/ })
    .first()
    .getAttribute('rel');
  check(`${tag}: external link uses noopener noreferrer`, rel === 'noopener noreferrer', String(rel));
  await shot(page, `${tag}-evidence`);
  await page.keyboard.press('Escape');
  await drawer.waitFor({ state: 'hidden' });
  const focused = await page.evaluate(
    () => document.activeElement?.getAttribute('aria-label') ?? document.activeElement?.textContent ?? '',
  );
  check(
    `${tag}: focus returns to the trigger after closing the drawer`,
    /View supporting information/.test(focused),
    focused,
  );

  await page.getByRole('link', { name: 'Prepare consultation summary' }).click();
  await page.waitForURL('**/summary/**');
  await page.getByRole('heading', { name: 'Reported symptoms' }).waitFor();
  check(
    `${tag}: page title contains no symptom text`,
    (await page.title()) === 'Consultation summary · Feeltriva',
    await page.title(),
  );
  check(`${tag}: URL has no query string`, new URL(page.url()).search === '');
  await page.getByRole('button', { name: 'Copy text' }).click();
  await expectVisible(
    page,
    page.getByText('Tick the box to confirm you’ve reviewed the summary first.'),
    `${tag}: export requires the review acknowledgement`,
  );
  await page.getByRole('checkbox', { name: /I’ve reviewed this summary/ }).check();
  await page.getByRole('button', { name: 'Copy text' }).click();
  await expectVisible(page, page.getByText('Summary text copied to your clipboard.'), `${tag}: copy text confirms`);
  const clipboard = await page.evaluate(() => navigator.clipboard.readText());
  check(
    `${tag}: copied text carries the demo label`,
    clipboard.startsWith('Design demo · Sample information') && clipboard.includes('Reported symptoms'),
  );
  await page.getByRole('button', { name: 'Share…' }).click();
  const share = page.getByRole('dialog', { name: 'Share this summary' });
  await share.waitFor();
  check(`${tag}: unavailable share integrations are labelled`, (await share.getByText('Unavailable').count()) === 3);
  await page.keyboard.press('Escape');
  await noOverflow(page, `${tag} summary`);
  await shot(page, `${tag}-summary`);

  await page.emulateMedia({ media: 'print' });
  check(`${tag}: print hides the app chrome`, !(await page.getByRole('region', { name: 'Demo notice' }).isVisible()));
  check(
    `${tag}: print keeps the summary document`,
    await page.getByRole('article', { name: 'Consultation summary document' }).isVisible(),
  );
  const printed = await page.getByRole('article', { name: 'Consultation summary document' }).innerText();
  check(
    `${tag}: printed document has the demo label in header and footer`,
    printed.split('Design demo · Sample information').length - 1 >= 2,
  );
  if (OUT) {
    await page.pdf({ path: join(OUT, `${tag}-summary.pdf`), format: 'A4' });
  }
  await page.emulateMedia({ media: 'screen' });

  const storage = await page.evaluate(async () => ({
    local: Object.keys(localStorage),
    session: Object.keys(sessionStorage),
    idb: indexedDB.databases ? (await indexedDB.databases()).map((db) => db.name) : [],
    caches: 'caches' in window ? await caches.keys() : [],
    sw: 'serviceWorker' in navigator ? (await navigator.serviceWorker.getRegistrations()).length : 0,
  }));
  check(
    `${tag}: no health data in browser storage`,
    storage.local.every((key) => ALLOWED_STORAGE_KEYS.includes(key)) &&
      storage.session.length === 0 &&
      storage.idb.length === 0 &&
      storage.caches.length === 0 &&
      storage.sw === 0,
    JSON.stringify(storage),
  );
}

async function run() {
  const browser = await chromium.launch({ channel: CHANNEL, headless: true });

  // --- Routes render at every required width without horizontal overflow ----------------
  for (const [tag, viewport] of Object.entries(VIEWPORTS)) {
    await flow(browser, `routes ${tag}`, viewport, async (page) => {
      for (const path of [
        '/',
        '/start',
        '/history',
        '/settings/privacy',
        '/conditions/demo.possibility_a',
        '/conditions/unknown',
        '/review',
        '/assess/00000000-0000-4000-8000-000000000000',
        '/nope',
      ]) {
        const response = await page.goto(`${BASE}${path}`);
        check(`${tag} ${path}: responds 200`, response?.status() === 200, String(response?.status()));
        await page.getByRole('heading', { level: 1 }).first().waitFor({ timeout: 8000 });
        await expectVisible(
          page,
          page.getByText('Design demo · Sample scenarios · Not a medical assessment.'),
          `${tag} ${path}: demo banner present`,
        );
        await noOverflow(page, `${tag} ${path}`);
        if (path === '/' || path === '/start') await shot(page, `${tag}-route${path === '/' ? '-landing' : '-start'}`);
      }
    });
  }

  // --- Scenario 1: normal flow, on phone and desktop ---------------------------------
  await flow(browser, 'scenario 1 normal (390)', VIEWPORTS.w390, (page) => normalFlow(page, 's1-390'));
  await flow(browser, 'scenario 1 normal (1440)', VIEWPORTS.w1440, (page) => normalFlow(page, 's1-1440'));
  await flow(browser, 'scenario 1 normal (320)', VIEWPORTS.w320, (page) => normalFlow(page, 's1-320'));
  await flow(browser, 'scenario 1 normal (768)', VIEWPORTS.w768, (page) => normalFlow(page, 's1-768'));

  // --- Scenario 2: correction -> stale -> refreshed ----------------------------------
  await flow(browser, 'scenario 2 correction', VIEWPORTS.w1440, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Correct an earlier answer');
    await page.waitForURL('**/results/**');
    await page.getByRole('heading', { name: 'Illustrative possibility B' }).waitFor();
    await page.getByRole('button', { name: 'Remove or correct: Sample symptom B' }).click();
    const editor = page.getByRole('dialog', { name: 'Remove or correct this detail' });
    check(
      's2: correction dialog has nothing preselected',
      (await editor.getByRole('radio', { checked: true }).count()) === 0,
    );
    await editor.getByRole('radio', { name: /I don’t have this/ }).check();
    await editor.getByRole('button', { name: 'Save change' }).click();
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'This result needs updating' }),
      's2: stale result is flagged',
    );
    await expectAbsent(
      page,
      page.getByRole('link', { name: 'Prepare consultation summary' }),
      's2: stale result removes its primary action',
    );
    check(
      's2: stale explanation actions are disabled',
      await page
        .getByRole('button', { name: /View supporting information/ })
        .first()
        .isDisabled(),
    );
    await shot(page, 's2-stale');
    await page.getByRole('button', { name: 'Update result' }).click();
    await page.getByRole('heading', { name: 'This result needs updating' }).waitFor({ state: 'hidden' });
    await expectAbsent(
      page,
      page.getByRole('heading', { name: 'Illustrative possibility B' }),
      's2: refreshed result reflects the correction',
    );
    await expectVisible(
      page,
      page.getByRole('link', { name: 'Prepare consultation summary' }),
      's2: refreshed result restores its primary action',
    );
  });

  // --- Scenario 3: urgent -------------------------------------------------------------
  await flow(browser, 'scenario 3 urgent', VIEWPORTS.w390, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Urgent-state preview');
    await page.waitForURL('**/assess/**');
    await expectVisible(page, page.getByText('Urgent-state preview'), 's3: urgent preview label');
    await expectVisible(
      page,
      page.getByText(/Sample urgent action: placeholder text/),
      's3: action text is a labelled placeholder',
    );
    await expectAbsent(page, page.getByText('Follow-up question'), 's3: routine questioning stops');
    await expectAbsent(page, page.getByRole('button', { name: 'Send', exact: true }), 's3: composer is paused');
    check(
      's3: urgent panel is announced as an alert',
      (await page.getByRole('alert').filter({ hasText: 'This needs urgent attention' }).count()) === 1,
    );
    const text = await page.getByRole('main').innerText();
    check('s3: no phone number or emergency number is shown', !/\b(911|999|112|000|108)\b/.test(text));
    await shot(page, 's3-urgent-assess');
    await page.getByRole('link', { name: 'View what to do next' }).click();
    await page.waitForURL('**/results/**');
    await page.getByRole('heading', { level: 2, name: 'What to do next' }).waitFor();
    await expectAbsent(
      page,
      page.getByText('Possible explanation', { exact: true }),
      's3: no explanation cards in the urgent state',
    );
    await expectAbsent(
      page,
      page.getByRole('heading', { name: /Illustrative possibility/ }),
      's3: no illustrative possibility headings',
    );
    await noOverflow(page, 's3 results');
    await shot(page, 's3-urgent-results');
  });

  // --- Scenario 4: insufficient information ------------------------------------------
  await flow(browser, 'scenario 4 insufficient', VIEWPORTS.w768, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Insufficient information');
    await page.waitForURL('**/results/**');
    await expectVisible(
      page,
      page.getByText(/This is an incomplete result, not a\s+reassuring one/),
      's4: incomplete result is stated',
    );
    await expectVisible(page, page.getByText('Urgency not assessed').first(), 's4: urgency shown as not assessed');
    const text = await page.getByRole('main').innerText();
    check(
      's4: no routine/low-risk badge',
      !/\bRoutine\b|low risk|Low urgency|\bNormal\b/i.test(
        text.replace(/does not mean your situation is low urgency/gi, ''),
      ),
    );
    await expectVisible(page, page.getByText(/Sample missing detail/).first(), 's4: missing information is explained');
    await shot(page, 's4-insufficient');
    await page.getByRole('link', { name: 'Answer the next question' }).click();
    await page.waitForURL('**/assess/**');
    await page.getByRole('heading', { name: /enter the sample measurement/ }).waitFor();
    await page.getByLabel('Number').fill('9999');
    await page.getByLabel('Unit').selectOption('sample unit A');
    await page.getByRole('button', { name: 'Send answer' }).click();
    await expectVisible(page, page.getByText('Enter a number of 500 or less.'), 's4: number range validated inline');
    await page.getByLabel('Number').fill('42');
    await page.getByRole('button', { name: 'Send answer' }).click();
    await page.getByRole('heading', { name: /anything else you would like to add/ }).waitFor();
    check('s4: follow-up question offered after insufficient result', true);
  });

  // --- Scenario 5: out of scope -------------------------------------------------------
  await flow(browser, 'scenario 5 out of scope', VIEWPORTS.w390, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Unsupported scope');
    await page.waitForURL('**/results/**');
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'This is outside what Feeltriva can help with' }),
      's5: limitation screen',
    );
    await expectAbsent(page, page.getByText('Possible explanation', { exact: true }), 's5: no explanation cards');
    await expectVisible(
      page,
      page.getByRole('link', { name: 'Prepare consultation summary' }),
      's5: summary access preserved',
    );
    await shot(page, 's5-out-of-scope');
  });

  // --- Scenario 6: backend unavailable, then offline --------------------------------
  await flow(browser, 'scenario 6 unavailable + offline', VIEWPORTS.w1440, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Backend unavailable and offline');
    await page.waitForURL('**/results/**');
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'We couldn’t complete this assessment' }),
      's6: unavailable message',
    );
    await expectAbsent(page, page.getByText('Possible explanation', { exact: true }), 's6: no result invented');
    await expectVisible(
      page,
      page.getByRole('link', { name: 'View consultation summary' }),
      's6: summary option offered',
    );
    await page.getByRole('button', { name: 'Try again' }).click();
    await page.getByRole('button', { name: 'Try again' }).waitFor();
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'We couldn’t complete this assessment' }),
      's6: retry during outage still shows no result',
    );
    await shot(page, 's6-unavailable');

    await page.getByRole('button', { name: 'Demo tools' }).click();
    const tools = page.getByRole('dialog', { name: 'Demo tools' });
    check(
      's6: outage switch reflects the scenario',
      (await tools.getByRole('switch', { name: 'Service outage' }).getAttribute('aria-checked')) === 'true',
    );
    await tools.getByRole('switch', { name: 'Service outage' }).click();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Try again' }).click();
    await expectVisible(
      page,
      page.getByRole('heading', { level: 2, name: 'What to do next' }),
      's6: retry succeeds once the service is back',
    );

    await page.getByRole('link', { name: 'Add or correct details' }).first().click();
    await page.waitForURL('**/assess/**');
    await page.getByRole('heading', { name: 'Your result is available' }).waitFor();
    await page.getByRole('button', { name: 'Demo tools' }).click();
    await page.getByRole('dialog', { name: 'Demo tools' }).getByRole('switch', { name: 'Simulate offline' }).click();
    await page.keyboard.press('Escape');
    await expectVisible(page, page.getByRole('heading', { name: 'You’re offline' }), 's6: offline state shown');
    await expectAbsent(
      page,
      page.getByRole('heading', { name: 'Your result is available' }),
      's6: no "result available" step while offline',
    );
    const box = page.getByLabel('Add more details');
    await box.fill('unsent sample text');
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await expectVisible(
      page,
      page.getByRole('alert').filter({ hasText: 'We couldn’t reach the service' }),
      's6: failed send is reported inline',
    );
    await expectVisible(
      page,
      page.getByText('Not sent yet. This text is only in this box until it’s sent.'),
      's6: unsent text is distinguished from saved details',
    );
    check('s6: unsent text is retained after a failed send', (await box.inputValue()) === 'unsent sample text');
    await shot(page, 's6-offline');
    await page.getByRole('button', { name: 'Demo tools' }).click();
    await page.getByRole('dialog', { name: 'Demo tools' }).getByRole('switch', { name: 'Simulate offline' }).click();
    await page.keyboard.press('Escape');
    await page.getByRole('heading', { name: 'You’re offline' }).waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByRole('log', { name: 'Conversation' }).getByText('unsent sample text').waitFor();
    check('s6: text sends after reconnecting', (await box.inputValue()) === '');
  });

  // --- Scenario 7: empty history -> sample -> preview -> delete -> receipt ----------
  await flow(browser, 'scenario 7 history', VIEWPORTS.w390, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Empty history');
    await page.waitForURL('**/history');
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'No saved assessments yet' }),
      's7: empty history explanation',
    );
    await page.getByRole('button', { name: 'Start a sample assessment' }).click();
    await page.getByRole('heading', { name: 'Sample assessment 1' }).waitFor();
    await expectVisible(page, page.getByText('Completed', { exact: true }), 's7: sample is listed as completed');
    const cardText = await page.getByRole('listitem').filter({ hasText: 'Sample assessment 1' }).innerText();
    check('s7: history card shows no explanation name', !/Illustrative possibility/.test(cardText));
    await shot(page, 's7-history');
    await page.getByRole('link', { name: 'View summary: Sample assessment 1' }).click();
    await page.waitForURL('**/summary/**');
    await page.getByRole('heading', { name: 'Reported symptoms' }).waitFor();
    await page.goBack();
    await page.waitForURL('**/history');
    await page.getByRole('button', { name: 'Delete: Sample assessment 1' }).click();
    await page
      .getByRole('alertdialog', { name: 'Delete this assessment?' })
      .getByRole('button', { name: 'Delete assessment' })
      .click();
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'Deletion scheduled' }),
      's7: receipt shows deletion as scheduled, not completed',
    );
    await expectAbsent(
      page,
      page.getByRole('heading', { name: 'Deletion completed' }),
      's7: completion is not claimed while queued',
    );
    await expectVisible(page, page.getByText(/demo-receipt-/), 's7: receipt id shown');
    await shot(page, 's7-receipt');
    await page.getByRole('button', { name: /Demo: simulate the service finishing deletion/ }).click();
    await expectVisible(page, page.getByRole('heading', { name: 'Deletion completed' }), 's7: completed receipt state');
  });

  // --- Scenario 8: evidence missing --------------------------------------------------
  await flow(browser, 'scenario 8 evidence missing', VIEWPORTS.w1440, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Evidence missing');
    await page.waitForURL('**/results/**');
    await expectVisible(page, page.getByRole('heading', { name: 'Incomplete result' }), 's8: incomplete result shown');
    await expectAbsent(
      page,
      page.getByRole('heading', { name: 'Illustrative possibility A' }),
      's8: unsupported explanation withheld',
    );
    await shot(page, 's8-evidence-missing');
  });

  // --- Scenario 9: version conflict ----------------------------------------------------
  await flow(browser, 'scenario 9 conflict', VIEWPORTS.w390, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Concurrent update');
    await page.waitForURL('**/assess/**');
    await page.getByRole('heading', { name: /have you also noticed sample symptom C/ }).waitFor();
    await page.getByRole('radio', { name: 'Yes', exact: true }).check();
    await page.getByRole('button', { name: 'Send answer' }).click();
    await expectVisible(
      page,
      page.getByText('Your details changed. Refreshing this assessment…').first(),
      's9: conflict message shown',
    );
    await expectVisible(
      page,
      page.getByText('Your answer wasn’t sent. Check it still applies, then send it again.'),
      's9: resubmission is required',
    );
    check('s9: unsent selection is retained', await page.getByRole('radio', { name: 'Yes', exact: true }).isChecked());
    await shot(page, 's9-conflict');
    await page.getByRole('button', { name: 'Send answer' }).click();
    await page.getByRole('heading', { name: /how long have you had sample symptom A/ }).waitFor();
    check('s9: resubmitted answer accepted against the new version', true);
    await page.getByRole('button', { name: /Your details/ }).click();
    await expectVisible(
      page,
      page.getByRole('dialog', { name: 'What you’ve shared' }).getByText(/Sample detail D/),
      's9: refreshed state includes the other tab’s change',
    );
  });

  // --- Scenario 10: internal reviewer ------------------------------------------------
  await flow(browser, 'scenario 10 reviewer', VIEWPORTS.w1440, async (page) => {
    await page.goto(`${BASE}/review`);
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'Reviewer access is required' }),
      's10: review is gated when preview is off',
    );
    await loadScenario(page, 'Internal reviewer');
    await page.waitForURL('**/review/data');
    await expectVisible(page, page.getByText('Internal review', { exact: true }), 's10: labelled internal review');
    await page.getByRole('button', { name: 'View details for vomiting', exact: true }).click();
    const drawer = page.getByRole('dialog', { name: 'vomiting' });
    await drawer.waitFor();
    await expectVisible(page, drawer.getByText('Column 12:'), 's10: column position preserved');
    await drawer.getByLabel('Add a note').fill('Demo note: columns 12 and 601 disagree; needs reconciliation.');
    await drawer.getByRole('button', { name: 'Save demo note' }).click();
    await expectVisible(page, drawer.getByText('Demo note saved. It is kept in memory only.'), 's10: demo note saved');
    await expectVisible(page, drawer.getByText('Demo change'), 's10: change is labelled as a demo change');
    await shot(page, 's10-review-drawer');
    await page.keyboard.press('Escape');
    await shot(page, 's10-review-data');
    const reviewNav = page.getByRole('navigation', { name: 'Internal review sections' });
    await reviewNav.getByRole('link', { name: 'Overview' }).click();
    for (const figure of ['960', '37', '27,622']) {
      await expectVisible(page, page.getByText(figure, { exact: true }), `s10: audit fact ${figure}`);
    }
    await shot(page, 's10-review-overview');
    await reviewNav.getByRole('link', { name: 'Releases' }).click();
    check('s10: publish control is disabled', await page.getByRole('button', { name: 'Publish release' }).isDisabled());
    await reviewNav.getByRole('link', { name: 'Model evaluation' }).click();
    await expectVisible(
      page,
      page.getByText('Baseline rejected for clinical serving.'),
      's10: research baseline verdict',
    );
    await expectVisible(page, page.getByText('Not evaluated').first(), 's10: clinical validation says "Not evaluated"');
  });

  await flow(browser, 'reviewer pages (390)', VIEWPORTS.w390, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Internal reviewer');
    await page.waitForURL('**/review/data');
    for (const name of [
      'Overview',
      'Disease mappings',
      'Feature mappings',
      'Evidence',
      'Questions/rules',
      'Releases',
      'Data quality',
      'Model evaluation',
    ]) {
      await page.getByRole('navigation', { name: 'Internal review sections' }).getByRole('link', { name }).click();
      await page.getByRole('heading', { level: 1 }).first().waitFor();
      await noOverflow(page, `review ${name} (390)`);
    }
  });

  // --- Extra state: session expired ---------------------------------------------------
  await flow(browser, 'state session expired', VIEWPORTS.w390, async (page) => {
    await page.goto(`${BASE}/`);
    await loadScenario(page, 'Session expired');
    await page.waitForURL('**/assess/**');
    await expectVisible(
      page,
      page.getByRole('heading', { name: 'Your session has ended' }),
      'expired: session-ended state',
    );
    await expectVisible(
      page,
      page.getByRole('link', { name: 'Start a new symptom check' }),
      'expired: safe restart offered',
    );
  });

  // --- Keyboard: skip link, dialog focus trap ---------------------------------------
  await flow(browser, 'keyboard and focus', VIEWPORTS.w1440, async (page) => {
    await page.goto(`${BASE}/`);
    await page.keyboard.press('Tab');
    const first = await page.evaluate(() => document.activeElement?.textContent ?? '');
    check('keyboard: first tab stop is the skip link', first.trim() === 'Skip to main content', first);
    await page.getByRole('button', { name: 'About', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'About Feeltriva' });
    await dialog.waitFor();
    await expectVisible(
      page,
      dialog.getByText('Draft', { exact: true }),
      'footer: informational content is marked draft',
    );
    for (let i = 0; i < 6; i += 1) await page.keyboard.press('Tab');
    check(
      'keyboard: focus stays inside the open dialog',
      await page.evaluate(() => !!document.activeElement?.closest('[role="dialog"]')),
    );
    await page.keyboard.press('Escape');
    await dialog.waitFor({ state: 'hidden' });
    check(
      'keyboard: focus returns to the footer button',
      (await page.evaluate(() => document.activeElement?.textContent ?? '')).trim() === 'About',
    );
  });

  await browser.close();

  const failed = results.filter((result) => !result.ok);
  console.log(`\n${results.length - failed.length} passed, ${failed.length} failed (${results.length} checks)`);
  if (failed.length > 0) {
    for (const item of failed) console.log(`  FAILED: ${item.name}${item.detail ? ` — ${item.detail}` : ''}`);
    process.exit(1);
  }
}

run().catch((error) => {
  console.error(error);
  process.exit(1);
});
