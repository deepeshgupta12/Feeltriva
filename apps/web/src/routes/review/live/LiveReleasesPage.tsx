import { useId, useState } from 'react';

import { field, part, ReviewApiError, type LiveReviewApi, type ReviewItem } from '@/api/liveReview';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

/** One kind of published version: where the service lists it, what it is published from, and what it holds. */
interface Kind {
  key: string;
  title: string;
  /** What one working set of this kind is called in a sentence. */
  noun: string;
  path: string;
  working: string;
  idParam: string;
  holds: ReadonlyArray<readonly [string, string]>;
}

const KINDS: readonly Kind[] = [
  {
    key: 'rules',
    title: 'Published sets of urgency rules',
    noun: 'set of rules',
    path: '/releases',
    working: 'rule_sets',
    idParam: 'bundle_id',
    holds: [
      ['rules', 'urgency rules'],
      ['questions', 'follow-up questions'],
      ['evidence', 'published pages they quote'],
      ['features', 'symptoms and other items they use'],
    ],
  },
  {
    key: 'names',
    title: 'Published lists of names',
    noun: 'list of names',
    path: '/mapping-releases',
    working: 'name_lists',
    idParam: 'mapping_release_id',
    holds: [
      ['features', 'symptoms and other items'],
      ['diseases', 'conditions'],
      ['disease_mappings', 'condition names from data files'],
      ['feature_mappings', 'columns of data files'],
    ],
  },
  {
    key: 'knowledge',
    title: 'Published texts and facts',
    noun: 'set of texts and facts',
    path: '/knowledge-releases',
    working: 'knowledge_sets',
    idParam: 'knowledge_release_id',
    holds: [
      ['statements', 'texts about conditions'],
      ['evidence', 'facts linking a condition and a symptom'],
      ['sources', 'data sources'],
    ],
  },
];

function holdsText(release: ReviewItem, holds: Kind['holds']): string {
  return holds.map(([name, words]) => `${field(release, name) || '0'} ${words}`).join(' · ');
}

function when(release: ReviewItem): string {
  const at = new Date(field(release, 'published_at'));
  return Number.isNaN(at.getTime()) ? field(release, 'published_at') : formatDateTime(at);
}

function rows(body: ReviewItem, name: string): ReviewItem[] {
  const value = body[name];
  return Array.isArray(value) ? (value as ReviewItem[]) : [];
}

/** The sample sets the tests use are not offered for publishing. */
const isSample = (id: string): boolean => id.startsWith('fixture-');

interface ConfirmProps {
  api: LiveReviewApi;
  /** What the first button says, for example "Publish this version". */
  action: string;
  /** What the second click says, for example "Yes, publish it". */
  confirm: string;
  /** Said before the second click. */
  warning: string;
  path: string;
  body: Record<string, string>;
  /** Told to the reviewer after the service has done it. */
  done: (answer: ReviewItem) => string;
  /** Called with that sentence; the page shows it and reads everything again. */
  onDone: (message: string) => void;
}

