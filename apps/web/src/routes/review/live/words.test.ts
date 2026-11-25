import { describe, expect, it } from 'vitest';

import { REVIEW_STATE_LABELS } from '@/api/liveReview';

import { howGrouped, howMatched, kindOfName, kindOfText, thingToCheck, wordingCue, zeroMeaning } from './words';

describe('plain words for the codes of the stored data', () => {
  it('puts every code the stored data holds today into words', () => {
    // The codes are those found in the main database on 2026-11-25; none is shown raw.
    const matched = [
      'exact_label',
      'mondo_equivalent',
      'exact_synonym',
      'exact_title',
      'exact_titleofotherentity',
      'source_provided',
      'exact_name',
      'short_name_in_question',
      'reviewer_confirmed',
    ];
    for (const code of matched) {
      expect(howMatched(code)).not.toContain('_');
      expect(howMatched(code)).not.toBe(code);
    }
    expect(howGrouped('lexical_casefold_whitespace')).toBe('Same spelling, ignoring capital letters and extra spaces');
    expect(zeroMeaning('no_per_source')).toBe('The source’s own description says a 0 means “no”');
    expect(zeroMeaning('no_answer')).toBe('The question was not answered');
    expect(['description', 'cause', 'symptom', 'treatment'].map(kindOfText)).toEqual([
      'Description',
      'Causes',
      'Symptoms',
      'Treatment',
    ]);
    expect(['hedge', 'negation', 'population'].map(wordingCue)).toEqual([
      'Cautious wording',
      'Says that something is not so',
      'Names a group of people',
    ]);
    expect(thingToCheck('cut_off')).toBe('text cut short');
    expect([kindOfName('disease'), kindOfName('feature')]).toEqual(['a condition', 'a symptom or other item']);
  });

  it('shows a code it does not know as it is, with spaces, and hides nothing', () => {
    expect(howMatched('some_new_method')).toBe('some new method');
    expect(zeroMeaning('never_seen')).toBe('never seen');
  });

  it('names the four states of a decision without the word "pending" or "retired"', () => {
    expect(REVIEW_STATE_LABELS).toEqual({
      pending: 'Waiting for a decision',
      approved: 'Approved',
      rejected: 'Rejected',
      retired: 'No longer used',
    });
  });
});
