/**
 * Flow tests: the AssessmentController driving the in-memory MockAssessmentService through
 * the same calls the screens make. These cover the behaviours the product must never get
 * wrong: stale results, version conflicts, urgent handoff, incomplete results and the
 * "never invent a result" rule.
 */
import { describe, expect, it } from 'vitest';

import { ApiError } from '@/api/errors';
import { MockAssessmentService } from '@/api/mock/MockAssessmentService';
import { CONSENT_VERSION } from '@/config/consent';
import { SAMPLE_FEATURES, SAMPLE_INTAKE_TEXT, SAMPLE_QUESTIONS } from '@/fixtures/sampleContent';
import type { ScenarioId } from '@/fixtures/scenarios';

import { AssessmentController, CONFLICT_MESSAGE } from './AssessmentController';
import {
  currentObservations,
  groupObservations,
  isAssessmentStale,
  observationLabel,
  selectCandidates,
} from './selectors';

async function start(scenario: ScenarioId) {
  const mock = new MockAssessmentService({ latencyMs: 0, scenario });
  const session = await mock.startSession({ consent_version: CONSENT_VERSION });
  const controller = new AssessmentController(mock, session.session_id, session);
  return { mock, controller, sessionId: session.session_id };
}

async function startWithIntake(scenario: ScenarioId) {
  const context = await start(scenario);
  expect(await context.controller.sendText(SAMPLE_INTAKE_TEXT)).toBe(true);
  return context;
}

async function answerStandardQuestions(controller: AssessmentController) {
  expect(await controller.answerQuestion('no', 'No')).toBe(true);
  expect(await controller.answerQuestion({ value: 3, unit: 'days' }, '3 days')).toBe(true);
  expect(await controller.answerQuestion('sample_level_2', 'A moderate amount')).toBe(true);
  expect(await controller.answerQuestion(['sample_situation_1'], 'Sample situation 1')).toBe(true);
}

describe('normal flow', () => {
  it('goes from intake through follow-ups to a provisional sample result and a summary', async () => {
    const { controller } = await start('normal');
    expect(controller.getSnapshot().session?.state).toBe('intake');
    expect(controller.getSnapshot().transcript[0]?.text).toBe('What have you been feeling?');

    await controller.sendText(SAMPLE_INTAKE_TEXT);
    let state = controller.getSnapshot();
    expect(state.session?.state).toBe('clarifying');
    expect(state.session?.observation_version).toBe(1);
    // Interpretations start unconfirmed so the user is asked to check them.
    expect(currentObservations(state.session).every((item) => !item.confirmed)).toBe(true);
    expect(state.question?.question_id).toBe(SAMPLE_QUESTIONS.presenceGamma.question_id);
    expect(state.question?.observation_version).toBe(1);

    await answerStandardQuestions(controller);
    state = controller.getSnapshot();
    // The service has no further question (HTTP 204 equivalent): not an error.
    expect(state.question).toBeNull();
    expect(state.questionVersion).toBe(state.session?.observation_version);
    expect(state.failure).toBeNull();

    const assessment = await controller.assess();
    state = controller.getSnapshot();
    expect(assessment?.status).toBe('provisional');
    expect(state.session?.state).toBe('result_ready');
    expect(isAssessmentStale(state.session, state.assessment)).toBe(false);
    expect(assessment?.candidates.map((candidate) => candidate.name)).toEqual([
      'Illustrative possibility A',
      'Illustrative possibility B',
    ]);
    expect(selectCandidates(assessment!, state.session).withheld).toBe(0);

    const summary = await controller.createSummary();
    expect(summary?.requires_user_review).toBe(true);
    expect(summary?.observation_version).toBe(state.session?.observation_version);
    expect(summary?.summary_text).toContain('Sample consultation summary');
  });

  it('lists "not present" only after an explicit denial: silence stays unknown', async () => {
    const { controller } = await startWithIntake('normal');
    let groups = groupObservations(currentObservations(controller.getSnapshot().session));
    expect(groups.notPresent).toHaveLength(0);
    expect(groups.reported.map(observationLabel)).toEqual(['Sample symptom A', 'Sample symptom B']);

    await controller.answerQuestion('no', 'No');
    groups = groupObservations(currentObservations(controller.getSnapshot().session));
    expect(groups.notPresent.map(observationLabel)).toEqual(['Sample symptom C']);
  });

  it('files "not sure" under needs clarification, not under not present', async () => {
    const { controller } = await startWithIntake('normal');
    await controller.answerQuestion('not_sure', 'I’m not sure');
    const groups = groupObservations(currentObservations(controller.getSnapshot().session));
    expect(groups.notPresent).toHaveLength(0);
    expect(groups.needsClarification.map(observationLabel)).toEqual(['Sample symptom C']);
  });

  it('never interprets typed text: any first message yields the same sample details', async () => {
    const { controller } = await start('normal');
    await controller.sendText('completely different words that the demo must not analyse');
    const labels = currentObservations(controller.getSnapshot().session).map(observationLabel);
    expect(labels).toEqual(['Sample symptom A', 'Sample symptom B']);
  });
});

