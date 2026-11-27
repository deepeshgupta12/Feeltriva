import {
  DEMO_KNOWLEDGE_RELEASE,
  DEMO_RULES_VERSION,
  MISSING_EVIDENCE_ID,
  SAMPLE_CANDIDATES,
  SAMPLE_EVIDENCE,
  SAMPLE_FEATURES,
  SAMPLE_INTAKE_OBSERVATIONS,
  SAMPLE_NEXT_ACTION_TEXT,
  SAMPLE_QUESTION_BY_ID,
  SAMPLE_UNKNOWNS,
  type MockQuestionFixture,
  type SampleFeature,
} from '@/fixtures/sampleContent';
import { MOCK_SCENARIO_PROFILES, type MockScenarioProfile, type ScenarioId } from '@/fixtures/scenarios';
import { dateBounds } from '@/lib/answers';
import { uuid } from '@/lib/uuid';

import type { AssessmentService } from '../assessmentService';
import { ApiError, kindForStatus, shouldKeepIdempotencyKey, toApiError } from '../errors';
import { MutationGate, operationFingerprint } from '../idempotency';
import {
  DURATION_UNITS,
  NOT_SURE,
  isCalendarDate,
  type AnswerSubmit,
  type Assessment,
  type AssessmentRequest,
  type Candidate,
  type DeletionReceipt,
  type Demographics,
  type Evidence,
  type ObservationInput,
  type ObservationRecord,
  type ObservationSubmit,
  type Presence,
  type Question,
  type ServerSessionState,
  type Session,
  type SessionCreate,
  type Summary,
} from '../types';

export interface MockAssessmentServiceOptions {
  /** Simulated latency per call. Use 0 in tests. */
  latencyMs?: number;
  scenario?: ScenarioId;
  now?: () => Date;
}

interface MockSessionRecord {
  scenario: ScenarioId;
  profile: MockScenarioProfile;
  session_id: string;
  observation_version: number;
  state: ServerSessionState;
  expires_at: string;
  demographics?: Demographics;
  /** Append-only observation log, including superseded revisions. */
  records: ObservationRecord[];
  answered: Set<string>;
  conflictArmed: boolean;
  expired: boolean;
  deletion: DeletionReceipt | null;
  /** The last assessment made; current only while its version is the session's. */
  assessment?: Assessment;
}

export interface MockRequestLogEntry {
  method: string;
  path: string;
  idempotencyKey: string | null;
  /** False when the simulated network dropped the request before it reached the server. */
  delivered: boolean;
}

const SESSION_LIFETIME_MS = 60 * 60 * 1000;

/**
 * In-memory stand-in for the assessment API, used by the design demo and by tests.
 *
 * It follows the same contract as the HTTP adapter (observation versions, 409 on stale
 * versions, idempotent mutations, `null` for "no question") but its content is scripted:
 * the scenario decides what happens, and typed text is never interpreted. All state lives
 * in this object and disappears on reload.
 */
export class MockAssessmentService implements AssessmentService {
  /** Every attempted call, for tests and debugging. Holds no payloads. */
  readonly requestLog: MockRequestLogEntry[] = [];

  private readonly sessions = new Map<string, MockSessionRecord>();
  private readonly handledKeys = new Map<string, { fingerprint: string; result: unknown }>();
  private readonly mutations = new MutationGate();
  private readonly now: () => Date;
  private scenario: ScenarioId;
  private latencyMs: number;
  private offline = false;
  private outage = false;
  private dropNextResponse = false;
  private requestCounter = 0;

  constructor(options: MockAssessmentServiceOptions = {}) {
    this.latencyMs = options.latencyMs ?? 0;
    this.scenario = options.scenario ?? 'normal';
    this.now = options.now ?? (() => new Date());
  }

  // -------------------------------------------------------------------------
  // Demo controls (not part of AssessmentService)
  // -------------------------------------------------------------------------

  /** Scenario applied to sessions created from now on. */
  setScenario(scenario: ScenarioId): void {
    this.scenario = scenario;
  }

  getScenario(): ScenarioId {
    return this.scenario;
  }

  setLatency(latencyMs: number): void {
    this.latencyMs = latencyMs;
  }

  getLatency(): number {
    return this.latencyMs;
  }

  /** While offline, every call fails as if the network were unreachable. */
  setOffline(offline: boolean): void {
    this.offline = offline;
  }

