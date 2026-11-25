/**
 * The internal review workspace against the running API (live mode).
 *
 * Every call goes to a reviewer-only route of the API, which checks the reviewer role itself;
 * nothing in the browser is authorization. A decision is recorded by the API under the
 * reviewer's name, with a note, and can be read back from the API.
 *
 * Codes of outside vocabularies appear in this workspace because it is for reviewers. No
 * patient-facing screen uses this module.
 */
export type ReviewState = 'pending' | 'approved' | 'rejected' | 'retired';

export const REVIEW_STATES: readonly ReviewState[] = ['pending', 'approved', 'rejected', 'retired'];

export const REVIEW_STATE_LABELS: Record<ReviewState, string> = {
  pending: 'Waiting for a decision',
  approved: 'Approved',
  rejected: 'Rejected',
  retired: 'No longer used',
};

/** What a review list answers with. Lists differ in their extra fields, so items stay loosely typed. */
export interface ReviewList {
  total: number;
  items: ReviewItem[];
  [extra: string]: unknown;
}

export type ReviewItem = Record<string, unknown>;

export interface ReviewNoteRecord {
  note_id: string;
  reviewer: string;
  note: string;
  status_change: string | null;
  at: string | null;
}

export interface DecisionResult {
  target_type: string;
  target_id: string;
  previous_status: string;
  review_status: string;
  reviewer: string;
}

/** What the service answers when many rows were decided at once: all of them, or none. */
export interface BulkResult {
  target_type: string;
  review_status: string;
  decided: number;
  reviewer: string;
}

export type ReviewParams = Record<string, string | number | boolean | null | undefined>;

/** An answer of the API that is not a success: its own code and message, to show to the reviewer. */
export class ReviewApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ReviewApiError';
    this.status = status;
    this.code = code;
  }
}

export interface LiveReviewApi {
  /** The name decisions are recorded under, or null when no reviewer sign-in is configured. */
  readonly reviewer: string | null;
  get(path: string, params?: ReviewParams): Promise<Record<string, unknown>>;
  /** One action of the review service that is not a decision on a row: publishing, going back, merging. */
  post(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>>;
  list(path: string, params?: ReviewParams): Promise<ReviewList>;
  notes(targetType: string, targetId: string): Promise<ReviewNoteRecord[]>;
  /** Records a note; with `status`, a decision. The API requires the note in both cases. */
  decide(targetType: string, targetId: string, note: string, status?: ReviewState): Promise<DecisionResult>;
  /** One decision with one note for many rows. The service decides all of them or, if it refuses one, none. */
  decideMany(targetType: string, targetIds: readonly string[], note: string, status: ReviewState): Promise<BulkResult>;
  setApplicability(claimId: string, text: string | null, note: string): Promise<Record<string, unknown>>;
}

interface HttpLiveReviewOptions {
  baseUrl: string;
  /** Local development only: sent as `Bearer dev-reviewer:<name>`. */
  devReviewer: string | null;
  fetchImpl?: typeof fetch;
}

const REVIEW_ROOT = '/internal/v1/review';

export class HttpLiveReviewApi implements LiveReviewApi {
  readonly reviewer: string | null;
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: HttpLiveReviewOptions) {
    this.baseUrl = options.baseUrl;
    this.reviewer = options.devReviewer;
    this.fetchImpl = options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  get(path: string, params: ReviewParams = {}): Promise<Record<string, unknown>> {
    return this.request('GET', path, params);
  }

  post(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.request('POST', path, {}, body);
  }

  async list(path: string, params: ReviewParams = {}): Promise<ReviewList> {
    const body = await this.request('GET', path, params);
    const items = Array.isArray(body.items) ? (body.items as ReviewItem[]) : [];
    return { ...body, items, total: typeof body.total === 'number' ? body.total : items.length };
  }

  async notes(targetType: string, targetId: string): Promise<ReviewNoteRecord[]> {
    const body = await this.request('GET', '/notes', { target_type: targetType, target_id: targetId });
    return Array.isArray(body.items) ? (body.items as ReviewNoteRecord[]) : [];
  }

  async decide(targetType: string, targetId: string, note: string, status?: ReviewState): Promise<DecisionResult> {
    const body: Record<string, unknown> = { target_type: targetType, target_id: targetId, note };
    if (status) {
      body.status = status;
    }
    return (await this.request('POST', '/decisions', {}, body)) as unknown as DecisionResult;
  }

  async decideMany(
    targetType: string,
    targetIds: readonly string[],
    note: string,
    status: ReviewState,
  ): Promise<BulkResult> {
    const body = { target_type: targetType, target_ids: [...targetIds], note, status };
    return (await this.request('POST', '/decisions/bulk', {}, body)) as unknown as BulkResult;
  }

  setApplicability(claimId: string, text: string | null, note: string): Promise<Record<string, unknown>> {
    return this.request('POST', `/claims/${encodeURIComponent(claimId)}/applicability`, {}, { text, note });
  }

  private async request(
    method: 'GET' | 'POST',
    path: string,
    params: ReviewParams,
    body?: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    if (!this.reviewer) {
      throw new ReviewApiError(401, 'reviewer_not_configured', 'Reviewer sign-in is not configured in this build.');
    }
    const url = new URL(`${this.baseUrl}${REVIEW_ROOT}${path}`);
    for (const [name, value] of Object.entries(params)) {
      if (value !== null && value !== undefined && value !== '' && value !== false) {
        url.searchParams.set(name, String(value));
      }
    }
    const headers: Record<string, string> = { Authorization: `Bearer dev-reviewer:${this.reviewer}` };
    if (body) {
      headers['Content-Type'] = 'application/json';
    }
    let response: Response;
    try {
      response = await this.fetchImpl(url.toString(), {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ReviewApiError(0, 'network_error', 'The review service could not be reached.');
    }
    const parsed: unknown = await response.json().catch(() => null);
    const record = parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
    if (!response.ok) {
      const code = typeof record.code === 'string' ? record.code : 'request_failed';
      const message = typeof record.message === 'string' ? record.message : 'The request could not be completed.';
      throw new ReviewApiError(response.status, code, message);
    }
    return record;
  }
}

/** Reads a field of a loosely typed review item as text; missing values read as an empty string. */
export function field(item: ReviewItem, name: string): string {
  const value = item[name];
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return value === null || value === undefined ? '' : JSON.stringify(value);
}

/** Reads a list of texts of a review item; anything that is not a text is left out. */
export function texts(item: ReviewItem, name: string): string[] {
  const value = item[name];
  return Array.isArray(value) ? value.filter((entry): entry is string => typeof entry === 'string') : [];
}

/** Reads a nested object of a review item, or an empty object. */
export function part(item: ReviewItem, name: string): ReviewItem {
  const value = item[name];
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as ReviewItem) : {};
}

export function isReviewState(value: string): value is ReviewState {
  return (REVIEW_STATES as readonly string[]).includes(value);
}
