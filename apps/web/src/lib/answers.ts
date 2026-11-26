/**
 * Draft handling for follow-up answers: empty drafts (nothing preselected), validation
 * against the backend-provided answer schema, and the wire value for `AnswerSubmit.answer`.
 */
import {
  DURATION_UNITS,
  NOT_SURE,
  TODAY,
  isCalendarDate,
  type AnswerOption,
  type AnswerSchema,
  type AnswerValue,
  type DurationUnit,
} from '@/api/types';

export const NOT_SURE_LABEL = 'I’m not sure';
/** The service accepts a free-text answer of up to 2,000 characters; a longer one would be refused there. */
export const MAX_FREE_TEXT_LENGTH = 2_000;

export type AnswerDraft =
  | { kind: 'choice'; value: string | null }
  | { kind: 'multi'; values: string[]; notSure: boolean }
  | { kind: 'number'; text: string; unit: string; notSure: boolean }
  | { kind: 'duration'; text: string; unit: DurationUnit | ''; notSure: boolean }
  | { kind: 'date'; text: string; notSure: boolean }
  | { kind: 'text'; text: string; notSure: boolean };

export type DraftResult = { ok: true; value: AnswerValue; label: string } | { ok: false; message: string };

const YES_NO_UNSURE_OPTIONS: readonly AnswerOption[] = [
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
  { value: NOT_SURE, label: NOT_SURE_LABEL },
];

/** Options to render for single-answer questions, including "I'm not sure" when allowed. */
export function choiceOptions(schema: AnswerSchema): readonly AnswerOption[] {
  if (schema.type === 'yes_no_unsure') {
    return YES_NO_UNSURE_OPTIONS;
  }
  const options = schema.options ?? [];
  const hasNotSure = options.some((option) => option.value === NOT_SURE);
  return schema.allow_not_sure && !hasNotSure ? [...options, { value: NOT_SURE, label: NOT_SURE_LABEL }] : options;
}

/** Units offered for a number question. One unit means it is shown as fixed text. */
export function numberUnits(schema: AnswerSchema): string[] {
  if (schema.units && schema.units.length > 0) {
    return schema.units;
  }
  return schema.unit ? [schema.unit] : [];
}

/** Units offered for a duration question: the schema's subset, or all four. */
export function durationUnits(schema: AnswerSchema): DurationUnit[] {
  const allowed = (schema.units ?? []).filter((unit): unit is DurationUnit =>
    (DURATION_UNITS as readonly string[]).includes(unit),
  );
  return allowed.length > 0 ? allowed : [...DURATION_UNITS];
}