/** A note, then a second click, then one request to the service; its refusal is shown in its own words. */
function ConfirmedAction({ api, action, confirm, warning, path, body, done, onDone }: ConfirmProps) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    if (note.trim().length === 0) {
      setError('Write a note first. It is kept with the version as the reason.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const answer = await api.post(path, { ...body, note: note.trim() });
      setOpen(false);
      setNote('');
      onDone(done(answer));
    } catch (caught) {
      setError(caught instanceof ReviewApiError ? caught.message : 'The service could not do this.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2">
      {open ? (
        <div className="rounded-control border border-attention/40 bg-attention-soft p-3">
          <p className="font-medium text-ink">{warning}</p>
          <label htmlFor={`${id}-note`} className="mb-1 mt-2 block font-medium text-ink">
            Note (required)
          </label>
          <textarea
            id={`${id}-note`}
            rows={2}
            value={note}
            maxLength={2000}
            onChange={(event) => {
              setNote(event.target.value);
              setError(null);
            }}
            className="field-control max-w-3xl"
          />
          {error ? (
            <p role="alert" className="mt-1 max-w-3xl text-sm font-medium text-urgent">
              {error}
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <Button size="sm" loading={busy} loadingLabel="Working…" onClick={() => void send()}>
              {confirm}
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          {action}
        </Button>
      )}
    </div>
  );
}

/** What the next version of one working set would hold, and the button that publishes it. */
function NextVersion({
  api,
  kind,
  sets,
  onDone,
}: {
  api: LiveReviewApi;
  kind: Kind;
  sets: string[];
  onDone: (message: string) => void;
}) {
  const id = useId();
  const [chosen, setChosen] = useState(sets.length === 1 ? (sets[0] ?? '') : '');
  const { state } = useAsync(`review:live:next:${kind.key}:${chosen}`, () =>
    chosen ? api.get(`${kind.path}/preview`, { [kind.idParam]: chosen }) : Promise.resolve(null),
  );
  const preview = state.status === 'loaded' ? state.data : null;
  const problems = preview && Array.isArray(preview.problems) ? (preview.problems as string[]) : [];
  const waiting = preview ? part(preview, 'unresolved') : {};
  const stillWaiting = kind.holds
    .filter(([name]) => typeof waiting[name] === 'number' && waiting[name] > 0)
    .map(([name, words]) => `${field(waiting, name)} ${words}`);

  return (
    <div className="mt-3 rounded-control border border-dashed border-line p-3">
      <h3 className="font-display text-base font-bold text-ink">The next version</h3>
      {sets.length === 0 ? (
        <p className="mt-1 text-ink-secondary">There is no {kind.noun} to publish from.</p>
      ) : (
        <div className="mt-1 max-w-xl">
          <label htmlFor={`${id}-set`} className="mb-1 block text-sm font-medium text-ink-secondary">
            Which {kind.noun} (its name in the system)
          </label>
          <select
            id={`${id}-set`}
            value={chosen}
            onChange={(event) => setChosen(event.target.value)}
            className="field-control"
          >
            {sets.length === 1 ? null : <option value="">Choose one</option>}
            {sets.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      )}
      {chosen && state.status === 'loading' ? <p className="mt-2 text-ink-secondary">Working it out…</p> : null}
      {chosen && state.status === 'failed' ? (
        <p role="alert" className="mt-2 text-attention">
          The service could not work out the next version.
        </p>
      ) : null}
      {preview ? (
        <div className="mt-2 text-ink">
          {preview.same_as_release ? (
            <p>
              Nothing has changed since <code>{field(preview, 'same_as_release')}</code>, so there is nothing new to
              publish.
            </p>
          ) : problems.length > 0 ? (
            <>
              <p>It cannot be published yet. The service says:</p>
              <ul className="list-disc pl-5">
                {problems.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            </>
          ) : (
            <p>
              It would be version {field(preview, 'would_be_number')} and hold: {holdsText(preview, kind.holds)}.
            </p>
          )}
          {stillWaiting.length > 0 ? (
            <p className="mt-1 text-ink-secondary">
              Left out because they still wait for a decision: {stillWaiting.join(' · ')}.
            </p>
          ) : null}
          {preview.publishable ? (
            <ConfirmedAction
              api={api}
              action="Publish this version"
              confirm="Yes, publish it"
              warning="A published version can never be changed or removed. A mistake is corrected only by publishing another version or by going back to an earlier one."
              path={kind.path}
              body={{ [kind.idParam]: chosen }}
              done={(answer) => `Published as ${field(answer, 'release_id')}. It is the version in use now.`}
              onDone={onDone}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Published versions (M2.4h): what has been published, what the next version would hold, publishing
 * it, and going back to an earlier one. Publishing and going back are done by the review service
 * under the reviewer's name; each needs a note and a second click, and nothing the service refuses
 * is hidden. A published version is never changed or deleted.
 */
export function LiveReleasesPage() {
  const { liveReview } = useServices();
  // What the last action did. It stands above the lists, which are read again after every action.
  const [notice, setNotice] = useState<string | null>(null);
  const done = (message: string) => {
    setNotice(message);
    reload();
  };
  const { state, reload } = useAsync('review:live:releases', async () => ({
    lists: await Promise.all(KINDS.map((kind) => liveReview.list(kind.path))),
    working: await liveReview.get('/working-sets'),
    bundle: await liveReview.get('/serving-bundle'),
  }));

  return (
    <div>
      <ReviewPageHeader title="Published versions" badge={<StatusBadge tone="info">Real stored data</StatusBadge>}>
        <p>
          What has been published so far, and whether the service has everything it would need to run on it. Here you
          can also publish the next version and go back to an earlier one. A published version can never be changed or
          deleted; a correction is a new version. Nothing here is shown to patients while the live medical mode is
          switched off.
        </p>
      </ReviewPageHeader>
      <p role="status" className="mb-3 min-h-6 font-semibold text-info">
        {notice}
      </p>
      {state.status === 'loading' ? <ReviewLoading label="Loading published versions…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <div className="space-y-6">
          {KINDS.map((kind, index) => (
            <section key={kind.path} aria-label={kind.title}>
              <h2 className="font-display text-lg font-bold text-ink">{kind.title}</h2>
              {state.data.lists[index]?.items.length ? (
                <ul className="mt-1 space-y-2">
                  {state.data.lists[index].items.map((release) => (
                    <li key={field(release, 'release_id')} className="rounded-control border border-line p-3">
                      <p className="font-semibold text-ink">
                        <code className="break-all">{field(release, 'release_id')}</code>{' '}
                        <span className="font-normal text-ink-secondary">(its name in the system)</span>{' '}
                        {release.is_current ? <StatusBadge tone="info">In use now</StatusBadge> : null}
                      </p>
                      <p className="text-ink-secondary">{holdsText(release, kind.holds)}</p>
                      <p className="text-sm text-ink-secondary">
                        Published by {field(release, 'published_by')} · {when(release)}
                      </p>
                      {release.is_current ? null : (
                        <ConfirmedAction
                          api={liveReview}
                          action="Go back to this version"
                          confirm="Yes, make it the version in use"
                          warning="The service will use this earlier version in place of the one in use now. No version is deleted, and you can change back the same way."
                          path={`${kind.path}/current`}
                          body={{ release_id: field(release, 'release_id') }}
                          done={(answer) => `${field(answer, 'release_id')} is the version in use now.`}
                          onDone={done}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-ink-secondary">Nothing published yet.</p>
              )}
              <NextVersion
                api={liveReview}
                kind={kind}
                sets={rows(state.data.working, kind.working)
                  .map((row) => field(row, 'id'))
                  .filter((value) => !isSample(value))}
                onDone={done}
              />
            </section>
          ))}
          <section aria-label="What the service would run on">
            <h2 className="font-display text-lg font-bold text-ink">What the service would run on</h2>
            {state.data.bundle.assembled ? (
              <p className="mt-1 text-ink">
                Everything it needs is there: {field(state.data.bundle, 'rules')} urgency rules,{' '}
                {field(state.data.bundle, 'features')} symptoms and other items,{' '}
                {field(state.data.bundle, 'response_texts')} standard replies and{' '}
                {field(state.data.bundle, 'candidates')} possible conditions. It is put together from the set of rules{' '}
                <code>{field(part(part(state.data.bundle, 'built_from'), 'rule_release'), 'release_id')}</code> and the
                list of names{' '}
                <code>{field(part(part(state.data.bundle, 'built_from'), 'mapping_release'), 'release_id')}</code>.
              </p>
            ) : (
              <div className="mt-1 text-ink">
                <p>Not everything it needs is there yet. Missing:</p>
                <ul className="list-disc pl-5">
                  {(Array.isArray(state.data.bundle.problems) ? (state.data.bundle.problems as string[]) : []).map(
                    (problem) => (
                      <li key={problem}>{problem}</li>
                    ),
                  )}
                </ul>
              </div>
            )}
            <p className="mt-1 text-sm text-ink-secondary">
              The sample sets the tests use (their names begin with <code>fixture-</code>) are not offered for
              publishing.
            </p>
          </section>
        </div>
      ) : null}
    </div>
  );
}
