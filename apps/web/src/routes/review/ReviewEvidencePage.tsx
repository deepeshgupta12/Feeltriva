import { useId, useState, type FormEvent } from 'react';

import type { EvidenceReviewItem } from '@/api/reviewService';
import { Button } from '@/components/ui/Button';
import { Sheet } from '@/components/ui/Sheet';
import { SampleTag, StatusBadge } from '@/components/ui/StatusBadge';
import { formatDateTime, safeExternalUrl } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

const STATUS_LABELS: Record<EvidenceReviewItem['status'], string> = {
  draft: 'Draft',
  needs_review: 'Needs review',
};

export function ReviewEvidencePage() {
  const id = useId();
  const { review } = useServices();
  const { state, reload, setData } = useAsync('review:evidence', () => review.listEvidence());
  const [openId, setOpenId] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const items = state.status === 'loaded' ? state.data : [];
  const open = openId ? items.find((item) => item.id === openId) : undefined;
  const url = open ? safeExternalUrl(open.sourceUrl) : null;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!open) {
      return;
    }
    if (note.trim().length === 0) {
      setError('Write a note before saving.');
      return;
    }
    try {
      const updated = await review.saveEvidenceNote(open.id, note);
      setData(items.map((item) => (item.id === updated.id ? updated : item)));
      setNote('');
      setError(null);
      setMessage('Demo note saved. It is kept in memory only.');
    } catch {
      setError('The note could not be saved.');
    }
  };

  return (
    <div>
      <ReviewPageHeader title="Evidence" badge={<SampleTag>Sample items</SampleTag>}>
        <p>
          No evidence has been imported or approved yet. The items below are synthetic placeholders that show the review
          layout: original statement, source and locator, proposed atomic claim, applicability, status and notes.
        </p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading evidence…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <ul className="grid gap-3 lg:grid-cols-2">
          {items.map((item) => (
            <li key={item.id} className="rounded-control border border-line bg-surface p-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={item.status === 'needs_review' ? 'attention' : 'neutral'}>
                  {STATUS_LABELS[item.status]}
                </StatusBadge>
                {item.isSample ? <SampleTag /> : null}
              </div>
              <p className="mt-2 font-semibold text-ink">{item.proposedAtomicClaim}</p>
              <p className="mt-1 text-sm text-ink-secondary">{item.sourceTitle}</p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={() => {
                  setOpenId(item.id);
                  setNote('');
                  setMessage(null);
                  setError(null);
                }}
                aria-label={`Open evidence detail: ${item.proposedAtomicClaim}`}
              >
                Open detail
              </Button>
            </li>
          ))}
        </ul>
      ) : null}

      <Sheet
        open={open !== undefined}
        onOpenChange={(next) => {
          if (!next) setOpenId(null);
        }}
        title="Evidence detail"
        description="Sample item · not approved for serving"
        side="right"
      >
        {open ? (
          <div className="space-y-4 text-[0.9375rem]">
            <dl className="space-y-3">
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Original statement</dt>
                <dd className="mt-1 border-l-2 border-line pl-3 text-ink">{open.originalStatement}</dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Source and locator</dt>
                <dd className="text-ink">
                  {open.sourceTitle}
                  <span className="block text-ink-secondary">{open.locator}</span>
                  {url ? (
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex min-h-11 items-center font-medium text-primary underline underline-offset-4"
                    >
                      {url} (opens in a new tab)
                    </a>
                  ) : (
                    <span className="block text-ink-secondary">No source URL supplied.</span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Proposed atomic claim</dt>
                <dd className="text-ink">{open.proposedAtomicClaim}</dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Applicability</dt>
                <dd className="text-ink">{open.applicability}</dd>
              </div>
              <div>
                <dt className="text-sm font-semibold text-ink-secondary">Status</dt>
                <dd className="mt-1">
                  <StatusBadge tone={open.status === 'needs_review' ? 'attention' : 'neutral'}>
                    {STATUS_LABELS[open.status]}
                  </StatusBadge>
                </dd>
              </div>
            </dl>

            <section aria-labelledby={`${id}-notes`}>
              <h3 id={`${id}-notes`} className="font-display text-base font-bold text-ink">
                Reviewer notes
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
              <form onSubmit={(event) => void submit(event)} noValidate className="mt-3">
                <label htmlFor={`${id}-note`} className="mb-1 block font-medium text-ink">
                  Add a note
                </label>
                <textarea
                  id={`${id}-note`}
                  rows={3}
                  value={note}
                  maxLength={2000}
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? `${id}-note-error` : undefined}
                  onChange={(event) => {
                    setNote(event.target.value);
                    setError(null);
                  }}
                  className="field-control"
                />
                {error ? (
                  <p id={`${id}-note-error`} role="alert" className="mt-1 text-sm font-medium text-urgent">
                    {error}
                  </p>
                ) : null}
                <Button type="submit" size="sm" className="mt-2">
                  Save demo note
                </Button>
              </form>
              <p role="status" className="mt-2 min-h-6 font-medium text-info">
                {message}
              </p>
            </section>
          </div>
        ) : null}
      </Sheet>
    </div>
  );
}