describe('confirming and correcting observations', () => {
  it('confirms by superseding the original observation', async () => {
    const { controller } = await startWithIntake('normal');
    const original = currentObservations(controller.getSnapshot().session)[0]!;

    expect(await controller.confirmObservation(original.observation_id)).toBe(true);

    const session = controller.getSnapshot().session!;
    const replacement = session.observations.find((item) => item.supersedes === original.observation_id);
    expect(replacement).toMatchObject({
      feature_id: original.feature_id,
      presence: 'present',
      confirmed: true,
      onset: 'Since yesterday',
    });
    // The superseded revision is no longer current, and the version moved on.
    expect(currentObservations(session).some((item) => item.observation_id === original.observation_id)).toBe(false);
    expect(session.observation_version).toBe(2);
    // The question shown now belongs to the new version.
    expect(controller.getSnapshot().question?.observation_version).toBe(2);
  });

  it('makes the previous result stale after a correction, then refreshes it', async () => {
    const { controller } = await startWithIntake('correction');
    await answerStandardQuestions(controller);
    const first = await controller.assess();
    expect(first?.candidates).toHaveLength(2);

    const beta = currentObservations(controller.getSnapshot().session).find(
      (item) => item.feature_id === 'fx.signal_beta',
    )!;
    expect(await controller.reviseObservation(beta.observation_id, { presence: 'absent' })).toBe(true);

    let state = controller.getSnapshot();
    // The old result is still held, but it is stale and the server no longer reports a ready result.
    expect(state.assessment?.assessment_id).toBe(first?.assessment_id);
    expect(isAssessmentStale(state.session, state.assessment)).toBe(true);
    expect(state.session?.state).toBe('clarifying');
    expect(
      state.transcript.some((entry) => entry.kind === 'revision' && entry.text.includes('no longer applies')),
    ).toBe(true);

    const refreshed = await controller.assess();
    state = controller.getSnapshot();
    expect(refreshed?.assessment_id).not.toBe(first?.assessment_id);
    expect(isAssessmentStale(state.session, state.assessment)).toBe(false);
    // The refreshed sample result reflects the corrected detail.
    expect(refreshed?.candidates.map((candidate) => candidate.name)).toEqual(['Illustrative possibility A']);
  });

  it('does not offer structured edits for a detail the service could not match to a feature', async () => {
    const { controller } = await startWithIntake('normal');
    await controller.sendText('an extra note in my own words');
    const note = currentObservations(controller.getSnapshot().session).find((item) => item.feature_id === null)!;
    expect(note.raw_phrase).toBe('an extra note in my own words');
    expect(await controller.confirmObservation(note.observation_id)).toBe(false);
  });
});

