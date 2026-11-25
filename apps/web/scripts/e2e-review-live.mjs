// Browser test of the internal review workspace against a RUNNING review service (M2.4a, M2.4b).
//
// It records notes and decisions, so the service must run on a TEST database with invented rows,
// never on real data. No web server is started and no web port is used: `pnpm e2e:review` builds the
// app in live mode for this test and the test hands the built files to the browser itself, under the
// address of the one web port (5173). A web server that is running there is not touched.
// From the repository root:
//
//   export TEST_MIGRATION_DATABASE_URL=postgresql+psycopg://feeltriva:feeltriva_dev@127.0.0.1:5440/feeltriva_test
//   E2E_TAG=$(uv run python apps/web/scripts/seed_review_e2e.py)
//   DATABASE_URL=postgresql+psycopg://feeltriva_app:feeltriva_app_dev@127.0.0.1:5440/feeltriva_test \
//     CORS_ALLOWED_ORIGINS=http://localhost:5173 uv run uvicorn feeltriva_api.main:app_factory --factory --port 8001
//   (in apps/web)  E2E_TAG=$E2E_TAG pnpm e2e:review
//
// Environment: E2E_TAG (required), E2E_API_URL (default http://localhost:8001), E2E_DIST (the build,
// default node_modules/.cache/feeltriva-e2e-review), E2E_CHANNEL (default "chrome"), E2E_OUT_DIR (screenshots).
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';

import { chromium } from 'playwright-core';

const TAG = process.env.E2E_TAG ?? '';
const BASE = 'http://localhost:5173'; // an address only: the browser is handed the built files, nothing listens
const DIST = resolve(process.env.E2E_DIST ?? 'node_modules/.cache/feeltriva-e2e-review');
const API = (process.env.E2E_API_URL ?? 'http://localhost:8001').replace(/\/+$/, '');
const OUT = process.env.E2E_OUT_DIR ?? null;
const CHANNEL = process.env.E2E_CHANNEL ?? 'chrome';
const REVIEWER = 'dev-reviewer:e2e';

if (!/^[0-9a-f]{10}$/.test(TAG)) {
  console.error('E2E_TAG is required: the tag printed by apps/web/scripts/seed_review_e2e.py');
  process.exit(2);
}
if (!existsSync(join(DIST, 'index.html'))) {
  console.error(`no build of the app in ${DIST}: run this test with \`pnpm e2e:review\`, which builds it first`);
  process.exit(2);
}
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

/** What the service holds, asked directly: the browser must not be the only witness. */
async function service(path) {
  const response = await fetch(`${API}/internal/v1/review${path}`, {
    headers: { Authorization: `Bearer ${REVIEWER}` },
  });
  return response.json();
}

const browser = await chromium.launch({ channel: CHANNEL, headless: true });
// The page is handed over from disk, so Chrome does not count it as a page of this machine and would block its
// calls to the service on this machine; the permission says they are allowed.
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  permissions: ['local-network-access'],
});
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};
// The built app, handed to the browser from disk. A path that is not a file is a page of the app.
await context.route(`${BASE}/**`, (route) => {
  const path = normalize(decodeURIComponent(new URL(route.request().url()).pathname));
  const file = join(DIST, path);
  const found = file.startsWith(DIST) && extname(file) !== '' && existsSync(file);
  if (!found && extname(path) !== '') return route.fulfill({ status: 404, body: 'not found' });
  const served = found ? file : join(DIST, 'index.html');
  return route.fulfill({
    status: 200,
    contentType: TYPES[extname(served)] ?? 'application/octet-stream',
    body: readFileSync(served),
  });
});
const page = await context.newPage();
const problems = [];
const tokens = new Set();
page.on('console', (message) => {
  if (message.type() === 'error') problems.push(`console: ${message.text().slice(0, 200)}`);
});
page.on('pageerror', (error) => problems.push(`pageerror: ${String(error).slice(0, 200)}`));
page.on('request', (request) => {
  if (request.url().startsWith(API)) tokens.add(request.headers()['authorization'] ?? '(none)');
});
const shot = async (name) => {
  if (OUT) await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
};
const drawer = () => page.getByRole('dialog');

async function search(text) {
  await page.getByRole('searchbox').fill(text);
  await page.getByRole('button', { name: 'Show results' }).click();
}

async function record(note, button) {
  await drawer().getByLabel('Note (required)').fill(note);
  await drawer().getByRole('button', { name: button, exact: true }).click();
}

