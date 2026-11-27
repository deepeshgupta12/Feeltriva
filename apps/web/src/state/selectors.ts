/**
 * Pure presentation helpers over server data. They select and label what the service
 * returned; none of them derives urgency, ranks explanations or adds clinical meaning.
 */
import type { Assessment, Candidate, Evidence, ObservationRecord, Session, Urgency } from '@/api/types';
import { formatCalendarDate } from '@/lib/answers';
import { humanizeIdentifier } from '@/lib/format';

/** Latest non-superseded observations (corrections are append-only revisions). */
export function currentObservations(session: Session | null): ObservationRecord[] {
  if (!session) {
    return [];
  }
  const superseded = new Set<string>();
  for (const observation of session.observations) {
    if (observation.supersedes) {
      superseded.add(observation.supersedes);
    }
  }
  return session.observations.filter((observation) => !superseded.has(observation.observation_id));
}

export interface ObservationGroups {
  reported: ObservationRecord[];
  /** Only explicit denials. Silence is unknown and never appears here. */
  notPresent: ObservationRecord[];
  needsClarification: ObservationRecord[];
}

export function groupObservations(observations: ObservationRecord[]): ObservationGroups {
  const groups: ObservationGroups = { reported: [], notPresent: [], needsClarification: [] };
  for (const observation of observations) {
    switch (observation.presence) {
      case 'present':
        groups.reported.push(observation);
        break;
      case 'absent':
        groups.notPresent.push(observation);
        break;
      case 'uncertain':
        groups.needsClarification.push(observation);
        break;
      case 'not_asked':
        // Not asked means unknown: it is neither reported nor denied, so it is not listed.
        break;
    }
  }
  return groups;
}

/**
 * Display name for an observation: the user's own phrase when the service kept it, otherwise the
 * name the service gives the item (M3.12), otherwise a readable form of the feature id. No clinical
 * vocabulary is added here.
 */
export function observationLabel(
  observation: Pick<ObservationRecord, 'feature_id' | 'raw_phrase' | 'display_name'>,
): string {
  const phrase = observation.raw_phrase?.trim();
  if (phrase) {
    return phrase;
  }
  const named = observation.display_name?.trim();
  if (named) {
    return named;
  }
  if (observation.feature_id) {
    return humanizeIdentifier(observation.feature_id);
  }
  return 'Unlabelled detail';
}

/**
 * Formats an observation's free-form `value` for display, or null when there is nothing to show.
 *
 * `optionLabels` holds the words of the options of the questions seen in this visit, by their internal
 * value. A value that is such an internal value is shown in the option's own words, never as stored
 * (BUG-009); one that two questions use for different words is not shown at all.
 */
export function formatObservationValue(
  value: unknown,
  optionLabels: Readonly<Record<string, string>> = {},
): string | null {
  if (value === undefined || value === null || value === '') {
    return null;
  }
  if (typeof value === 'string') {
    const label = optionLabels[value];
    return label === undefined ? value : label || null;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => formatObservationValue(item, optionLabels))
      .filter((item): item is string => item !== null);
    return parts.length > 0 ? parts.join(', ') : null;
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    if (typeof record.date === 'string') {
      return formatCalendarDate(record.date);
    }
    if (typeof record.value === 'number' || typeof record.value === 'string') {
      return typeof record.unit === 'string' && record.unit ? `${record.value} ${record.unit}` : String(record.value);
    }
  }
  return null;
}

/** Onset, duration, severity, what else is known about the symptom, and the value, skipping what is absent or already said. */
export function observationDetails(
  observation: ObservationRecord,
  optionLabels: Readonly<Record<string, string>> = {},
): string[] {
  const details: string[] = [];
  if (observation.onset) details.push(observation.onset);
  if (observation.duration) details.push(observation.duration);
  if (observation.severity) details.push(observation.severity);
  // What else is known about the symptom (M3.12), as it was given.
  if (observation.location) details.push(observation.location);
  if (observation.pattern) details.push(observation.pattern);
  if (observation.triggers) details.push(`Triggers: ${observation.triggers}`);
  if (observation.relieving_factors) details.push(`Eased by: ${observation.relieving_factors}`);
  // The service's own words for the stored answer come first; without them, the words kept in this visit.
  const value = observation.value_label?.trim() || formatObservationValue(observation.value, optionLabels);
  // A duration answer comes back both as the duration and as the value it was given in: said once (BUG-008).
  const said = (text: string) => text.trim().toLowerCase().replace(/s$/, '');
  if (value && !details.some((detail) => said(detail) === said(value))) details.push(value);
  return details;
}

/** A result is stale as soon as it was computed for a different observation version. */
export function isAssessmentStale(session: Session | null, assessment: Assessment | null): boolean {
  return session !== null && assessment !== null && assessment.observation_version !== session.observation_version;
}

export interface CandidateView {
  candidate: Candidate;
  /** Evidence cited by the candidate that actually exists in the response. */
  evidence: Evidence[];
  fits: ObservationRecord[];
  needsClarification: ObservationRecord[];
}

export interface CandidateSelection {
  shown: CandidateView[];
  /** Candidates not rendered because none of their cited evidence was in the response. */
  withheld: number;
}

const MAX_CANDIDATES = 3;

/**
 * Chooses which candidate explanations may be rendered.
 *
 * A candidate is only shown with supporting information that is really present in the
 * response. If none of its `evidence_ids` resolve, the explanation is withheld rather than
 * displayed without support. Order is the service's order; nothing is re-ranked.
 */
export function selectCandidates(assessment: Assessment, session: Session | null): CandidateSelection {
  const evidenceById = new Map(assessment.evidence.map((item) => [item.evidence_id, item]));
  const observationsById = new Map((session?.observations ?? []).map((item) => [item.observation_id, item]));
  const resolveObservations = (ids: string[]) =>
    ids.map((id) => observationsById.get(id)).filter((item): item is ObservationRecord => item !== undefined);

  const shown: CandidateView[] = [];
  let withheld = 0;
  for (const candidate of assessment.candidates.slice(0, MAX_CANDIDATES)) {
    const evidence = candidate.evidence_ids
      .map((id) => evidenceById.get(id))
      .filter((item): item is Evidence => item !== undefined);
    if (evidence.length === 0) {
      withheld += 1;
      continue;
    }
    shown.push({
      candidate,
      evidence,
      fits: resolveObservations(candidate.supporting_observation_ids),
      needsClarification: resolveObservations(candidate.conflicting_observation_ids),
    });
  }
  return { shown, withheld };
}

export type Tone = 'neutral' | 'info' | 'attention' | 'urgent';

export interface UrgencyPresentation {
  label: string;
  tone: Tone;
  /** Extra sentence shown with the label where the bare label could be misread. */
  note: string | null;
}

/**
 * Labels for the urgency values in the contract. The guidance itself is the service's
 * `next_action.text`. `not_assessed` is deliberately never presented as low urgency.
 */
export function urgencyPresentation(urgency: Urgency): UrgencyPresentation {
  switch (urgency) {
    case 'emergency':
      return { label: 'Emergency', tone: 'urgent', note: null };
    case 'urgent':
      return { label: 'Urgent', tone: 'urgent', note: null };
    case 'routine':
      return { label: 'Routine', tone: 'info', note: null };
    case 'self_care_with_safety_net':
      return { label: 'Self-care with safety net', tone: 'info', note: null };
    case 'not_assessed':
      return {
        label: 'Urgency not assessed',
        tone: 'attention',
        note: 'Urgency has not been assessed. This does not mean your situation is low urgency.',
      };
  }
}
