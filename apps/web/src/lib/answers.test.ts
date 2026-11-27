import { afterEach, describe, expect, it, vi } from 'vitest';

import { parseAnswerSchema, type AnswerSchema } from '@/api/types';

import {
  choiceOptions,
  dateBounds,
  draftFromValue,
  emptyDraft,
  formatCalendarDate,
  MAX_FREE_TEXT_LENGTH,
  resolveDraft,
  withOptionLabels,
} from './answers';

const schemas: Record<string, AnswerSchema> = {
  yesNo: { type: 'yes_no_unsure' },
  single: {
    type: 'single_choice',
    options: [
      { value: 'a', label: 'Option A' },
      { value: 'b', label: 'Option B' },
    ],
  },
  singleUnsure: { type: 'single_choice', options: [{ value: 'a', label: 'Option A' }], allow_not_sure: true },
  multi: {
    type: 'multiple_choice',
    options: [
      { value: 'a', label: 'Option A' },
      { value: 'b', label: 'Option B' },
    ],
    allow_not_sure: true,
  },
  number: { type: 'number', units: ['kg', 'lb'], min: 1, max: 300 },
  numberFixedUnit: { type: 'number', unit: 'cm' },
  numberNoUnit: { type: 'number' },
  duration: { type: 'duration', min: 1 },
  text: { type: 'free_text' },
};

describe('emptyDraft', () => {
  it('never preselects a choice', () => {
    expect(emptyDraft(schemas.yesNo!)).toEqual({ kind: 'choice', value: null });
    expect(emptyDraft(schemas.multi!)).toEqual({ kind: 'multi', values: [], notSure: false });
    expect(emptyDraft(schemas.duration!)).toEqual({ kind: 'duration', text: '', unit: '', notSure: false });
    // With several units the user must choose; a single fixed unit is not a choice.
    expect(emptyDraft(schemas.number!)).toMatchObject({ unit: '' });
    expect(emptyDraft(schemas.numberFixedUnit!)).toMatchObject({ unit: 'cm' });
  });
});

describe('choiceOptions', () => {
  it('always offers not sure for yes/no/unsure and only when allowed for single choice', () => {
    expect(choiceOptions(schemas.yesNo!).map((option) => option.value)).toEqual(['yes', 'no', 'not_sure']);
    expect(choiceOptions(schemas.single!).map((option) => option.value)).toEqual(['a', 'b']);
    expect(choiceOptions(schemas.singleUnsure!).map((option) => option.value)).toEqual(['a', 'not_sure']);
  });
});

describe('resolveDraft', () => {
  it('requires a selection', () => {
    expect(resolveDraft(schemas.yesNo!, { kind: 'choice', value: null })).toMatchObject({ ok: false });
    expect(resolveDraft(schemas.multi!, { kind: 'multi', values: [], notSure: false })).toMatchObject({ ok: false });
  });

  it('produces the agreed wire values', () => {
    expect(resolveDraft(schemas.yesNo!, { kind: 'choice', value: 'not_sure' })).toEqual({
      ok: true,
      value: 'not_sure',
      label: 'I’m not sure',
    });
    expect(resolveDraft(schemas.single!, { kind: 'choice', value: 'b' })).toEqual({
      ok: true,
      value: 'b',
      label: 'Option B',
    });
    expect(resolveDraft(schemas.multi!, { kind: 'multi', values: ['b', 'a'], notSure: false })).toEqual({
      ok: true,
      value: ['a', 'b'],
      label: 'Option A, Option B',
    });
    expect(resolveDraft(schemas.number!, { kind: 'number', text: '72.5', unit: 'kg', notSure: false })).toEqual({
      ok: true,
      value: { value: 72.5, unit: 'kg' },
      label: '72.5 kg',
    });
    expect(resolveDraft(schemas.numberNoUnit!, { kind: 'number', text: '4', unit: '', notSure: false })).toEqual({
      ok: true,
      value: { value: 4, unit: null },
      label: '4',
    });
    expect(resolveDraft(schemas.duration!, { kind: 'duration', text: '1', unit: 'weeks', notSure: false })).toEqual({
      ok: true,
      value: { value: 1, unit: 'weeks' },
      label: '1 week',
    });
    expect(resolveDraft(schemas.text!, { kind: 'text', text: '  some words  ', notSure: false })).toEqual({
      ok: true,
      value: 'some words',
      label: 'some words',
    });
  });

  it('validates numbers, ranges and units inline', () => {
    expect(resolveDraft(schemas.number!, { kind: 'number', text: 'abc', unit: 'kg', notSure: false })).toMatchObject({
      ok: false,
    });
    expect(resolveDraft(schemas.number!, { kind: 'number', text: '0', unit: 'kg', notSure: false })).toEqual({
      ok: false,
      message: 'Enter a number of 1 or more.',
    });
    expect(resolveDraft(schemas.number!, { kind: 'number', text: '301', unit: 'kg', notSure: false })).toEqual({
      ok: false,
      message: 'Enter a number of 300 or less.',
    });
    expect(resolveDraft(schemas.number!, { kind: 'number', text: '70', unit: '', notSure: false })).toEqual({
      ok: false,
      message: 'Choose a unit.',
    });
    expect(resolveDraft(schemas.duration!, { kind: 'duration', text: '3', unit: '', notSure: false })).toMatchObject({
      ok: false,
    });
    expect(resolveDraft(schemas.text!, { kind: 'text', text: '   ', notSure: false })).toMatchObject({ ok: false });
  });

  it('only accepts "not sure" when the schema allows it', () => {
    // One form for every type of question: the service reads no other as "not sure" (BUG-010).
    const notSure = { ok: true, value: 'not_sure', label: 'I’m not sure' };
    expect(resolveDraft(schemas.multi!, { kind: 'multi', values: [], notSure: true })).toEqual(notSure);
    expect(
      resolveDraft({ type: 'free_text', allow_not_sure: true }, { kind: 'text', text: '', notSure: true }),
    ).toEqual(notSure);
    expect(resolveDraft({ type: 'date', allow_not_sure: true }, { kind: 'date', text: '', notSure: true })).toEqual(
      notSure,
    );
    // `number` here does not set allow_not_sure, so the flag is ignored and a number is required.
    expect(resolveDraft(schemas.number!, { kind: 'number', text: '', unit: '', notSure: true })).toMatchObject({
      ok: false,
    });
  });
});

