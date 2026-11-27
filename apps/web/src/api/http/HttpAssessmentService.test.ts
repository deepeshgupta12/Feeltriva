import { describe, expect, it, vi } from 'vitest';

import { ApiError } from '../errors';
import type { Session } from '../types';
import { createAuthTokenProvider, createDevAuthTokenProvider } from './auth';
import { HttpAssessmentService } from './HttpAssessmentService';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';

const session: Session = {
  session_id: SESSION_ID,
  observation_version: 1,
  state: 'clarifying',
  expires_at: '2030-01-01T00:00:00Z',
  observations: [],
};

function json(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });
}

function errorBody(code: string, retryable = false) {
  return { code, message: `message for ${code}`, retryable, request_id: 'req-123' };
}

type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

function createService(fetchMock: FetchMock, token: string | null = 'dev:test-subject') {
  return new HttpAssessmentService({
    baseUrl: 'http://api.test/',
    getAuthToken: () => token,
    fetchImpl: fetchMock,
  });
}

function headersOf(fetchMock: FetchMock, call: number): Record<string, string> {
  const init = fetchMock.mock.calls[call]?.[1];
  return (init?.headers ?? {}) as Record<string, string>;
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error('Expected the request to fail');
}

describe('HttpAssessmentService requests', () => {
  it('targets the OpenAPI paths with bearer auth and JSON bodies', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(session, 201)));
    const service = createService(fetchMock);

    await service.startSession({ consent_version: 'v1', demographics: { age_years: 40 } });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe('http://api.test/v1/sessions');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({ consent_version: 'v1', demographics: { age_years: 40 } });
    expect(headersOf(fetchMock, 0).Authorization).toBe('Bearer dev:test-subject');
    expect(headersOf(fetchMock, 0)['Content-Type']).toBe('application/json');
    // Health data is never cached and ambient cookies are never sent.
    expect(init?.cache).toBe('no-store');
    expect(init?.credentials).toBe('omit');
  });

  it('sends an Idempotency-Key on every mutation and none on reads', async () => {
    const fetchMock = vi.fn<typeof fetch>((_url, init) =>
      Promise.resolve(
        init?.method === 'DELETE'
          ? json({ session_id: SESSION_ID, status: 'deletion_scheduled', receipt_id: 'r1' })
          : json(session),
      ),
    );
    const service = createService(fetchMock);

    await service.getSession(SESSION_ID);
    await service.submitObservations(SESSION_ID, { observation_version: 1, text: 'sample text' });
    await service.submitAnswer(SESSION_ID, { observation_version: 1, question_id: 'q1', answer: 'yes' });
    await service.deleteSession(SESSION_ID);

    expect(headersOf(fetchMock, 0)['Idempotency-Key']).toBeUndefined();
    const keys = [1, 2, 3].map((call) => headersOf(fetchMock, call)['Idempotency-Key']);
    for (const key of keys) {
      expect(key).toMatch(/^[0-9a-f-]{36}$/);
    }
    expect(new Set(keys).size).toBe(3);
  });

  it('sends no Authorization header when no token is available', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(session)));
    const service = createService(fetchMock, null);

    await service.getSession(SESSION_ID);

    expect(headersOf(fetchMock, 0).Authorization).toBeUndefined();
  });

  it('carries observation_version as a query parameter for next-question', async () => {
    const question = {
      question_id: 'q1',
      wording: 'Sample?',
      answer_schema: { type: 'yes_no_unsure' },
      observation_version: 4,
    };
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(question)));
    const service = createService(fetchMock);

    const result = await service.getNextQuestion(SESSION_ID, 4);

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      `http://api.test/v1/sessions/${SESSION_ID}/next-question?observation_version=4`,
    );
    expect(result?.question_id).toBe('q1');
  });
});