describe('version conflict', () => {
  it('refreshes the authoritative session, keeps the unsent answer and requires resubmission', async () => {
    const { controller, mock, sessionId } = await startWithIntake('normal');
    const questionBefore = controller.getSnapshot().question!;
    mock.simulateConcurrentUpdate(sessionId); // another tab changed the details

    const accepted = await controller.answerQuestion('yes', 'Yes');

    const state = controller.getSnapshot();
    expect(accepted).toBe(false);
    expect(state.transcript.some((entry) => entry.text === CONFLICT_MESSAGE)).toBe(true);
    expect(state.conflict).toEqual({ refreshing: false });
    // Authoritative state was re-read: it includes the other tab's change and a new version.
    expect(state.session?.observation_version).toBe(2);
    expect(currentObservations(state.session).map(observationLabel)).toContain(
      'Sample detail D (added in another tab)',
    );
    // The answer was not applied to anything, and the draft is retained for the same question.
    expect(currentObservations(state.session).some((item) => item.feature_id === 'fx.signal_gamma')).toBe(false);
    expect(state.unsentAnswer).toEqual({ questionId: questionBefore.question_id, value: 'yes', label: 'Yes' });
    expect(state.question?.question_id).toBe(questionBefore.question_id);
    expect(state.question?.observation_version).toBe(2);

    // Resubmitting against the new version succeeds.
    expect(await controller.answerQuestion('yes', 'Yes')).toBe(true);
    expect(controller.getSnapshot().unsentAnswer).toBeNull();
    expect(controller.getSnapshot().conflict).toBeNull();
  });

  it('keeps unsent free text when a message collides with another change', async () => {
    const { controller, mock, sessionId } = await startWithIntake('normal');
    controller.setDraftText('more detail');
    mock.simulateConcurrentUpdate(sessionId);

    expect(await controller.sendText('more detail')).toBe(false);

    const state = controller.getSnapshot();
    expect(state.draftText).toBe('more detail');
    expect(state.transcript.some((entry) => entry.role === 'user' && entry.text === 'more detail')).toBe(false);
    expect(state.session?.observation_version).toBe(2);
  });

  it('rejects stale versions with 409 on every observation-dependent call', async () => {
    const { mock, sessionId } = await startWithIntake('normal');
    const stale = 0;
    for (const call of [
      () => mock.getNextQuestion(sessionId, stale),
      () => mock.assessSession(sessionId, { observation_version: stale }),
      () => mock.createSummary(sessionId, { observation_version: stale }),
      () => mock.submitObservations(sessionId, { observation_version: stale, text: 'x' }),
      () => mock.submitAnswer(sessionId, { observation_version: stale, question_id: 'q', answer: 'yes' }),
    ]) {
      await expect(call()).rejects.toMatchObject({ kind: 'conflict', status: 409 });
    }
  });

  it('drops an unsent answer, visibly, when the current question is a different one', async () => {
    const { controller, mock, sessionId } = await startWithIntake('unavailable');
    // Answering the only question in another "tab" means no question remains afterwards.
    const question = controller.getSnapshot().question!;
    await mock.submitAnswer(sessionId, { observation_version: 1, question_id: question.question_id, answer: 'no' });

    expect(await controller.answerQuestion('yes', 'Yes')).toBe(false);

    const state = controller.getSnapshot();
    expect(state.question).toBeNull();
    expect(state.unsentAnswer).toBeNull();
    expect(state.transcript.some((entry) => entry.text.includes('was not sent because the question changed'))).toBe(
      true,
    );
  });
});

describe('urgent handoff', () => {
  it('stops routine questioning and shows only the service-provided action', async () => {
    const { controller, mock, sessionId } = await startWithIntake('urgent');
    const state = controller.getSnapshot();

    expect(state.session?.state).toBe('urgent_handoff');
    expect(state.question).toBeNull();
    await expect(mock.getNextQuestion(sessionId, state.session!.observation_version)).resolves.toBeNull();
    // The action text is fetched automatically, exactly once, and carries no explanations.
    expect(state.assessment?.status).toBe('urgent_handoff');
    expect(state.assessment?.candidates).toEqual([]);
    expect(state.assessment?.next_action.text).toContain('Sample urgent action');
    expect(mock.requestLog.filter((entry) => entry.path.endsWith('/assessments'))).toHaveLength(1);
  });
});

describe('insufficient information', () => {
  it('returns no candidates, no assessed urgency and an approved follow-up question', async () => {
    const { controller } = await startWithIntake('insufficient');
    const assessment = await controller.assess();

    expect(assessment?.status).toBe('insufficient_information');
    expect(assessment?.urgency).toBe('not_assessed');
    expect(assessment?.candidates).toEqual([]);
    expect(assessment?.unknowns.length).toBeGreaterThan(0);
    expect(assessment?.next_action).toMatchObject({
      type: 'ask_question',
      question_id: SAMPLE_QUESTIONS.measurement.question_id,
    });
    // The follow-up it points to is the question the service offers next.
    expect(controller.getSnapshot().question?.question_id).toBe(SAMPLE_QUESTIONS.measurement.question_id);
    expect(controller.getSnapshot().session?.state).toBe('insufficient_information');
  });
});

