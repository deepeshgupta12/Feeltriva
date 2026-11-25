import { Search } from 'lucide-react';
import { useId, useMemo, useState, type FormEvent } from 'react';

import type { MappingRow, ReviewStatus } from '@/api/reviewService';
import { Button } from '@/components/ui/Button';
import { ScrollRegion } from '@/components/ui/ScrollRegion';
import { Sheet } from '@/components/ui/Sheet';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { REVIEW_STATUS_LABELS } from '@/fixtures/review';
import { formatDateTime } from '@/lib/format';

import { ReviewStatusBadge } from './ReleaseBadge';

interface ReviewTableProps {
  caption: string;
  rows: readonly MappingRow[];
  onSaveNote: (rowId: string, text: string) => Promise<void>;
  onSetStatus: (rowId: string, status: ReviewStatus) => Promise<void>;
}

const DEMO_ACTIONS: ReadonlyArray<{ status: ReviewStatus; label: string }> = [
  { status: 'flagged_demo', label: 'Mark: needs sorting out' },
  { status: 'accepted_demo', label: 'Mark acceptable' },
  { status: 'rejected_demo', label: 'Mark rejected' },
];

function columnText(row: MappingRow): string {
  if (row.columns.length === 0) {
    return 'A value of the name column';
  }
  return row.columns.map((column) => `column ${column.columnIndex}`).join(', ');
}

function lastReviewedText(row: MappingRow): string {
  return row.lastReviewed ? formatDateTime(new Date(row.lastReviewed)) : 'Not looked at yet';
}

/**
 * Mapping inventory for reviewers: search, status filter, a detail drawer and reviewer
 * notes. The source term and its column position are always shown as imported. Actions
 * change demo state only and are labelled "Demo change"; they approve nothing for serving.
 */