/** A blank draft. Nothing is ever preselected. */
export function emptyDraft(schema: AnswerSchema): AnswerDraft {
  switch (schema.type) {
    case 'yes_no_unsure':
    case 'single_choice':
      return { kind: 'choice', value: null };
    case 'multiple_choice':
      return { kind: 'multi', values: [], notSure: false };
    case 'number': {
      const units = numberUnits(schema);
      // A single fixed unit is not a choice, so it can be filled in.
      return { kind: 'number', text: '', unit: units.length === 1 ? (units[0] ?? '') : '', notSure: false };
    }
    case 'duration':
      return { kind: 'duration', text: '', unit: '', notSure: false };
    case 'date':
      return { kind: 'date', text: '', notSure: false };
    case 'free_text':
      return { kind: 'text', text: '', notSure: false };
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Rebuilds a draft from a value the user already chose (kept after a failed or conflicting send). */
export function draftFromValue(schema: AnswerSchema, value: AnswerValue): AnswerDraft {
  const draft = emptyDraft(schema);
  const notSure = value === NOT_SURE;
  switch (draft.kind) {
    case 'choice':
      return typeof value === 'string' ? { kind: 'choice', value } : draft;
    case 'multi':
      if (notSure) return { ...draft, notSure: true };
      return Array.isArray(value) ? { ...draft, values: [...value] } : draft;
    case 'number':
      if (notSure) return { ...draft, notSure: true };
      return isRecord(value) && typeof value.value === 'number'
        ? { ...draft, text: String(value.value), unit: typeof value.unit === 'string' ? value.unit : draft.unit }
        : draft;
    case 'duration':
      if (notSure) return { ...draft, notSure: true };
      return isRecord(value) && typeof value.value === 'number' && typeof value.unit === 'string'
        ? { ...draft, text: String(value.value), unit: value.unit as DurationUnit }
        : draft;
    case 'date':
      if (notSure) return { ...draft, notSure: true };
      return isRecord(value) && isCalendarDate(value.date) ? { ...draft, text: value.date } : draft;
    case 'text':
      if (notSure) return { ...draft, notSure: true };
      return typeof value === 'string' ? { ...draft, text: value } : draft;
  }
}

const calendarFormatter = new Intl.DateTimeFormat('en-GB', { dateStyle: 'long', timeZone: 'UTC' });

/** A calendar date in words, "20 November 2026". The date is a day, not a moment: no time zone moves it. */
export function formatCalendarDate(iso: string): string {
  return isCalendarDate(iso) ? calendarFormatter.format(new Date(`${iso}T00:00:00Z`)) : iso;
}

/** The day it is for the person at this device, as YYYY-MM-DD. */
export function localToday(now: Date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** The first and last day a date question accepts, with "today" read as the day at this device. */
export function dateBounds(schema: AnswerSchema, now: Date = new Date()): { earliest?: string; latest?: string } {
  const resolve = (bound: string | undefined) => (bound === TODAY ? localToday(now) : bound);
  const earliest = resolve(schema.earliest);
  const latest = resolve(schema.latest);
  return { ...(earliest ? { earliest } : {}), ...(latest ? { latest } : {}) };
}

/**
 * The words of each option of the questions seen in this visit, by the option's internal value (BUG-009).
 * The service stores the internal value of a chosen option; it is shown to the person in the option's own
 * words. A value that two questions use for different words is kept as '' and shown as neither.
 */
export function withOptionLabels(
  known: Readonly<Record<string, string>>,
  schema: AnswerSchema,
): Record<string, string> {
  const next = { ...known };
  for (const option of schema.options ?? []) {
    const seen = next[option.value];
    next[option.value] = seen === undefined || seen === option.label ? option.label : '';
  }
  return next;
}

function parseNumber(text: string): number | null {
  const normalised = text.trim().replace(',', '.');
  if (normalised.length === 0 || !/^-?\d+(\.\d+)?$/.test(normalised)) {
    return null;
  }
  const parsed = Number(normalised);
  return Number.isFinite(parsed) ? parsed : null;
}

function rangeMessage(schema: AnswerSchema, value: number): string | null {
  if (schema.min !== undefined && value < schema.min) {
    return `Enter a number of ${schema.min} or more.`;
  }
  if (schema.max !== undefined && value > schema.max) {
    return `Enter a number of ${schema.max} or less.`;
  }
  return null;
}

function singularUnit(value: number, unit: string): string {
  return value === 1 ? unit.replace(/s$/, '') : unit;
}

/**
 * Validates a draft and produces the wire value plus a readable label for the transcript.
 *
 * "Not sure" is sent as the string `not_sure` for every type of question: the service reads no
 * other form as "not sure" (BUG-010). Only offered when the schema allows it.
 */
export function resolveDraft(schema: AnswerSchema, draft: AnswerDraft): DraftResult {
  const notSureAllowed = schema.allow_not_sure === true;

  switch (draft.kind) {
    case 'choice': {
      const option = choiceOptions(schema).find((item) => item.value === draft.value);
      if (!option) {
        return { ok: false, message: 'Choose an answer to continue.' };
      }
      return { ok: true, value: option.value, label: option.label };
    }
    case 'multi': {
      if (draft.notSure && notSureAllowed) {
        return { ok: true, value: NOT_SURE, label: NOT_SURE_LABEL };
      }
      const selected = (schema.options ?? []).filter((option) => draft.values.includes(option.value));
      if (selected.length === 0) {
        return { ok: false, message: 'Select at least one option to continue.' };
      }
      return {
        ok: true,
        value: selected.map((option) => option.value),
        label: selected.map((option) => option.label).join(', '),
      };
    }
    case 'number': {
      if (draft.notSure && notSureAllowed) {
        return { ok: true, value: NOT_SURE, label: NOT_SURE_LABEL };
      }
      const parsed = parseNumber(draft.text);
      if (parsed === null) {
        return { ok: false, message: 'Enter a number, for example 12 or 12.5.' };
      }
      const range = rangeMessage(schema, parsed);
      if (range) {
        return { ok: false, message: range };
      }
      const units = numberUnits(schema);
      if (units.length > 1 && !units.includes(draft.unit)) {
        return { ok: false, message: 'Choose a unit.' };
      }
      const unit = units.length === 0 ? null : units.length === 1 ? (units[0] ?? null) : draft.unit;
      return { ok: true, value: { value: parsed, unit }, label: unit ? `${parsed} ${unit}` : String(parsed) };
    }
    case 'duration': {
      if (draft.notSure && notSureAllowed) {
        return { ok: true, value: NOT_SURE, label: NOT_SURE_LABEL };
      }
      const parsed = parseNumber(draft.text);
      if (parsed === null || parsed < 0) {
        return { ok: false, message: 'Enter how long as a number, for example 3.' };
      }
      const range = rangeMessage(schema, parsed);
      if (range) {
        return { ok: false, message: range };
      }
      if (draft.unit === '' || !durationUnits(schema).includes(draft.unit)) {
        return { ok: false, message: 'Choose hours, days, weeks or months.' };
      }
      return {
        ok: true,
        value: { value: parsed, unit: draft.unit },
        label: `${parsed} ${singularUnit(parsed, draft.unit)}`,
      };
    }
    case 'date': {
      if (draft.notSure && notSureAllowed) {
        return { ok: true, value: NOT_SURE, label: NOT_SURE_LABEL };
      }
      if (!isCalendarDate(draft.text)) {
        return { ok: false, message: 'Choose a date to continue.' };
      }
      const { earliest, latest } = dateBounds(schema);
      if (earliest && draft.text < earliest) {
        return {
          ok: false,
          message:
            schema.earliest === TODAY
              ? 'Choose a date that is today or later.'
              : `Choose a date on or after ${formatCalendarDate(earliest)}.`,
        };
      }
      if (latest && draft.text > latest) {
        return {
          ok: false,
          message:
            schema.latest === TODAY
              ? 'Choose a date that is today or earlier.'
              : `Choose a date on or before ${formatCalendarDate(latest)}.`,
        };
      }
      return { ok: true, value: { date: draft.text }, label: formatCalendarDate(draft.text) };
    }
    case 'text': {
      if (draft.notSure && notSureAllowed) {
        return { ok: true, value: NOT_SURE, label: NOT_SURE_LABEL };
      }
      const text = draft.text.trim();
      if (text.length === 0) {
        return { ok: false, message: 'Write an answer to continue.' };
      }
      if (text.length > MAX_FREE_TEXT_LENGTH) {
        return {
          ok: false,
          message: `Shorten your answer to ${MAX_FREE_TEXT_LENGTH.toLocaleString('en-US')} characters or fewer.`,
        };
      }
      return { ok: true, value: text, label: text };
    }
  }
}
