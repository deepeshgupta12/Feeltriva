import { describe, expect, it, vi } from 'vitest';

import { field, HttpLiveReviewApi, part, ReviewApiError, texts } from './liveReview';

function answering(status: number, body: unknown) {
  return vi.fn<typeof fetch>(() =>
    Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })),
  );
}

/** The JSON body a request was sent with. */
function sent(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(init?.body as string) as Record<string, unknown>;
}

function api(fetchImpl: typeof fetch, devReviewer: string | null = 'owner') {
  return new HttpLiveReviewApi({ baseUrl: 'http://api.test', devReviewer, fetchImpl });
}

describe('HttpLiveReviewApi', () => {
  it('asks the reviewer routes with the reviewer token and only the filters that are set', async () => {
    const fetchImpl = answering(200, { total: 1, items: [{ mapping_id: 'fm_1' }], label: 'x' });
    const listed = await api(fetchImpl).list('/feature-mappings', {
      conflicts_only: true,
      q: 'itch',
      status: '',
      mark: null,
      with_feature: false,
      limit: 25,
      offset: 0,
    });
    expect(listed.total).toBe(1);
    expect(listed.items).toEqual([{ mapping_id: 'fm_1' }]);
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe(
      'http://api.test/internal/v1/review/feature-mappings?conflicts_only=true&q=itch&limit=25&offset=0',
    );
    expect(init?.method).toBe('GET');
    expect(init?.headers).toEqual({ Authorization: 'Bearer dev-reviewer:owner' });
  });

  it('counts the items when a list gives no total', async () => {
    const listed = await api(answering(200, { items: [{}, {}] })).list('/releases');
    expect(listed.total).toBe(2);
  });

  it('records a note without a status and a decision with one', async () => {
    const fetchImpl = answering(200, { review_status: 'approved', previous_status: 'pending' });
    const live = api(fetchImpl);
    await live.decide('feature_mapping', 'fm_1', 'Columns 3 and 9 disagree.');
    await live.decide('feature_mapping', 'fm_1', 'Both kept.', 'approved');
    const bodies = fetchImpl.mock.calls.map(([, init]) => sent(init));
    expect(bodies).toEqual([
      { target_type: 'feature_mapping', target_id: 'fm_1', note: 'Columns 3 and 9 disagree.' },
      { target_type: 'feature_mapping', target_id: 'fm_1', note: 'Both kept.', status: 'approved' },
    ]);
    expect(fetchImpl.mock.calls[0]![0]).toBe('http://api.test/internal/v1/review/decisions');
    expect(fetchImpl.mock.calls[0]![1]?.method).toBe('POST');
  });

  it('reads the notes of one item and records the applicability of a claim', async () => {
    const fetchImpl = answering(200, {
      items: [{ note_id: 'n1', note: 'A note', reviewer: 'r', status_change: null }],
    });
    const live = api(fetchImpl);
    expect(await live.notes('claim', 'cl 1')).toHaveLength(1);
    expect(fetchImpl.mock.calls[0]![0]).toBe(
      'http://api.test/internal/v1/review/notes?target_type=claim&target_id=cl+1',
    );
    await live.setApplicability('cl/1', 'in children', 'The sentence says so.');
    expect(fetchImpl.mock.calls[1]![0]).toBe('http://api.test/internal/v1/review/claims/cl%2F1/applicability');
    expect(sent(fetchImpl.mock.calls[1]![1])).toEqual({
      text: 'in children',
      note: 'The sentence says so.',
    });
  });

  it('passes on the code and the message with which the service refuses', async () => {
    const refused = api(
      answering(409, { code: 'general_term_is_default', message: 'This term also has the more general candidate.' }),
    ).decide('terminology_link', 'tl_1', 'Approve.', 'approved');
    await expect(refused).rejects.toMatchObject({
      name: 'ReviewApiError',
      status: 409,
      code: 'general_term_is_default',
      message: 'This term also has the more general candidate.',
    });
  });

  it('reports a service that cannot be reached, and asks nothing without a reviewer', async () => {
    const down = vi.fn<typeof fetch>(() => Promise.reject(new TypeError('failed')));
    await expect(api(down).get('/overview')).rejects.toMatchObject({ code: 'network_error' });
    const unused = answering(200, {});
    const signedOut = api(unused, null);
    expect(signedOut.reviewer).toBeNull();
    await expect(signedOut.list('/claims')).rejects.toBeInstanceOf(ReviewApiError);
    await expect(signedOut.decide('claim', 'c', 'n')).rejects.toMatchObject({ code: 'reviewer_not_configured' });
    expect(unused).not.toHaveBeenCalled();
  });
});

describe('reading loosely typed review items', () => {
  it('reads fields, nested parts and lists of texts without throwing on what is missing', () => {
    const item = { name: 'itching', count: 3, flag: true, nested: { term: 'x' }, marks: ['cut_off', 4], none: null };
    expect([
      field(item, 'name'),
      field(item, 'count'),
      field(item, 'flag'),
      field(item, 'none'),
      field(item, 'gone'),
    ]).toEqual(['itching', '3', 'true', '', '']);
    expect(field(item, 'nested')).toBe('{"term":"x"}');
    expect(part(item, 'nested')).toEqual({ term: 'x' });
    expect(part(item, 'marks')).toEqual({});
    expect(texts(item, 'marks')).toEqual(['cut_off']);
    expect(texts(item, 'name')).toEqual([]);
  });
});
