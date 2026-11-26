import { useId, useState } from 'react';

import { field, ReviewApiError, texts, type LiveReviewApi, type ReviewItem } from '@/api/liveReview';
import { Button } from '@/components/ui/Button';
import { useAsync } from '@/lib/useAsync';

import type { MergeKind } from './mergeKinds';

/** Merging one name into another, taking it out again, and what has been done so far. */
export function MergePanel({
  api,
  item,
  kind,
  onChanged,
}: {
  api: LiveReviewApi;
  item: ReviewItem;
  kind: MergeKind;
  onChanged: () => void;
}) {
  const id = useId();
  const ownId = field(item, kind.idField);
  const [into, setInto] = useState('');
  const [keep, setKeep] = useState('');
  const [note, setNote] = useState('');
  const [asking, setAsking] = useState<'merge' | 'split' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const { state } = useAsync(`review:live:history:${ownId}:${version}`, () =>
    api.get(`${kind.path}/${encodeURIComponent(ownId)}/history`),
  );
  const merged = field(item, 'merged_into');
  const past =
    state.status === 'loaded' && Array.isArray(state.data.history) ? (state.data.history as ReviewItem[]) : [];
  const others = state.status === 'loaded' ? texts(state.data, kind.othersField) : [];

  const ask = (what: 'merge' | 'split') => {
    setMessage(null);
    if (note.trim().length === 0 || (what === 'merge' && into.trim().length === 0)) {
      setError(
        what === 'merge'
          ? `Give the name in the system of the ${kind.thing} to keep, and write a note.`
          : 'Write a note first.',
      );
      return;
    }
    setError(null);
    setAsking(what);
  };

  const send = async () => {
    if (!asking) {
      return;
    }
    setBusy(true);
    try {
      if (asking === 'merge') {
        const body: Record<string, unknown> = {
          [`source_${kind.idField}`]: ownId,
          [`target_${kind.idField}`]: into.trim(),
          note: note.trim(),
        };
        if (kind.canRename && keep.trim()) {
          body.kept_name = keep.trim();
        }
        await api.post(kind.mergePath, body);
        setMessage(`Merged. This name is now kept as another name of that ${kind.thing}.`);
      } else {
        await api.post(kind.splitPath, { [kind.idField]: ownId, note: note.trim() });
        setMessage('Taken out again. This name stands on its own.');
      }
      setNote('');
      setInto('');
      setKeep('');
      setVersion((value) => value + 1);
      onChanged();
    } catch (caught) {
      setError(caught instanceof ReviewApiError ? caught.message : 'The service could not do this.');
    } finally {
      setBusy(false);
      setAsking(null);
    }
  };

  return (
    <section aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`} className="font-display text-base font-bold text-ink">
        Two names for one {kind.thing}
      </h3>
      <p className="mt-1 text-ink-secondary">
        If this name and another one mean the same {kind.thing}, merge this one into the other. Nothing is deleted: this
        name is kept as another name of that {kind.thing}, and it can be taken out again.
        {kind.more ? ` ${kind.more}` : ''}
      </p>
      {others.length > 0 ? (
        <p className="mt-1 text-ink">
          Other names kept under this {kind.thing}: {others.join(' · ')}
        </p>
      ) : null}
      {past.length > 0 ? (
        <ul className="mt-2 space-y-1 text-sm text-ink-secondary">
          {past.map((event, index) => (
            <li key={`${field(event, 'at')}-${index}`}>
              {field(event, 'action') === 'merge' ? 'Merged' : 'Taken out again'} · {field(event, 'reviewer')} ·{' '}
              {field(event, 'note')}
            </li>
          ))}
        </ul>
      ) : null}
      {merged ? null : (
        <>
          <label htmlFor={`${id}-into`} className="mb-1 mt-2 block font-medium text-ink">
            Name in the system of the {kind.thing} to keep
          </label>
          <input
            id={`${id}-into`}
            type="text"
            value={into}
            placeholder={kind.placeholder}
            onChange={(event) => setInto(event.target.value)}
            className="field-control"
          />
          {kind.canRename ? (
            <>
              <label htmlFor={`${id}-keep`} className="mb-1 mt-2 block font-medium text-ink">
                Name to show for it (leave empty to keep its present name)
              </label>
              <input
                id={`${id}-keep`}
                type="text"
                value={keep}
                onChange={(event) => setKeep(event.target.value)}
                className="field-control"
              />
            </>
          ) : null}
        </>
      )}
      <label htmlFor={`${id}-note`} className="mb-1 mt-2 block font-medium text-ink">
        Note for the merge (required)
      </label>
      <textarea
        id={`${id}-note`}
        rows={2}
        value={note}
        maxLength={2000}
        onChange={(event) => {
          setNote(event.target.value);
          setError(null);
          setAsking(null);
        }}
        className="field-control"
      />
      {error ? (
        <p role="alert" className="mt-1 text-sm font-medium text-urgent">
          {error}
        </p>
      ) : null}
      {asking ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" loading={busy} loadingLabel="Working…" onClick={() => void send()}>
            {asking === 'merge' ? 'Yes, merge it' : 'Yes, take it out'}
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => setAsking(null)}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className="mt-2">
          {merged ? (
            <Button size="sm" variant="secondary" onClick={() => ask('split')}>
              Take this name out again
            </Button>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => ask('merge')}>
              Merge this name into that {kind.thing}
            </Button>
          )}
        </div>
      )}
      <p role="status" className="mt-1 min-h-6 font-medium text-info">
        {message}
      </p>
    </section>
  );
}
