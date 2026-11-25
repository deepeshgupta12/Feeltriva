import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import {
  ReviewApiError,
  type DecisionResult,
  type LiveReviewApi,
  type ReviewItem,
  type ReviewNoteRecord,
  type ReviewState,
} from '@/api/liveReview';
import { App } from '@/App';
import { AppProviders } from '@/state/AppProviders';
import { createAppServices } from '@/state/services';
import { TEST_CONFIG } from '@/test/harness';

/** A review service in memory: one repeated column heading, one vocabulary link, one statement with a claim. */
function fakeApi(reviewer: string | null = 'tester') {
  const rows: Record<string, ReviewItem[]> = {
    '/feature-mappings': [
      {
        mapping_id: 'fm_1',
        source_id: 'src_sample',
        file_path: 'sample.csv',
        column_index: 3,
        original_term: 'itching',
        proposed_canonical_id: 'feat_itching',
        zero_semantics: 'unknown',
        review_status: 'pending',
        conflicts: { repeated_header: true, repeated_positions: [3, 9], disagreement_rows: 12 },
      },
    ],
    '/terminology-links': [
      {
        link_id: 'tl_1',
        subject: { type: 'disease', id: 'dis_1', term: 'pretend ache' },
        system: 'ICD-11 MMS',
        system_version: 'test',
        code: 'ZZ00.0',
        title: 'Pretend ache of the left side',
        match_method: 'exact_synonym',
        detail: {},
        review_status: 'pending',
        reviewer: null,
      },
    ],
    '/link-proposals': [
      {
        proposal_id: 'lp_close',
        subject: { type: 'disease', id: 'dis_1', term: 'pretend ache' },
        system: 'ICD-11 MMS',
        system_version: 'test',
        basis: 'close_search_result',
        meaning: 'Close search result, no exact name',
        reason: 'no ICD-11 entity carries exactly this name; this is the best result of the name search',
        term: { code: 'ZZ10.Z', title: 'Pretend aching, unspecified', uri: 'http://example.invalid/ZZ10.Z' },
        can_be_confirmed: true,
        detail: { score: 0.93 },
        review_status: 'pending',
        reviewer: null,
        link: null,
      },
      {
        proposal_id: 'lp_none',
        subject: { type: 'feature', id: 'feat_1', term: 'pretend glow' },
        system: 'HPO',
        system_version: 'test',
        basis: 'no_term_near',
        meaning: 'No term near our name',
        reason: 'no term carries this name or shares half of its words',
        term: null,
        can_be_confirmed: false,
        detail: {},
        review_status: 'pending',
        reviewer: null,
        link: null,
      },
    ],
    '/rules': [
      {
        rule_id: 'urg.sample.hat',
        bundle_id: 'sample-rules',
        priority: 10,
        condition_ast: { op: 'present', feature: 'feat_hat' },
        action: { type: 'escalate', urgency: 'emergency', text: 'Sample text shown to the person (invented).' },
        review_status: 'pending',
        decided_by: null,
        decision_note: null,
        in_words_unavailable: null,
        in_words: {
          number: 1,
          of: 2,
          title: 'A pretend hat with a scarf',
          level: 'Emergency',
          level_meaning: 'The published advice is an ambulance or an emergency department now.',
          fires_when: [
            { depth: 0, text: 'all of these together:', heads_a_group: true },
            { depth: 1, text: '“a pretend hat”', heads_a_group: false },
            { depth: 1, text: 'any one of: “a scarf”; “a coat”', heads_a_group: false },
          ],
          shown: 'Sample text shown to the person (invented).',
          why_this_level: 'The invented advice names exactly this combination.',
          checked_with: {
            fires: 'recorded as present “a pretend hat”; “a scarf”',
            does_not_fire: 'recorded as present “a pretend hat”; recorded as absent “a scarf”; “a coat”',
          },
          basis: [
            {
              publisher: 'Sample Publisher',
              title: 'Hats and scarves',
              url: 'https://example.invalid/hats',
              page_reviewed: '01 January 2026',
              quotes: ['Wear a hat when it is cold.'],
            },
          ],
        },
      },
      {
        rule_id: 'urg.sample.coat',
        bundle_id: 'sample-rules',
        priority: 20,
        condition_ast: { op: 'present', feature: 'feat_coat' },
        action: { type: 'escalate', urgency: 'urgent', text: 'Another sample text (invented).' },
        review_status: 'pending',
        decided_by: null,
        decision_note: null,
        in_words: null,
        in_words_unavailable: 'The rule file this rule set was stored from is not on this installation.',
      },
    ],
    '/diseases': [
      {
        disease_id: 'dis_flu',
        name: 'flu',
        definition: null,
        merged_into: null,
        review_status: 'pending',
        decided_by: null,
        decision_note: null,
      },
    ],
    '/evidence': [
      {
        evidence_id: 'ev_1',
        disease: { id: 'dis_flu', term: 'flu' },
        feature: { id: 'feat_cough', term: 'cough' },
        relationship: 'co_occurs_in_source_sample',
        evidence_type: 'dataset_cooccurrence',
        context: { source: 'sample.zip/data.csv', exact_duplicate_rows_with_label: 12 },
        frequency: 0.528158,
        frequency_denominator: 657,
        review_status: 'pending',
      },
    ],
    '/claims': [
      {
        statement_id: 'st_1',
        statement_type: 'symptom',
        disease: { id: 'dis_1', term: 'pretend ache' },
        text: 'Signs include a hat and a scarf.',
        has_a_mark: true,
        claims: [
          {
            claim_id: 'cl_s',
            kind: 'sentence',
            text: 'Signs include a hat and a scarf.',
            cues: {},
            marks: [],
            rule: 'test:sentence',
            review_status: 'pending',
            applicability: null,
            proposed_feature: null,
            items: [
              {
                claim_id: 'cl_hat',
                kind: 'list_item',
                text: 'a hat',
                cues: { first_item_preposition: ['of'] },
                marks: ['first_item_preposition'],
                rule: 'test:enumeration',
                review_status: 'pending',
                applicability: null,
                proposed_feature: { id: 'feat_hat', term: 'hat' },
              },
            ],
          },
        ],
      },
    ],
  };
  const notes: ReviewNoteRecord[] = [];
  const requests: Array<{ path: string; params: unknown }> = [];
  const decide = vi.fn((targetType: string, targetId: string, note: string, status?: ReviewState) => {
    if (targetType === 'terminology_link' && status === 'approved') {
      return Promise.reject(
        new ReviewApiError(
          409,
          'general_term_is_default',
          'This term also has the more general candidate "Pretend ache".',
        ),
      );
    }
    notes.push({
      note_id: `n${notes.length + 1}`,
      reviewer: `dev-reviewer:${reviewer}`,
      note,
      status_change: status ?? null,
      at: '2026-11-24T10:00:00+00:00',
    });
    for (const list of Object.values(rows)) {
      for (const row of list) {
        if (status && [row.mapping_id, row.link_id, row.proposal_id].includes(targetId)) {
          row.review_status = status;
        }
      }
    }
    const result: DecisionResult = {
      target_type: targetType,
      target_id: targetId,
      previous_status: 'pending',
      review_status: status ?? 'pending',
      reviewer: `dev-reviewer:${reviewer}`,
    };
    return Promise.resolve(result);
  });
  const decideMany = vi.fn((targetType: string, targetIds: readonly string[], _note: string, status: ReviewState) => {
    if (targetType === 'terminology_link' && status === 'approved') {
      return Promise.reject(
        new ReviewApiError(
          409,
          'general_term_is_default',
          'Nothing was changed. The row tl_1 cannot take this decision: the general term is the default.',
        ),
      );
    }
    for (const list of Object.values(rows)) {
      for (const row of list) {
        if ([row.mapping_id, row.link_id, row.proposal_id].some((id) => targetIds.includes(String(id)))) {
          row.review_status = status;
        }
      }
    }
    return Promise.resolve({
      target_type: targetType,
      review_status: status,
      decided: targetIds.length,
      reviewer: `dev-reviewer:${reviewer}`,
    });
  });
  // Published versions (M2.4h): one list of names is published; its working set has changed since.
  const published: ReviewItem[] = [
    {
      release_id: 'names-sample.r1',
      number: 1,
      is_current: true,
      features: 3,
      diseases: 0,
      disease_mappings: 0,
      feature_mappings: 0,
      published_by: 'dev-reviewer:tester',
      published_at: '2026-11-24T07:04:04+00:00',
    },
  ];
  const post = vi.fn((path: string, body: Record<string, unknown>) => {
    if (path === '/mapping-releases') {
      for (const release of published) {
        release.is_current = false;
      }
      published.push({ ...published[0], release_id: 'names-sample.r2', number: 2, is_current: true, features: 4 });
      return Promise.resolve({ release_id: 'names-sample.r2' });
    }
    if (path === '/disease-merges') {
      if (body.target_disease_id === 'dis_flu') {
        return Promise.reject(new ReviewApiError(409, 'same_label', 'A label cannot be merged into itself.'));
      }
      (rows['/diseases'] ?? []).forEach((row) => {
        row.merged_into = body.target_disease_id;
      });
      return Promise.resolve({ disease_id: 'dis_flu', merged_into: body.target_disease_id });
    }
    if (path === '/mapping-releases/current') {
      for (const release of published) {
        release.is_current = release.release_id === body.release_id;
      }
      return Promise.resolve({ release_id: body.release_id });
    }
    return Promise.reject(new ReviewApiError(409, 'release_not_publishable', 'This release cannot be published.'));
  });
  const gets: Record<string, () => Record<string, unknown>> = {
    '/working-sets': () => ({
      rule_sets: [{ id: 'fixture-rules' }],
      name_lists: [{ id: 'names-sample' }],
      knowledge_sets: [{ id: 'texts-sample' }],
    }),
    '/mapping-releases/preview': () =>
      published.length > 1
        ? { publishable: false, problems: [], same_as_release: 'names-sample.r2', would_be_number: 3 }
        : {
            publishable: true,
            problems: [],
            same_as_release: null,
            would_be_number: 2,
            features: 4,
            diseases: 0,
            disease_mappings: 0,
            feature_mappings: 0,
            unresolved: { features: 7, diseases: 0 },
          },
    '/knowledge-releases/preview': () => ({
      publishable: false,
      problems: ['no statement and no evidence is approved'],
      same_as_release: null,
      would_be_number: 1,
    }),
    '/serving-bundle': () => ({ assembled: false, problems: ['no rule release is current'] }),
    '/diseases/dis_flu/history': () => ({ disease_id: 'dis_flu', synonyms: [], merged_labels: [], history: [] }),
  };
  const api: LiveReviewApi = {
    reviewer,
    post,
    get: (path: string) =>
      gets[path]
        ? Promise.resolve(gets[path]())
        : Promise.resolve({ sources: 14, disease_candidates: 960, statements: { pending: 2952 } }),
    list: (path, params) => {
      requests.push({ path, params });
      const items = structuredClone(path === '/mapping-releases' ? published : (rows[path] ?? []));
      return Promise.resolve({
        total: items.length,
        items,
        marks: { first_item_preposition: 'The first item of this list starts with a few shared words.' },
      });
    },
    notes: () => Promise.resolve(structuredClone(notes)),
    decide,
    decideMany,
    setApplicability: vi.fn(() => Promise.resolve({})),
  };
  return { api, decide, decideMany, post, requests };
}

