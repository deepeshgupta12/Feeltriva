/**
 * Runtime checks for service responses. The UI only renders responses that match the
 * contract; anything else becomes an `invalid_response` error instead of a partial result.
 */
import { ApiError } from './errors';
import type { Assessment, Consent, DeletionReceipt, Question, Session, Summary } from './types';

const PRESENCE = ['present', 'absent', 'uncertain', 'not_asked'];
const ASSESSMENT_STATUS = [
  'needs_clarification',
  'provisional',
  'urgent_handoff',
  'out_of_scope',
  'insufficient_information',
  'system_unavailable',
];
const URGENCY = ['not_assessed', 'emergency', 'urgent', 'routine', 'self_care_with_safety_net'];
const NEXT_ACTION = ['ask_question', 'seek_care', 'show_summary', 'retry'];
const DELETION_STATUS = ['deletion_scheduled', 'deleted'];

type Rec = Record<string, unknown>;

function fail(what: string, detail: string): never {
  throw new ApiError({
    kind: 'invalid_response',
    status: null,
    code: 'invalid_response',
    message: `The service returned an unexpected ${what} (${detail}).`,
    retryable: false,
  });
}

function isRec(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isVersion(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

export function parseSession(value: unknown): Session {
  if (!isRec(value)) fail('session', 'not an object');
  if (!isString(value.session_id)) fail('session', 'session_id');
  if (!isVersion(value.observation_version)) fail('session', 'observation_version');
  if (!isString(value.state)) fail('session', 'state');
  if (!isString(value.expires_at)) fail('session', 'expires_at');
  if (!Array.isArray(value.observations)) fail('session', 'observations');
  for (const observation of value.observations) {
    if (!isRec(observation)) fail('session', 'observation');
    if (!isNullableString(observation.feature_id)) fail('session', 'observation.feature_id');
    if (!isString(observation.presence) || !PRESENCE.includes(observation.presence)) {
      fail('session', 'observation.presence');
    }
    if (typeof observation.confirmed !== 'boolean') fail('session', 'observation.confirmed');
    if (!isString(observation.observation_id)) fail('session', 'observation.observation_id');
    if (!isVersion(observation.observation_version)) fail('session', 'observation.observation_version');
  }
  if (value.demographics !== undefined && !isRec(value.demographics)) fail('session', 'demographics');
  return value as unknown as Session;
}

export function parseQuestion(value: unknown): Question {
  if (!isRec(value)) fail('question', 'not an object');
  if (!isString(value.question_id)) fail('question', 'question_id');
  if (!isString(value.wording)) fail('question', 'wording');
  if (!isVersion(value.observation_version)) fail('question', 'observation_version');
  if (!isRec(value.answer_schema)) fail('question', 'answer_schema');
  return value as unknown as Question;
}

export function parseAssessment(value: unknown): Assessment {
  if (!isRec(value)) fail('assessment', 'not an object');
  if (!isString(value.assessment_id)) fail('assessment', 'assessment_id');
  if (!isString(value.session_id)) fail('assessment', 'session_id');
  if (!isVersion(value.observation_version)) fail('assessment', 'observation_version');
  if (!isString(value.status) || !ASSESSMENT_STATUS.includes(value.status)) fail('assessment', 'status');
  if (!isString(value.urgency) || !URGENCY.includes(value.urgency)) fail('assessment', 'urgency');
  if (!Array.isArray(value.candidates) || value.candidates.length > 3) fail('assessment', 'candidates');
  for (const candidate of value.candidates) {
    if (!isRec(candidate)) fail('assessment', 'candidate');
    if (!isString(candidate.disease_id)) fail('assessment', 'candidate.disease_id');
    if (!isString(candidate.name)) fail('assessment', 'candidate.name');
    if (!isString(candidate.explanation)) fail('assessment', 'candidate.explanation');
    if (!isStringArray(candidate.supporting_observation_ids))
      fail('assessment', 'candidate.supporting_observation_ids');
    if (!isStringArray(candidate.conflicting_observation_ids))
      fail('assessment', 'candidate.conflicting_observation_ids');
    if (!isStringArray(candidate.evidence_ids)) fail('assessment', 'candidate.evidence_ids');
  }
  if (!isStringArray(value.unknowns)) fail('assessment', 'unknowns');
  const nextAction = value.next_action;
  if (!isRec(nextAction)) fail('assessment', 'next_action');
  if (!isString(nextAction.type) || !NEXT_ACTION.includes(nextAction.type)) fail('assessment', 'next_action.type');
  if (!isString(nextAction.text)) fail('assessment', 'next_action.text');
  if (nextAction.question_id !== undefined && !isString(nextAction.question_id)) {
    fail('assessment', 'next_action.question_id');
  }
  if (!isStringArray(value.evidence_ids)) fail('assessment', 'evidence_ids');
  const versions = value.versions;
  if (!isRec(versions)) fail('assessment', 'versions');
  for (const key of ['knowledge', 'rules', 'model', 'prompt']) {
    if (!isNullableString(versions[key])) fail('assessment', `versions.${key}`);
  }
  if (!Array.isArray(value.evidence)) fail('assessment', 'evidence');
  for (const evidence of value.evidence) {
    if (!isRec(evidence)) fail('assessment', 'evidence item');
    if (!isString(evidence.evidence_id)) fail('assessment', 'evidence.evidence_id');
    if (!isString(evidence.source_title)) fail('assessment', 'evidence.source_title');
    if (!isNullableString(evidence.source_url)) fail('assessment', 'evidence.source_url');
    if (!isString(evidence.excerpt)) fail('assessment', 'evidence.excerpt');
    if (!isString(evidence.knowledge_release)) fail('assessment', 'evidence.knowledge_release');
  }
  return value as unknown as Assessment;
}

export function parseSummary(value: unknown): Summary {
  if (!isRec(value)) fail('summary', 'not an object');
  if (!isString(value.session_id)) fail('summary', 'session_id');
  if (!isVersion(value.observation_version)) fail('summary', 'observation_version');
  if (!isString(value.summary_text)) fail('summary', 'summary_text');
  if (value.requires_user_review !== true) fail('summary', 'requires_user_review');
  return value as unknown as Summary;
}

export function parseDeletionReceipt(value: unknown): DeletionReceipt {
  if (!isRec(value)) fail('deletion receipt', 'not an object');
  if (!isString(value.session_id)) fail('deletion receipt', 'session_id');
  if (!isString(value.status) || !DELETION_STATUS.includes(value.status)) fail('deletion receipt', 'status');
  if (!isString(value.receipt_id)) fail('deletion receipt', 'receipt_id');
  return value as unknown as DeletionReceipt;
}

/** The terms are shown word for word, so a part that is missing means nothing is shown and nothing can be agreed to. */
export function parseConsent(value: unknown): Consent {
  if (!isRec(value)) fail('terms', 'not an object');
  if (!isString(value.version) || value.version.length === 0) fail('terms', 'version');
  if (value.status !== 'draft' && value.status !== 'approved') fail('terms', 'status');
  if (!isString(value.title)) fail('terms', 'title');
  if (!Array.isArray(value.sections) || value.sections.length === 0) fail('terms', 'sections');
  for (const section of value.sections) {
    if (!isRec(section) || !isString(section.heading) || !isStringArray(section.paragraphs)) fail('terms', 'section');
  }
  if (!isString(value.acknowledgement) || value.acknowledgement.length === 0) fail('terms', 'acknowledgement');
  if (!isRec(value.training) || !isString(value.training.label) || !isString(value.training.explanation)) {
    fail('terms', 'training');
  }
  return value as unknown as Consent;
}