describe('draftFromValue', () => {
  it('restores a retained answer exactly', () => {
    expect(draftFromValue(schemas.yesNo!, 'yes')).toEqual({ kind: 'choice', value: 'yes' });
    expect(draftFromValue(schemas.multi!, ['a'])).toEqual({ kind: 'multi', values: ['a'], notSure: false });
    expect(draftFromValue(schemas.multi!, 'not_sure')).toEqual({ kind: 'multi', values: [], notSure: true });
    expect(draftFromValue({ type: 'date' }, { date: '2026-01-15' })).toEqual({
      kind: 'date',
      text: '2026-01-15',
      notSure: false,
    });
    expect(draftFromValue({ type: 'date', allow_not_sure: true }, 'not_sure')).toMatchObject({ notSure: true });
    expect(draftFromValue(schemas.duration!, { value: 2, unit: 'days' })).toEqual({
      kind: 'duration',
      text: '2',
      unit: 'days',
      notSure: false,
    });
    expect(draftFromValue(schemas.number!, { value: 70, unit: 'lb' })).toEqual({
      kind: 'number',
      text: '70',
      unit: 'lb',
      notSure: false,
    });
  });
});

describe('parseAnswerSchema', () => {
  it('accepts the agreed shapes', () => {
    expect(parseAnswerSchema({ type: 'yes_no_unsure', help_text: 'Why' })).toEqual({
      type: 'yes_no_unsure',
      help_text: 'Why',
    });
    expect(parseAnswerSchema({ type: 'duration', units: ['days', 'weeks'], min: 1, max: 10 })).toEqual({
      type: 'duration',
      units: ['days', 'weeks'],
      min: 1,
      max: 10,
    });
  });

  it('returns null for shapes it cannot render safely rather than guessing', () => {
    expect(parseAnswerSchema(null)).toBeNull();
    expect(parseAnswerSchema({})).toBeNull();
    expect(parseAnswerSchema({ type: 'slider' })).toBeNull();
    expect(parseAnswerSchema({ type: 'single_choice' })).toBeNull();
    expect(parseAnswerSchema({ type: 'single_choice', options: [{ value: 1, label: 'x' }] })).toBeNull();
  });

  it('drops blank help text so the disclosure is hidden', () => {
    expect(parseAnswerSchema({ type: 'free_text', help_text: '   ' })).toEqual({ type: 'free_text' });
  });
});

