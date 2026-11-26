import { useId, useState } from 'react';

import { REVIEW_STATE_LABELS, ReviewApiError, type LiveReviewApi, type ReviewState } from '@/api/liveReview';
import { Button } from '@/components/ui/Button';

interface BulkDecisionProps {
  api: LiveReviewApi;
  targetType: string;
  /** The rows shown that can take a decision; a row that takes notes only is left out by the list. */
  ids: readonly string[];
  /** Other words for the two decisions on this kind of row, as in the panel of one row. */
  labels?: { approved?: string; rejected?: string };
  onDone: () => void;
}

/**
 * One decision, with one note, for every row the list shows (M2.4j). The service decides each row
 * exactly as it decides a single one and writes the note on each under the reviewer's name. If it
 * refuses one row it changes nothing and says which row and why. A second click is asked for,
 * because the decision goes to many rows of the real data at once.
 */
export function BulkDecision({ api, targetType, ids, labels, onDone }: BulkDecisionProps) {
  const id = useId();
  const [note, setNote] = useState('');
  const [asking, setAsking] = useState<ReviewState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const count = ids.length;
  const rows = count === 1 ? 'the 1 row shown' : `all ${count} rows shown`;
  const choices: ReadonlyArray<{ status: ReviewState; label: string }> = [
    { status: 'approved', label: labels?.approved ? `${labels.approved} for ${rows}` : `Approve ${rows}` },
    { status: 'rejected', label: labels?.rejected ? `${labels.rejected} for ${rows}` : `Reject ${rows}` },
    { status: 'pending', label: `Undo the decision for ${rows}` },
  ];

  const ask = (status: ReviewState) => {
    setMessage(null);
    if (note.trim().length === 0) {
      setError('Write a note first. It is saved on every one of these rows as the reason.');
      return;
    }
    setError(null);
    setAsking(status);
  };

  const record = async () => {
    if (!asking || busy) {
      return;
    }
    setBusy(true);
    try {
      const result = await api.decideMany(targetType, ids, note.trim(), asking);
      setMessage(
        `Recorded: ${REVIEW_STATE_LABELS[asking]} for ${result.decided} ${result.decided === 1 ? 'row' : 'rows'}, under ${api.reviewer ?? 'the reviewer'}.`,
      );
      setNote('');
      onDone();
    } catch (caught) {
      setError(caught instanceof ReviewApiError ? caught.message : 'This could not be recorded.');
    } finally {
      setBusy(false);
      setAsking(null);
    }
  };

  return (
    <section aria-labelledby={`${id}-heading`} className="mt-5 rounded-control border border-line p-4">
      <h2 id={`${id}-heading`} className="font-display text-base font-bold text-ink">
        Decide all the rows shown at once
      </h2>
      <p className="mt-1 max-w-4xl text-[0.9375rem] text-ink-secondary">
        One decision and one note for every row on this page. Each row is decided exactly as if you had opened it, and
        the note is saved on each under your name. If the service cannot accept the decision for one of the rows, it
        changes nothing and tells you which row and why.
      </p>
      {count === 0 ? (
        message ? null : (
          <p className="mt-2 text-ink-secondary">No row shown here can take a decision.</p>
        )
      ) : (
        <>
          <label htmlFor={`${id}-note`} className="mb-1 mt-3 block font-medium text-ink">
            Note for all these rows (required)
          </label>
          <textarea
            id={`${id}-note`}
            rows={2}
            value={note}
            maxLength={2000}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? `${id}-error` : undefined}
            onChange={(event) => {
              setNote(event.target.value);
              setError(null);
              setAsking(null);
            }}
            className="field-control max-w-3xl"
          />
          {error ? (
            <p id={`${id}-error`} role="alert" className="mt-1 max-w-3xl text-sm font-medium text-urgent">
              {error}
            </p>
          ) : null}
          {asking ? (
            <div className="mt-2 rounded-control border border-attention/40 bg-attention-soft p-3">
              <p className="font-medium text-ink">
                Record &ldquo;{REVIEW_STATE_LABELS[asking]}&rdquo; for {rows}? This is saved on the real data.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" loading={busy} loadingLabel="Saving…" onClick={() => void record()}>
                  Yes, record it
                </Button>
                <Button size="sm" variant="secondary" disabled={busy} onClick={() => setAsking(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-2 flex flex-wrap gap-2">
              {choices.map((choice) => (
                <Button key={choice.status} size="sm" variant="secondary" onClick={() => ask(choice.status)}>
                  {choice.label}
                </Button>
              ))}
            </div>
          )}
        </>
      )}
      {/* One element whatever the list shows: the list is read again after a decision and has no row for a
          moment, and what was recorded must stay where it is (and be announced once) through that. */}
      <p role="status" className="mt-2 min-h-6 font-medium text-info">
        {message}
      </p>
    </section>
  );
}
