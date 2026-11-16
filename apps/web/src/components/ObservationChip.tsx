import { Pencil, Undo2, UserRoundCheck } from 'lucide-react';

import type { ObservationRecord } from '@/api/types';
import { cn } from '@/lib/cn';
import { observationDetails, observationLabel } from '@/state/selectors';

import { StatusBadge } from './ui/StatusBadge';

interface ObservationChipProps {
  observation: ObservationRecord;
  /** A request is in flight; actions are disabled so nothing is submitted twice. */
  busy?: boolean;
  onConfirm?: () => void;
  onEdit?: () => void;
  onCorrect?: () => void;
  className?: string;
}

const ACTION =
  'inline-flex min-h-11 items-center gap-1.5 rounded-control px-2.5 text-[0.9375rem] font-semibold text-primary hover:bg-teal-soft disabled:opacity-50';

/**
 * One thing the user has shared: wording, timing details and whether they have confirmed
 * it. Confirmation here means "the user agreed this is what they said". It uses a plain
 * text label, never a green tick, because it is not a clinical confirmation.
 */
export function ObservationChip({
  observation,
  busy = false,
  onConfirm,
  onEdit,
  onCorrect,
  className,
}: ObservationChipProps) {
  const label = observationLabel(observation);
  const details = observationDetails(observation);
  // The service could not match this to a known feature, so there is nothing structured to edit.
  const unmatched = observation.feature_id === null;
  const interactive = !unmatched && (onConfirm || onEdit || onCorrect);

  return (
    <li className={cn('rounded-control border border-line bg-surface p-3', className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
        <div className="min-w-0">
          <p className="font-semibold text-ink">{unmatched ? `“${label}”` : label}</p>
          {details.length > 0 ? <p className="text-[0.9375rem] text-ink-secondary">{details.join(' · ')}</p> : null}
        </div>
        {unmatched ? (
          <StatusBadge tone="neutral">Saved as a note</StatusBadge>
        ) : observation.confirmed ? (
          <StatusBadge tone="neutral" icon={<UserRoundCheck aria-hidden="true" className="size-4 shrink-0" />}>
            You confirmed this
          </StatusBadge>
        ) : (
          <StatusBadge tone="attention">Please confirm</StatusBadge>
        )}
      </div>

      {unmatched ? (
        <p className="mt-1.5 text-sm text-ink-secondary">
          Kept in your own words. It hasn’t been matched to a known detail, so it can’t be edited here.
        </p>
      ) : null}

      {interactive ? (
        <div className="-mx-1.5 mt-1.5 flex flex-wrap gap-x-1">
          {!observation.confirmed && onConfirm ? (
            <button
              type="button"
              className={ACTION}
              disabled={busy}
              onClick={onConfirm}
              aria-label={`That’s right: ${label}`}
            >
              That’s right
            </button>
          ) : null}
          {onEdit ? (
            <button type="button" className={ACTION} disabled={busy} onClick={onEdit} aria-label={`Edit: ${label}`}>
              <Pencil aria-hidden="true" className="size-4" />
              Edit
            </button>
          ) : null}
          {onCorrect ? (
            <button
              type="button"
              className={ACTION}
              disabled={busy}
              onClick={onCorrect}
              aria-label={`Remove or correct: ${label}`}
            >
              <Undo2 aria-hidden="true" className="size-4" />
              Remove/correct
            </button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
