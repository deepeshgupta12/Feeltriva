import type {
  AnswerSubmit,
  Assessment,
  AssessmentRequest,
  Consent,
  DeletionReceipt,
  ObservationSubmit,
  Question,
  Session,
  SessionCreate,
  Summary,
} from './types';

/**
 * The single boundary between the UI and the assessment backend.
 *
 * Two implementations exist: `MockAssessmentService` (in-memory demo scenarios) and
 * `HttpAssessmentService` (FastAPI, per packages/contracts/openapi.json). The UI renders what these
 * methods return; it never derives urgency, candidates or question order itself.
 *
 * Contract shared by every implementation:
 * - Failures reject with `ApiError`.
 * - Mutations are idempotent: the implementation attaches an Idempotency-Key, reuses it
 *   when the same payload is retried after an indeterminate failure, and issues a new one
 *   for a new operation. An identical mutation that is still in flight is not sent twice.
 * - Requests that depend on the user's details carry `observation_version`; a stale
 *   version rejects with `ApiError.kind === 'conflict'`.
 */
export interface AssessmentService {
  /** GET /v1/consent — the current terms. Their `version` is what `startSession` sends as `consent_version`. */
  getConsent(): Promise<Consent>;
  /** POST /v1/sessions — refused with `consent_version_not_current` unless it names the current terms. */
  startSession(input: SessionCreate): Promise<Session>;
  /** GET /v1/sessions/{session_id} */
  getSession(sessionId: string): Promise<Session>;
  /** POST /v1/sessions/{session_id}/observations — free text, or structured confirm/correct. */
  submitObservations(sessionId: string, input: ObservationSubmit): Promise<Session>;
  /** POST /v1/sessions/{session_id}/answers */
  submitAnswer(sessionId: string, input: AnswerSubmit): Promise<Session>;
  /** POST /v1/sessions/{session_id}/assessments */
  assessSession(sessionId: string, input: AssessmentRequest): Promise<Assessment>;
  /**
   * GET /v1/sessions/{session_id}/assessment — the assessment already made for the details as they stand
   * now; resolves `null` when there is none (HTTP 404 `no_current_assessment`).
   */
  getCurrentAssessment(sessionId: string): Promise<Assessment | null>;
  /** GET /v1/sessions/{session_id}/next-question — resolves `null` on HTTP 204 (no question). */
  getNextQuestion(sessionId: string, observationVersion: number): Promise<Question | null>;
  /** POST /v1/sessions/{session_id}/summary */
  createSummary(sessionId: string, input: AssessmentRequest): Promise<Summary>;
  /** DELETE /v1/sessions/{session_id} */
  deleteSession(sessionId: string): Promise<DeletionReceipt>;
}
