// Read-only browser check of the review lists (M2.4i): every list of the workspace opens on the stored
// data and shows its rows in plain words. It records nothing: it opens pages and rows and reads them, and
// it fails if the browser sends a request that changes data. So it may run against the real data.
//
//   (repo root)   uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000
//   (apps/web)    pnpm dev:review
//   (apps/web)    pnpm e2e:lists
//
// Environment: E2E_BASE_URL (default http://localhost:5173), E2E_CHANNEL (default "chrome"),
// E2E_OUT_DIR (screenshots).
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

import { chromium } from 'playwright-core';

const BASE = (process.env.E2E_BASE_URL ?? 'http://localhost:5173').replace(/\/+$/, '');
const OUT = process.env.E2E_OUT_DIR ?? null;
const CHANNEL = process.env.E2E_CHANNEL ?? 'chrome';
if (OUT) mkdirSync(OUT, { recursive: true });

// Words a reviewer should not have to read: the old terms of the workspace and the codes of the stored data.
const NOT_PLAIN = [
  'lexical',
  'canonical',
  'pending',
  'retired',
  'mapping',
  'vocabulary',
  'serving bundle',
  'semantic',
  'dataset_cooccurrence',
  'possible_subtype',
  'possible_synonym',
  'adds_words',
  'risk_factor',
  'yes_no_unsure',
];
// What a slip of the page itself would leave, looked for as whole words ("pregnancy" holds "nan").
const SLIPS = /\b(undefined|NaN|null)\b/;
const LISTS = [
  ['conditions', 'Conditions', true],
  ['items', 'Symptoms and other items', true],
  ['pairs', 'Names that may mean the same', true],
  ['facts', 'Facts from the data files', true],
  ['text-parts', 'Parts of the text files', true],
  ['sources', 'Data sources', true],
  ['questions', 'Follow-up questions', true],
  ['replies', 'Standard replies', true],
  ['rule-sets', 'Sets of urgency rules', true],
];

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
const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
const writes = [];
const problems = [];
page.on('request', (request) => {
  if (request.method() !== 'GET' && request.method() !== 'OPTIONS') writes.push(`${request.method()} ${request.url()}`);
});
page.on('pageerror', (error) => problems.push(String(error).slice(0, 200)));
// Stored names are data: they are set as code and left out of the reading for unclear words.
const words = (locator) =>
  locator.evaluate((element) => {
    const copy = element.cloneNode(true);
    copy.querySelectorAll('code').forEach((node) => node.remove());
    return copy.textContent ?? '';
  });

try {
  await page.goto(`${BASE}/review/more`);
  await page.getByRole('heading', { name: 'More lists to review' }).waitFor();
  check(
    'the page of further lists names all nine',
    (await page.locator('main li a').count()) === LISTS.length,
    String(await page.locator('main li a').count()),
  );
  for (const [path, heading] of LISTS) {
    await page.goto(`${BASE}/review/${path}`);
    await page.getByRole('heading', { name: heading, level: 1 }).waitFor();
    await page.getByText(/^Showing 1 to /).waitFor({ timeout: 60000 });
    const rows = await page.locator('tbody tr').count();
    const shown = await words(page.locator('main'));
    const unclear = NOT_PLAIN.filter((word) => shown.toLowerCase().includes(word.toLowerCase()));
    if (SLIPS.test(shown)) unclear.push(`a slip of the page: ${SLIPS.exec(shown)[0]}`);
    await page.locator('tbody tr').first().getByRole('button').click();
    const drawer = page.getByRole('dialog');
    await drawer.getByText('Write a note or make a decision').waitFor();
    const inside = await words(drawer);
    if (SLIPS.test(inside)) unclear.push(`a slip in the row: ${SLIPS.exec(inside)[0]}`);
    unclear.push(
      ...NOT_PLAIN.filter((word) => inside.toLowerCase().includes(word.toLowerCase())).map((w) => `${w} (in the row)`),
    );
    if (OUT) {
      await page.waitForTimeout(400);
      await page.screenshot({ path: join(OUT, `list-${path}.png`) });
    }
    await page.keyboard.press('Escape');
    check(
      `${heading}: opens with ${rows} rows shown, a row opens, and its words are plain`,
      rows > 0 && unclear.length === 0,
      unclear.join(', '),
    );
  }
  check('no error in the browser', problems.length === 0, problems.join(' || '));
  check(
    'the check recorded nothing: the browser sent no request that changes data',
    writes.length === 0,
    writes.join(' | '),
  );
} catch (error) {
  failures.push('the check ran to its end');
  console.log(`FAIL  the check ran to its end  — ${String(error).slice(0, 400)}`);
  if (OUT) await page.screenshot({ path: join(OUT, 'failure-lists.png') });
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failures.length} failed`);
process.exit(failures.length === 0 ? 0 : 1);