try {
  // ---- 1. Inspect a duplicate column and save a note ------------------------------------------------
  await page.goto(`${BASE}/review/data`);
  await page.getByRole('heading', { name: 'Repeated columns in the data files' }).waitFor();
  check(
    'in live mode the notice at the top does not call the page a design demo with sample scenarios',
    (await page.getByRole('region', { name: 'Demo notice' }).innerText()).startsWith(
      'Test version · Connected to the service',
    ),
    await page.getByRole('region', { name: 'Demo notice' }).innerText(),
  );
  check(
    'the workspace says under whose name decisions are recorded',
    await page.getByText('Your decisions are saved under the name e2e').isVisible(),
  );
  await search(`itching ${TAG}`);
  await page.getByRole('button', { name: `Review itching ${TAG} (column 3)` }).click();
  await drawer().waitFor();
  check(
    'the duplicate column shows both positions and the rows in which they disagree',
    await drawer().getByText('The heading is repeated at columns 3, 9; the columns disagree in 12 rows').isVisible(),
  );
  await drawer().getByText('No notes yet.').waitFor();
  await drawer().getByRole('button', { name: 'Save note' }).click();
  check('a note is required before anything is sent', await drawer().getByText('Write a note first.').isVisible());
  const note = `Columns 3 and 9 disagree in 12 rows (${TAG}).`;
  await record(note, 'Save note');
  await drawer().getByText('Note saved under e2e.').waitFor();
  // The drawer reads the notes again from the service after saving.
  const shown = (locator) =>
    locator.waitFor({ timeout: 5000 }).then(
      () => true,
      () => false,
    );
  check('the saved note is shown with the reviewer', await shown(drawer().getByText(note)));
  check(
    'the note carries the reviewer under whose name it was recorded',
    await shown(drawer().getByText(/Note · dev-reviewer:e2e/)),
  );
  await shot('1-duplicate-column-note');
  const notes = await service(`/notes?target_type=feature_mapping&target_id=e2e_fm_${TAG}_3`);
  check(
    'the service holds the note under the reviewer, with no status changed',
    notes.items.length === 1 &&
      notes.items[0].note === note &&
      notes.items[0].reviewer === REVIEWER &&
      notes.items[0].status_change === null,
    JSON.stringify(notes.items),
  );
  // After a reload the note is read from the service again.
  await page.reload();
  await search(`itching ${TAG}`);
  await page.getByRole('button', { name: `Review itching ${TAG} (column 3)` }).click();
  check('after a reload the note is still there', await shown(drawer().getByText(note)));

  // ---- 2. Vocabulary links: the general term is the default; approve one, reject the other ----------
  await page.goto(`${BASE}/review/links`);
  await page.getByRole('heading', { name: 'Matches to medical reference lists' }).waitFor();
  await search(TAG);
  await page.getByRole('button', { name: new RegExp(`Pretend ache of the left side ${TAG}`) }).click();
  await drawer().waitFor();
  check('a reviewer sees the code of the link', await drawer().getByText(`ZZ${TAG}.0`).isVisible());
  await record('The source names the left side.', 'Approve');
  await drawer().getByRole('alert').waitFor();
  check(
    'the service refuses the narrower term while the general one stands, and says why',
    (await drawer().getByRole('alert').innerText()).includes('the general term is the default'),
    await drawer().getByRole('alert').innerText(),
  );
  await record('Only when the source says so.', 'Reject');
  await drawer().getByText('Recorded: Rejected, under e2e.').waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: new RegExp(`→ Pretend ache ${TAG}$`) }).click();
  await drawer().waitFor();
  await record('The general term is preferred.', 'Approve');
  await drawer().getByText('Recorded: Approved, under e2e.').waitFor();
  await shot('2-vocabulary-links');
  const links = await service(`/terminology-links?q=${TAG}`);
  const statuses = Object.fromEntries(
    links.items.map((item) => [item.link_id.split('_').pop(), [item.review_status, item.reviewer]]),
  );
  check(
    'the service holds one link approved and one rejected, both under the reviewer',
    JSON.stringify(statuses) === JSON.stringify({ general: ['approved', REVIEWER], narrow: ['rejected', REVIEWER] }),
    JSON.stringify(statuses),
  );

  // ---- 3. A statement with its claims: a mark to check, a proposed feature, a decision --------------
  await page.goto(`${BASE}/review/evidence?statement=e2e_st_${TAG}`);
  await page.getByRole('heading', { name: 'Texts about conditions' }).waitFor();
  await page.getByRole('button', { name: 'Review claim: a pretend hat' }).waitFor();
  check(
    'the item shows what to check and the symptom recognised in it',
    (await page.getByText('Check: how the list is worded').isVisible()) &&
      (await page.getByText(`Symptom recognised: hat ${TAG}`).isVisible()),
  );
  await page.getByRole('button', { name: 'Review claim: a pretend hat' }).click();
  await drawer().waitFor();
  check(
    'the drawer says what to check for the mark',
    await drawer()
      .getByText(/The first item of this list starts with a few words/)
      .isVisible(),
  );
  await record('The item names the feature.', 'Approve');
  await drawer().getByText('Recorded: Approved, under e2e.').waitFor();
  await shot('3-claims');
  const evidence = await service(`/evidence?disease_id=e2e_dis_${TAG}`);
  check(
    'the approved item became one evidence row for its disease and feature',
    evidence.total === 1 &&
      evidence.items[0].feature.id === `e2e_feat_${TAG}` &&
      evidence.items[0].review_status === 'approved',
    JSON.stringify(evidence.items),
  );

  // ---- 4. Suggested matches: confirm one close search result and reject another (M2.4b) -------------
  await page.goto(`${BASE}/review/suggestions`);
  await page.getByRole('heading', { name: 'Suggested matches to check' }).waitFor();
  await search(TAG);
  const chill = new RegExp(`Review pretend chill ${TAG} → Pretend chilling ${TAG}`);
  await page.getByRole('button', { name: chill }).waitFor();
  const before = await service(`/terminology-links?q=YY${TAG}`);
  check('a close search result is not a link before a reviewer confirms it', before.total === 0, String(before.total));
  await page.getByRole('button', { name: chill }).click();
  await drawer().waitFor();
  check(
    'the suggestion shows why it was not matched automatically, in plain words, and how close it is',
    (await drawer()
      .getByText('The search found an entry that comes close, but none with exactly our name')
      .isVisible()) && (await drawer().getByText('Search score 0.96 (the best possible is 1)').isVisible()),
  );
  await record('The entry names the same condition.', 'Confirm match');
  await drawer().getByText('Recorded: Approved, under e2e.').waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: new RegExp(`Review pretend shiver ${TAG} → Pretend shaking ${TAG}`) }).click();
  await drawer().waitFor();
  await record('Shaking is not the same as shivering here.', 'Reject match');
  await drawer().getByText('Recorded: Rejected, under e2e.').waitFor();
  await page.keyboard.press('Escape');
  await page.getByText('Yes, confirmed').waitFor();
  await shot('4-suggested-matches');
  const made = await service(`/terminology-links?q=YY${TAG}`);
  check(
    'confirming made exactly one link, approved under the reviewer; rejecting made none',
    made.total === 1 &&
      made.items[0].code === `YY${TAG}.1` &&
      made.items[0].review_status === 'approved' &&
      made.items[0].reviewer === REVIEWER &&
      made.items[0].match_method === 'reviewer_confirmed',
    JSON.stringify(made.items),
  );
  const decided = await service(`/link-proposals?q=${TAG}&basis=close_search_result`);
  const outcome = Object.fromEntries(
    decided.items.map((item) => [item.proposal_id.split('_').pop(), [item.review_status, item.reviewer]]),
  );
  check(
    'the service holds one suggestion confirmed and one rejected, both under the reviewer',
    JSON.stringify(outcome) === JSON.stringify({ near: ['approved', REVIEWER], far: ['rejected', REVIEWER] }),
    JSON.stringify(outcome),
  );
  // A name without a suggestion: a note can be written, no decision is offered.
  await page.getByRole('button', { name: new RegExp(`Review hat ${TAG} → no suggestion`) }).click();
  await drawer().waitFor();
  check(
    'a row without a suggestion offers a note and no decision',
    (await drawer()
      .getByText(/There is no suggested entry to confirm or reject/)
      .isVisible()) &&
      (await drawer().getByRole('button', { name: 'Confirm match' }).count()) === 0 &&
      (await drawer().getByRole('button', { name: 'Save note' }).isVisible()),
  );

  // ---- 5. Many rows at once: one note, a second click, and the service decides every row (M2.4j) ----
  await page.keyboard.press('Escape');
  await page.goto(`${BASE}/review/data`);
  await page.getByRole('heading', { name: 'Repeated columns in the data files' }).waitFor();
  await search(`itching ${TAG}`);
  await page.getByText('Showing 1 to 2 of 2').waitFor();
  const bulk = page.locator('section', {
    has: page.getByRole('heading', { name: 'Decide all the rows shown at once' }),
  });
  await bulk.getByLabel('Note for all these rows (required)').fill(`Both columns are kept as they came (${TAG}).`);
  await bulk.getByRole('button', { name: 'Approve all 2 rows shown' }).click();
  const untouched = await service(`/feature-mappings?q=itching ${TAG}&conflicts_only=true`);
  check(
    'nothing is recorded before the second click',
    untouched.items.every((item) => item.review_status === 'pending'),
    JSON.stringify(untouched.items.map((item) => item.review_status)),
  );
  await bulk.getByRole('button', { name: 'Yes, record it' }).click();
  await bulk.getByText('Recorded: Approved for 2 rows, under e2e.').waitFor();
  await shot('5-many-rows-at-once');
  const together = await service(`/feature-mappings?q=itching ${TAG}&conflicts_only=true`);
  const eachNote = await service(`/notes?target_type=feature_mapping&target_id=e2e_fm_${TAG}_9`);
  check(
    'both rows are approved, and each carries the note under the reviewer',
    together.items.length === 2 &&
      together.items.every((item) => item.review_status === 'approved') &&
      eachNote.items.length === 1 &&
      eachNote.items[0].reviewer === REVIEWER &&
      eachNote.items[0].status_change === 'approved',
    JSON.stringify([together.items.map((item) => item.review_status), eachNote.items]),
  );

  // ---- 6. Published versions: publish, publish again, go back to the first (M2.4h) -----------------
  const decideByService = (targetType, targetId, status) =>
    fetch(`${API}/internal/v1/review/decisions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${REVIEWER}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_type: targetType, target_id: targetId, status, note: `Set by the test (${TAG}).` }),
    });
  const names = () => page.getByRole('region', { name: 'Published lists of names' });
  const publish = async (note) => {
    await page.goto(`${BASE}/review/releases`);
    await page.getByRole('heading', { name: 'Published versions' }).waitFor();
    await names().getByLabel('Which list of names (its name in the system)').selectOption(`e2e-map-${TAG}`);
    await names().getByRole('button', { name: 'Publish this version' }).click();
    await names().getByLabel('Note (required)').fill(note);
    await names().getByRole('button', { name: 'Yes, publish it' }).click();
  };
  await publish(`First version of this run (${TAG}).`);
  await page.getByText(`Published as e2e-map-${TAG}.r1. It is the version in use now.`).waitFor();
  // Something changes, so that there is a second version to publish.
  await decideByService('feature', `e2e_feat_${TAG}`, 'approved');
  await publish(`Second version of this run (${TAG}).`);
  await page.getByText(`Published as e2e-map-${TAG}.r2. It is the version in use now.`).waitFor();
  const first = names().locator('li', { hasText: `e2e-map-${TAG}.r1` });
  await first.getByRole('button', { name: 'Go back to this version' }).click();
  await first.getByLabel('Note (required)').fill(`The second version is withdrawn (${TAG}).`);
  await first.getByRole('button', { name: 'Yes, make it the version in use' }).click();
  await page.getByText(`e2e-map-${TAG}.r1 is the version in use now.`).waitFor();
  await first.getByText('In use now').waitFor();
  await shot('6-published-versions');
  const versions = (await service('/mapping-releases')).items.filter((item) =>
    item.release_id.startsWith(`e2e-map-${TAG}.`),
  );
  check(
    'the service holds both versions under the reviewer, and the first is the one in use again',
    JSON.stringify(versions.map((item) => [item.release_id, item.is_current, item.published_by]).sort()) ===
      JSON.stringify([
        [`e2e-map-${TAG}.r1`, true, REVIEWER],
        [`e2e-map-${TAG}.r2`, false, REVIEWER],
      ]),
    JSON.stringify(versions.map((item) => [item.release_id, item.is_current])),
  );

  check(
    'every request to the service carried the reviewer token and no other',
    tokens.size === 1 && tokens.has(`Bearer ${REVIEWER}`),
    [...tokens].join(' | '),
  );
  // The refused approval is a 409 the browser reports in its console; nothing else may be there.
  const unexpected = problems.filter((problem) => !problem.includes('409'));
  check('no error in the browser other than the refused approval', unexpected.length === 0, unexpected.join(' || '));
} catch (error) {
  failures.push('the flow ran to its end');
  console.log(`FAIL  the flow ran to its end  — ${String(error).slice(0, 400)}`);
  await shot('failure');
} finally {
  await browser.close();
}

console.log(`\n${passed} passed, ${failures.length} failed`);
process.exit(failures.length === 0 ? 0 : 1);