describe('date answers', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts empty and asks for a date', () => {
    expect(emptyDraft({ type: 'date' })).toEqual({ kind: 'date', text: '', notSure: false });
    expect(resolveDraft({ type: 'date' }, { kind: 'date', text: '', notSure: false })).toEqual({
      ok: false,
      message: 'Choose a date to continue.',
    });
    expect(resolveDraft({ type: 'date' }, { kind: 'date', text: '2026-02-30', notSure: false })).toMatchObject({
      ok: false,
    });
  });

  it('sends the date as an object and shows it in words', () => {
    expect(resolveDraft({ type: 'date' }, { kind: 'date', text: '2026-01-15', notSure: false })).toEqual({
      ok: true,
      value: { date: '2026-01-15' },
      label: '15 January 2026',
    });
    expect(formatCalendarDate('2026-11-20')).toBe('20 November 2026');
    // Something that is not a date is shown as it is, not as an invented date.
    expect(formatCalendarDate('soon')).toBe('soon');
  });

  it('reads "today" as the day at this device and keeps to the bounds of the question', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 2, 10, 23, 30));
    const past: AnswerSchema = { type: 'date', latest: 'today' };
    expect(dateBounds(past)).toEqual({ latest: '2026-03-10' });
    expect(resolveDraft(past, { kind: 'date', text: '2026-03-10', notSure: false })).toMatchObject({ ok: true });
    expect(resolveDraft(past, { kind: 'date', text: '2026-03-11', notSure: false })).toEqual({
      ok: false,
      message: 'Choose a date that is today or earlier.',
    });
    const fixed: AnswerSchema = { type: 'date', earliest: '2026-01-01', latest: '2026-01-31' };
    expect(resolveDraft(fixed, { kind: 'date', text: '2025-12-31', notSure: false })).toEqual({
      ok: false,
      message: 'Choose a date on or after 1 January 2026.',
    });
    expect(resolveDraft(fixed, { kind: 'date', text: '2026-02-01', notSure: false })).toEqual({
      ok: false,
      message: 'Choose a date on or before 31 January 2026.',
    });
  });

  it('is a question this build can show only when its bounds can be read', () => {
    expect(parseAnswerSchema({ type: 'date', latest: 'today', earliest: '2020-01-01' })).toEqual({
      type: 'date',
      latest: 'today',
      earliest: '2020-01-01',
    });
    expect(parseAnswerSchema({ type: 'date', latest: 'soon' })).toBeNull();
    expect(parseAnswerSchema({ type: 'date', earliest: '2026-02-30' })).toBeNull();
  });
});

describe('free text', () => {
  it('is no longer than the service accepts', () => {
    expect(MAX_FREE_TEXT_LENGTH).toBe(2000);
    const long = 'a'.repeat(2001);
    expect(resolveDraft({ type: 'free_text' }, { kind: 'text', text: long, notSure: false })).toEqual({
      ok: false,
      message: 'Shorten your answer to 2,000 characters or fewer.',
    });
  });
});

describe('withOptionLabels', () => {
  it('keeps the words of each option by its internal value, and neither where two questions disagree', () => {
    const first = withOptionLabels({}, schemas.single!);
    expect(first).toEqual({ a: 'Option A', b: 'Option B' });
    const again = withOptionLabels(first, schemas.singleUnsure!);
    expect(again).toEqual({ a: 'Option A', b: 'Option B' });
    const other = withOptionLabels(again, { type: 'single_choice', options: [{ value: 'a', label: 'Another A' }] });
    expect(other).toEqual({ a: '', b: 'Option B' });
    // A question without options changes nothing.
    expect(withOptionLabels(other, { type: 'date' })).toEqual(other);
  });
});

describe('a question about clinically relevant context', () => {
  it('offers "Prefer not to answer" last, beside its own choices, and sends it as its own value', () => {
    const context = parseAnswerSchema({ type: 'yes_no_unsure', allow_prefer_not_to_answer: true })!;
    expect(choiceOptions(context).map((option) => option.label)).toEqual([
      'Yes',
      'No',
      'I’m not sure',
      'Prefer not to answer',
    ]);
    expect(resolveDraft(context, { kind: 'choice', value: 'prefer_not_to_answer' })).toEqual({
      ok: true,
      value: 'prefer_not_to_answer',
      label: 'Prefer not to answer',
    });
    // An ordinary question does not offer it, and a value that is not offered is not an answer.
    expect(choiceOptions(schemas.yesNo!).map((option) => option.value)).toEqual(['yes', 'no', 'not_sure']);
    expect(resolveDraft(schemas.yesNo!, { kind: 'choice', value: 'prefer_not_to_answer' })).toMatchObject({
      ok: false,
    });
    const single = parseAnswerSchema({
      type: 'single_choice',
      options: [{ value: 'a', label: 'Option A' }],
      allow_not_sure: true,
      allow_prefer_not_to_answer: true,
    })!;
    expect(choiceOptions(single).map((option) => option.value)).toEqual(['a', 'not_sure', 'prefer_not_to_answer']);
  });
});