export function ReviewTable({ caption, rows, onSaveNote, onSetStatus }: ReviewTableProps) {
  const id = useId();
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<ReviewStatus | 'all'>('all');
  const [openId, setOpenId] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [noteError, setNoteError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const statuses = useMemo(() => [...new Set(rows.map((row) => row.reviewStatus))], [rows]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (status !== 'all' && row.reviewStatus !== status) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return [row.originalTerm, row.proposedCanonicalTerm, row.source, row.candidateId]
        .join(' ')
        .toLowerCase()
        .includes(needle);
    });
  }, [rows, query, status]);

  const open = openId ? rows.find((row) => row.id === openId) : undefined;

  const openRow = (rowId: string) => {
    setOpenId(rowId);
    setNote('');
    setNoteError(null);
    setSavedMessage(null);
  };

  const submitNote = async (event: FormEvent) => {
    event.preventDefault();
    if (!open || saving) {
      return;
    }
    if (note.trim().length === 0) {
      setNoteError('Write a note before saving.');
      return;
    }
    setSaving(true);
    setNoteError(null);
    try {
      await onSaveNote(open.id, note);
      setNote('');
      setSavedMessage('Demo note saved. It is not stored and is gone when you close the page.');
    } catch {
      setNoteError('The note could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const applyStatus = async (next: ReviewStatus) => {
    if (!open || saving) {
      return;
    }
    setSaving(true);
    try {
      await onSetStatus(open.id, next);
      setSavedMessage(`Demo change saved: ${REVIEW_STATUS_LABELS[next]}. Nothing was approved for real use.`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem] flex-1">
          <label htmlFor={`${id}-search`} className="mb-1 block text-sm font-medium text-ink-secondary">
            Search names, data files or names in the system
          </label>
          <div className="relative">
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted"
            />
            <input
              id={`${id}-search`}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="field-control pl-9"
            />
          </div>
        </div>
        <div className="min-w-[12rem]">
          <label htmlFor={`${id}-status`} className="mb-1 block text-sm font-medium text-ink-secondary">
            Decision so far
          </label>
          <select
            id={`${id}-status`}
            value={status}
            onChange={(event) => setStatus(event.target.value as ReviewStatus | 'all')}
            className="field-control"
          >
            <option value="all">Any</option>
            {statuses.map((value) => (
              <option key={value} value={value}>
                {REVIEW_STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <p role="status" className="mt-3 text-sm text-ink-secondary">
        Showing {filtered.length} of {rows.length} rows
      </p>

      <ScrollRegion label={caption} className="mt-2">
        <table className="w-full min-w-[68rem] table-fixed border-collapse text-left text-[0.9375rem]">
          <caption className="sr-only">{caption}</caption>
          <colgroup>
            <col className="w-[22%]" />
            <col className="w-[13%]" />
            <col className="w-[16%]" />
            <col className="w-[14%]" />
            <col className="w-[15%]" />
            <col className="w-[12%]" />
            <col className="w-[8%]" />
          </colgroup>
          <thead className="bg-page text-sm text-ink-secondary">
            <tr>
              {[
                'Data file',
                'Name in the data file',
                'Name it is grouped under',
                'How it was grouped',
                'Decision so far',
                'Disagreements',
                'Last looked at',
              ].map((heading) => (
                <th key={heading} scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  {heading}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <tr key={row.id} className="border-b border-line align-top last:border-b-0">
                <td className="px-3 py-2.5 text-ink-secondary">
                  {row.source}
                  <span className="block text-sm">{columnText(row)}</span>
                </td>
                <th scope="row" className="px-3 py-2.5 font-normal">
                  <button
                    type="button"
                    onClick={() => openRow(row.id)}
                    className="min-h-11 text-left font-semibold text-primary underline decoration-primary/40 underline-offset-4 hover:text-primary-hover"
                    aria-label={`View details for ${row.originalTerm}`}
                  >
                    {row.originalTerm}
                  </button>
                  {row.demoChanged ? (
                    <span className="mt-1 block">
                      <StatusBadge tone="sample">Demo change</StatusBadge>
                    </span>
                  ) : null}
                </th>
                <td className="px-3 py-2.5">
                  {row.proposedCanonicalTerm}
                  <span className="block font-mono text-sm text-ink-secondary">{row.candidateId}</span>
                </td>
                <td className="px-3 py-2.5 text-ink-secondary">{row.mappingMethod}</td>
                <td className="px-3 py-2.5">
                  <ReviewStatusBadge status={row.reviewStatus} />
                </td>
                <td className="px-3 py-2.5 text-ink-secondary">{row.conflicts ?? 'None found'}</td>
                <td className="px-3 py-2.5 text-ink-secondary">{lastReviewedText(row)}</td>
              </tr>
            ))}
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-6 text-center text-ink-secondary">
                  Nothing matches.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </ScrollRegion>

      <Sheet
        open={open !== undefined}
        onOpenChange={(next) => {
          if (!next) setOpenId(null);
        }}
        title={open ? open.originalTerm : 'Details'}
        description="Counted from the data files · grouped by spelling only, not clinically approved"
        side="right"
      >
        {open ? (
          <div className="space-y-5 text-[0.9375rem]">
            <dl className="space-y-3">
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Data file</dt>
                <dd className="text-ink">{open.source}</dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Name and column in the data file</dt>
                <dd className="text-ink">
                  {open.columns.length > 0 ? (
                    <ul className="list-disc pl-5">
                      {open.columns.map((column) => (
                        <li key={column.columnIndex}>
                          Column {column.columnIndex}: <code>{column.originalHeader}</code>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <>
                      <code>{open.originalTerm}</code> (a value of the name column)
                    </>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Name it is grouped under</dt>
                <dd className="text-ink">
                  {open.proposedCanonicalTerm}{' '}
                  <span className="font-mono text-sm text-ink-secondary">({open.candidateId})</span>
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">How it was grouped</dt>
                <dd className="text-ink">{open.mappingMethod}</dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Decision so far</dt>
                <dd className="mt-1 flex flex-wrap items-center gap-2">
                  <ReviewStatusBadge status={open.reviewStatus} />
                  {open.demoChanged ? <StatusBadge tone="sample">Demo change</StatusBadge> : null}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Disagreements</dt>
                <dd className="text-ink">{open.conflicts ?? 'None found'}</dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Last looked at</dt>
                <dd className="text-ink">{lastReviewedText(open)}</dd>
              </div>
            </dl>

            <section aria-labelledby={`${id}-notes`}>
              <h3 id={`${id}-notes`} className="font-display text-base font-bold text-ink">
                Notes
              </h3>
              {open.notes.length > 0 ? (
                <ul className="mt-2 space-y-2">
                  {open.notes.map((item) => (
                    <li key={item.id} className="rounded-control border border-line bg-page p-3">
                      <p className="whitespace-pre-wrap text-ink">{item.text}</p>
                      <p className="mt-1 text-sm text-ink-secondary">
                        Demo note · {formatDateTime(new Date(item.createdAt))}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-ink-secondary">No notes yet.</p>
              )}
              <form onSubmit={(event) => void submitNote(event)} noValidate className="mt-3">
                <label htmlFor={`${id}-note`} className="mb-1 block font-medium text-ink">
                  Add a note
                </label>
                <textarea
                  id={`${id}-note`}
                  rows={3}
                  value={note}
                  maxLength={2000}
                  aria-invalid={noteError ? true : undefined}
                  aria-describedby={noteError ? `${id}-note-error` : undefined}
                  onChange={(event) => {
                    setNote(event.target.value);
                    setNoteError(null);
                  }}
                  className="field-control"
                />
                {noteError ? (
                  <p id={`${id}-note-error`} role="alert" className="mt-1 text-sm font-medium text-urgent">
                    {noteError}
                  </p>
                ) : null}
                <Button type="submit" size="sm" className="mt-2" loading={saving} loadingLabel="Saving…">
                  Save demo note
                </Button>
              </form>
            </section>

            <section aria-labelledby={`${id}-actions`}>
              <h3 id={`${id}-actions`} className="font-display text-base font-bold text-ink">
                Mark this row
              </h3>
              <p className="mt-1 text-ink-secondary">
                These marks exist in this demo only. They approve no medical content for real use.
              </p>
              <div className="mt-2 flex flex-col gap-2">
                {DEMO_ACTIONS.map((action) => (
                  <Button
                    key={action.status}
                    variant="secondary"
                    size="sm"
                    disabled={saving || open.reviewStatus === action.status}
                    onClick={() => void applyStatus(action.status)}
                  >
                    {action.label}
                  </Button>
                ))}
              </div>
            </section>

            <p role="status" className="min-h-6 font-medium text-info">
              {savedMessage}
            </p>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
