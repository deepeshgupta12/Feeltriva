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
/**
 * `training_consent` may be left out: the service then records that it was not given. (The generated type
 * marks every field that has a default as always present, which holds for what the service stores, not for
 * what a client has to send.)
 */
export type SessionCreate = Omit<Schemas['SessionCreate'], 'training_consent'> & { training_consent?: boolean };
/** The terms a person agrees to before a check starts (`GET /v1/consent`). */
export type Consent = Schemas['Consent'];
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
  'date',
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
  /** Set by the service on a question about clinically relevant context: declining is always an answer. */
  allow_prefer_not_to_answer?: boolean;
  unit?: string;
  units?: string[];
  min?: number;
  max?: number;
  /** For a date question: the first and last day that can be answered, as YYYY-MM-DD or the word "today". */
  earliest?: string;
  latest?: string;
  /** Backend-provided copy for the "Why this question?" disclosure. */
  help_text?: string;
}

export const NOT_SURE = 'not_sure';
/** The answer that declines a question about clinically relevant context. */
export const PREFER_NOT_TO_ANSWER = 'prefer_not_to_answer';
/** A bound of a date question that means the day of whoever answers. */
export const TODAY = 'today';

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
/** A calendar date, written YYYY-MM-DD. An object, so that it is never taken for an option or for free text. */
export interface DateAnswer {
  date: string;
}

/** Every value the UI can put in `AnswerSubmit.answer`. "Not sure" is the string `not_sure` for every type. */
export type AnswerValue = string | string[] | NumberAnswer | DurationAnswer | DateAnswer;

/** True for a date written YYYY-MM-DD that exists in the calendar. */
export function isCalendarDate(text: unknown): text is string {
  if (typeof text !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return false;
  }
  const parsed = new Date(`${text}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === text;
}

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
  if (raw.allow_prefer_not_to_answer === true) {
    schema.allow_prefer_not_to_answer = true;
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
  for (const bound of ['earliest', 'latest'] as const) {
    const value = raw[bound];
    if (value === undefined) continue;
    // A bound this build cannot read would let a date through that the service refuses.
    if (value !== TODAY && !isCalendarDate(value)) {
      return null;
    }
    schema[bound] = value;
  }
  if (typeof raw.help_text === 'string' && raw.help_text.trim().length > 0) {
    schema.help_text = raw.help_text;
  }
  return schema;
}