  isOffline(): boolean {
    return this.offline;
  }

  /**
   * The next mutation is committed by the "server" but its response is lost, as if the
   * connection dropped. A retry with the same Idempotency-Key must get the original response.
   */
  loseNextResponse(): void {
    this.dropNextResponse = true;
  }

  /** While the outage is on, assessment requests fail with 503. */
  setOutage(outage: boolean): void {
    this.outage = outage;
  }

  isOutage(): boolean {
    return this.outage;
  }

  /** The next answer or correction for this session collides with a simulated second tab. */
  armConflict(sessionId: string): void {
    const record = this.sessions.get(sessionId);
    if (record) {
      record.conflictArmed = true;
    }
  }

  /** Simulates another tab adding a detail: the observation version moves on. */
  simulateConcurrentUpdate(sessionId: string): void {
    const record = this.sessions.get(sessionId);
    if (record && !record.deletion) {
      this.applyConcurrentUpdate(record);
    }
  }

  /** Every later call for this session answers 401. */
  expireSession(sessionId: string): void {
    const record = this.sessions.get(sessionId);
    if (record) {
      record.expired = true;
    }
  }

  /** Demo-only: moves a scheduled deletion to "deleted" so the completed receipt can be previewed. */
  completeDeletion(sessionId: string): DeletionReceipt | null {
    const record = this.sessions.get(sessionId);
    if (!record?.deletion) {
      return null;
    }
    record.deletion = { ...record.deletion, status: 'deleted' };
    return { ...record.deletion };
  }

  /** Clears every session and control. */
  reset(): void {
    this.sessions.clear();
    this.handledKeys.clear();
    this.requestLog.length = 0;
    this.offline = false;
    this.outage = false;
    this.dropNextResponse = false;
    this.scenario = 'normal';
  }

  // -------------------------------------------------------------------------
  // AssessmentService
  // -------------------------------------------------------------------------

  startSession(input: SessionCreate): Promise<Session> {
    return this.mutate('POST', '/v1/sessions', input, () => {
      if (typeof input.consent_version !== 'string' || input.consent_version.length === 0) {
        throw this.error(422, 'validation_failed', 'consent_version is required.');
      }
      const age = input.demographics?.age_years;
      if (age !== undefined && (!Number.isInteger(age) || age < 0 || age > 130)) {
        throw this.error(422, 'validation_failed', 'age_years must be between 0 and 130.');
      }
      const scenario = this.scenario;
      const profile = MOCK_SCENARIO_PROFILES[scenario];
      const record: MockSessionRecord = {
        scenario,
        profile,
        session_id: uuid(),
        observation_version: 0,
        state: 'intake',
        expires_at: new Date(this.now().getTime() + SESSION_LIFETIME_MS).toISOString(),
        records: [],
        answered: new Set(),
        conflictArmed: profile.armsConflict === true,
        expired: false,
        deletion: null,
      };
      if (input.demographics) {
        record.demographics = structuredClone(input.demographics);
      }
      if (profile.startsWithOutage) {
        this.outage = true;
      }
      this.sessions.set(record.session_id, record);
      return this.view(record);
    });
  }

  async getSession(sessionId: string): Promise<Session> {
    await this.transport('GET', sessionPath(sessionId), null);
    return this.view(this.requireSession(sessionId));
  }

  submitObservations(sessionId: string, input: ObservationSubmit): Promise<Session> {
    return this.mutate('POST', `${sessionPath(sessionId)}/observations`, input, () => {
      const record = this.requireSession(sessionId);
      const isText = 'text' in input;
      // The first message cannot collide with another tab; later changes can.
      if (record.state !== 'intake') {
        this.triggerArmedConflict(record);
      }
      this.checkVersion(record, input.observation_version);

      if (isText) {
        this.applyText(record, input.text);
      } else {
        this.applyStructured(record, input.observations);
      }
      return this.view(record);
    });
  }

  submitAnswer(sessionId: string, input: AnswerSubmit): Promise<Session> {
    return this.mutate('POST', `${sessionPath(sessionId)}/answers`, input, () => {
      const record = this.requireSession(sessionId);
      this.triggerArmedConflict(record);
      this.checkVersion(record, input.observation_version);

      const current = this.nextQuestionFixture(record);
      if (!current || current.question_id !== input.question_id) {
        throw this.error(409, 'question_not_current', 'That question is not the current question.');
      }
      this.applyAnswer(record, current, input.answer);
      record.answered.add(current.question_id);
      record.observation_version += 1;
      this.invalidateResult(record);
      return this.view(record);
    });
  }

