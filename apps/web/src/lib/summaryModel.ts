/**
 * Builds the consultation summary shown on screen, printed and copied as text.
 *
 * It only arranges what the service returned (observations, answers given in this
 * session, the current assessment and the service's summary text). User-reported
 * information and provisional explanations are kept in separate sections.
 */
import type { Assessment, Session, Summary } from '@/api/types';
import type { TranscriptEntry } from '@/state/AssessmentController';
import {
  currentObservations,
  groupObservations,
  observationDetails,
  observationLabel,
  selectCandidates,
  urgencyPresentation,
} from '@/state/selectors';

import { formatDate } from './format';

export const SUMMARY_DEMO_LABEL = 'Design demo · Sample information';

export interface SummarySection {
  id: string;
  title: string;
  /** Why the section exists or how to read it. */
  note?: string;
  items: string[];
  /** Shown when there are no items. */
  emptyText: string;
  /** Separates the user's own report from anything the service suggested. */
  origin: 'reported_by_user' | 'from_assessment';
}

export interface SummaryModel {
  demoLabel: string;
  title: string;
  date: string;
  sections: SummarySection[];
  /** Verbatim `summary_text` from the service, or null when not yet available. */
  serviceText: string | null;
  disclaimer: string;
}

export interface SummaryInput {
  session: Session;
  /** Only a result for the current observation version may be included. */
  assessment: Assessment | null;
  assessmentIsStale: boolean;
  summary: Summary | null;
  transcript: readonly TranscriptEntry[];
  generatedAt: Date;
  /** The words of the options of the questions seen in this visit, by their internal value. */
  optionLabels?: Readonly<Record<string, string>>;
}

function answeredQuestions(transcript: readonly TranscriptEntry[]): string[] {
  const pairs: string[] = [];
  for (let index = 0; index < transcript.length - 1; index += 1) {
    const question = transcript[index];
    const answer = transcript[index + 1];
    if (question?.kind === 'question' && answer?.kind === 'answer') {
      pairs.push(`${question.text} — ${answer.text}`);
    }
  }
  return pairs;
}

export function buildSummaryModel(input: SummaryInput): SummaryModel {
  const { session, assessment, assessmentIsStale, summary, transcript, generatedAt } = input;
  const observations = currentObservations(session);
  const groups = groupObservations(observations);
  const usable = assessment !== null && !assessmentIsStale ? assessment : null;

  const timing: string[] = [];
  const demographics = session.demographics;
  if (demographics?.age_years !== undefined) {
    timing.push(`Age: ${demographics.age_years}`);
  }
  if (demographics?.gender_identity) {
    timing.push(`Gender identity: ${demographics.gender_identity}`);
  }
  for (const observation of observations) {
    const details = observationDetails(observation, input.optionLabels);
    if (details.length > 0) {
      timing.push(`${observationLabel(observation)}: ${details.join(', ')}`);
    }
  }

  const unresolved = [
    ...groups.needsClarification.map((observation) => `Unclear: ${observationLabel(observation)}`),
    ...(usable?.unknowns ?? []),
  ];

  const nextStep: string[] = [];
  let nextStepEmpty = 'No result has been produced for these details yet.';
  if (assessmentIsStale) {
    nextStepEmpty = 'Your details changed after the last result. Update the result to include a next step.';
  }
  if (usable) {
    const urgency = urgencyPresentation(usable.urgency);
    nextStep.push(usable.next_action.text);
    nextStep.push(`Urgency: ${urgency.label}${urgency.note ? ` (${urgency.note})` : ''}`);
  }

  const explanations = usable ? selectCandidates(usable, session).shown.map((view) => view.candidate.name) : [];

  const sections: SummarySection[] = [
    {
      id: 'reported',
      title: 'Reported symptoms',
      items: groups.reported.map(observationLabel),
      emptyText: 'Nothing reported yet.',
      origin: 'reported_by_user',
    },
    {
      id: 'negatives',
      title: 'Explicitly not present',
      note: 'Only what was explicitly denied. Anything not mentioned is unknown.',
      items: groups.notPresent.map(observationLabel),
      emptyText: 'Nothing was explicitly denied.',
      origin: 'reported_by_user',
    },
    {
      id: 'timing',
      title: 'Timing and context',
      items: timing,
      emptyText: 'No timing or context details recorded.',
      origin: 'reported_by_user',
    },
    {
      id: 'answers',
      title: 'Confirmed answers',
      note: 'Answers given to follow-up questions in this session.',
      items: answeredQuestions(transcript),
      emptyText: 'No follow-up answers recorded in this session.',
      origin: 'reported_by_user',
    },
    {
      id: 'unresolved',
      title: 'Unresolved questions',
      items: unresolved,
      emptyText: 'None listed.',
      origin: 'from_assessment',
    },
    {
      id: 'next_step',
      title: 'Next step from the assessment',
      items: nextStep,
      emptyText: nextStepEmpty,
      origin: 'from_assessment',
    },
    {
      id: 'explanations',
      title: 'Provisional explanations (not a diagnosis)',
      note: 'Possibilities suggested by the assessment, not reported by the person and not confirmed.',
      items: explanations,
      emptyText: 'None shown.',
      origin: 'from_assessment',
    },
  ];

  return {
    demoLabel: SUMMARY_DEMO_LABEL,
    title: 'Consultation summary',
    date: formatDate(generatedAt),
    sections,
    serviceText: summary && summary.observation_version === session.observation_version ? summary.summary_text : null,
    disclaimer:
      'Prepared with Feeltriva. This summary does not confirm a diagnosis. A health professional may need to examine you or arrange tests.',
  };
}

/** Plain-text version for the "Copy text" action. */
export function summaryToPlainText(model: SummaryModel): string {
  const lines: string[] = [model.demoLabel, '', model.title, `Date: ${model.date}`, ''];
  let origin: SummarySection['origin'] | null = null;
  for (const section of model.sections) {
    if (section.origin !== origin) {
      origin = section.origin;
      lines.push(
        origin === 'reported_by_user' ? '== Reported by you ==' : '== From the assessment (provisional) ==',
        '',
      );
    }
    lines.push(section.title);
    if (section.items.length === 0) {
      lines.push(`  ${section.emptyText}`);
    } else {
      for (const item of section.items) {
        lines.push(`  - ${item}`);
      }
    }
    lines.push('');
  }
  if (model.serviceText) {
    lines.push('Summary text from the assessment service', model.serviceText, '');
  }
  lines.push(model.disclaimer, model.demoLabel);
  return lines.join('\n');
}
