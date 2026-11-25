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
  const api: LiveReviewApi = {
    reviewer,
    get: () => Promise.resolve({ sources: 14, disease_candidates: 960, statements: { pending: 2952 } }),
    list: (path, params) => {
      requests.push({ path, params });
      const items = structuredClone(rows[path] ?? []);
      return Promise.resolve({
        total: items.length,
        items,
        marks: { first_item_preposition: 'The first item of this list holds a preposition.' },
      });
    },
    notes: () => Promise.resolve(structuredClone(notes)),
    decide,
    setApplicability: vi.fn(() => Promise.resolve({})),
  };
  return { api, decide, requests };
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

    expect(await screen.findByRole('heading', { name: 'Data quality: repeated column headings' })).toBeInTheDocument();
    expect(screen.getByText(/Decisions are recorded under tester/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Vocabulary links' })).toBeInTheDocument();
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

    expect(await screen.findByRole('heading', { name: 'Statements and claims' })).toBeInTheDocument();
    expect(await screen.findByText(/pretend ache · symptom · has a mark to check/)).toBeInTheDocument();
    expect(screen.getByText('Check: first item preposition')).toBeInTheDocument();
    expect(screen.getByText('Proposed feature: hat')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Review claim: a hat' }));
    const drawer = await screen.findByRole('dialog');
    // The drawer says what to check for the mark, in the words the service gives.
    expect(within(drawer).getByText('The first item of this list holds a preposition.')).toBeInTheDocument();
    await user.type(within(drawer).getByLabelText('For whom or when this holds'), 'in winter');
    await user.click(within(drawer).getByRole('button', { name: 'Save applicability' }));
    expect(api.setApplicability).toHaveBeenCalledWith('cl_hat', 'in winter', 'Applicability recorded: in winter');
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
    expect(within(drawer).getByText('Search score 0.93 out of 1')).toBeInTheDocument();
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

  it('asks the service for nothing when no reviewer sign-in is configured', async () => {
    const { api, requests } = fakeApi(null);
    renderLive('/review/data', api);

    expect(await screen.findByRole('heading', { name: 'Reviewer sign-in is not configured' })).toBeInTheDocument();
    expect(screen.getByText(/nothing in the browser is authorization/)).toBeInTheDocument();
    expect(requests).toEqual([]);
  });
});
