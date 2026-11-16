import type { AssessmentService } from '@/api/assessmentService';
import { toApiError, type ApiError } from '@/api/errors';
import {
  parseSessionState,
  type AnswerValue,
  type Assessment,
  type DeletionReceipt,
  type ObservationInput,
  type ObservationRecord,
  type Presence,
  type Question,
  type ServerSessionState,
  type Session,
  type Summary,
} from '@/api/types';

import { currentObservations, observationLabel } from './selectors';

export type PendingOp =
  'load' | 'refresh' | 'text' | 'answer' | 'observation' | 'question' | 'assess' | 'summary' | 'delete';

/**
 * Client-side loading state. This is UI state only: it is tracked separately from the
 * server's `Session.state` and never changes what the assessment says.
 */
export type LoadStatus = 'idle' | 'loading' | 'ready' | 'not_found' | 'expired' | 'forbidden' | 'failed' | 'deleted';

export interface TranscriptEntry {
  id: string;
  role: 'assistant' | 'user' | 'notice';
  kind: 'prompt' | 'acknowledgement' | 'question' | 'text' | 'answer' | 'revision' | 'conflict';
  text: string;
}

export interface OperationFailure {
  op: PendingOp;
  error: ApiError;
}

/** An answer the user chose that the service has not accepted (yet). */
export interface UnsentAnswer {
  questionId: string;
  value: AnswerValue;
  label: string;
}

export interface ObservationRevision {
  presence: Presence;
  onset?: string;
  duration?: string;
  severity?: string;
}

export interface AssessmentViewState {
  sessionId: string;
  load: LoadStatus;
  /** Authoritative session as last returned by the service. */
  session: Session | null;
  /** Current follow-up question, always for `session.observation_version`. */
  question: Question | null;
  /** Observation version for which the service has answered "next question" (question or none). */
  questionVersion: number | null;
  /** Last assessment received. May be stale: compare with `session.observation_version`. */
  assessment: Assessment | null;
  summary: Summary | null;
  /** Conversation shown on screen. In memory only; never persisted. */
  transcript: readonly TranscriptEntry[];
  /** Composer text. Kept when a send fails so nothing typed is lost. */
  draftText: string;
  unsentAnswer: UnsentAnswer | null;
  pending: readonly PendingOp[];
  /** Set while (and after) recovering from an observation-version conflict. */
  conflict: { refreshing: boolean } | null;
  failure: OperationFailure | null;
  deletion: DeletionReceipt | null;
}

export const CONFLICT_MESSAGE = 'Your details changed. Refreshing this assessment…';
export const OPENING_PROMPT = 'What have you been feeling?';

const DETAIL_MUTATIONS: readonly PendingOp[] = ['text', 'answer', 'observation', 'delete'];
const MAX_CONSECUTIVE_QUESTION_CONFLICTS = 2;

/** States in which the service may have another routine question. */
function acceptsQuestions(state: ServerSessionState | 'unknown'): boolean {
  return (
    state === 'clarifying' || state === 'assessing' || state === 'result_ready' || state === 'insufficient_information'
  );
}

/**
 * Holds one assessment session's in-memory view state and talks to the AssessmentService.
 *
 * Rules it enforces for every screen:
 * - the server session is the only source of truth for details, state and versions;
 * - one detail-changing request at a time (duplicate submits are ignored while pending);
 * - on a version conflict it refreshes the authoritative session, keeps the unsent draft
 *   and requires the user to resubmit against the new question/version;
 * - a failed call never produces or alters a result.
 */
export class AssessmentController {
  readonly sessionId: string;

  private readonly service: AssessmentService;
  private readonly listeners = new Set<() => void>();
  private state: AssessmentViewState;
  private entryCounter = 0;
  private questionFetchRunning = false;
  private questionFetchQueued = false;
  private consecutiveQuestionConflicts = 0;
  private autoAssessedVersion: number | null = null;
  private staleNoticeForAssessment: string | null = null;

