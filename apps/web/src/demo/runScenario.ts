/**
 * Loads a demo scenario by driving the mock service through the same public
 * AssessmentService calls the screens use, so every scenario starts from real view state.
 */
import type { MockAssessmentService } from '@/api/mock/MockAssessmentService';
import type { AnswerValue } from '@/api/types';
import { CONSENT_VERSION } from '@/config/consent';
import { SAMPLE_INTAKE_TEXT, SAMPLE_QUESTIONS } from '@/fixtures/sampleContent';
import type { ScenarioId } from '@/fixtures/scenarios';
import type { AssessmentController } from '@/state/AssessmentController';
import type { SessionRegistry } from '@/state/SessionRegistry';

export interface ScenarioRunContext {
  mock: MockAssessmentService;
  registry: SessionRegistry;
  setReviewerPreview: (enabled: boolean) => void;
}

export interface ScenarioOutcome {
  /** Where to send the user once the scenario is loaded. */
  route: string;
}

/** Fixed answers used when a scenario needs questions answered before it starts. */
const SCRIPTED_ANSWERS: Record<string, { value: AnswerValue; label: string }> = {
  [SAMPLE_QUESTIONS.presenceGamma.question_id]: { value: 'no', label: 'No' },
  [SAMPLE_QUESTIONS.durationAlpha.question_id]: { value: { value: 3, unit: 'days' }, label: '3 days' },
  [SAMPLE_QUESTIONS.severityBeta.question_id]: { value: 'sample_level_2', label: 'A moderate amount' },
  [SAMPLE_QUESTIONS.context.question_id]: { value: ['sample_situation_1'], label: 'Sample situation 1' },
  [SAMPLE_QUESTIONS.measurement.question_id]: {
    value: { value: 42, unit: 'sample unit A' },
    label: '42 sample unit A',
  },
  [SAMPLE_QUESTIONS.startDate.question_id]: { value: { date: '2026-01-15' }, label: '15 January 2026' },
  [SAMPLE_QUESTIONS.freeText.question_id]: { value: 'Sample note', label: 'Sample note' },
};

async function seedSession(context: ScenarioRunContext, scenario: ScenarioId): Promise<AssessmentController> {
  context.mock.setScenario(scenario);
  const session = await context.mock.startSession({ consent_version: CONSENT_VERSION });
  const controller = context.registry.create(session);
  await controller.sendText(SAMPLE_INTAKE_TEXT);
  return controller;
}

async function answerScriptedQuestions(controller: AssessmentController): Promise<void> {
  for (let guard = 0; guard < 12; guard += 1) {
    const question = controller.getSnapshot().question;
    const scripted = question ? SCRIPTED_ANSWERS[question.question_id] : undefined;
    if (!question || !scripted) {
      return;
    }
    const accepted = await controller.answerQuestion(scripted.value, scripted.label);
    if (!accepted) {
      return;
    }
  }
}

/** Creates one finished sample assessment with a summary (used by the empty-history flow). */
export async function createCompletedSample(context: ScenarioRunContext): Promise<AssessmentController> {
  const latency = context.mock.getLatency();
  context.mock.setLatency(0);
  try {
    const controller = await seedSession(context, 'history');
    await answerScriptedQuestions(controller);
    await controller.assess();
    await controller.createSummary();
    return controller;
  } finally {
    context.mock.setLatency(latency);
  }
}

/**
 * Resets the demo and loads `scenario`. Seeding runs without simulated latency; the
 * configured latency is restored afterwards so the screens still show loading states.
 */
export async function runScenario(scenario: ScenarioId, context: ScenarioRunContext): Promise<ScenarioOutcome> {
  const { mock, registry } = context;
  const latency = mock.getLatency();
  mock.reset();
  registry.clear();
  mock.setLatency(0);
  mock.setScenario(scenario);

  try {
    switch (scenario) {
      case 'normal':
        return { route: '/start' };

      case 'history':
        return { route: '/history' };

      case 'reviewer':
        context.setReviewerPreview(true);
        return { route: '/review/data' };

      case 'correction':
      case 'evidence_missing': {
        const controller = await seedSession(context, scenario);
        await answerScriptedQuestions(controller);
        await controller.assess();
        return { route: `/results/${controller.sessionId}` };
      }

      case 'unavailable': {
        const controller = await seedSession(context, scenario);
        await answerScriptedQuestions(controller);
        // The outage is on for this scenario, so this request fails and no result exists.
        await controller.assess();
        return { route: `/results/${controller.sessionId}` };
      }

      case 'insufficient': {
        const controller = await seedSession(context, scenario);
        await controller.assess();
        return { route: `/results/${controller.sessionId}` };
      }

      case 'out_of_scope': {
        const controller = await seedSession(context, scenario);
        return { route: `/results/${controller.sessionId}` };
      }

      case 'urgent':
      case 'conflict': {
        const controller = await seedSession(context, scenario);
        return { route: `/assess/${controller.sessionId}` };
      }

      case 'session_expired': {
        const controller = await seedSession(context, scenario);
        mock.expireSession(controller.sessionId);
        await controller.refresh();
        return { route: `/assess/${controller.sessionId}` };
      }
    }
  } finally {
    mock.setLatency(latency);
  }
}