function renderLive(route: string, api: LiveReviewApi) {
  const config = { ...TEST_CONFIG, serviceMode: 'http' as const, devAuth: true, devReviewer: api.reviewer };
  const services = createAppServices(config, { liveReview: api });
  const user = userEvent.setup();
  render(
    <MemoryRouter initialEntries={[route]}>
      <AppProviders services={services}>
        <App />
      </AppProviders>
    </MemoryRouter>,
  );
  return user;
}

describe('the review workspace against the review service', () => {
  it('shows a repeated column heading as stored and records a note under the reviewer', async () => {
    const { api, decide, requests } = fakeApi();
    const user = renderLive('/review/data', api);

    expect(await screen.findByRole('heading', { name: 'Repeated columns in the data files' })).toBeInTheDocument();
    expect(screen.getByText(/Your decisions are saved under the name tester/)).toBeInTheDocument();
    // In live mode nothing is a sample scenario, and the notice at the top says so.
    expect(screen.getByRole('region', { name: 'Demo notice' })).toHaveTextContent(
      'Test version · Connected to the service on this computer · Not a medical assessment.',
    );
    expect(screen.queryByText(/Sample scenarios/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Matches to reference lists' })).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Review itching (column 3)' }));
    // The list asked the service for the repeated headings only.
    expect(requests[0]).toMatchObject({
      path: '/feature-mappings',
      params: { conflicts_only: true, limit: 25, offset: 0 },
    });

    const drawer = await screen.findByRole('dialog');
    expect(
      within(drawer).getByText('The heading is repeated at columns 3, 9; the columns disagree in 12 rows'),
    ).toBeInTheDocument();
    expect(await within(drawer).findByText('No notes yet.')).toBeInTheDocument();
    // A note is required: nothing is sent without one.
    await user.click(within(drawer).getByRole('button', { name: 'Save note' }));
    expect(within(drawer).getByRole('alert')).toHaveTextContent('Write a note first.');
    expect(decide).not.toHaveBeenCalled();

    await user.type(within(drawer).getByLabelText('Note (required)'), 'Columns 3 and 9 disagree in 12 rows.');
    await user.click(within(drawer).getByRole('button', { name: 'Save note' }));
    expect(decide).toHaveBeenCalledWith('feature_mapping', 'fm_1', 'Columns 3 and 9 disagree in 12 rows.', undefined);
    // The saved note is read back from the service and shown with the reviewer's name.
    expect(await within(drawer).findByText('Columns 3 and 9 disagree in 12 rows.')).toBeInTheDocument();
    expect(within(drawer).getByText(/Note · dev-reviewer:tester/)).toBeInTheDocument();
    expect(within(drawer).getByRole('status')).toHaveTextContent('Note saved under tester.');

    // A decision is recorded the same way and the row shows its new status.
    await user.type(within(drawer).getByLabelText('Note (required)'), 'Both columns are kept.');
    await user.click(within(drawer).getByRole('button', { name: 'Approve' }));
    expect(decide).toHaveBeenLastCalledWith('feature_mapping', 'fm_1', 'Both columns are kept.', 'approved');
    expect(await within(drawer).findByText('Recorded: Approved, under tester.')).toBeInTheDocument();
    expect(within(drawer).getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it('shows the reason when the service refuses a decision', async () => {
    const { api } = fakeApi();
    const user = renderLive('/review/links', api);

    await user.click(
      await screen.findByRole('button', { name: /Review pretend ache → Pretend ache of the left side/ }),
    );
    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('ZZ00.0')).toBeInTheDocument(); // codes are for reviewers
    await user.type(within(drawer).getByLabelText('Note (required)'), 'The source names the left side.');
    await user.click(within(drawer).getByRole('button', { name: 'Approve' }));
    expect(await within(drawer).findByRole('alert')).toHaveTextContent(
      'This term also has the more general candidate "Pretend ache".',
    );
  });

  it('lists a statement with its sentence, the items of its list, their marks and proposed feature', async () => {
    const { api } = fakeApi();
    const user = renderLive('/review/evidence', api);

    expect(await screen.findByRole('heading', { name: 'Texts about conditions' })).toBeInTheDocument();
    expect(await screen.findByText(/pretend ache · Symptoms · has something to check/)).toBeInTheDocument();
    expect(screen.getByText('Check: how the list is worded')).toBeInTheDocument();
    expect(screen.getByText('Symptom recognised: hat')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review claim: a hat' }));
    const drawer = await screen.findByRole('dialog');
    // The drawer says what to check for the mark, in the words the service gives.
    expect(within(drawer).getByText('The first item of this list starts with a few shared words.')).toBeInTheDocument();
    await user.type(within(drawer).getByLabelText('For whom or when this holds'), 'in winter');
    await user.click(within(drawer).getByRole('button', { name: 'Save for whom or when' }));
    expect(api.setApplicability).toHaveBeenCalledWith('cl_hat', 'in winter', 'For whom or when this holds: in winter');
  });

  it('shows a suggested match in plain words, lets a reviewer confirm it, and offers no decision without a suggestion', async () => {
    const { api, decide } = fakeApi();
    const user = renderLive('/review/suggestions', api);

    expect(await screen.findByRole('heading', { name: 'Suggested matches to check' })).toBeInTheDocument();
    expect(screen.getByText(/Nothing on this page counts as a match until a reviewer confirms it/)).toBeInTheDocument();
    expect(
      await screen.findByText('The search found an entry that comes close, but none with exactly our name'),
    ).toBeInTheDocument();
    expect(screen.getByText('No entry has this name or a similar one')).toBeInTheDocument();
    expect(screen.getByText('Not possible: nothing to confirm')).toBeInTheDocument();
    expect(screen.getByText('No decision needed')).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: 'Review pretend ache → Pretend aching, unspecified (ICD-11 MMS)' }),
    );
    let drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('ZZ10.Z')).toBeInTheDocument(); // codes are for reviewers
    expect(within(drawer).getByText('Search score 0.93 (the best possible is 1)')).toBeInTheDocument();
    expect(within(drawer).getByText('pretend ache (a condition)')).toBeInTheDocument();
    await user.type(within(drawer).getByLabelText('Note (required)'), 'It names the same condition.');
    await user.click(within(drawer).getByRole('button', { name: 'Confirm match' }));
    expect(decide).toHaveBeenLastCalledWith('link_proposal', 'lp_close', 'It names the same condition.', 'approved');
    expect(await within(drawer).findByText('Recorded: Approved, under tester.')).toBeInTheDocument();
    await user.keyboard('{Escape}');

    // A row without a suggestion takes a note, and no decision is offered for it.
    await user.click(await screen.findByRole('button', { name: 'Review pretend glow → no suggestion (HPO)' }));
    drawer = await screen.findByRole('dialog');
    expect(
      within(drawer).getByText(/There is no suggested entry to confirm or reject for this row/),
    ).toBeInTheDocument();
    expect(within(drawer).queryByRole('button', { name: 'Confirm match' })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole('button', { name: 'Reject match' })).not.toBeInTheDocument();
    expect(within(drawer).getByRole('button', { name: 'Save note' })).toBeInTheDocument();
  });

  it('shows an urgency rule in words: when it applies, what the person is told, why, and its quoted basis', async () => {
    const { api } = fakeApi();
    const user = renderLive('/review/rules', api);

    expect(await screen.findByRole('heading', { name: 'Urgency rules' })).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Review 1. A pretend hat with a scarf' }));
    let drawer = await screen.findByRole('dialog');
    expect(
      within(drawer).getByText('Emergency. The published advice is an ambulance or an emergency department now.'),
    ).toBeInTheDocument();
    // The condition, line for line as the service gives it; a line that heads a group is set apart.
    expect(within(drawer).getByText('all of these together:')).toHaveClass('font-semibold');
    expect(within(drawer).getByText('“a pretend hat”')).toHaveClass('ml-5');
    expect(within(drawer).getByText('any one of: “a scarf”; “a coat”')).toBeInTheDocument();
    expect(within(drawer).getByText('Sample text shown to the person (invented).')).toBeInTheDocument();
    expect(within(drawer).getByText('The invented advice names exactly this combination.')).toBeInTheDocument();
    expect(
      within(drawer).getByText('The rule applies: recorded as present “a pretend hat”; “a scarf”.'),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByText(
        'The rule does not apply: recorded as present “a pretend hat”; recorded as absent “a scarf”; “a coat”.',
      ),
    ).toBeInTheDocument();
    expect(within(drawer).getByRole('link', { name: 'Hats and scarves' })).toHaveAttribute(
      'href',
      'https://example.invalid/hats',
    );
    expect(within(drawer).getByText(/Sample Publisher,.*page last reviewed 01 January 2026:/)).toBeInTheDocument();
    expect(within(drawer).getByText('“Wear a hat when it is cold.”')).toBeInTheDocument();
    expect(within(drawer).getByText('1 of 2')).toBeInTheDocument();
    await user.keyboard('{Escape}');

    // A rule the service cannot put into words is shown as stored, with the reason.
    await user.click(await screen.findByRole('button', { name: 'Review urg.sample.coat' }));
    drawer = await screen.findByRole('dialog');
    expect(
      within(drawer).getByText('The rule file this rule set was stored from is not on this installation.'),
    ).toBeInTheDocument();
    expect(within(drawer).getByText('Another sample text (invented).')).toBeInTheDocument();
  });

  it('decides all rows shown at once after a note and a second click, and leaves out rows that take no decision', async () => {
    const { api, decideMany } = fakeApi();
    const user = renderLive('/review/suggestions', api);

    const bulk = (await screen.findByRole('heading', { name: 'Decide all the rows shown at once' })).closest('section');
    expect(bulk).not.toBeNull();
    const panel = within(bulk as HTMLElement);
    // Of the two rows shown, one has a suggestion; the other takes notes only and is not sent.
    await user.click(panel.getByRole('button', { name: 'Confirm match for the 1 row shown' }));
    expect(panel.getByRole('alert')).toHaveTextContent('Write a note first.');
    expect(decideMany).not.toHaveBeenCalled();
    await user.type(panel.getByLabelText('Note for all these rows (required)'), 'Checked as a group.');
    await user.click(panel.getByRole('button', { name: 'Confirm match for the 1 row shown' }));
    // Nothing is sent before the second click.
    expect(
      panel.getByText(/Record “Approved” for the 1 row shown\? This is saved on the real data\./),
    ).toBeInTheDocument();
    expect(decideMany).not.toHaveBeenCalled();
    await user.click(panel.getByRole('button', { name: 'Yes, record it' }));
    expect(decideMany).toHaveBeenCalledWith('link_proposal', ['lp_close'], 'Checked as a group.', 'approved');
    expect(await panel.findByText('Recorded: Approved for 1 row, under tester.')).toBeInTheDocument();
  });

  it('shows which row the service refused when it changes nothing for a whole page', async () => {
    const { api } = fakeApi();
    const user = renderLive('/review/links', api);

    const bulk = (await screen.findByRole('heading', { name: 'Decide all the rows shown at once' })).closest('section');
    const panel = within(bulk as HTMLElement);
    await user.type(panel.getByLabelText('Note for all these rows (required)'), 'All exact names.');
    await user.click(panel.getByRole('button', { name: 'Approve the 1 row shown' }));
    await user.click(panel.getByRole('button', { name: 'Yes, record it' }));
    expect(await panel.findByRole('alert')).toHaveTextContent(
      'Nothing was changed. The row tl_1 cannot take this decision: the general term is the default.',
    );
    // The list offers more rows on a page, up to the most the service decides at once.
    expect(screen.getByLabelText('Rows on a page')).toHaveValue('25');
    expect(within(screen.getByLabelText('Rows on a page')).getAllByRole('option')).toHaveLength(3);
  });

  it('publishes the next version after a note and a second click, and goes back to the earlier one', async () => {
    const { api, post } = fakeApi();
    const user = renderLive('/review/releases', api);

    expect(await screen.findByRole('heading', { name: 'Published versions' })).toBeInTheDocument();
    const names = screen.getByRole('region', { name: 'Published lists of names' });
    // The one list of names is chosen by itself; the next version and what is left out are shown.
    expect(
      await within(names).findByText(/It would be version 2 and hold: 4 symptoms and other items/),
    ).toBeInTheDocument();
    expect(
      within(names).getByText(/Left out because they still wait for a decision: 7 symptoms and other items/),
    ).toBeInTheDocument();
    // A set that cannot be published says why, in the service's words, and offers no button.
    const texts = screen.getByRole('region', { name: 'Published texts and facts' });
    expect(await within(texts).findByText('no statement and no evidence is approved')).toBeInTheDocument();
    expect(within(texts).queryByRole('button', { name: 'Publish this version' })).not.toBeInTheDocument();
    // The sample set of the tests is not offered.
    expect(
      within(screen.getByRole('region', { name: 'Published sets of urgency rules' })).getByText(
        'There is no set of rules to publish from.',
      ),
    ).toBeInTheDocument();

    await user.click(within(names).getByRole('button', { name: 'Publish this version' }));
    expect(within(names).getByText(/A published version can never be changed or removed/)).toBeInTheDocument();
    await user.click(within(names).getByRole('button', { name: 'Yes, publish it' }));
    expect(within(names).getByRole('alert')).toHaveTextContent('Write a note first.');
    expect(post).not.toHaveBeenCalled();
    await user.type(within(names).getByLabelText('Note (required)'), 'Four names checked.');
    await user.click(within(names).getByRole('button', { name: 'Yes, publish it' }));
    expect(post).toHaveBeenCalledWith('/mapping-releases', {
      mapping_release_id: 'names-sample',
      note: 'Four names checked.',
    });
    // What happened stays on the page while the lists are read again.
    expect(await screen.findByText('Published as names-sample.r2. It is the version in use now.')).toBeInTheDocument();

    // The new version is the one in use; the earlier one can be gone back to.
    const after = await screen.findByRole('region', { name: 'Published lists of names' });
    expect((await within(after).findAllByText('names-sample.r2')).length).toBeGreaterThan(0);
    expect(await within(after).findByText(/Nothing has changed since/)).toBeInTheDocument();
    await user.click(within(after).getByRole('button', { name: 'Go back to this version' }));
    await user.type(within(after).getByLabelText('Note (required)'), 'Version 2 holds a wrong name.');
    await user.click(within(after).getByRole('button', { name: 'Yes, make it the version in use' }));
    expect(post).toHaveBeenLastCalledWith('/mapping-releases/current', {
      release_id: 'names-sample.r1',
      note: 'Version 2 holds a wrong name.',
    });
    expect(await screen.findByText('names-sample.r1 is the version in use now.')).toBeInTheDocument();
  });

  it('lists the remaining review lists in plain words and opens a fact with what its count means', async () => {
    const { api } = fakeApi();
    const user = renderLive('/review/more', api);

    expect(await screen.findByRole('heading', { name: 'More lists to review' })).toBeInTheDocument();
    for (const name of [
      'Conditions',
      'Symptoms and other items',
      'Names that may mean the same',
      'Facts from the data files',
      'Parts of the text files',
      'Data sources',
      'Follow-up questions',
      'Standard replies',
      'Sets of urgency rules',
    ]) {
      expect(screen.getByRole('link', { name: new RegExp(`^${name}`) })).toBeInTheDocument();
    }
    await user.click(screen.getByRole('link', { name: /^Facts from the data files/ }));
    expect(await screen.findByRole('heading', { name: 'Facts from the data files' })).toBeInTheDocument();
    expect(screen.getByText(/It is not how common the symptom is among real patients/)).toBeInTheDocument();
    // The stored code and the share are put into words.
    const facts = await screen.findByRole('table');
    expect(within(facts).getByText('Counted in a data file')).toBeInTheDocument();
    expect(within(facts).getByText('52.8% of 657 rows with this condition')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review flu and cough' }));
    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText('sample.zip/data.csv')).toBeInTheDocument();
    expect(within(drawer).getByText('12')).toBeInTheDocument();
  });

  it('merges one condition name into another after a note and a second click, and shows a refusal', async () => {
    const { api, post } = fakeApi();
    const user = renderLive('/review/conditions', api);

    await user.click(await screen.findByRole('button', { name: 'Review flu' }));
    const drawer = await screen.findByRole('dialog');
    expect(await within(drawer).findByRole('heading', { name: 'Two names for one condition' })).toBeInTheDocument();
    await user.click(within(drawer).getByRole('button', { name: 'Merge this name into that condition' }));
    expect(within(drawer).getByRole('alert')).toHaveTextContent('Give the name in the system of the condition to keep');
    expect(post).not.toHaveBeenCalled();

    // The service refuses a merge into itself; its own words are shown.
    await user.type(within(drawer).getByLabelText('Name in the system of the condition to keep'), 'dis_flu');
    await user.type(within(drawer).getByLabelText('Note for the merge (required)'), 'Both are influenza.');
    await user.click(within(drawer).getByRole('button', { name: 'Merge this name into that condition' }));
    await user.click(within(drawer).getByRole('button', { name: 'Yes, merge it' }));
    expect(await within(drawer).findByRole('alert')).toHaveTextContent('A label cannot be merged into itself.');

    await user.clear(within(drawer).getByLabelText('Name in the system of the condition to keep'));
    await user.type(within(drawer).getByLabelText('Name in the system of the condition to keep'), 'dis_influenza');
    await user.type(
      within(drawer).getByLabelText('Name to show for it (leave empty to keep its present name)'),
      'influenza',
    );
    await user.click(within(drawer).getByRole('button', { name: 'Merge this name into that condition' }));
    await user.click(within(drawer).getByRole('button', { name: 'Yes, merge it' }));
    expect(post).toHaveBeenLastCalledWith('/disease-merges', {
      source_disease_id: 'dis_flu',
      target_disease_id: 'dis_influenza',
      note: 'Both are influenza.',
      kept_name: 'influenza',
    });
    expect(
      await within(drawer).findByText('Merged. This name is now kept as another name of that condition.'),
    ).toBeInTheDocument();
    // Once merged, the panel offers to take the name out again.
    expect(await within(drawer).findByRole('button', { name: 'Take this name out again' })).toBeInTheDocument();
  });

  it('asks the service for nothing when no reviewer sign-in is configured', async () => {
    const { api, requests } = fakeApi(null);
    renderLive('/review/data', api);

    expect(await screen.findByRole('heading', { name: 'Reviewer sign-in is not set up' })).toBeInTheDocument();
    expect(screen.getByText(/nothing in the browser decides that/)).toBeInTheDocument();
    expect(requests).toEqual([]);
  });
});
