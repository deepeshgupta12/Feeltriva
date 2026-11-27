import { describe, expect, it } from 'vitest';

import type { Assessment, ObservationRecord, Session } from '@/api/types';
import { parseSessionState } from '@/api/types';
import { parseConfig } from '@/config/env';

import {
  currentObservations,
  formatObservationValue,
  groupObservations,
  observationDetails,
  isAssessmentStale,
  observationLabel,
  urgencyPresentation,
} from './selectors';

function observation(overrides: Partial<ObservationRecord>): ObservationRecord {
  return {
    observation_id: 'o1',
    observation_version: 1,
    feature_id: 'fx.signal_alpha',
    presence: 'present',
    confirmed: false,
    ...overrides,
  };
}

function session(observations: ObservationRecord[], version = 1): Session {
  return {
    session_id: 's1',
    observation_version: version,
    state: 'clarifying',
    expires_at: '2030-01-01T00:00:00Z',
    observations,
  };
}

describe('observationLabel', () => {
  it('prefers the raw phrase and otherwise humanises the feature id without adding meaning', () => {
    expect(observationLabel({ feature_id: 'fx.signal_alpha', raw_phrase: 'my own words' })).toBe('my own words');
    expect(observationLabel({ feature_id: 'fx.signal_alpha' })).toBe('Signal alpha');
    expect(observationLabel({ feature_id: 'fx.signal_alpha', raw_phrase: '   ' })).toBe('Signal alpha');
    expect(observationLabel({ feature_id: null })).toBe('Unlabelled detail');
  });
});

describe('currentObservations', () => {
  it('hides superseded revisions', () => {
    const original = observation({ observation_id: 'o1' });
    const correction = observation({ observation_id: 'o2', supersedes: 'o1', presence: 'absent', confirmed: true });
    expect(currentObservations(session([original, correction])).map((item) => item.observation_id)).toEqual(['o2']);
    expect(currentObservations(null)).toEqual([]);
  });
});

describe('groupObservations', () => {
  it('never lists not_asked anywhere: unknown is not "not present"', () => {
    const groups = groupObservations([
      observation({ observation_id: 'a', presence: 'present' }),
      observation({ observation_id: 'b', presence: 'absent' }),
      observation({ observation_id: 'c', presence: 'uncertain' }),
      observation({ observation_id: 'd', presence: 'not_asked' }),
    ]);
    expect(groups.reported.map((item) => item.observation_id)).toEqual(['a']);
    expect(groups.notPresent.map((item) => item.observation_id)).toEqual(['b']);
    expect(groups.needsClarification.map((item) => item.observation_id)).toEqual(['c']);
  });
});

describe('isAssessmentStale', () => {
  it('is stale exactly when the versions differ', () => {
    const assessment = { observation_version: 3 } as Assessment;
    expect(isAssessmentStale(session([], 3), assessment)).toBe(false);
    expect(isAssessmentStale(session([], 4), assessment)).toBe(true);
    expect(isAssessmentStale(session([], 4), null)).toBe(false);
  });
});

describe('urgencyPresentation', () => {
  it('never presents not_assessed as low urgency', () => {
    const presentation = urgencyPresentation('not_assessed');
    expect(presentation.label).toBe('Urgency not assessed');
    expect(presentation.tone).toBe('attention');
    expect(presentation.note).toContain('does not mean');
  });

  it('uses the urgent tone for urgent and emergency', () => {
    expect(urgencyPresentation('urgent').tone).toBe('urgent');
    expect(urgencyPresentation('emergency').tone).toBe('urgent');
  });
});

describe('formatObservationValue', () => {
  it('formats the value shapes the answer contract produces', () => {
    expect(formatObservationValue({ value: 42, unit: 'kg' })).toBe('42 kg');
    expect(formatObservationValue({ value: 42, unit: null })).toBe('42');
    expect(formatObservationValue(['a', 'b'])).toBe('a, b');
    expect(formatObservationValue(undefined)).toBeNull();
    expect(formatObservationValue({ unexpected: true })).toBeNull();
  });
});

