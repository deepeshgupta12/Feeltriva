import { useId, useState, type ReactNode } from 'react';

import {
  isReviewState,
  REVIEW_STATE_LABELS,
  ReviewApiError,
  type DecisionResult,
  type LiveReviewApi,
  type ReviewState,
} from '@/api/liveReview';
import { Button } from '@/components/ui/Button';
import { Sheet } from '@/components/ui/Sheet';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';

export interface ReviewTarget {
  type: string;
  id: string;
  title: string;
  status: string;
  details: readonly { label: string; value: ReactNode }[];
  /**
   * Set for an item that takes notes but no decision (the service would refuse one): the reason, in
   * words for the reviewer. The decision buttons are then not offered.
   */
  notesOnly?: string | null;
  /** Other words for the two decisions on this kind of item, for example "Confirm match". */
  decisionLabels?: { approved?: string; rejected?: string };
}

interface DecisionDrawerProps {
  api: LiveReviewApi;
  target: ReviewTarget | null;
  onClose: () => void;
  /** Called after a note or decision was recorded, with what the service answered, so the list can be read again. */
  onChanged: (result: DecisionResult) => void;
  children?: ReactNode;
}

const DECISIONS: ReadonlyArray<{ status: ReviewState; label: string }> = [
  { status: 'approved', label: 'Approve' },
  { status: 'rejected', label: 'Reject' },
  { status: 'pending', label: 'Undo the decision' },
];

export function StateBadge({ status }: { status: string }) {
  const tone = status === 'approved' ? 'info' : status === 'pending' ? 'neutral' : 'attention';
  return <StatusBadge tone={tone}>{isReviewState(status) ? REVIEW_STATE_LABELS[status] : status}</StatusBadge>;
}

/**
 * One item of the review workspace: what it is, the notes and decisions recorded on it, and the
 * form that records another. Every note and decision is written by the API under the reviewer's
 * name; the API requires a note with each decision and may refuse a decision, in which case its
 * own message is shown.
 */
export function DecisionDrawer({ api, target, onClose, onChanged, children }: DecisionDrawerProps) {
  const id = useId();
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const key = target ? `${target.type}:${target.id}` : 'none';
  const { state: notes } = useAsync(`review:notes:${key}:${version}`, () =>
    target ? api.notes(target.type, target.id) : Promise.resolve([]),
  );

  const record = async (status?: ReviewState) => {
    if (!target || busy) {
      return;
    }
    if (note.trim().length === 0) {
      setError('Write a note first. Every note and decision is recorded with its reason.');
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await api.decide(target.type, target.id, note.trim(), status);
      setNote('');
      setMessage(
        status
          ? `Recorded: ${REVIEW_STATE_LABELS[status]}, under ${api.reviewer ?? 'the reviewer'}.`
          : `Note saved under ${api.reviewer ?? 'the reviewer'}.`,
      );
      setVersion((value) => value + 1);
      onChanged(result);
    } catch (caught) {
      setError(caught instanceof ReviewApiError ? caught.message : 'This could not be recorded.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      open={target !== null}
      onOpenChange={(next) => {
        if (!next) {
          setNote('');
          setError(null);
          setMessage(null);
          onClose();
        }
      }}
      title={target ? target.title : 'Details'}
      description="For reviewers only. Nothing here reaches a patient until it is approved and then published."
      side="right"
    >
      {target ? (
        <div className="space-y-5 text-[0.9375rem]">
          <dl className="space-y-3">
            <div>
              <dt className="text-sm font-semibold text-ink-secondary">Decision so far</dt>
              <dd className="mt-1">
                <StateBadge status={target.status} />
              </dd>
            </div>
            {target.details.map((detail) => (
              <div key={detail.label}>
                <dt className="text-sm font-semibold text-ink-secondary">{detail.label}</dt>
                <dd className="break-words text-ink">{detail.value}</dd>
              </div>
            ))}
          </dl>

          {children}

          <section aria-labelledby={`${id}-notes`}>
            <h3 id={`${id}-notes`} className="font-display text-base font-bold text-ink">
              Notes and decisions so far
            </h3>
            {notes.status === 'loading' ? <p className="mt-1 text-ink-secondary">Loading notes…</p> : null}
            {notes.status === 'failed' ? (
              <p role="alert" className="mt-1 text-attention">
                The notes could not be loaded.
              </p>
            ) : null}
            {notes.status === 'loaded' && notes.data.length === 0 ? (
              <p className="mt-1 text-ink-secondary">No notes yet.</p>
            ) : null}
            {notes.status === 'loaded' && notes.data.length > 0 ? (
              <ul className="mt-2 space-y-2">
                {notes.data.map((item) => (
                  <li key={item.note_id} className="rounded-control border border-line bg-page p-3">
                    <p className="whitespace-pre-wrap text-ink">{item.note}</p>
                    <p className="mt-1 text-sm text-ink-secondary">
                      {item.status_change
                        ? `Decision: ${isReviewState(item.status_change) ? REVIEW_STATE_LABELS[item.status_change] : item.status_change} · `
                        : 'Note · '}
                      {item.reviewer}
                      {item.at ? ` · ${formatDateTime(new Date(item.at))}` : ''}
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </section>

          <section aria-labelledby={`${id}-record`}>
            <h3 id={`${id}-record`} className="font-display text-base font-bold text-ink">
              Write a note or make a decision
            </h3>
            <p className="mt-1 text-ink-secondary">
              Saved under the name <strong>{api.reviewer}</strong>. Approving something here does not show it to anyone:
              it reaches a patient only after it has also been published.
            </p>
            <label htmlFor={`${id}-note`} className="mb-1 mt-2 block font-medium text-ink">
              Note (required)
            </label>
            <textarea
              id={`${id}-note`}
              rows={3}
              value={note}
              maxLength={2000}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? `${id}-error` : undefined}
              onChange={(event) => {
                setNote(event.target.value);
                setError(null);
              }}
              className="field-control"
            />
            {error ? (
              <p id={`${id}-error`} role="alert" className="mt-1 text-sm font-medium text-urgent">
                {error}
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" loading={busy} loadingLabel="Saving…" onClick={() => void record()}>
                Save note
              </Button>
              {target.notesOnly
                ? null
                : DECISIONS.map((decision) => (
                    <Button
                      key={decision.status}
                      variant="secondary"
                      size="sm"
                      disabled={busy || target.status === decision.status}
                      onClick={() => void record(decision.status)}
                    >
                      {(decision.status === 'approved' && target.decisionLabels?.approved) ||
                        (decision.status === 'rejected' && target.decisionLabels?.rejected) ||
                        decision.label}
                    </Button>
                  ))}
            </div>
            {target.notesOnly ? <p className="mt-2 text-ink-secondary">{target.notesOnly}</p> : null}
            <p role="status" className="mt-2 min-h-6 font-medium text-info">
              {message}
            </p>
          </section>
        </div>
      ) : null}
    </Sheet>
  );
}
