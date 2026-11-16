import type { ApiErrorBody } from './types';

/**
 * How the UI should react to a failed call. Derived from transport status first and the
 * server `code` second; components switch on this instead of raw status numbers.
 */
export type ApiErrorKind =
  | 'network' // request never reached the service (offline, DNS, CORS, aborted connection)
  | 'timeout'
  | 'unauthenticated' // 401, or 403 with code `session_expired`: the session has ended
  | 'forbidden' // 403
  | 'not_found' // 404 (missing, deleted or not owned)
  | 'conflict' // 409 stale version, question no longer current, or questioning paused
  | 'idempotency_conflict' // 409 same Idempotency-Key, different payload
  | 'in_progress' // 409 `request_in_progress`: the same request is still being processed
  | 'validation' // 400 / 422
  | 'rate_limited' // 429
  | 'unavailable' // 503 and other 5xx
  | 'invalid_response' // 2xx body that does not match the contract
  | 'unexpected';

export interface ApiErrorInit {
  kind: ApiErrorKind;
  status: number | null;
  code: string;
  message: string;
  retryable: boolean;
  requestId?: string | null;
  retryAfterSeconds?: number | null;
  cause?: unknown;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string;
  readonly retryable: boolean;
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(init: ApiErrorInit) {
    super(init.message, init.cause === undefined ? undefined : { cause: init.cause });
    this.name = 'ApiError';
    this.kind = init.kind;
    this.status = init.status;
    this.code = init.code;
    this.retryable = init.retryable;
    this.requestId = init.requestId ?? null;
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }
}

export function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const body = value as Record<string, unknown>;
  return (
    typeof body.code === 'string' &&
    typeof body.message === 'string' &&
    typeof body.retryable === 'boolean' &&
    typeof body.request_id === 'string'
  );
}

/**
 * Maps an HTTP status (plus the server error `code`, when present) to an error kind.
 * 409 covers two different situations in the contract; an idempotency-key collision is
 * recognised by its code, everything else is treated as an observation-version conflict.
 */
export function kindForStatus(status: number, code?: string): ApiErrorKind {
  switch (status) {
    case 400:
    case 422:
      return 'validation';
    case 401:
      return 'unauthenticated';
    case 403:
      // The API reports an expired session as 403 `session_expired`.
      return code === 'session_expired' ? 'unauthenticated' : 'forbidden';
    case 404:
      return 'not_found';
    case 409:
      if (code === 'request_in_progress') {
        return 'in_progress';
      }
      // `stale_observation_version`, `question_not_current` and `questioning_paused` are all
      // resolved the same way: re-read the authoritative session and resubmit if still wanted.
      return code !== undefined && /idempot/i.test(code) ? 'idempotency_conflict' : 'conflict';
    case 429:
      return 'rate_limited';
    default:
      return status >= 500 ? 'unavailable' : 'unexpected';
  }
}

/** Fallback retryability when the server did not send a parseable Error body. */
export function defaultRetryable(kind: ApiErrorKind): boolean {
  return (
    kind === 'network' ||
    kind === 'timeout' ||
    kind === 'rate_limited' ||
    kind === 'unavailable' ||
    kind === 'in_progress'
  );
}

/** Normalises anything thrown by a service call into an ApiError. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }
  return new ApiError({
    kind: 'unexpected',
    status: null,
    code: 'unexpected_error',
    message: error instanceof Error ? error.message : 'Unexpected error',
    retryable: false,
    cause: error,
  });
}

/**
 * Whether a retry of the *same payload* should reuse its Idempotency-Key.
 * True when the outcome on the server is unknown or explicitly retryable; false when the
 * server gave a definitive answer for that payload (the next attempt is a new operation).
 */
export function shouldKeepIdempotencyKey(error: ApiError): boolean {
  switch (error.kind) {
    case 'network':
    case 'timeout':
    case 'rate_limited':
    case 'unavailable':
    case 'in_progress':
      return true;
    case 'conflict':
    case 'idempotency_conflict':
    case 'validation':
    case 'unauthenticated':
    case 'forbidden':
    case 'not_found':
      return false;
    default:
      return error.retryable;
  }
}
