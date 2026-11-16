import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { ClipboardList, EllipsisVertical, FileText, ListChecks, RotateCcw, Trash2 } from 'lucide-react';
import { Link } from 'react-router';

import type { ServerSessionState } from '@/api/types';
import type { Tone } from '@/state/selectors';

import { StatusBadge } from './ui/StatusBadge';

interface ConversationHeaderProps {
  sessionId: string;
  /** Server-reported state, or `unknown` for a value this build does not recognise. */
  state: ServerSessionState | 'unknown' | null;
  /** Number of saved details, shown on the "Your details" button. */
  detailCount: number;
  onOpenDetails: () => void;
  onRestart: () => void;
  onDelete: () => void;
}

const STATE_LABELS: Record<ServerSessionState | 'unknown', { label: string; tone: Tone }> = {
  intake: { label: 'Getting started', tone: 'neutral' },
  clarifying: { label: 'Clarifying details', tone: 'info' },
  assessing: { label: 'Preparing result', tone: 'info' },
  result_ready: { label: 'Result available', tone: 'info' },
  urgent_handoff: { label: 'Urgent attention', tone: 'urgent' },
  out_of_scope: { label: 'Outside what we cover', tone: 'attention' },
  insufficient_information: { label: 'More information needed', tone: 'attention' },
  system_unavailable: { label: 'Assessment unavailable', tone: 'attention' },
  closed: { label: 'Ended', tone: 'neutral' },
  unknown: { label: 'Status unavailable', tone: 'neutral' },
};

const MENU_ITEM =
  'flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-left font-medium text-ink data-[highlighted]:bg-teal-soft data-[highlighted]:outline-none';

/**
 * Title, current state and actions for the conversation. The title is generic: no name
 * and no symptoms. The state label reflects the server-reported state and is never
 * changed by loading animations.
 */
export function ConversationHeader({
  sessionId,
  state,
  detailCount,
  onOpenDetails,
  onRestart,
  onDelete,
}: ConversationHeaderProps) {
  const stateLabel = state ? STATE_LABELS[state] : null;
  return (
    <div className="sticky top-[var(--demo-banner-height,0px)] z-20 border-b border-line bg-page/95 backdrop-blur [@media(max-height:560px)]:static print:hidden">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-2 gap-y-1 px-4 py-2 sm:px-6">
        <h1 tabIndex={-1} className="font-display text-lg font-bold text-ink sm:text-2xl">
          Symptom check
        </h1>

        <button
          type="button"
          onClick={onOpenDetails}
          className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-control border border-line bg-surface px-3 font-semibold text-ink hover:border-ink-muted xl:hidden"
        >
          <ListChecks aria-hidden="true" className="size-4 shrink-0" />
          {/* Below 390px only the icon and count are shown; the name stays available to assistive technology. */}
          <span className="max-xs:sr-only">Your details</span>
          {detailCount > 0 ? (
            <span className="rounded-full bg-teal-soft px-2 text-sm text-ink">
              {detailCount}
              <span className="sr-only"> saved</span>
            </span>
          ) : null}
        </button>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            aria-label="Conversation options"
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-control text-ink-secondary hover:bg-teal-soft hover:text-ink"
          >
            <EllipsisVertical aria-hidden="true" className="size-5" />
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={6}
              className="z-50 min-w-60 rounded-control border border-line bg-surface p-1.5 shadow-float"
            >
              <DropdownMenu.Item asChild>
                <Link to={`/results/${sessionId}`} className={MENU_ITEM}>
                  <ClipboardList aria-hidden="true" className="size-4 shrink-0" />
                  View result
                </Link>
              </DropdownMenu.Item>
              <DropdownMenu.Item asChild>
                <Link to={`/summary/${sessionId}`} className={MENU_ITEM}>
                  <FileText aria-hidden="true" className="size-4 shrink-0" />
                  Consultation summary
                </Link>
              </DropdownMenu.Item>
              <DropdownMenu.Separator className="my-1 h-px bg-line" />
              <DropdownMenu.Item className={MENU_ITEM} onSelect={onRestart}>
                <RotateCcw aria-hidden="true" className="size-4 shrink-0" />
                Start over
              </DropdownMenu.Item>
              <DropdownMenu.Item className={`${MENU_ITEM} text-urgent`} onSelect={onDelete}>
                <Trash2 aria-hidden="true" className="size-4 shrink-0" />
                Delete this assessment
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        {stateLabel ? (
          <div className="col-span-full">
            <StatusBadge tone={stateLabel.tone}>
              <span className="sr-only">Current state: </span>
              {stateLabel.label}
            </StatusBadge>
          </div>
        ) : null}
      </div>
    </div>
  );
}