describe('answers the person can read back', () => {
  it('remembers the words of the options it has shown, by their internal value', async () => {
    const { controller } = await startWithIntake('normal');
    expect(controller.getSnapshot().optionLabels).toEqual({});
    expect(await controller.answerQuestion('no', 'No')).toBe(true);
    expect(await controller.answerQuestion({ value: 3, unit: 'days' }, '3 days')).toBe(true);
    // The third question offers three levels; their words are kept from the moment it is shown.
    expect(controller.getSnapshot().question?.question_id).toBe(SAMPLE_QUESTIONS.severityBeta.question_id);
    expect(controller.getSnapshot().optionLabels).toMatchObject({
      sample_level_1: 'A little',
      sample_level_2: 'A moderate amount',
      sample_level_3: 'A lot',
    });
  });

  it('asks for a date, refuses one after today, and keeps the date that was given', async () => {
    const { controller } = await startWithIntake('insufficient');
    expect(await controller.answerQuestion({ value: 42, unit: 'sample unit A' }, '42 sample unit A')).toBe(true);
    expect(controller.getSnapshot().question?.question_id).toBe(SAMPLE_QUESTIONS.startDate.question_id);
    expect(await controller.answerQuestion({ date: '2999-01-01' }, '1 January 2999')).toBe(false);
    expect(controller.getSnapshot().failure?.error.code).toBe('invalid_answer');
    expect(await controller.answerQuestion({ date: '2026-01-15' }, '15 January 2026')).toBe(true);
    const session = controller.getSnapshot().session!;
    const dated = currentObservations(session).find((item) => item.feature_id === SAMPLE_FEATURES.alpha.feature_id);
    expect(dated?.value).toEqual({ date: '2026-01-15' });
    // The next question is the free-text one, as before.
    expect(controller.getSnapshot().question?.question_id).toBe(SAMPLE_QUESTIONS.freeText.question_id);
  });

  it('reads "not sure" on a date question as not sure, in the one form the service reads', async () => {
    const { controller } = await startWithIntake('insufficient');
    expect(await controller.answerQuestion({ value: 42, unit: 'sample unit A' }, '42 sample unit A')).toBe(true);
    expect(await controller.answerQuestion('not_sure', 'I’m not sure')).toBe(true);
    expect(controller.getSnapshot().question?.question_id).toBe(SAMPLE_QUESTIONS.freeText.question_id);
  });
});

describe('a result that was already made', () => {
  it('is read back when the conversation is opened again, not made a second time', async () => {
    const { mock, controller, sessionId } = await startWithIntake('normal');
    await answerStandardQuestions(controller);
    await controller.assess();
    const made = controller.getSnapshot().assessment!;
    expect(made.status).toBe('provisional');
    const before = mock.requestLog.filter((entry) => entry.path.endsWith('/assessments')).length;

    // The same conversation opened by a page that holds nothing of it in memory.
    const reopened = new AssessmentController(mock, sessionId);
    await reopened.load();
    expect(reopened.getSnapshot().assessment).toEqual(made);
    expect(mock.requestLog.filter((entry) => entry.path.endsWith('/assessments'))).toHaveLength(before);
    expect(mock.requestLog.some((entry) => entry.method === 'GET' && entry.path.endsWith('/assessment'))).toBe(true);
  });

  it('is not read back once a detail has changed since', async () => {
    const { mock, controller, sessionId } = await startWithIntake('normal');
    await answerStandardQuestions(controller);
    await controller.assess();
    await expect(mock.getCurrentAssessment(sessionId)).resolves.not.toBeNull();
    const session = controller.getSnapshot().session!;
    const first = currentObservations(session)[0]!;
    expect(await controller.reviseObservation(first.observation_id, { presence: 'absent' })).toBe(true);
    await expect(mock.getCurrentAssessment(sessionId)).resolves.toBeNull();
  });
});

describe('out of scope', () => {
  it('pauses questioning and keeps the summary available', async () => {
    const { controller } = await startWithIntake('out_of_scope');
    const state = controller.getSnapshot();

    expect(state.session?.state).toBe('out_of_scope');
    expect(state.question).toBeNull();
    expect(state.assessment?.status).toBe('out_of_scope');
    expect(state.assessment?.candidates).toEqual([]);
    await expect(controller.createSummary()).resolves.toMatchObject({ requires_user_review: true });
  });
});

