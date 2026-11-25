import { describe, expect, it, vi } from 'vitest';

import { HttpConditionInfoService, toConditionInfo } from './conditionInfoService';

const served = {
  disease_id: 'dis_1',
  name: 'pretend ache',
  definition: 'An invented condition.',
  statements: [
    {
      statement_id: 'st_1',
      statement_type: 'description',
      text: 'It is used in tests.',
      sources: [{ record_id: 'rec_1', source_url: 'https://www.example.org/pretend-ache' }],
    },
    {
      statement_id: 'st_2',
      statement_type: 'symptom',
      text: 'A pretend hat.',
      sources: [
        { record_id: 'rec_1', source_url: 'https://www.example.org/pretend-ache' },
        { record_id: 'rec_2', source_url: null },
      ],
    },
    {
      statement_id: 'st_3',
      statement_type: 'prevention',
      text: 'Wear a scarf.',
      sources: [{ record_id: 'rec_3', source_url: 'not a url' }],
    },
    { statement_id: 'st_4', statement_type: 'prognosis', text: 'A kind the page has no section for.', sources: [] },
  ],
};

function service(response: Response | (() => Promise<Response>)) {
  const fetchImpl = vi.fn((_input: string | URL | Request, _init?: RequestInit) =>
    typeof response === 'function' ? response() : Promise.resolve(response),
  );
  const api = new HttpConditionInfoService({
    baseUrl: 'http://api.test/',
    getAuthToken: () => 'dev:someone',
    fetchImpl,
  });
  return { api, fetchImpl };
}

describe('condition information from the service', () => {
  it('lays the published texts out by section, each with the record it rests on, and adds nothing', () => {
    const info = toConditionInfo(served);
    expect(info.is_sample).toBe(false);
    expect(info.overview).toBe('An invented condition. It is used in tests.');
    expect(info.symptoms).toEqual(['A pretend hat.']);
    expect(info.management).toEqual(['Wear a scarf.']);
    expect(info.causes).toBeUndefined(); // a section without a published text is left out, never filled
    // One source line per text and record; a kind of text without a section brings no source either.
    expect(info.sources.map((source) => [source.evidence_id, source.source_title, source.excerpt])).toEqual([
      ['st_1:rec_1', 'example.org', 'It is used in tests.'],
      ['st_2:rec_1', 'example.org', 'A pretend hat.'],
      ['st_2:rec_2', 'Source record', 'A pretend hat.'],
      ['st_3:rec_3', 'Source record', 'Wear a scarf.'],
    ]);
    // No code of an outside vocabulary is part of what the page gets.
    expect(JSON.stringify(info)).not.toMatch(/ICD|MONDO|SNOMED|HP:/);
  });

  it('asks the service with the visit’s token and no cookies, and reads its answer', async () => {
    const { api, fetchImpl } = service(new Response(JSON.stringify(served), { status: 200 }));
    const info = await api.getCondition('dis 1/x');
    expect(info?.name).toBe('pretend ache');
    const [url, init] = fetchImpl.mock.calls[0] ?? [];
    expect(url).toBe('http://api.test/v1/conditions/dis%201%2Fx');
    expect(init).toMatchObject({ credentials: 'omit', headers: { Authorization: 'Bearer dev:someone' } });
  });

  it('gives nothing when the service has nothing reviewed and published, and fails loudly on any other answer', async () => {
    const missing = service(new Response(JSON.stringify({ code: 'condition_not_available' }), { status: 404 }));
    expect(await missing.api.getCondition('dis_none')).toBeNull();
    const refused = service(new Response('{}', { status: 403 }));
    await expect(refused.api.getCondition('dis_1')).rejects.toThrow('could not be loaded (403)');
  });
});
