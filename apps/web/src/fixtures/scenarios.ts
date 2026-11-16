/**
 * Demo scenarios (specification section 15) and how the mock service behaves in each.
 * Selecting a scenario changes UI state deterministically. Typed text never changes the
 * outcome: the mock does not interpret what the user writes.
 */
import { SAMPLE_QUESTIONS } from './sampleContent';

export const SCENARIO_IDS = [
  'normal',
  'correction',
  'urgent',
  'insufficient',
  'out_of_scope',
  'unavailable',
  'history',
  'evidence_missing',
  'conflict',
  'reviewer',
  'session_expired',
] as const;

export type ScenarioId = (typeof SCENARIO_IDS)[number];

export type MockResultKind = 'provisional' | 'urgent' | 'insufficient' | 'out_of_scope' | 'evidence_missing';

export interface MockScenarioProfile {
  /** Session state the mock reports after the first message. */
  afterIntake: 'clarifying' | 'urgent_handoff' | 'out_of_scope';
  /** Scripted follow-up questions, asked in order. */
  questionIds: readonly string[];
  result: MockResultKind;
  /** Assessment requests fail with 503 until the outage is switched off. */
  startsWithOutage?: boolean;
  /** The first answer or correction collides with a simulated update from another tab. */
  armsConflict?: boolean;
}

const STANDARD_QUESTIONS = [
  SAMPLE_QUESTIONS.presenceGamma.question_id,
  SAMPLE_QUESTIONS.durationAlpha.question_id,
  SAMPLE_QUESTIONS.severityBeta.question_id,
  SAMPLE_QUESTIONS.context.question_id,
] as const;

const STANDARD: MockScenarioProfile = {
  afterIntake: 'clarifying',
  questionIds: STANDARD_QUESTIONS,
  result: 'provisional',
};

export const MOCK_SCENARIO_PROFILES: Record<ScenarioId, MockScenarioProfile> = {
  normal: STANDARD,
  correction: STANDARD,
  history: STANDARD,
  reviewer: STANDARD,
  session_expired: STANDARD,
  conflict: { ...STANDARD, armsConflict: true },
  urgent: { afterIntake: 'urgent_handoff', questionIds: [], result: 'urgent' },
  out_of_scope: { afterIntake: 'out_of_scope', questionIds: [], result: 'out_of_scope' },
  insufficient: {
    afterIntake: 'clarifying',
    questionIds: [SAMPLE_QUESTIONS.measurement.question_id, SAMPLE_QUESTIONS.freeText.question_id],
    result: 'insufficient',
  },
  unavailable: {
    afterIntake: 'clarifying',
    questionIds: [SAMPLE_QUESTIONS.presenceGamma.question_id],
    result: 'provisional',
    startsWithOutage: true,
  },
  evidence_missing: {
    afterIntake: 'clarifying',
    questionIds: [SAMPLE_QUESTIONS.presenceGamma.question_id],
    result: 'evidence_missing',
  },
};

export interface DemoScenario {
  id: ScenarioId;
  /** Number from the specification's scenario list; extra states have none. */
  number: number | null;
  title: string;
  description: string;
  /** What to do once the scenario has loaded. */
  hint: string;
}

export const DEMO_SCENARIOS: readonly DemoScenario[] = [
  {
    id: 'normal',
    number: 1,
    title: 'Normal sample assessment',
    description: 'Intake, confirm details, follow-up questions, provisional sample result, summary.',
    hint: 'Accept the acknowledgement, load the example text, then confirm details and answer the sample questions.',
  },
  {
    id: 'correction',
    number: 2,
    title: 'Correct an earlier answer',
    description: 'A finished sample result becomes stale after a correction, then refreshes.',
    hint: 'Under “What we understood”, choose Edit or Remove/correct. The result is marked as needing an update; choose “Update result”.',
  },
  {
    id: 'urgent',
    number: 3,
    title: 'Urgent-state preview',
    description: 'Routine questioning stops and a high-priority panel is shown.',
    hint: 'The action text is a labelled placeholder. No explanation cards or follow-up questions are shown.',
  },
  {
    id: 'insufficient',
    number: 4,
    title: 'Insufficient information',
    description: 'What is missing is explained and the next approved question is offered.',
    hint: 'Choose “Answer the next question” to continue, or open the summary.',
  },
  {
    id: 'out_of_scope',
    number: 5,
    title: 'Unsupported scope',
    description: 'A clear limitation screen with summary access.',
    hint: 'No explanation is shown. The summary is still available.',
  },
  {
    id: 'unavailable',
    number: 6,
    title: 'Backend unavailable and offline',
    description: 'The assessment request fails; nothing is invented and input stays recoverable.',
    hint: 'Try again while the outage is on, then switch “Service outage” off and retry. Use “Simulate offline” on the conversation screen to see unsent text retained.',
  },
  {
    id: 'history',
    number: 7,
    title: 'Empty history',
    description: 'Empty state, create a sample, preview it, delete it and read the receipt.',
    hint: 'Choose “Start a sample assessment”, open its summary, then delete it and check the receipt status.',
  },
  {
    id: 'evidence_missing',
    number: 8,
    title: 'Evidence missing',
    description: 'A candidate explanation without supporting information is withheld.',
    hint: 'The result is marked incomplete and the unsupported explanation is not rendered.',
  },
  {
    id: 'conflict',
    number: 9,
    title: 'Concurrent update',
    description: 'A change from another tab causes a version conflict on the next answer.',
    hint: 'Choose an answer and send it. The app refreshes the assessment, keeps your selection and asks you to send it again.',
  },
  {
    id: 'reviewer',
    number: 10,
    title: 'Internal reviewer',
    description: 'Inspect a repeated header in the data-quality inventory and save a demo note.',
    hint: 'Open a row, add a reviewer note and save. Changes are demo-only.',
  },
  {
    id: 'session_expired',
    number: null,
    title: 'Session expired',
    description: 'The service reports that the session has ended.',
    hint: 'Only a safe restart is offered.',
  },
];

export function findScenario(id: ScenarioId): DemoScenario {
  const scenario = DEMO_SCENARIOS.find((item) => item.id === id);
  if (!scenario) {
    throw new Error(`Unknown scenario: ${id}`);
  }
  return scenario;
}