  constructor(service: AssessmentService, sessionId: string, initialSession?: Session) {
    this.service = service;
    this.sessionId = sessionId;
    this.state = {
      sessionId,
      load: initialSession ? 'ready' : 'idle',
      session: initialSession ?? null,
      question: null,
      questionVersion: null,
      assessment: null,
      summary: null,
      transcript: [],
      draftText: '',
      unsentAnswer: null,
      pending: [],
      conflict: null,
      failure: null,
      deletion: null,
    };
    if (
      initialSession &&
      parseSessionState(initialSession.state) === 'intake' &&
      initialSession.observations.length === 0
    ) {
      this.pushEntry('assistant', 'prompt', OPENING_PROMPT);
    }
  }

  // ---------------------------------------------------------------------
  // Store plumbing (useSyncExternalStore-compatible)
  // ---------------------------------------------------------------------

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  readonly getSnapshot = (): AssessmentViewState => this.state;

  private patch(partial: Partial<AssessmentViewState>): void {
    this.state = { ...this.state, ...partial };
    for (const listener of this.listeners) {
      listener();
    }
  }

  private begin(op: PendingOp): void {
    if (!this.state.pending.includes(op)) {
      this.patch({ pending: [...this.state.pending, op] });
    }
  }

  private end(op: PendingOp): void {
    this.patch({ pending: this.state.pending.filter((item) => item !== op) });
  }

  private isPending(op: PendingOp): boolean {
    return this.state.pending.includes(op);
  }

  /** True while a request that changes the user's details is in flight. */
  isMutating(): boolean {
    return this.state.pending.some((op) => DETAIL_MUTATIONS.includes(op));
  }

  private pushEntry(role: TranscriptEntry['role'], kind: TranscriptEntry['kind'], text: string): void {
    this.entryCounter += 1;
    const entry: TranscriptEntry = { id: `${this.sessionId}-${this.entryCounter}`, role, kind, text };
    this.patch({ transcript: [...this.state.transcript, entry] });
  }

  // ---------------------------------------------------------------------
  // Local (non-network) actions
  // ---------------------------------------------------------------------

  setDraftText(text: string): void {
    if (text !== this.state.draftText) {
      this.patch({ draftText: text });
    }
  }

  dismissFailure(): void {
    if (this.state.failure) {
      this.patch({ failure: null });
    }
  }

  dismissConflictNotice(): void {
    if (this.state.conflict && !this.state.conflict.refreshing) {
      this.patch({ conflict: null });
    }
  }

  // ---------------------------------------------------------------------
  // Loading and refreshing
  // ---------------------------------------------------------------------

  /** Fetches the session when this controller was created without one. */
  async load(): Promise<void> {
    if (this.isPending('load') || this.state.load === 'deleted') {
      return;
    }
    this.begin('load');
    this.patch({ load: 'loading', failure: null });
    try {
      const session = await this.service.getSession(this.sessionId);
      this.patch({ load: 'ready' });
      this.applySession(session);
    } catch (error) {
      const apiError = toApiError(error);
      if (!this.handleAccessError(apiError)) {
        this.patch({ load: 'failed', failure: { op: 'load', error: apiError } });
      }
      return;
    } finally {
      this.end('load');
    }
    await this.syncAfterChange();
  }

  /** Re-reads the authoritative session (used by "Reconnect" and "Try again"). */
  async refresh(): Promise<boolean> {
    if (this.isPending('refresh') || this.state.load === 'deleted') {
      return false;
    }
    if (this.state.session === null) {
      await this.load();
      return this.state.load === 'ready';
    }
    this.begin('refresh');
    this.patch({ failure: null });
    try {
      const session = await this.service.getSession(this.sessionId);
      this.applySession(session);
    } catch (error) {
      const apiError = toApiError(error);
      if (!this.handleAccessError(apiError)) {
        this.patch({ failure: { op: 'refresh', error: apiError } });
      }
      return false;
    } finally {
      this.end('refresh');
    }
    await this.syncAfterChange();
    return true;
  }

  // ---------------------------------------------------------------------
  // Detail-changing actions
  // ---------------------------------------------------------------------

