import type { AssessmentService } from '../assessmentService';
import {
  ApiError,
  defaultRetryable,
  isApiErrorBody,
  kindForStatus,
  shouldKeepIdempotencyKey,
  toApiError,
} from '../errors';
import { IdempotencyKeyStore, MutationGate, operationFingerprint } from '../idempotency';
import type {
  AnswerSubmit,
  Assessment,
  AssessmentRequest,
  DeletionReceipt,
  ObservationSubmit,
  Question,
  Session,
  SessionCreate,
  Summary,
} from '../types';
import { parseAssessment, parseDeletionReceipt, parseQuestion, parseSession, parseSummary } from '../validate';
import type { AuthTokenProvider } from './auth';

export interface HttpAssessmentServiceOptions {
  /** e.g. http://localhost:8000 — no trailing slash needed. */
  baseUrl: string;
  /** Supplies the bearer token; see src/api/http/auth.ts. */
  getAuthToken: AuthTokenProvider;
  /** Injectable for tests. Defaults to the global fetch. */
  fetchImpl?: typeof fetch;
  idempotencyKeys?: IdempotencyKeyStore;
  /** Per-request timeout. */
  timeoutMs?: number;
}

interface RequestOptions<T> {
  method: 'GET' | 'POST' | 'DELETE';
  path: string;
  query?: Record<string, string>;
  body?: unknown;
  /** Mutations carry an Idempotency-Key and are de-duplicated while in flight. */
  mutation: boolean;
  /** Parses a 2xx JSON body. */
  parse: (payload: unknown) => T;
  /** Value for HTTP 204. When omitted, 204 is a contract violation. */
  onNoContent?: () => T;
}

const DEFAULT_TIMEOUT_MS = 30_000;

/**
 * REST adapter for the FastAPI assessment service (specs/openapi.json).
 *
 * It only transports and validates: no clinical logic, no fallbacks that invent a result.
 * Health data passes through memory only; nothing is cached or written to browser storage.
 */
export class HttpAssessmentService implements AssessmentService {
  private readonly baseUrl: string;
  private readonly getAuthToken: AuthTokenProvider;
  private readonly fetchImpl: typeof fetch;
  private readonly mutations: MutationGate;
  private readonly timeoutMs: number;

  constructor(options: HttpAssessmentServiceOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.getAuthToken = options.getAuthToken;
    this.fetchImpl = options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
    this.mutations = new MutationGate(options.idempotencyKeys ?? new IdempotencyKeyStore());
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  }

  startSession(input: SessionCreate): Promise<Session> {
    return this.request({
      method: 'POST',
      path: '/v1/sessions',
      body: input,
      mutation: true,
      parse: parseSession,
    });
  }

  getSession(sessionId: string): Promise<Session> {
    return this.request({
      method: 'GET',
      path: sessionPath(sessionId),
      mutation: false,
      parse: parseSession,
    });
  }

  submitObservations(sessionId: string, input: ObservationSubmit): Promise<Session> {
    return this.request({
      method: 'POST',
      path: `${sessionPath(sessionId)}/observations`,
      body: input,
      mutation: true,
      parse: parseSession,
    });
  }

  submitAnswer(sessionId: string, input: AnswerSubmit): Promise<Session> {
    return this.request({
      method: 'POST',
      path: `${sessionPath(sessionId)}/answers`,
      body: input,
      mutation: true,
      parse: parseSession,
    });
  }

  assessSession(sessionId: string, input: AssessmentRequest): Promise<Assessment> {
    return this.request({
      method: 'POST',
      path: `${sessionPath(sessionId)}/assessments`,
      body: input,
      mutation: true,
      parse: parseAssessment,
    });
  }

  getNextQuestion(sessionId: string, observationVersion: number): Promise<Question | null> {
    return this.request<Question | null>({
      method: 'GET',
      path: `${sessionPath(sessionId)}/next-question`,
      query: { observation_version: String(observationVersion) },
      mutation: false,
      parse: parseQuestion,
      // 204 = no further applicable question. This is a normal answer, not an error.
      onNoContent: () => null,
    });
  }

