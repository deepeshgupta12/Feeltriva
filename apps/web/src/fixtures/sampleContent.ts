/**
 * Deterministic, visibly synthetic content for the mock assessment service.
 *
 * Nothing in this file is clinical content. Feature names, questions, explanations and
 * next steps are placeholders that say so in their own wording, so no screen can be
 * mistaken for a medical assessment. Do not replace these with realistic conditions:
 * approved content only ever comes from the backend.
 */
import type { AnswerSchema, Evidence } from '@/api/types';

export const DEMO_KNOWLEDGE_RELEASE = 'kr-demo-0';
export const DEMO_RULES_VERSION = 'rules-demo-0';

/** Loaded by the "Try an example conversation" chip. Never submitted automatically. */
export const SAMPLE_INTAKE_TEXT =
  'Sample entry: I have had sample symptom A since yesterday, and sample symptom B comes and goes.';

export interface SampleFeature {
  feature_id: string;
  raw_phrase: string;
}

export const SAMPLE_FEATURES = {
  alpha: { feature_id: 'fx.signal_alpha', raw_phrase: 'Sample symptom A' },
  beta: { feature_id: 'fx.signal_beta', raw_phrase: 'Sample symptom B' },
  gamma: { feature_id: 'fx.signal_gamma', raw_phrase: 'Sample symptom C' },
  delta: { feature_id: 'fx.signal_delta', raw_phrase: 'Sample detail D (added in another tab)' },
  epsilon: { feature_id: 'fx.context_epsilon', raw_phrase: 'Sample situations' },
  zeta: { feature_id: 'fx.measure_zeta', raw_phrase: 'Sample measurement' },
} as const satisfies Record<string, SampleFeature>;

/** What the mock "extracts" from the first message, whatever was typed. */
export const SAMPLE_INTAKE_OBSERVATIONS: ReadonlyArray<SampleFeature & { onset?: string; duration?: string }> = [
  { ...SAMPLE_FEATURES.alpha, onset: 'Since yesterday' },
  { ...SAMPLE_FEATURES.beta, duration: 'Comes and goes' },
];

/** How the mock applies an answer to its in-memory session. Not clinical logic. */
export type MockAnswerEffect =
  | { kind: 'set_presence'; feature: SampleFeature }
  | { kind: 'set_duration'; feature: SampleFeature }
  | { kind: 'set_severity'; feature: SampleFeature }
  | { kind: 'add_value'; feature: SampleFeature }
  | { kind: 'add_note' };

export interface MockQuestionFixture {
  question_id: string;
  wording: string;
  answer_schema: AnswerSchema;
  effect: MockAnswerEffect;
}

const SAMPLE_HELP_TEXT =
  'Sample explanation. In the live service, the assessment service supplies the reason a question is being asked.';

export const SAMPLE_QUESTIONS = {
  presenceGamma: {
    question_id: 'q.sample_presence_gamma',
    wording: 'Sample question: have you also noticed sample symptom C?',
    answer_schema: { type: 'yes_no_unsure', help_text: SAMPLE_HELP_TEXT },
    effect: { kind: 'set_presence', feature: SAMPLE_FEATURES.gamma },
  },
  durationAlpha: {
    question_id: 'q.sample_duration_alpha',
    wording: 'Sample question: how long have you had sample symptom A?',
    answer_schema: { type: 'duration', min: 1, max: 999, help_text: SAMPLE_HELP_TEXT },
    effect: { kind: 'set_duration', feature: SAMPLE_FEATURES.alpha },
  },
  severityBeta: {
    question_id: 'q.sample_severity_beta',
    wording: 'Sample question: how much does sample symptom B affect your day?',
    answer_schema: {
      type: 'single_choice',
      options: [
        { value: 'sample_level_1', label: 'A little' },
        { value: 'sample_level_2', label: 'A moderate amount' },
        { value: 'sample_level_3', label: 'A lot' },
      ],
      allow_not_sure: true,
    },
    effect: { kind: 'set_severity', feature: SAMPLE_FEATURES.beta },
  },
  context: {
    question_id: 'q.sample_context',
    wording: 'Sample question: which of these sample situations apply to you?',
    answer_schema: {
      type: 'multiple_choice',
      options: [
        { value: 'sample_situation_1', label: 'Sample situation 1' },
        { value: 'sample_situation_2', label: 'Sample situation 2' },
        { value: 'sample_situation_3', label: 'Sample situation 3' },
      ],
      allow_not_sure: true,
      help_text: SAMPLE_HELP_TEXT,
    },
    effect: { kind: 'add_value', feature: SAMPLE_FEATURES.epsilon },
  },
  measurement: {
    question_id: 'q.sample_measurement',
    wording: 'Sample question: enter the sample measurement, if you know it.',
    answer_schema: {
      type: 'number',
      units: ['sample unit A', 'sample unit B'],
      min: 0,
      max: 500,
      allow_not_sure: true,
      help_text: SAMPLE_HELP_TEXT,
    },
    effect: { kind: 'add_value', feature: SAMPLE_FEATURES.zeta },
  },
  startDate: {
    question_id: 'q.sample_start_date',
    wording: 'Sample question: on which date did sample symptom A start?',
    answer_schema: { type: 'date', latest: 'today', allow_not_sure: true, help_text: SAMPLE_HELP_TEXT },
    effect: { kind: 'add_value', feature: SAMPLE_FEATURES.alpha },
  },
  freeText: {
    question_id: 'q.sample_free_text',
    wording: 'Sample question: is there anything else you would like to add?',
    answer_schema: { type: 'free_text' },
    effect: { kind: 'add_note' },
  },
} as const satisfies Record<string, MockQuestionFixture>;