  /** Sends free text. Resolves true when the service accepted it. */
  async sendText(text: string): Promise<boolean> {
    const session = this.state.session;
    const trimmed = text.trim();
    if (!session || trimmed.length === 0 || this.isMutating()) {
      return false;
    }
    this.begin('text');
    this.patch({ failure: null });
    let accepted = false;
    let resync = false;
    try {
      const next = await this.service.submitObservations(this.sessionId, {
        observation_version: session.observation_version,
        text: trimmed,
      });
      this.pushEntry('user', 'text', trimmed);
      this.patch({ draftText: '', conflict: null });
      this.applySession(next);
      const needsConfirmation = currentObservations(next).some((observation) => !observation.confirmed);
      this.pushEntry(
        'assistant',
        'acknowledgement',
        needsConfirmation
          ? 'Thanks. Please check what I understood under “What you’ve shared” and correct anything that isn’t right.'
          : 'Thanks. I’ve added that to what you’ve shared.',
      );
      accepted = true;
    } catch (error) {
      // The draft stays in the composer: nothing typed is lost on a failed send.
      resync = await this.handleMutationError('text', error);
    } finally {
      this.end('text');
    }
    if (accepted || resync) {
      await this.syncAfterChange();
    }
    return accepted;
  }

  /**
   * Answers the current question. The answer is bound to the question id and version the
   * user actually saw, so it can never be attached to a different question.
   */
  async answerQuestion(value: AnswerValue, label: string): Promise<boolean> {
    const question = this.state.question;
    if (!question || !this.state.session || this.isMutating()) {
      return false;
    }
    this.begin('answer');
    this.patch({ failure: null, unsentAnswer: { questionId: question.question_id, value, label } });
    let accepted = false;
    let resync = false;
    try {
      const next = await this.service.submitAnswer(this.sessionId, {
        observation_version: question.observation_version,
        question_id: question.question_id,
        answer: value,
      });
      this.pushEntry('assistant', 'question', question.wording);
      this.pushEntry('user', 'answer', label);
      this.patch({ unsentAnswer: null, question: null, conflict: null });
      this.applySession(next);
      accepted = true;
    } catch (error) {
      resync = await this.handleMutationError('answer', error);
    } finally {
      this.end('answer');
    }
    if (accepted || resync) {
      await this.syncAfterChange();
    }
    return accepted;
  }

  /** "That's right": re-records the observation as confirmed, superseding the original. */
  confirmObservation(observationId: string): Promise<boolean> {
    const observation = this.findCurrentObservation(observationId);
    if (!observation) {
      return Promise.resolve(false);
    }
    return this.submitRevision(
      observation,
      {
        presence: observation.presence,
        onset: observation.onset,
        duration: observation.duration,
        severity: observation.severity,
      },
      false,
    );
  }

  /** "Edit" / "Remove or correct": supersedes the observation with the user's correction. */
  reviseObservation(observationId: string, revision: ObservationRevision): Promise<boolean> {
    const observation = this.findCurrentObservation(observationId);
    if (!observation) {
      return Promise.resolve(false);
    }
    return this.submitRevision(observation, revision, true);
  }

  private findCurrentObservation(observationId: string): ObservationRecord | undefined {
    return currentObservations(this.state.session).find((item) => item.observation_id === observationId);
  }

  private async submitRevision(
    observation: ObservationRecord,
    revision: ObservationRevision,
    announce: boolean,
  ): Promise<boolean> {
    const session = this.state.session;
    // An observation the service could not map to a feature cannot be revised structurally.
    if (!session || observation.feature_id === null || this.isMutating()) {
      return false;
    }
    const input: ObservationInput = {
      feature_id: observation.feature_id,
      presence: revision.presence,
      confirmed: true,
      supersedes: observation.observation_id,
    };
    if (observation.value !== undefined && revision.presence === observation.presence) {
      input.value = observation.value;
    }
    const onset = revision.onset?.trim();
    const duration = revision.duration?.trim();
    const severity = revision.severity?.trim();
    if (onset) input.onset = onset;
    if (duration) input.duration = duration;
    if (severity) input.severity = severity;

    this.begin('observation');
    this.patch({ failure: null });
    let accepted = false;
    let resync = false;
    try {
      const next = await this.service.submitObservations(this.sessionId, {
        observation_version: session.observation_version,
        observations: [input],
      });
      this.patch({ conflict: null });
      if (announce) {
        this.pushEntry('notice', 'revision', `You updated “${observationLabel(observation)}”.`);
      }
      this.applySession(next);
      accepted = true;
    } catch (error) {
      resync = await this.handleMutationError('observation', error);
    } finally {
      this.end('observation');
    }
    if (accepted || resync) {
      await this.syncAfterChange();
    }
    return accepted;
  }

