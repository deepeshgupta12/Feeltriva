import { describe, expect, it } from 'vitest';

import { parseAnswerSchema, type AnswerSchema } from '@/api/types';

import { choiceOptions, draftFromValue, emptyDraft, resolveDraft } from './answers';

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
    expect(resolveDraft(schemas.multi!, { kind: 'multi', values: [], notSure: true })).toEqual({
      ok: true,
      value: ['not_sure'],
      label: 'I’m not sure',
    });
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
    expect(draftFromValue(schemas.multi!, ['not_sure'])).toEqual({ kind: 'multi', values: [], notSure: true });
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