  assessSession(sessionId: string, input: AssessmentRequest): Promise<Assessment> {
    return this.mutate('POST', `${sessionPath(sessionId)}/assessments`, input, () => {
      const record = this.requireSession(sessionId);
      this.checkVersion(record, input.observation_version);
      if (record.state === 'intake') {
        throw this.error(422, 'nothing_to_assess', 'No details have been shared yet.');
      }
      if (this.outage) {
        record.state = 'system_unavailable';
        throw this.error(503, 'assessment_unavailable', 'The assessment could not be completed.', true);
      }
      const made = this.buildAssessment(record);
      record.assessment = made;
      return made;
    });
  }

  async getCurrentAssessment(sessionId: string): Promise<Assessment | null> {
    await this.transport('GET', `${sessionPath(sessionId)}/assessment`, null);
    const record = this.requireSession(sessionId);
    const made = record.assessment;
    return made && made.observation_version === record.observation_version ? structuredClone(made) : null;
  }

  async getNextQuestion(sessionId: string, observationVersion: number): Promise<Question | null> {
    await this.transport('GET', `${sessionPath(sessionId)}/next-question`, null);
    const record = this.requireSession(sessionId);
    this.checkVersion(record, observationVersion);
    const fixture = this.nextQuestionFixture(record);
    if (!fixture) {
      return null;
    }
    return {
      question_id: fixture.question_id,
      wording: fixture.wording,
      answer_schema: structuredClone(fixture.answer_schema),
      observation_version: record.observation_version,
    };
  }

  createSummary(sessionId: string, input: AssessmentRequest): Promise<Summary> {
    return this.mutate('POST', `${sessionPath(sessionId)}/summary`, input, () => {
      const record = this.requireSession(sessionId);
      this.checkVersion(record, input.observation_version);
      return {
        session_id: record.session_id,
        observation_version: record.observation_version,
        summary_text: this.buildSummaryText(record),
        requires_user_review: true,
      };
    });
  }

  deleteSession(sessionId: string): Promise<DeletionReceipt> {
    return this.mutate('DELETE', sessionPath(sessionId), undefined, () => {
      const record = this.requireSession(sessionId);
      // Deletion is queued, not instant: the receipt says so and the UI must not claim more.
      record.deletion = {
        session_id: record.session_id,
        status: 'deletion_scheduled',
        receipt_id: `demo-receipt-${record.session_id.slice(0, 8)}`,
      };
      record.state = 'closed';
      return { ...record.deletion };
    });
  }

  // -------------------------------------------------------------------------
  // Simulated transport and server plumbing
  // -------------------------------------------------------------------------

