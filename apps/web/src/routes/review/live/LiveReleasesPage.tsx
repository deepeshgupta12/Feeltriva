import { field, part, type ReviewItem } from '@/api/liveReview';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDateTime } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

/** The kinds of published version, with what each holds: the service's name of a count and the words for it. */
const KINDS: ReadonlyArray<{ path: string; title: string; holds: ReadonlyArray<readonly [string, string]> }> = [
  {
    path: '/releases',
    title: 'Published sets of urgency rules',
    holds: [
      ['rules', 'urgency rules'],
      ['questions', 'follow-up questions'],
      ['evidence', 'published pages they quote'],
      ['features', 'symptoms and other items they use'],
    ],
  },
  {
    path: '/mapping-releases',
    title: 'Published lists of names',
    holds: [
      ['features', 'symptoms and other items'],
      ['diseases', 'conditions'],
      ['disease_mappings', 'condition names from data files'],
      ['feature_mappings', 'columns of data files'],
    ],
  },
  {
    path: '/knowledge-releases',
    title: 'Published texts and facts',
    holds: [
      ['statements', 'texts about conditions'],
      ['evidence', 'facts linking a condition and a symptom'],
      ['sources', 'data sources'],
    ],
  },
];

function holdsText(release: ReviewItem, holds: ReadonlyArray<readonly [string, string]>): string {
  return holds.map(([name, words]) => `${field(release, name) || '0'} ${words}`).join(' · ');
}

function when(release: ReviewItem): string {
  const at = new Date(field(release, 'published_at'));
  return Number.isNaN(at.getTime()) ? field(release, 'published_at') : formatDateTime(at);
}

/**
 * Published releases, read only. A release is never edited or deleted; publishing and rollback
 * are done through the review service by a reviewer, not from this screen.
 */
export function LiveReleasesPage() {
  const { liveReview } = useServices();
  const { state, reload } = useAsync('review:live:releases', async () => ({
    lists: await Promise.all(KINDS.map((kind) => liveReview.list(kind.path))),
    bundle: await liveReview.get('/serving-bundle'),
  }));

  return (
    <div>
      <ReviewPageHeader title="Published versions" badge={<StatusBadge tone="info">Real stored data</StatusBadge>}>
        <p>
          What has been published so far, and whether the service has everything it would need to run on it. A published
          version can never be changed or deleted; a correction is a new version. Nothing here is shown to patients
          while the live medical mode is switched off.
        </p>
      </ReviewPageHeader>
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
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-ink-secondary">Nothing published yet.</p>
              )}
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
          </section>
        </div>
      ) : null}
    </div>
  );
}
