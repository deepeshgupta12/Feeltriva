import type { ReactNode } from 'react';

import type { Assessment } from '@/api/types';
import { urgencyPresentation } from '@/state/selectors';

import { SampleTag, StatusBadge } from './ui/StatusBadge';

interface NextActionCardProps {
  assessment: Assessment;
  /** The primary action for this result. Omitted when the result is stale. */
  action?: ReactNode;
  secondaryAction?: ReactNode;
  stale?: boolean;
}

/**
 * "What to do next": the service's action text and urgency, shown first on the results
 * screen. Both come straight from the assessment response. Teal is the brand colour and is
 * not used here to suggest that a situation is safe.
 */
export function NextActionCard({ assessment, action, secondaryAction, stale = false }: NextActionCardProps) {
  const urgency = urgencyPresentation(assessment.urgency);
  return (
    <div className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={urgency.tone}>{urgency.label}</StatusBadge>
        <SampleTag>Design demo · Sample result</SampleTag>
      </div>
      <p className="mt-3 text-lg font-medium leading-relaxed text-ink">{assessment.next_action.text}</p>
      {urgency.note ? <p className="mt-2 text-ink-secondary">{urgency.note}</p> : null}
      {!stale && (action || secondaryAction) ? (
        <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {action}
          {secondaryAction}
        </div>
      ) : null}
    </div>
  );
}