  private async transport(method: string, path: string, idempotencyKey: string | null): Promise<void> {
    if (this.latencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.latencyMs));
    } else {
      await Promise.resolve();
    }
    this.requestLog.push({ method, path, idempotencyKey, delivered: !this.offline });
    if (this.offline) {
      throw this.networkError();
    }
  }

  private networkError(): ApiError {
    return new ApiError({
      kind: 'network',
      status: null,
      code: 'network_error',
      message: 'The assessment service could not be reached.',
      retryable: true,
    });
  }

  private mutate<T>(method: string, path: string, body: unknown, handler: () => T): Promise<T> {
    const fingerprint = operationFingerprint(method, path, body);
    return this.mutations.run(
      fingerprint,
      async (idempotencyKey) => {
        await this.transport(method, path, idempotencyKey);
        // Server-side idempotency: a replayed key returns the original response, and the
        // same key with a different payload is rejected.
        const handled = this.handledKeys.get(idempotencyKey);
        if (handled) {
          if (handled.fingerprint !== fingerprint) {
            throw this.error(409, 'idempotency_key_conflict', 'This Idempotency-Key was used for a different request.');
          }
          return structuredClone(handled.result) as T;
        }
        const result = handler();
        this.handledKeys.set(idempotencyKey, { fingerprint, result: structuredClone(result) });
        if (this.dropNextResponse) {
          this.dropNextResponse = false;
          throw this.networkError();
        }
        return structuredClone(result);
      },
      (error) => shouldKeepIdempotencyKey(toApiError(error)),
    );
  }

  private error(status: number, code: string, message: string, retryable = false): ApiError {
    this.requestCounter += 1;
    const kind = kindForStatus(status, code);
    return new ApiError({
      kind,
      status,
      code,
      message,
      retryable,
      requestId: `mock-request-${this.requestCounter}`,
    });
  }

  private requireSession(sessionId: string): MockSessionRecord {
    const record = this.sessions.get(sessionId);
    if (!record || record.deletion) {
      throw this.error(404, 'session_not_found', 'This assessment was not found.');
    }
    if (record.expired) {
      throw this.error(403, 'session_expired', 'This session has ended.');
    }
    return record;
  }

  private checkVersion(record: MockSessionRecord, observationVersion: number): void {
    if (observationVersion !== record.observation_version) {
      throw this.error(409, 'stale_observation_version', 'The details for this assessment have changed.');
    }
  }

  private triggerArmedConflict(record: MockSessionRecord): void {
    if (record.conflictArmed) {
      record.conflictArmed = false;
      this.applyConcurrentUpdate(record);
    }
  }

  private view(record: MockSessionRecord): Session {
    const session: Session = {
      session_id: record.session_id,
      observation_version: record.observation_version,
      state: record.state,
      expires_at: record.expires_at,
      observations: structuredClone(record.records),
    };
    if (record.demographics) {
      session.demographics = structuredClone(record.demographics);
    }
    return session;
  }

  // -------------------------------------------------------------------------
  // Scripted behaviour
  // -------------------------------------------------------------------------

  private currentRecords(record: MockSessionRecord): ObservationRecord[] {
    const superseded = new Set(record.records.map((item) => item.supersedes).filter(Boolean));
    return record.records.filter((item) => !superseded.has(item.observation_id));
  }

  private currentFor(record: MockSessionRecord, feature: SampleFeature): ObservationRecord | undefined {
    return this.currentRecords(record).find((item) => item.feature_id === feature.feature_id);
  }

  private append(
    record: MockSessionRecord,
    fields: Omit<ObservationRecord, 'observation_id' | 'observation_version'>,
  ): ObservationRecord {
    const created: ObservationRecord = {
      ...fields,
      observation_id: uuid(),
      // Stamped with the version this change produces; callers bump the version once per request.
      observation_version: record.observation_version + 1,
    };
    record.records.push(created);
    return created;
  }

  /** A changed detail means any earlier result no longer applies. */
  private invalidateResult(record: MockSessionRecord): void {
    if (
      record.state === 'result_ready' ||
      record.state === 'insufficient_information' ||
      record.state === 'system_unavailable' ||
      record.state === 'assessing'
    ) {
      record.state = 'clarifying';
    }
  }

  private applyConcurrentUpdate(record: MockSessionRecord): void {
    this.append(record, {
      ...SAMPLE_FEATURES.delta,
      presence: 'present',
      confirmed: true,
    });
    record.observation_version += 1;
    this.invalidateResult(record);
  }

  private applyText(record: MockSessionRecord, text: string): void {
    const trimmed = typeof text === 'string' ? text.trim() : '';
    if (trimmed.length === 0 || trimmed.length > 10_000) {
      throw this.error(422, 'validation_failed', 'Text must be between 1 and 10,000 characters.');
    }
    if (record.state === 'intake') {
      // The mock does not read the message. It always lists the same sample details,
      // unconfirmed, so the user is asked to check them.
      for (const sample of SAMPLE_INTAKE_OBSERVATIONS) {
        this.append(record, { ...sample, presence: 'present', confirmed: false });
      }
      record.observation_version += 1;
      record.state = record.profile.afterIntake;
      return;
    }
    // Later messages are stored verbatim as an unmatched note; nothing is inferred from them.
    this.append(record, {
      feature_id: null,
      presence: 'uncertain',
      confirmed: true,
      raw_phrase: trimmed.slice(0, 280),
    });
    record.observation_version += 1;
    this.invalidateResult(record);
  }

  private applyStructured(record: MockSessionRecord, observations: ObservationInput[]): void {
    if (!Array.isArray(observations) || observations.length === 0 || observations.length > 100) {
      throw this.error(422, 'validation_failed', 'Between 1 and 100 observations are required.');
    }
    const current = this.currentRecords(record);
    const prepared: Array<Omit<ObservationRecord, 'observation_id' | 'observation_version'>> = [];
    for (const input of observations) {
      if (typeof input.feature_id !== 'string' || input.feature_id.length === 0) {
        throw this.error(422, 'validation_failed', 'feature_id is required.');
      }
      let rawPhrase: string | undefined;
      if (input.supersedes !== undefined) {
        const target = current.find((item) => item.observation_id === input.supersedes);
        if (!target) {
          throw this.error(422, 'invalid_supersedes', 'The detail being corrected is not current for this assessment.');
        }
        rawPhrase = target.raw_phrase;
      }
      rawPhrase ??= Object.values(SAMPLE_FEATURES).find(
        (feature) => feature.feature_id === input.feature_id,
      )?.raw_phrase;
      prepared.push({
        feature_id: input.feature_id,
        presence: input.presence,
        confirmed: input.confirmed,
        ...(input.value !== undefined ? { value: input.value } : {}),
        ...(input.onset ? { onset: input.onset } : {}),
        ...(input.duration ? { duration: input.duration } : {}),
        ...(input.severity ? { severity: input.severity } : {}),
        ...(input.supersedes ? { supersedes: input.supersedes } : {}),
        ...(rawPhrase ? { raw_phrase: rawPhrase } : {}),
      });
    }
    for (const fields of prepared) {
      this.append(record, fields);
    }
    record.observation_version += 1;
    this.invalidateResult(record);
  }

  private nextQuestionFixture(record: MockSessionRecord): MockQuestionFixture | null {
    if (
      record.state === 'intake' ||
      record.state === 'urgent_handoff' ||
      record.state === 'out_of_scope' ||
      record.state === 'closed'
    ) {
      return null;
    }
    for (const questionId of record.profile.questionIds) {
      if (!record.answered.has(questionId)) {
        return SAMPLE_QUESTION_BY_ID.get(questionId) ?? null;
      }
    }
    return null;
  }

  private applyAnswer(record: MockSessionRecord, question: MockQuestionFixture, answer: unknown): void {
    const invalid = () => this.error(422, 'invalid_answer', 'That answer does not match the question.');
    const schema = question.answer_schema;
    const effect = question.effect;
    const existing = 'feature' in effect ? this.currentFor(record, effect.feature) : undefined;
    const carried = existing
      ? {
          ...(existing.onset ? { onset: existing.onset } : {}),
          ...(existing.duration ? { duration: existing.duration } : {}),
          ...(existing.severity ? { severity: existing.severity } : {}),
          ...(existing.value !== undefined ? { value: existing.value } : {}),
          supersedes: existing.observation_id,
        }
      : {};
    const notSure = schema.allow_not_sure === true && isNotSure(answer);

    switch (schema.type) {
      case 'yes_no_unsure': {
        if (answer !== 'yes' && answer !== 'no' && answer !== NOT_SURE) throw invalid();
        if (effect.kind !== 'set_presence') throw invalid();
        const presence: Presence = answer === 'yes' ? 'present' : answer === 'no' ? 'absent' : 'uncertain';
        this.append(record, { ...effect.feature, ...carried, presence, confirmed: true });
        return;
      }
      case 'duration': {
        if (effect.kind !== 'set_duration') throw invalid();
        if (notSure) return;
        if (!isRecord(answer) || !isFiniteNumber(answer.value) || !isDurationUnit(answer.unit)) throw invalid();
        if (!withinRange(answer.value, schema.min, schema.max)) throw invalid();
        const unit = answer.value === 1 ? answer.unit.replace(/s$/, '') : answer.unit;
        this.append(record, {
          ...effect.feature,
          ...carried,
          presence: existing?.presence ?? 'uncertain',
          duration: `${answer.value} ${unit}`,
          confirmed: true,
        });
        return;
      }
      case 'single_choice': {
        if (typeof answer !== 'string') throw invalid();
        if (effect.kind !== 'set_severity') throw invalid();
        if (notSure) return;
        const option = schema.options?.find((item) => item.value === answer);
        if (!option) throw invalid();
        this.append(record, {
          ...effect.feature,
          ...carried,
          presence: existing?.presence ?? 'uncertain',
          severity: option.label,
          confirmed: true,
        });
        return;
      }
      case 'multiple_choice': {
        if (effect.kind !== 'add_value') throw invalid();
        if (notSure) {
          this.append(record, { ...effect.feature, presence: 'uncertain', confirmed: true });
          return;
        }
        if (!Array.isArray(answer) || answer.length === 0) throw invalid();
        const labels: string[] = [];
        for (const value of answer) {
          const option = schema.options?.find((item) => item.value === value);
          if (!option) throw invalid();
          labels.push(option.label);
        }
        this.append(record, { ...effect.feature, presence: 'present', value: labels, confirmed: true });
        return;
      }
      case 'number': {
        if (effect.kind !== 'add_value') throw invalid();
        if (notSure) {
          this.append(record, { ...effect.feature, presence: 'uncertain', confirmed: true });
          return;
        }
        if (!isRecord(answer) || !isFiniteNumber(answer.value)) throw invalid();
        if (!withinRange(answer.value, schema.min, schema.max)) throw invalid();
        if (answer.unit !== null && typeof answer.unit !== 'string') throw invalid();
        this.append(record, {
          ...effect.feature,
          presence: 'present',
          value: { value: answer.value, unit: answer.unit },
          confirmed: true,
        });
        return;
      }
      case 'date': {
        if (effect.kind !== 'add_value') throw invalid();
        if (notSure) {
          this.append(record, { ...effect.feature, ...carried, presence: 'uncertain', confirmed: true });
          return;
        }
        if (!isRecord(answer) || !isCalendarDate(answer.date)) throw invalid();
        const { earliest, latest } = dateBounds(schema);
        if ((earliest && answer.date < earliest) || (latest && answer.date > latest)) throw invalid();
        this.append(record, {
          ...effect.feature,
          ...carried,
          presence: existing?.presence ?? 'present',
          value: { date: answer.date },
          confirmed: true,
        });
        return;
      }
      case 'free_text': {
        if (notSure) return;
        if (typeof answer !== 'string' || answer.trim().length === 0) throw invalid();
        this.append(record, {
          feature_id: null,
          presence: 'uncertain',
          confirmed: true,
          raw_phrase: answer.trim().slice(0, 280),
        });
        return;
      }
    }
  }

  private buildAssessment(record: MockSessionRecord): Assessment {
    const base = {
      assessment_id: uuid(),
      session_id: record.session_id,
      observation_version: record.observation_version,
      versions: { knowledge: DEMO_KNOWLEDGE_RELEASE, rules: DEMO_RULES_VERSION, model: null, prompt: null },
    };
    const empty = { candidates: [], evidence_ids: [], evidence: [] };

    switch (record.profile.result) {
      case 'urgent': {
        record.state = 'urgent_handoff';
        return {
          ...base,
          ...empty,
          status: 'urgent_handoff',
          urgency: 'urgent',
          unknowns: [],
          next_action: { type: 'seek_care', text: SAMPLE_NEXT_ACTION_TEXT.urgent },
        };
      }
      case 'out_of_scope': {
        record.state = 'out_of_scope';
        return {
          ...base,
          ...empty,
          status: 'out_of_scope',
          urgency: 'not_assessed',
          unknowns: [SAMPLE_UNKNOWNS.scope],
          next_action: { type: 'show_summary', text: SAMPLE_NEXT_ACTION_TEXT.outOfScope },
        };
      }
      case 'insufficient': {
        record.state = 'insufficient_information';
        const next = this.nextQuestionFixture(record);
        const measured = this.currentFor(record, SAMPLE_FEATURES.zeta)?.presence === 'present';
        return {
          ...base,
          ...empty,
          status: 'insufficient_information',
          urgency: 'not_assessed',
          unknowns: [...(measured ? [] : [SAMPLE_UNKNOWNS.measurementMissing]), SAMPLE_UNKNOWNS.changeOverTime],
          next_action: next
            ? { type: 'ask_question', text: SAMPLE_NEXT_ACTION_TEXT.insufficientAsk, question_id: next.question_id }
            : { type: 'show_summary', text: SAMPLE_NEXT_ACTION_TEXT.insufficientSummary },
        };
      }
      case 'evidence_missing': {
        record.state = 'result_ready';
        const alpha = this.currentFor(record, SAMPLE_FEATURES.alpha);
        return {
          ...base,
          status: 'provisional',
          urgency: 'not_assessed',
          // The candidate cites evidence that is not in the response. The UI must withhold it.
          candidates: [
            {
              ...SAMPLE_CANDIDATES.a,
              supporting_observation_ids: alpha ? [alpha.observation_id] : [],
              conflicting_observation_ids: [],
              evidence_ids: [MISSING_EVIDENCE_ID],
            },
          ],
          evidence_ids: [],
          evidence: [],
          unknowns: [SAMPLE_UNKNOWNS.evidence],
          next_action: { type: 'show_summary', text: SAMPLE_NEXT_ACTION_TEXT.evidenceMissing },
        };
      }
      case 'provisional': {
        record.state = 'result_ready';
        const alpha = this.currentFor(record, SAMPLE_FEATURES.alpha);
        const beta = this.currentFor(record, SAMPLE_FEATURES.beta);
        const gamma = this.currentFor(record, SAMPLE_FEATURES.gamma);
        const core = [alpha, beta, gamma].filter((item): item is ObservationRecord => item !== undefined);
        const ids = (items: ObservationRecord[]) => items.map((item) => item.observation_id);

        const candidates: Candidate[] = [];
        if (alpha?.presence === 'present') {
          candidates.push({
            ...SAMPLE_CANDIDATES.a,
            supporting_observation_ids: ids(core.filter((item) => item.presence === 'present')),
            conflicting_observation_ids: ids(core.filter((item) => item.presence === 'uncertain')),
            evidence_ids: [SAMPLE_EVIDENCE.first.evidence_id, SAMPLE_EVIDENCE.second.evidence_id],
          });
        }
        if (beta?.presence === 'present') {
          candidates.push({
            ...SAMPLE_CANDIDATES.b,
            supporting_observation_ids: [beta.observation_id],
            conflicting_observation_ids: gamma && gamma.presence !== 'present' ? [gamma.observation_id] : [],
            evidence_ids: [SAMPLE_EVIDENCE.second.evidence_id],
          });
        }
        const usedEvidenceIds = new Set(candidates.flatMap((candidate) => candidate.evidence_ids));
        const evidence: Evidence[] = Object.values(SAMPLE_EVIDENCE).filter((item) =>
          usedEvidenceIds.has(item.evidence_id),
        );
        return {
          ...base,
          status: 'provisional',
          urgency: 'routine',
          candidates,
          evidence_ids: evidence.map((item) => item.evidence_id),
          evidence: structuredClone(evidence),
          unknowns: [
            ...(!gamma || gamma.presence === 'uncertain' ? [SAMPLE_UNKNOWNS.gammaUnknown] : []),
            ...(candidates.length === 0 ? [SAMPLE_UNKNOWNS.noSupport] : []),
            SAMPLE_UNKNOWNS.inPerson,
          ],
          next_action: { type: 'seek_care', text: SAMPLE_NEXT_ACTION_TEXT.provisional },
        };
      }
    }
  }

  private buildSummaryText(record: MockSessionRecord): string {
    const current = this.currentRecords(record);
    const describe = (item: ObservationRecord) => {
      const label = item.raw_phrase ?? item.feature_id ?? 'Unlabelled detail';
      const extras = [item.onset, item.duration, item.severity].filter(Boolean).join(', ');
      return extras ? `${label} (${extras})` : label;
    };
    const list = (presence: Presence) => {
      const items = current.filter((item) => item.presence === presence).map(describe);
      return items.length > 0 ? items.join('; ') : 'None recorded';
    };
    return [
      'Sample consultation summary (design demo, not a medical assessment).',
      `Reported: ${list('present')}.`,
      `Explicitly not present: ${list('absent')}.`,
      `Needs clarification: ${list('uncertain')}.`,
      'This sample text is generated by the demo service from the sample details listed above.',
    ].join('\n');
  }
}

function sessionPath(sessionId: string): string {
  return `/v1/sessions/${sessionId}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isDurationUnit(value: unknown): value is (typeof DURATION_UNITS)[number] {
  return typeof value === 'string' && (DURATION_UNITS as readonly string[]).includes(value);
}

function withinRange(value: number, min: number | undefined, max: number | undefined): boolean {
  return (min === undefined || value >= min) && (max === undefined || value <= max);
}

/** "Not sure" is the one string `not_sure`, as the service reads it (BUG-010). */
function isNotSure(answer: unknown): boolean {
  return answer === NOT_SURE;
}