describe('evidence missing', () => {
  it('withholds a candidate whose cited evidence is not in the response', async () => {
    const { controller } = await startWithIntake('evidence_missing');
    await controller.answerQuestion('no', 'No');
    const assessment = await controller.assess();

    // The service sent a candidate, but its evidence id resolves to nothing.
    expect(assessment?.candidates).toHaveLength(1);
    expect(assessment?.evidence).toEqual([]);

    const selection = selectCandidates(assessment!, controller.getSnapshot().session);
    expect(selection.shown).toEqual([]);
    expect(selection.withheld).toBe(1);
  });

  it('shows only the citations that actually exist for a partially supported candidate', async () => {
    const { controller } = await startWithIntake('normal');
    await answerStandardQuestions(controller);
    const assessment = (await controller.assess())!;
    const partial = {
      ...assessment,
      candidates: [{ ...assessment.candidates[0]!, evidence_ids: ['ev.sample_1', 'ev.does_not_exist'] }],
    };

    const selection = selectCandidates(partial, controller.getSnapshot().session);
    expect(selection.shown[0]?.evidence.map((item) => item.evidence_id)).toEqual(['ev.sample_1']);
  });
});

describe('backend unavailable and offline', () => {
  it('produces no result when the assessment fails, then succeeds on retry', async () => {
    const { controller, mock } = await startWithIntake('unavailable');
    await controller.answerQuestion('no', 'No');

    expect(await controller.assess()).toBeNull();
    let state = controller.getSnapshot();
    expect(state.assessment).toBeNull();
    expect(state.failure).toMatchObject({ op: 'assess' });
    expect(state.failure?.error).toMatchObject({ kind: 'unavailable', status: 503, retryable: true });
    // Saved details are untouched and the summary still works.
    expect(currentObservations(state.session)).toHaveLength(3);
    await expect(controller.createSummary()).resolves.not.toBeNull();

    mock.setOutage(false);
    const assessment = await controller.assess();
    state = controller.getSnapshot();
    expect(assessment?.status).toBe('provisional');
    expect(state.failure).toBeNull();
  });

  it('keeps unsent text when offline and distinguishes it from saved observations', async () => {
    const { controller, mock } = await startWithIntake('normal');
    const savedBefore = currentObservations(controller.getSnapshot().session).length;
    controller.setDraftText('typed while offline');
    mock.setOffline(true);

    expect(await controller.sendText('typed while offline')).toBe(false);

    let state = controller.getSnapshot();
    expect(state.failure?.error.kind).toBe('network');
    expect(state.draftText).toBe('typed while offline');
    expect(currentObservations(state.session)).toHaveLength(savedBefore);
    expect(state.transcript.some((entry) => entry.text === 'typed while offline')).toBe(false);

    mock.setOffline(false);
    expect(await controller.sendText('typed while offline')).toBe(true);
    state = controller.getSnapshot();
    expect(state.draftText).toBe('');
    expect(currentObservations(state.session)).toHaveLength(savedBefore + 1);
  });

  it('reports an expired session instead of continuing', async () => {
    const { controller, mock, sessionId } = await startWithIntake('session_expired');
    mock.expireSession(sessionId);

    expect(await controller.answerQuestion('yes', 'Yes')).toBe(false);
    expect(controller.getSnapshot().load).toBe('expired');
    expect(controller.getSnapshot().question).toBeNull();
  });
});