describe('HttpAssessmentService idempotency', () => {
  it('reuses the same key when the same payload is retried after a 503', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(errorBody('assessment_unavailable', true), 503))
      .mockResolvedValueOnce(json(session));
    const service = createService(fetchMock);
    const payload = { observation_version: 1, text: 'sample text' };

    const first = await rejection(service.submitObservations(SESSION_ID, payload));
    expect(first.kind).toBe('unavailable');
    await service.submitObservations(SESSION_ID, payload);

    expect(headersOf(fetchMock, 0)['Idempotency-Key']).toBeDefined();
    expect(headersOf(fetchMock, 1)['Idempotency-Key']).toBe(headersOf(fetchMock, 0)['Idempotency-Key']);
  });

  it('reuses the same key when the network fails and the request is retried', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(json(session));
    const service = createService(fetchMock);
    const payload = { observation_version: 1, question_id: 'q1', answer: 'no' };

    const first = await rejection(service.submitAnswer(SESSION_ID, payload));
    expect(first.kind).toBe('network');
    expect(first.retryable).toBe(true);
    await service.submitAnswer(SESSION_ID, payload);

    expect(headersOf(fetchMock, 1)['Idempotency-Key']).toBe(headersOf(fetchMock, 0)['Idempotency-Key']);
  });

  it('uses a new key for a new operation, including the same payload sent again after success', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(session)));
    const service = createService(fetchMock);

    await service.submitObservations(SESSION_ID, { observation_version: 1, text: 'first' });
    await service.submitObservations(SESSION_ID, { observation_version: 1, text: 'second' });
    await service.submitObservations(SESSION_ID, { observation_version: 1, text: 'second' });

    const keys = [0, 1, 2].map((call) => headersOf(fetchMock, call)['Idempotency-Key']);
    expect(new Set(keys).size).toBe(3);
  });

  it('does not keep a key after a version conflict: the resubmission is a new operation', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(errorBody('stale_observation_version'), 409))
      .mockResolvedValueOnce(json(session));
    const service = createService(fetchMock);
    const payload = { observation_version: 1, text: 'sample text' };

    await rejection(service.submitObservations(SESSION_ID, payload));
    await service.submitObservations(SESSION_ID, payload);

    expect(headersOf(fetchMock, 1)['Idempotency-Key']).not.toBe(headersOf(fetchMock, 0)['Idempotency-Key']);
  });

  it('suppresses a duplicate submit while the first is still pending', async () => {
    let release: (response: Response) => void = () => {};
    const fetchMock = vi.fn<typeof fetch>(
      () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    );
    const service = createService(fetchMock);
    const payload = { observation_version: 1, text: 'sample text' };

    const first = service.submitObservations(SESSION_ID, payload);
    const second = service.submitObservations(SESSION_ID, payload);
    await Promise.resolve();
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    release(json(session));
    await expect(first).resolves.toMatchObject({ session_id: SESSION_ID });
    await expect(second).resolves.toMatchObject({ session_id: SESSION_ID });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('HttpAssessmentService responses', () => {
  it('treats 204 from next-question as "no question", not an error', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(new Response(null, { status: 204 })));
    const service = createService(fetchMock);

    await expect(service.getNextQuestion(SESSION_ID, 2)).resolves.toBeNull();
  });

  it('rejects a 204 where a body is required', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(new Response(null, { status: 204 })));
    const service = createService(fetchMock);

    const error = await rejection(service.getSession(SESSION_ID));
    expect(error.kind).toBe('invalid_response');
  });

  it('maps 409 to a version conflict using the Error schema', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('stale_observation_version'), 409)));
    const service = createService(fetchMock);

    const error = await rejection(service.assessSession(SESSION_ID, { observation_version: 1 }));

    expect(error).toMatchObject({
      kind: 'conflict',
      status: 409,
      code: 'stale_observation_version',
      message: 'message for stale_observation_version',
      retryable: false,
      requestId: 'req-123',
    });
  });

  it.each(['stale_observation_version', 'question_not_current', 'questioning_paused'])(
    'treats 409 %s as a conflict that needs the session re-read',
    async (code) => {
      const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody(code), 409)));
      const error = await rejection(
        createService(fetchMock).submitAnswer(SESSION_ID, { observation_version: 1, question_id: 'q1', answer: 'yes' }),
      );
      expect(error.kind).toBe('conflict');
    },
  );

  it('treats 403 session_expired as an ended session, not as a permission problem', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('session_expired'), 403)));
    const error = await rejection(createService(fetchMock).getSession(SESSION_ID));
    expect(error.kind).toBe('unauthenticated');
    expect(error.status).toBe(403);
  });

  it('keeps the key and asks for a retry when the same request is still in progress', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(json(errorBody('request_in_progress', true), 409))
      .mockResolvedValueOnce(json(session));
    const service = createService(fetchMock);
    const payload = { observation_version: 1, text: 'sample text' };

    const error = await rejection(service.submitObservations(SESSION_ID, payload));
    expect(error).toMatchObject({ kind: 'in_progress', retryable: true });
    await service.submitObservations(SESSION_ID, payload);
    expect(headersOf(fetchMock, 1)['Idempotency-Key']).toBe(headersOf(fetchMock, 0)['Idempotency-Key']);
  });

  it('distinguishes an idempotency-key conflict from a version conflict', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('idempotency_key_conflict'), 409)));
    const service = createService(fetchMock);

    const error = await rejection(service.assessSession(SESSION_ID, { observation_version: 1 }));
    expect(error.kind).toBe('idempotency_conflict');
  });

  it('maps 503 to "unavailable" and keeps the server retryable flag and request id', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('assessment_unavailable', true), 503)));
    const service = createService(fetchMock);

    const error = await rejection(service.assessSession(SESSION_ID, { observation_version: 1 }));

    expect(error).toMatchObject({ kind: 'unavailable', status: 503, retryable: true, requestId: 'req-123' });
  });

  it.each([
    [401, 'unauthenticated'],
    [403, 'forbidden'],
    [404, 'not_found'],
    [422, 'validation'],
    [400, 'validation'],
    [429, 'rate_limited'],
    [500, 'unavailable'],
  ] as const)('maps HTTP %i to "%s"', async (status, kind) => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('some_code'), status)));
    const service = createService(fetchMock);

    const error = await rejection(service.getSession(SESSION_ID));
    expect(error.kind).toBe(kind);
    expect(error.status).toBe(status);
  });

  it('reads the current assessment, and takes "none for these details" as an answer, not a failure', async () => {
    const none = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('no_current_assessment'), 404)));
    await expect(createService(none).getCurrentAssessment(SESSION_ID)).resolves.toBeNull();
    const [url, init] = none.mock.calls[0]!;
    expect(url).toBe(`http://api.test/v1/sessions/${SESSION_ID}/assessment`);
    expect(init?.method).toBe('GET');
    expect(headersOf(none, 0)['Idempotency-Key']).toBeUndefined();
    // A session that is missing answers 404 as well, with another code: that stays a failure.
    const gone = vi.fn<typeof fetch>(() => Promise.resolve(json(errorBody('session_not_found'), 404)));
    expect((await rejection(createService(gone).getCurrentAssessment(SESSION_ID))).kind).toBe('not_found');
  });

  it('reads Retry-After on 429', async () => {
    const fetchMock = vi.fn<typeof fetch>(() =>
      Promise.resolve(json(errorBody('rate_limited', true), 429, { 'Retry-After': '12' })),
    );
    const service = createService(fetchMock);

    const error = await rejection(service.getSession(SESSION_ID));
    expect(error.retryAfterSeconds).toBe(12);
  });

  it('falls back safely when an error response is not the Error schema', async () => {
    const fetchMock = vi.fn<typeof fetch>(() =>
      Promise.resolve(new Response('<html>Bad gateway</html>', { status: 502 })),
    );
    const service = createService(fetchMock);

    const error = await rejection(service.getSession(SESSION_ID));
    expect(error).toMatchObject({ kind: 'unavailable', status: 502, code: 'http_502', retryable: true });
  });

  it('rejects a 2xx body that does not match the contract instead of rendering it', async () => {
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json({ session_id: SESSION_ID, state: 'clarifying' })));
    const service = createService(fetchMock);

    const error = await rejection(service.getSession(SESSION_ID));
    expect(error.kind).toBe('invalid_response');
  });

  it('rejects an assessment with more than three candidates', async () => {
    const candidate = {
      disease_id: 'd',
      name: 'n',
      explanation: 'e',
      supporting_observation_ids: [],
      conflicting_observation_ids: [],
      evidence_ids: [],
    };
    const assessment = {
      assessment_id: 'a',
      session_id: SESSION_ID,
      observation_version: 1,
      status: 'provisional',
      urgency: 'not_assessed',
      candidates: [candidate, candidate, candidate, candidate],
      unknowns: [],
      next_action: { type: 'show_summary', text: 't' },
      evidence_ids: [],
      versions: { knowledge: null, rules: null, model: null, prompt: null },
      evidence: [],
    };
    const fetchMock = vi.fn<typeof fetch>(() => Promise.resolve(json(assessment)));
    const service = createService(fetchMock);

    const error = await rejection(service.assessSession(SESSION_ID, { observation_version: 1 }));
    expect(error.kind).toBe('invalid_response');
  });
});

describe('dev auth token provider', () => {
  it('issues one anonymous dev:<uuid> token per provider and holds it in memory only', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const provider = createDevAuthTokenProvider();

    const first = await provider();
    const second = await provider();

    expect(first).toMatch(/^dev:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(second).toBe(first);
    expect(await createDevAuthTokenProvider()()).not.toBe(first);
    expect(setItem).not.toHaveBeenCalled();
  });

  it('does not fake a token when dev auth is off', async () => {
    expect(await createAuthTokenProvider({ devAuth: false })()).toBeNull();
    expect(await createAuthTokenProvider({ devAuth: true })()).toMatch(/^dev:/);
  });
});