export const SAMPLE_QUESTION_BY_ID: ReadonlyMap<string, MockQuestionFixture> = new Map(
  Object.values(SAMPLE_QUESTIONS).map((question) => [question.question_id, question]),
);

export const SAMPLE_EVIDENCE = {
  first: {
    evidence_id: 'ev.sample_1',
    source_title: 'Sample source A (placeholder)',
    source_url: 'https://example.org/feeltriva-sample-source-a',
    excerpt:
      'Sample excerpt. In the live service, a passage from a reviewed source appears here so you can see what an explanation is based on.',
    knowledge_release: DEMO_KNOWLEDGE_RELEASE,
  },
  second: {
    evidence_id: 'ev.sample_2',
    source_title: 'Sample source B (placeholder, no link supplied)',
    source_url: null,
    excerpt: 'Sample excerpt. This placeholder shows a source that was supplied without a link.',
    knowledge_release: DEMO_KNOWLEDGE_RELEASE,
  },
} as const satisfies Record<string, Evidence>;

/** An evidence id that deliberately resolves to nothing (scenario 8). */
export const MISSING_EVIDENCE_ID = 'ev.sample_missing';

export const SAMPLE_CANDIDATES = {
  a: {
    disease_id: 'demo.possibility_a',
    name: 'Illustrative possibility A',
    explanation:
      'Sample explanation text. In the live service this is approved content describing why an explanation is being considered. It is not based on anything you typed.',
  },
  b: {
    disease_id: 'demo.possibility_b',
    name: 'Illustrative possibility B',
    explanation:
      'Sample explanation text for a second illustrative possibility. It is a placeholder and does not describe a real condition.',
  },
} as const;

export const SAMPLE_NEXT_ACTION_TEXT = {
  provisional:
    'Sample next step: placeholder guidance. In the live service, the approved next step from the assessment service appears here.',
  urgent:
    'Sample urgent action: placeholder text. Approved urgent instructions and contact details from the assessment service would appear here. This preview contains no real emergency guidance.',
  insufficientAsk: 'Sample: one more answer would help complete this check.',
  insufficientSummary:
    'Sample: there is not enough information to suggest an explanation. A summary of what you shared is available.',
  outOfScope: 'Sample limitation: placeholder text. Approved guidance on where to go next would appear here.',
  evidenceMissing: 'Sample: this result is incomplete. A summary of what you shared is available.',
} as const;

export const SAMPLE_UNKNOWNS = {
  gammaUnknown: 'Sample unknown: whether sample symptom C is present.',
  inPerson: 'Sample unknown: details a health professional would need to check in person.',
  noSupport: 'Sample unknown: no reported detail currently supports a possible explanation.',
  measurementMissing: 'Sample missing detail: the sample measurement has not been provided.',
  changeOverTime: 'Sample missing detail: how sample symptom A has changed over time.',
  scope: 'Sample scope limit: this preview treats the sample details as outside what the service covers.',
  evidence: 'Sample: supporting information for one possible explanation was not available, so it is not shown.',
} as const;