describe('idempotency and duplicate submits (mock)', () => {
  it('reuses the Idempotency-Key for a retried payload and issues a new one for a new operation', async () => {
    const { mock, sessionId } = await start('normal');
    const payload = { observation_version: 0, text: SAMPLE_INTAKE_TEXT };
    const attempts = () => mock.requestLog.filter((entry) => entry.path.endsWith('/observations'));

    mock.setOffline(true);
    await expect(mock.submitObservations(sessionId, payload)).rejects.toBeInstanceOf(ApiError);
    mock.setOffline(false);
    await mock.submitObservations(sessionId, payload);
    await mock.submitObservations(sessionId, { observation_version: 1, text: 'another message' });

    const [dropped, retried, next] = attempts();
    expect(dropped?.delivered).toBe(false);
    expect(retried?.delivered).toBe(true);
    expect(dropped?.idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    // Same payload retried -> same key. New operation -> new key.
    expect(retried?.idempotencyKey).toBe(dropped?.idempotencyKey);
    expect(next?.idempotencyKey).not.toBe(retried?.idempotencyKey);
  });

  it('does not apply a mutation twice when its response was lost and the request is retried', async () => {
    const { controller, mock } = await start('normal');

    // The server commits the message, but the client never sees the response.
    mock.loseNextResponse();
    expect(await controller.sendText(SAMPLE_INTAKE_TEXT)).toBe(false);
    expect(controller.getSnapshot().failure?.error.kind).toBe('network');
    expect(controller.getSnapshot().session?.observation_version).toBe(0);

    // Retrying the same payload replays the original response instead of adding it again.
    expect(await controller.sendText(SAMPLE_INTAKE_TEXT)).toBe(true);
    const session = controller.getSnapshot().session!;
    expect(session.observation_version).toBe(1);
    expect(session.observations).toHaveLength(2);
    const [first, retry] = mock.requestLog.filter((entry) => entry.path.endsWith('/observations'));
    expect(retry?.idempotencyKey).toBe(first?.idempotencyKey);
  });

  it('sends one request when the same submit is triggered twice while pending', async () => {
    const { controller, mock } = await start('normal');

    const [first, second] = await Promise.all([
      controller.sendText(SAMPLE_INTAKE_TEXT),
      controller.sendText(SAMPLE_INTAKE_TEXT),
    ]);

    expect([first, second]).toEqual([true, false]);
    expect(mock.requestLog.filter((entry) => entry.path.endsWith('/observations'))).toHaveLength(1);
    expect(controller.getSnapshot().session?.observation_version).toBe(1);
  });

  it('de-duplicates an identical in-flight mutation at the service boundary too', async () => {
    const { mock, sessionId } = await start('normal');
    const payload = { observation_version: 0, text: SAMPLE_INTAKE_TEXT };

    const [a, b] = await Promise.all([
      mock.submitObservations(sessionId, payload),
      mock.submitObservations(sessionId, payload),
    ]);

    expect(a.observation_version).toBe(1);
    expect(b.observation_version).toBe(1);
    expect(mock.requestLog.filter((entry) => entry.path.endsWith('/observations'))).toHaveLength(1);
  });
});

describe('deletion', () => {
  it('returns a scheduled receipt, clears in-memory details and never claims completion early', async () => {
    const { controller, mock, sessionId } = await startWithIntake('normal');

    const receipt = await controller.deleteSession();

    expect(receipt).toMatchObject({ session_id: sessionId, status: 'deletion_scheduled' });
    const state = controller.getSnapshot();
    expect(state.load).toBe('deleted');
    expect(state.session).toBeNull();
    expect(state.transcript).toEqual([]);
    expect(state.assessment).toBeNull();
    await expect(mock.getSession(sessionId)).rejects.toMatchObject({ kind: 'not_found' });

    // Only the service can move the receipt to "deleted".
    controller.applyDeletionReceipt(mock.completeDeletion(sessionId)!);
    expect(controller.getSnapshot().deletion?.status).toBe('deleted');
  });
});

describe('mock answer validation', () => {
  it('rejects an invalid answer with 422 and an answer to a question that is not current with 409', async () => {
    const { mock, sessionId } = await startWithIntake('normal');
    await expect(
      mock.submitAnswer(sessionId, {
        observation_version: 1,
        question_id: SAMPLE_QUESTIONS.presenceGamma.question_id,
        answer: 'maybe',
      }),
    ).rejects.toMatchObject({ kind: 'validation', status: 422 });
    await expect(
      mock.submitAnswer(sessionId, {
        observation_version: 1,
        question_id: SAMPLE_QUESTIONS.context.question_id,
        answer: ['sample_situation_1'],
      }),
    ).rejects.toMatchObject({ kind: 'conflict', status: 409, code: 'question_not_current' });
  });
});

describe('the demo service and the terms', () => {
  it('starts a session only for its current terms, and keeps the agreement with it', async () => {
    const mock = new MockAssessmentService({ latencyMs: 0 });
    const terms = await mock.getConsent();
    expect(terms.version).toBe(CONSENT_VERSION);

    await expect(mock.startSession({ consent_version: 'an-older-version' })).rejects.toMatchObject({
      status: 409,
      code: 'consent_version_not_current',
    });

    const plain = await mock.startSession({ consent_version: terms.version });
    expect(plain).toMatchObject({ consent_version: terms.version, training_consent: false });
    expect(Number.isNaN(Date.parse(plain.consent_accepted_at ?? ''))).toBe(false);
    const allowed = await mock.startSession({ consent_version: terms.version, training_consent: true });
    expect(allowed.training_consent).toBe(true);
    // The agreement stays with the session however often it is read.
    expect(await mock.getSession(allowed.session_id)).toMatchObject({
      consent_version: terms.version,
      training_consent: true,
      consent_accepted_at: allowed.consent_accepted_at,
    });
  });
});
