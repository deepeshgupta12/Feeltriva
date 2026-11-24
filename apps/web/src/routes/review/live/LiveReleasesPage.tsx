import { field, part, type ReviewItem } from '@/api/liveReview';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

const KINDS: ReadonlyArray<{ path: string; title: string; holds: readonly string[] }> = [
  { path: '/releases', title: 'Rule releases', holds: ['rules', 'questions', 'evidence', 'features'] },
  {
    path: '/mapping-releases',
    title: 'Mapping releases',
    holds: ['features', 'diseases', 'disease_mappings', 'feature_mappings'],
  },
  { path: '/knowledge-releases', title: 'Knowledge releases', holds: ['statements', 'evidence', 'sources'] },
];

function holdsText(release: ReviewItem, names: readonly string[]): string {
  return names.map((name) => `${field(release, name) || '0'} ${name.replace(/_/g, ' ')}`).join(' · ');
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
      <ReviewPageHeader title="Releases" badge={<StatusBadge tone="info">Live review data</StatusBadge>}>
        <p>
          What has been published, and whether the serving bundle can be assembled from it. A published release cannot
          be edited or deleted. Nothing here is served while clinical mode is off.
        </p>
      </ReviewPageHeader>
      {state.status === 'loading' ? <ReviewLoading label="Loading releases…" /> : null}
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
                        {field(release, 'release_id')}{' '}
                        {release.is_current ? <StatusBadge tone="info">Current</StatusBadge> : null}
                      </p>
                      <p className="text-ink-secondary">{holdsText(release, kind.holds)}</p>
                      <p className="text-sm text-ink-secondary">
                        Published by {field(release, 'published_by')} · {field(release, 'published_at')}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-ink-secondary">None published.</p>
              )}
            </section>
          ))}
          <section aria-label="Serving bundle">
            <h2 className="font-display text-lg font-bold text-ink">Serving bundle</h2>
            {state.data.bundle.assembled ? (
              <p className="mt-1 text-ink">
                Can be assembled from the current releases: {field(state.data.bundle, 'rules')} rules,{' '}
                {field(state.data.bundle, 'features')} features, {field(state.data.bundle, 'response_texts')} response
                texts, {field(state.data.bundle, 'candidates')} candidates. Built from rule release{' '}
                {field(part(part(state.data.bundle, 'built_from'), 'rule_release'), 'release_id')} and mapping release{' '}
                {field(part(part(state.data.bundle, 'built_from'), 'mapping_release'), 'release_id')}.
              </p>
            ) : (
              <div className="mt-1 text-ink">
                <p>Cannot be assembled yet. Missing:</p>
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
