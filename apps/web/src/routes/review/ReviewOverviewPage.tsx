import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router';

import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatCount } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

const NEXT_STEPS = [
  { to: '/review/data', label: 'Data quality', detail: 'Repeated header names and where their columns disagree.' },
  { to: '/review/diseases', label: 'Disease mappings', detail: 'Lexical disease candidates awaiting semantic review.' },
  { to: '/review/features', label: 'Feature mappings', detail: 'Positional feature mappings by source column.' },
  { to: '/review/releases', label: 'Releases', detail: 'What a knowledge release would contain and what blocks it.' },
] as const;

export function ReviewOverviewPage() {
  const { review } = useServices();
  const { state, reload } = useAsync('review:overview', () => review.getOverview());

  return (
    <div>
      <ReviewPageHeader title="Overview">
        <p>
          Figures below come from the audit of the imported source archives. They describe the raw datasets, not
          reviewed medical knowledge, and none of them is a clinical accuracy measure.
        </p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading audit figures…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {state.data.facts.map((fact) => (
              <li key={fact.id} className="rounded-control border border-line bg-surface p-4">
                <StatusBadge tone="neutral">Imported dataset audit</StatusBadge>
                <p className="mt-3 font-display text-3xl font-bold text-ink">{formatCount(fact.value)}</p>
                <p className="mt-0.5 font-semibold text-ink">{fact.label}</p>
                <p className="mt-1 text-sm text-ink-secondary">{fact.detail}</p>
              </li>
            ))}
          </ul>

          <dl className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-control border border-line bg-surface p-4">
              <dt className="text-sm font-semibold text-ink-secondary">Normalisation used for lexical grouping</dt>
              <dd className="mt-1 text-ink">{state.data.normalization}</dd>
            </div>
            <div className="rounded-control border border-line bg-surface p-4">
              <dt className="text-sm font-semibold text-ink-secondary">Clinical de-duplication status</dt>
              <dd className="mt-1 text-ink">{state.data.clinicalDedupStatus}</dd>
            </div>
          </dl>
        </>
      ) : null}

      <section aria-labelledby="review-next-heading" className="mt-6">
        <h2 id="review-next-heading" className="font-display text-lg font-bold text-ink">
          Review queues
        </h2>
        <ul className="mt-2 grid gap-3 md:grid-cols-2">
          {NEXT_STEPS.map((item) => (
            <li key={item.to}>
              <Link
                to={item.to}
                className="flex min-h-11 items-start justify-between gap-3 rounded-control border border-line bg-surface p-4 hover:border-ink-muted"
              >
                <span>
                  <span className="block font-semibold text-ink">{item.label}</span>
                  <span className="block text-sm text-ink-secondary">{item.detail}</span>
                </span>
                <ArrowRight aria-hidden="true" className="mt-1 size-4 shrink-0 text-ink-secondary" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