  createSummary(sessionId: string, input: AssessmentRequest): Promise<Summary> {
    return this.request({
      method: 'POST',
      path: `${sessionPath(sessionId)}/summary`,
      body: input,
      mutation: true,
      parse: parseSummary,
    });
  }

  deleteSession(sessionId: string): Promise<DeletionReceipt> {
    return this.request({
      method: 'DELETE',
      path: sessionPath(sessionId),
      mutation: true,
      parse: parseDeletionReceipt,
    });
  }

  private request<T>(options: RequestOptions<T>): Promise<T> {
    if (!options.mutation) {
      return this.send(options, null);
    }

    // Same payload retried -> same Idempotency-Key. New payload or completed operation ->
    // new key. An identical mutation that is still pending is not sent a second time.
    const fingerprint = operationFingerprint(options.method, options.path, options.body);
    return this.mutations.run(
      fingerprint,
      (idempotencyKey) => this.send(options, idempotencyKey),
      (error) => shouldKeepIdempotencyKey(toApiError(error)),
    );
  }

  private async send<T>(options: RequestOptions<T>, idempotencyKey: string | null): Promise<T> {
    const url = new URL(this.baseUrl + options.path);
    for (const [name, value] of Object.entries(options.query ?? {})) {
      url.searchParams.set(name, value);
    }

    const headers: Record<string, string> = { Accept: 'application/json' };
    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }
    if (idempotencyKey !== null) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    const token = await this.getAuthToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);

    let response: Response;
    try {
      response = await this.fetchImpl(url.toString(), {
        method: options.method,
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
        // The API is called with a bearer token, never ambient cookies.
        credentials: 'omit',
        // Health data must not be served from or written to the HTTP cache.
        cache: 'no-store',
      });
    } catch (error) {
      const timedOut = controller.signal.aborted;
      throw new ApiError({
        kind: timedOut ? 'timeout' : 'network',
        status: null,
        code: timedOut ? 'request_timeout' : 'network_error',
        message: timedOut ? 'The request took too long.' : 'The assessment service could not be reached.',
        retryable: true,
        cause: error,
      });
    } finally {
      clearTimeout(timer);
    }

    if (response.status === 204) {
      if (options.onNoContent) {
        return options.onNoContent();
      }
      throw new ApiError({
        kind: 'invalid_response',
        status: 204,
        code: 'invalid_response',
        message: 'The service returned no content where a response body was expected.',
        retryable: false,
      });
    }

    if (!response.ok) {
      throw await errorFromResponse(response);
    }

    let payload: unknown;
    try {
      payload = await response.json();
    } catch (error) {
      throw new ApiError({
        kind: 'invalid_response',
        status: response.status,
        code: 'invalid_response',
        message: 'The service returned a response that could not be read.',
        retryable: false,
        cause: error,
      });
    }
    return options.parse(payload);
  }
}

function sessionPath(sessionId: string): string {
  return `/v1/sessions/${encodeURIComponent(sessionId)}`;
}

function parseRetryAfter(header: string | null): number | null {
  if (!header) {
    return null;
  }
  const seconds = Number(header);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
}

/** Builds an ApiError from a non-2xx response, using the contract's Error schema when present. */
async function errorFromResponse(response: Response): Promise<ApiError> {
  const body: unknown = await response.json().catch(() => null);
  const retryAfterSeconds = parseRetryAfter(response.headers.get('Retry-After'));

  if (isApiErrorBody(body)) {
    return new ApiError({
      kind: kindForStatus(response.status, body.code),
      status: response.status,
      code: body.code,
      message: body.message,
      retryable: body.retryable,
      requestId: body.request_id,
      retryAfterSeconds,
    });
  }

  const kind = kindForStatus(response.status);
  return new ApiError({
    kind,
    status: response.status,
    code: `http_${response.status}`,
    message: `The service responded with status ${response.status}.`,
    retryable: defaultRetryable(kind),
    requestId: response.headers.get('X-Request-Id'),
    retryAfterSeconds,
  });
}