  // ---------------------------------------------------------------------
  // Assessment, summary, deletion
  // ---------------------------------------------------------------------

  /** Requests a result for the current observation version. Never fabricates one on failure. */
  async assess(): Promise<Assessment | null> {
    const session = this.state.session;
    if (!session || this.isPending('assess') || this.isMutating()) {
      return null;
    }
    this.begin('assess');
    this.patch({ failure: null });
    let assessment: Assessment | null = null;
    let resync = false;
    try {
      assessment = await this.service.assessSession(this.sessionId, {
        observation_version: session.observation_version,
      });
      this.patch({ assessment, conflict: null });
    } catch (error) {
      resync = await this.handleMutationError('assess', error);
    } finally {
      this.end('assess');
    }
    if (assessment) {
      // The session state usually changes with a result (for example to result_ready).
      await this.refreshQuietly();
    } else if (resync) {
      await this.syncAfterChange();
    }
    return assessment;
  }

  async createSummary(): Promise<Summary | null> {
    const session = this.state.session;
    if (!session || this.isPending('summary')) {
      return null;
    }
    this.begin('summary');
    this.patch({ failure: null });
    try {
      const summary = await this.service.createSummary(this.sessionId, {
        observation_version: session.observation_version,
      });
      this.patch({ summary });
      return summary;
    } catch (error) {
      // After a conflict the session has been refreshed; the summary page asks again
      // for the new version.
      await this.handleMutationError('summary', error);
      return null;
    } finally {
      this.end('summary');
    }
  }

  /** Deletes the session and drops every health detail held in memory for it. */
  async deleteSession(): Promise<DeletionReceipt | null> {
    if (this.isPending('delete') || this.state.load === 'deleted') {
      return this.state.deletion;
    }
    this.begin('delete');
    this.patch({ failure: null });
    try {
      const receipt = await this.service.deleteSession(this.sessionId);
      this.patch({
        load: 'deleted',
        deletion: receipt,
        session: null,
        question: null,
        questionVersion: null,
        assessment: null,
        summary: null,
        transcript: [],
        draftText: '',
        unsentAnswer: null,
        conflict: null,
      });
      return receipt;
    } catch (error) {
      const apiError = toApiError(error);
      if (!this.handleAccessError(apiError)) {
        this.patch({ failure: { op: 'delete', error: apiError } });
      }
      return null;
    } finally {
      this.end('delete');
    }
  }

  /** Demo-only: reflect a receipt status the mock service changed out of band. */
  applyDeletionReceipt(receipt: DeletionReceipt): void {
    if (this.state.load === 'deleted') {
      this.patch({ deletion: receipt });
    }
  }

  // ---------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------

  private applySession(session: Session): void {
    const partial: Partial<AssessmentViewState> = { session };
    // A question fetched for an older version must not be answerable any more.
    if (this.state.question && this.state.question.observation_version !== session.observation_version) {
      partial.question = null;
    }
    if (this.state.questionVersion !== null && this.state.questionVersion !== session.observation_version) {
      partial.questionVersion = null;
    }
    this.patch(partial);

    const assessment = this.state.assessment;
    if (
      assessment &&
      assessment.observation_version !== session.observation_version &&
      this.staleNoticeForAssessment !== assessment.assessment_id
    ) {
      this.staleNoticeForAssessment = assessment.assessment_id;
      this.pushEntry(
        'notice',
        'revision',
        'Your details changed, so the earlier result no longer applies. Ask for an updated result when you’re ready.',
      );
    }
  }

  /** Decides what to fetch next from the server-reported state. No clinical decisions here. */
  private async syncAfterChange(): Promise<void> {
    const session = this.state.session;
    if (!session) {
      return;
    }
    const flow = parseSessionState(session.state);
    if (flow === 'urgent_handoff' || flow === 'out_of_scope') {
      // Routine questioning stops. The action text comes from the service, so ask for it once.
      this.patch({ question: null, questionVersion: session.observation_version });
      const hasCurrent = this.state.assessment?.observation_version === session.observation_version;
      const canAssess = !this.isPending('assess') && !this.isMutating();
      if (!hasCurrent && canAssess && this.autoAssessedVersion !== session.observation_version) {
        this.autoAssessedVersion = session.observation_version;
        await this.assess();
      }
      return;
    }
    if (!acceptsQuestions(flow)) {
      this.patch({ question: null, questionVersion: null });
      return;
    }
    await this.fetchQuestion();
  }

