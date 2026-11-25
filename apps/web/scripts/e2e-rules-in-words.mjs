// Read-only browser check of the urgency rules screen (M2.4c): for every rule, the screen shows the same
// words as the review document docs/review/urgency_rules_draft.md.
//
// It records nothing: it opens the rules, opens each rule and compares. So it may run against the real
// rule set. It needs the service on port 8000 and the web app in live review mode on the one web port:
//
//   (repo root)   uv run uvicorn feeltriva_api.main:app_factory --factory --port 8000
//   (apps/web)    pnpm dev:review
//   (apps/web)    pnpm e2e:rules
//
// Environment: E2E_BASE_URL (default http://localhost:5173), E2E_CHANNEL (default "chrome"),
// E2E_OUT_DIR (screenshots), E2E_RULE_SET (default "urgency-draft").
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright-core';

const BASE = (process.env.E2E_BASE_URL ?? 'http://localhost:5173').replace(/\/+$/, '');
const OUT = process.env.E2E_OUT_DIR ?? null;
const CHANNEL = process.env.E2E_CHANNEL ?? 'chrome';
const RULE_SET = process.env.E2E_RULE_SET ?? 'urgency-draft';
const HERE = dirname(fileURLToPath(import.meta.url));
const DOCUMENT = readFileSync(resolve(HERE, '../../../docs/review/urgency_rules_draft.md'), 'utf8');

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

/** The rules of the document: number, title and the text of the rule's own part. */
const SECTIONS = DOCUMENT.split('\n### Rule ')
  .slice(1)
  .map((part) => {
    const section = part.split('\n## ')[0];
    const [, number, title] = /^(\d+)\. (.*)\n/.exec(section);
    return { number: Number(number), title, section };
  });

/** What the document says about one rule, as the plain strings a screen can show. */
function expected({ section }) {
  const between = (from, to) => section.split(from)[1].split(to)[0];
  const lines = (text) =>
    text
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.startsWith('- '))
      .map((line) => line.slice(2).replaceAll('**', ''));
  const basis = section.split('**Basis, quoted word for word**')[1];
  return {
    condition: lines(between('**Fires when**', '**The person is shown**')),
    shown: between('**The person is shown**\n\n> ', '\n'),
    why: between('**Why this level.** ', '\n'),
    fires: between('- Fires: ', '\n'),
    quiet: between('- Does not fire: ', '\n'),
    quotes: lines(basis).filter((line) => line.startsWith('“')),
    level: /\| \*\*(\w+)\*\* \|/.exec(section)[1],
  };
}

const squash = (text) => text.replace(/\s+/g, ' ').trim();

const browser = await chromium.launch({ channel: CHANNEL, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const writes = [];
page.on('request', (request) => {
  if (request.method() !== 'GET' && request.method() !== 'OPTIONS') writes.push(`${request.method()} ${request.url()}`);
});

try {
  await page.goto(`${BASE}/review/rules`);
  await page.getByRole('heading', { name: 'Urgency rules' }).waitFor();
  check('the document holds the rules', SECTIONS.length > 0, String(SECTIONS.length));
  let same = 0;
  const differences = [];
  for (const rule of SECTIONS) {
    const want = expected(rule);
    await page.getByRole('button', { name: `Review ${rule.number}. ${rule.title}`, exact: true }).click();
    const drawer = page.getByRole('dialog');
    await drawer.getByText('When this rule applies').waitFor();
    const shown = squash(await drawer.innerText());
    const missing = [
      ...want.condition,
      want.shown,
      want.why,
      `The rule applies: ${want.fires}`,
      `The rule does not apply: ${want.quiet}`,
      ...want.quotes,
      `${rule.number} of ${SECTIONS.length}`,
      `${want.level}.`,
    ].filter((text) => !shown.includes(squash(text)));
    if (missing.length === 0) {
      same += 1;
    } else {
      differences.push(`rule ${rule.number}: ${missing[0].slice(0, 120)}`);
    }
    if (OUT && rule.number === 1) {
      await page.waitForTimeout(500); // the drawer slides in
      await page.screenshot({ path: join(OUT, 'rule-1-in-words.png') });
    }
    await page.keyboard.press('Escape');
    await drawer.waitFor({ state: 'hidden' });
  }
  check(
    `rule 1 is shown in the same words as the review document (${RULE_SET})`,
    !differences.some((difference) => difference.startsWith('rule 1:')),
    differences.find((difference) => difference.startsWith('rule 1:')) ?? '',
  );
  check(
    `every rule of the document is shown in the document's words (${same} of ${SECTIONS.length})`,
    same === SECTIONS.length,
    differences.join(' || '),
  );
  check(
    'the check recorded nothing: the browser sent no request that changes data',
    writes.length === 0,
    writes.join(' | '),
  );
} catch (error) {
  failures.push('the check ran to its end');
  console.log(`FAIL  the check ran to its end  — ${String(error).slice(0, 400)}`);
  if (OUT) await page.screenshot({ path: join(OUT, 'failure-rules.png'), fullPage: true });
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failures.length} failed`);
process.exit(failures.length === 0 ? 0 : 1);
