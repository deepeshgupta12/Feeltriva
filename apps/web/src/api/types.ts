/**
 * Domain types for the assessment API.
 *
 * Wire shapes come from the generated OpenAPI schema (`pnpm gen:api`). This module only
 * adds the pieces the OpenAPI document leaves open: the session state vocabulary and the
 * `Question.answer_schema` shape agreed with the backend.
 */
import type { components } from './generated/schema';

type Schemas = components['schemas'];

export type Demographics = Schemas['Demographics'];
export type SessionCreate = Schemas['SessionCreate'];
export type Session = Schemas['Session'];
export type ObservationRecord = Schemas['ObservationRecord'];
export type ObservationInput = Schemas['Observation'];
export type Presence = ObservationRecord['presence'];
export type AssessmentRequest = Schemas['AssessmentRequest'];
export type Assessment = Schemas['Assessment'];
export type AssessmentStatus = Assessment['status'];
export type Urgency = Assessment['urgency'];
export type NextAction = Assessment['next_action'];
export type Candidate = Schemas['Candidate'];
export type Evidence = Schemas['Evidence'];
export type AnswerSubmit = Schemas['AnswerSubmit'];
export type Summary = Schemas['Summary'];
export type DeletionReceipt = Schemas['DeletionReceipt'];
export type ApiErrorBody = Schemas['Error'];

/**
 * The OpenAPI schema types `answer_schema` as an open object. It is carried as `unknown`
 * and narrowed with `parseAnswerSchema` before anything is rendered.
 */
export type Question = Omit<Schemas['Question'], 'answer_schema'> & { answer_schema: unknown };

/** Exactly one of `text` or `observations` (the OpenAPI `oneOf`). */
export type ObservationSubmit =
  { observation_version: number; text: string } | { observation_version: number; observations: ObservationInput[] };

// ---------------------------------------------------------------------------
// Session state
// ---------------------------------------------------------------------------

export const SERVER_SESSION_STATES = [
  'intake',
  'clarifying',
  'assessing',
  'result_ready',
  'urgent_handoff',
  'out_of_scope',
  'insufficient_information',
  'system_unavailable',
  'closed',
] as const;

/** States the assessment service can report in `Session.state`. */
export type ServerSessionState = (typeof SERVER_SESSION_STATES)[number];

/**
 * Full flow state model. `consent_pending` exists only in the browser, before a session
 * has been created. Everything else is reported by the server and never derived locally.
 */
export type AssessmentFlowState = 'consent_pending' | ServerSessionState;

/** Returns the recognised state, or `unknown` for a value this build does not know. */
export function parseSessionState(state: string): ServerSessionState | 'unknown' {
  return (SERVER_SESSION_STATES as readonly string[]).includes(state) ? (state as ServerSessionState) : 'unknown';
}

// ---------------------------------------------------------------------------
// Question answer schema
// ---------------------------------------------------------------------------

export const ANSWER_TYPES = [
  'yes_no_unsure',
  'single_choice',
  'multiple_choice',
  'number',
  'duration',
  'free_text',
] as const;

export type AnswerType = (typeof ANSWER_TYPES)[number];

export interface AnswerOption {
  value: string;
  label: string;
}

export interface AnswerSchema {
  type: AnswerType;
  options?: AnswerOption[];
  allow_not_sure?: boolean;
  unit?: string;
  units?: string[];
  min?: number;
  max?: number;
  /** Backend-provided copy for the "Why this question?" disclosure. */
  help_text?: string;
}

export const NOT_SURE = 'not_sure';

export const DURATION_UNITS = ['hours', 'days', 'weeks', 'months'] as const;
export type DurationUnit = (typeof DURATION_UNITS)[number];

export type YesNoUnsureAnswer = 'yes' | 'no' | typeof NOT_SURE;
export interface NumberAnswer {
  value: number;
  unit: string | null;
}
export interface DurationAnswer {
  value: number;
  unit: DurationUnit;
}

/** Every value the UI can put in `AnswerSubmit.answer`. */
export type AnswerValue = string | string[] | NumberAnswer | DurationAnswer;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function optionalNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/**
 * Narrows a raw `answer_schema`. Returns `null` when the shape is not one this build can
 * render safely; the caller then shows an "unsupported question" state instead of guessing.
 */
export function parseAnswerSchema(raw: unknown): AnswerSchema | null {
  if (!isRecord(raw)) {
    return null;
  }
  const type = raw.type;
  if (typeof type !== 'string' || !(ANSWER_TYPES as readonly string[]).includes(type)) {
    return null;
  }
  const schema: AnswerSchema = { type: type as AnswerType };

  if (Array.isArray(raw.options)) {
    const options: AnswerOption[] = [];
    for (const option of raw.options) {
      if (isRecord(option) && typeof option.value === 'string' && typeof option.label === 'string') {
        options.push({ value: option.value, label: option.label });
      } else {
        return null;
      }
    }
    schema.options = options;
  }
  if ((schema.type === 'single_choice' || schema.type === 'multiple_choice') && !schema.options?.length) {
    return null;
  }
  if (typeof raw.allow_not_sure === 'boolean') {
    schema.allow_not_sure = raw.allow_not_sure;
  }
  if (typeof raw.unit === 'string' && raw.unit.length > 0) {
    schema.unit = raw.unit;
  }
  if (Array.isArray(raw.units)) {
    const units = raw.units.filter((unit): unit is string => typeof unit === 'string' && unit.length > 0);
    if (units.length > 0) {
      schema.units = units;
    }
  }
  const min = optionalNumber(raw.min);
  if (min !== undefined) {
    schema.min = min;
  }
  const max = optionalNumber(raw.max);
  if (max !== undefined) {
    schema.max = max;
  }
  if (typeof raw.help_text === 'string' && raw.help_text.trim().length > 0) {
    schema.help_text = raw.help_text;
  }
  return schema;
}