  private async fetchQuestion(): Promise<void> {
    if (this.questionFetchRunning) {
      this.questionFetchQueued = true;
      return;
    }
    this.questionFetchRunning = true;
    this.begin('question');
    try {
      do {
        this.questionFetchQueued = false;
        await this.fetchQuestionOnce();
      } while (this.questionFetchQueued);
    } finally {
      this.questionFetchRunning = false;
      this.end('question');
    }
  }

  private async fetchQuestionOnce(): Promise<void> {
    const session = this.state.session;
    if (!session || !acceptsQuestions(parseSessionState(session.state))) {
      return;
    }
    const version = session.observation_version;
    try {
      const question = await this.service.getNextQuestion(this.sessionId, version);
      if (this.state.session?.observation_version !== version) {
        // Details changed while waiting; this answer is for an old version.
        this.questionFetchQueued = true;
        return;
      }
      this.consecutiveQuestionConflicts = 0;
      this.setQuestion(question, version);
    } catch (error) {
      const apiError = toApiError(error);
      if (apiError.kind === 'conflict' && this.consecutiveQuestionConflicts < MAX_CONSECUTIVE_QUESTION_CONFLICTS) {
        this.consecutiveQuestionConflicts += 1;
        if (await this.refreshForConflict()) {
          this.questionFetchQueued = true;
        }
        return;
      }
      if (!this.handleAccessError(apiError)) {
        this.patch({ failure: { op: 'question', error: apiError } });
      }
    }
  }

  private setQuestion(question: Question | null, version: number): void {
    const unsent = this.state.unsentAnswer;
    const partial: Partial<AssessmentViewState> = { question, questionVersion: version };
    if (this.state.failure?.op === 'question') {
      // An earlier attempt to load the question failed; this one succeeded.
      partial.failure = null;
    }
    if (unsent && (!question || question.question_id !== unsent.questionId)) {
      // The draft belonged to a question that is no longer current. It is dropped, visibly,
      // rather than being attached to a different question.
      partial.unsentAnswer = null;
      this.patch(partial);
      this.pushEntry('notice', 'conflict', 'Your earlier answer was not sent because the question changed.');
      return;
    }
    this.patch(partial);
  }

  /**
   * Records a failed request. For a version conflict (409) it refreshes the authoritative
   * session, keeping drafts, and resolves true so the caller re-syncs the question once its
   * own pending flag is cleared.
   */
  private async handleMutationError(op: PendingOp, error: unknown): Promise<boolean> {
    const apiError = toApiError(error);
    if (apiError.kind === 'conflict') {
      return this.refreshForConflict();
    }
    if (!this.handleAccessError(apiError)) {
      this.patch({ failure: { op, error: apiError } });
    }
    return false;
  }

  private async refreshForConflict(): Promise<boolean> {
    if (!this.state.conflict) {
      this.pushEntry('notice', 'conflict', CONFLICT_MESSAGE);
    }
    this.patch({ conflict: { refreshing: true } });
    try {
      const session = await this.service.getSession(this.sessionId);
      this.applySession(session);
      this.patch({ conflict: { refreshing: false } });
      return true;
    } catch (error) {
      const apiError = toApiError(error);
      this.patch({ conflict: null });
      if (!this.handleAccessError(apiError)) {
        this.patch({ failure: { op: 'refresh', error: apiError } });
      }
      return false;
    }
  }

  private async refreshQuietly(): Promise<void> {
    try {
      const session = await this.service.getSession(this.sessionId);
      this.applySession(session);
    } catch (error) {
      // The result already arrived; a failed state refresh must not replace it with an error.
      this.handleAccessError(toApiError(error));
      return;
    }
    await this.syncAfterChange();
  }

  /** 401/403/404 change what the whole screen shows. Returns true when handled. */
  private handleAccessError(error: ApiError): boolean {
    switch (error.kind) {
      case 'unauthenticated':
        this.patch({ load: 'expired', question: null });
        return true;
      case 'forbidden':
        this.patch({ load: 'forbidden', question: null });
        return true;
      case 'not_found':
        this.patch({ load: 'not_found', question: null });
        return true;
      default:
        return false;
    }
  }
}
