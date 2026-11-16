import { useId } from 'react';

import { ReleaseBadge } from '@/components/review/ReleaseBadge';
import { Button } from '@/components/ui/Button';
import { SampleTag } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

export function ReviewReleasesPage() {
  const id = useId();
  const { review } = useServices();
  const { state, reload } = useAsync('review:releases', () => review.listReleases());

  return (
    <div>
      <ReviewPageHeader title="Releases">
        <p>A release bundles the sources, mappings and rules that the assessment service is allowed to use.</p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading releases…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <ul className="space-y-4">
          {state.data.map((release, index) => (
            <li key={release.version} className="rounded-control border border-line bg-surface p-4 sm:p-5">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-mono text-lg font-bold text-ink">{release.version}</h2>
                <ReleaseBadge status={release.status} />
                {release.isSample ? <SampleTag>Demo release</SampleTag> : null}
              </div>

              <div className="mt-4 grid gap-5 lg:grid-cols-2">
                <div>
                  <h3 className="font-display text-base font-bold text-ink">Included</h3>
                  <dl className="mt-1.5 space-y-2 text-[0.9375rem]">
                    {release.included.map((item) => (
                      <div key={item.label}>
                        <dt className="font-semibold text-ink-secondary">{item.label}</dt>
                        <dd className="text-ink">{item.value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
                <div>
                  <h3 className="font-display text-base font-bold text-ink">Pending before publication</h3>
                  <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[0.9375rem] text-ink">
                    {release.pendingItems.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="mt-5 border-t border-line pt-4">
                <Button disabled={!release.publication.enabled} aria-describedby={`${id}-reason-${index}`}>
                  Publish release
                </Button>
                <p id={`${id}-reason-${index}`} className="mt-2 text-[0.9375rem] text-ink-secondary">
                  {release.publication.enabled
                    ? 'Ready to publish.'
                    : `Publishing is disabled. ${release.publication.reason}`}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