describe('the words the service gives (M3.12)', () => {
  it('names a detail by the person’s own phrase, then by the service’s name for the item, then by its id', () => {
    const named = observation({ display_name: 'Fixture signal alpha (sample)' });
    expect(observationLabel(named)).toBe('Fixture signal alpha (sample)');
    expect(observationLabel({ ...named, raw_phrase: 'my own words' })).toBe('my own words');
    expect(observationLabel(observation({}))).toBe('Signal alpha');
  });

  it('shows the stored answer in the service’s words, and what else is known about the symptom', () => {
    const answered = observation({ presence: 'absent', value: 'none', value_label: 'None of these' });
    // The service's words are used as they are, without the words kept in this visit.
    expect(observationDetails(answered)).toEqual(['None of these']);
    expect(observationDetails(answered, { none: 'Another wording' })).toEqual(['None of these']);
    const described = observation({
      onset: 'Since yesterday',
      location: 'left side',
      pattern: 'comes and goes',
      triggers: 'walking',
      relieving_factors: 'rest',
    });
    expect(observationDetails(described)).toEqual([
      'Since yesterday',
      'left side',
      'comes and goes',
      'Triggers: walking',
      'Eased by: rest',
    ]);
    // A duration the service also gives as the answer's words is still said once.
    expect(
      observationDetails(observation({ duration: '3 days', value: { value: 3, unit: 'days' }, value_label: '3 days' })),
    ).toEqual(['3 days']);
  });
});

describe('what is shown under a detail', () => {
  it('says a duration once, although the service returns it twice (BUG-008)', () => {
    const answered = observation({ duration: '3 days', value: { value: 3, unit: 'days' } });
    expect(observationDetails(answered)).toEqual(['3 days']);
    // Singular and plural of the same length of time are the same thing said twice.
    expect(observationDetails(observation({ duration: '1 day', value: { value: 1, unit: 'days' } }))).toEqual([
      '1 day',
    ]);
    // A different value is still shown beside the duration.
    expect(observationDetails(observation({ duration: '3 days', value: { value: 38, unit: 'u' } }))).toEqual([
      '3 days',
      '38 u',
    ]);
  });

  it('shows a chosen option in its own words, never as the internal value (BUG-009)', () => {
    const labels = { none: 'None of these', level_2: 'A moderate amount', both: '' };
    expect(observationDetails(observation({ presence: 'absent', value: 'none' }), labels)).toEqual(['None of these']);
    expect(formatObservationValue(['level_2', 'none'], labels)).toBe('A moderate amount, None of these');
    // An internal value that two questions use for different words is not shown at all.
    expect(formatObservationValue('both', labels)).toBeNull();
    // Words that are not an internal value of any question seen are shown as they are.
    expect(formatObservationValue('Sample situation 1', labels)).toBe('Sample situation 1');
  });

  it('shows a date answer in words', () => {
    expect(formatObservationValue({ date: '2026-01-15' })).toBe('15 January 2026');
    expect(observationDetails(observation({ value: { date: '2026-11-20' } }))).toEqual(['20 November 2026']);
  });
});

describe('parseSessionState', () => {
  it('recognises every contract state and flags anything else as unknown', () => {
    for (const state of [
      'intake',
      'clarifying',
      'assessing',
      'result_ready',
      'urgent_handoff',
      'out_of_scope',
      'insufficient_information',
      'system_unavailable',
      'closed',
    ]) {
      expect(parseSessionState(state)).toBe(state);
    }
    expect(parseSessionState('consent_pending')).toBe('unknown');
    expect(parseSessionState('something_new')).toBe('unknown');
  });
});

describe('parseConfig', () => {
  it('defaults to mock mode against localhost with dev auth off', () => {
    expect(parseConfig({})).toEqual({
      serviceMode: 'mock',
      apiBaseUrl: 'http://localhost:8000',
      devAuth: false,
      devReviewer: null,
      demoTools: true,
    });
  });

  it('reads http mode, trims the base URL and only enables dev auth for the exact string "true"', () => {
    expect(
      parseConfig({ VITE_SERVICE_MODE: 'http', VITE_API_BASE_URL: 'https://api.example.test/', VITE_DEV_AUTH: 'true' }),
    ).toEqual({
      serviceMode: 'http',
      apiBaseUrl: 'https://api.example.test',
      devAuth: true,
      devReviewer: null,
      demoTools: false,
    });
    expect(parseConfig({ VITE_DEV_AUTH: '1' }).devAuth).toBe(false);
    expect(parseConfig({ VITE_SERVICE_MODE: 'http', DEV: true }).demoTools).toBe(true);
    expect(parseConfig({ VITE_DEMO_TOOLS: 'false' }).demoTools).toBe(false);
  });

  it('takes a development reviewer name only with dev auth on, and only a plain name', () => {
    expect(parseConfig({ VITE_DEV_AUTH: 'true', VITE_DEV_REVIEWER: ' owner ' }).devReviewer).toBe('owner');
    expect(parseConfig({ VITE_DEV_REVIEWER: 'owner' }).devReviewer).toBeNull();
    expect(parseConfig({ VITE_DEV_AUTH: 'true', VITE_DEV_REVIEWER: 'a b:c' }).devReviewer).toBeNull();
    expect(parseConfig({ VITE_DEV_AUTH: 'true', VITE_DEV_REVIEWER: '' }).devReviewer).toBeNull();
  });
});
