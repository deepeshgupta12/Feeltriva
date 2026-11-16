import { FileText, MessagesSquare, Pencil, Trash2 } from 'lucide-react';

import { formatDateTime } from '@/lib/format';

import { Button, ButtonLink } from './ui/Button';
import { SampleTag, StatusBadge } from './ui/StatusBadge';

interface HistoryCardProps {
  sessionId: string;
  title: string;
  createdAt: Date;
  /** A current result exists for the saved details. */
  completed: boolean;
  summaryAvailable: boolean;
  onRename: () => void;
  onDelete: () => void;
}

/**
 * One saved assessment. It shows the date, the title the user chose, whether the check
 * was completed and whether a summary exists. It deliberately shows no explanation or
 * condition name: a past provisional result is not a medical history item.
 */
export function HistoryCard({
  sessionId,
  title,
  createdAt,
  completed,
  summaryAvailable,
  onRename,
  onDelete,
}: HistoryCardProps) {
  return (
    <li className="rounded-card border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-lg font-bold text-ink">{title}</h2>
          <p className="text-[0.9375rem] text-ink-secondary">
            <time dateTime={createdAt.toISOString()}>{formatDateTime(createdAt)}</time>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <SampleTag />
          <StatusBadge tone={completed ? 'info' : 'neutral'}>{completed ? 'Completed' : 'Incomplete'}</StatusBadge>
        </div>
      </div>
      <p className="mt-2 text-[0.9375rem] text-ink-secondary">
        {summaryAvailable ? 'A consultation summary is available.' : 'No summary has been prepared yet.'}
      </p>
      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <ButtonLink
          to={`/summary/${sessionId}`}
          size="sm"
          variant={summaryAvailable ? 'primary' : 'secondary'}
          icon={<FileText aria-hidden="true" className="size-4 shrink-0" />}
          aria-label={`${summaryAvailable ? 'View summary' : 'Prepare summary'}: ${title}`}
        >
          {summaryAvailable ? 'View summary' : 'Prepare summary'}
        </ButtonLink>
        <ButtonLink
          to={`/assess/${sessionId}`}
          size="sm"
          variant="secondary"
          icon={<MessagesSquare aria-hidden="true" className="size-4 shrink-0" />}
          aria-label={`Open conversation: ${title}`}
        >
          Open conversation
        </ButtonLink>
        <Button
          size="sm"
          variant="ghost"
          onClick={onRename}
          icon={<Pencil aria-hidden="true" className="size-4 shrink-0" />}
          aria-label={`Rename: ${title}`}
        >
          Rename
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-urgent hover:bg-urgent-soft"
          onClick={onDelete}
          icon={<Trash2 aria-hidden="true" className="size-4 shrink-0" />}
          aria-label={`Delete: ${title}`}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}
