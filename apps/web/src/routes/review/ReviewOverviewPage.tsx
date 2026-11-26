import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router';

import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatCount } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

const NEXT_STEPS = [
  {
    to: '/review/data',
    label: 'Repeated columns',
    detail: 'Column headings that appear more than once, and where their columns disagree.',
  },
  {
    to: '/review/diseases',
    label: 'Condition names',
    detail: 'Names grouped by spelling only, waiting for someone to check what they mean.',
  },
  {
    to: '/review/features',
    label: 'Symptom and question names',
    detail: 'One name suggested for each column of a data file.',
  },
  {
    to: '/review/releases',
    label: 'Published versions',
    detail: 'What a published version would hold, and what still stands in the way.',
  },
] as const;

/** The two notes of the data check, in plain words. A note this list does not know is shown as recorded. */
const IN_WORDS: Record<string, string> = {
  'casefold + strip + collapse whitespace only; no semantic synonym merges':
    'Capital letters and extra spaces were ignored, and nothing else. Names that mean the same but are spelled differently were not put together.',
  'not established; no cross-source patient identity inferred':
    'Not known. Nothing was assumed about whether a person in one data set is the same person in another.',
};
const inWords = (recorded: string): string => IN_WORDS[recorded] ?? recorded;

export function ReviewOverviewPage() {
  const { review } = useServices();
  const { state, reload } = useAsync('review:overview', () => review.getOverview());

  return (
    <div>
      <ReviewPageHeader title="Overview">
        <p>
          The figures below were counted from the data archives that were handed over. They describe the raw data sets,
          not reviewed medical knowledge, and none of them says how accurate anything is.
        </p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading the figures…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {state.data.facts.map((fact) => (
              <li key={fact.id} className="rounded-control border border-line bg-surface p-4">
                <StatusBadge tone="neutral">Imported dataset audit · counted from the data files</StatusBadge>
                <p className="mt-3 font-display text-3xl font-bold text-ink">{formatCount(fact.value)}</p>
                <p className="mt-0.5 font-semibold text-ink">{fact.label}</p>
                <p className="mt-1 text-sm text-ink-secondary">{fact.detail}</p>
              </li>
            ))}
          </ul>

          <dl className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="rounded-control border border-line bg-surface p-4">
              <dt className="text-sm font-semibold text-ink-secondary">How names were tidied before grouping</dt>
              <dd className="mt-1 text-ink">{inWords(state.data.normalization)}</dd>
            </div>
            <div className="rounded-control border border-line bg-surface p-4">
              <dt className="text-sm font-semibold text-ink-secondary">
                Whether the same patient appears more than once
              </dt>
              <dd className="mt-1 text-ink">{inWords(state.data.clinicalDedupStatus)}</dd>
            </div>
          </dl>
        </>
      ) : null}

      <section aria-labelledby="review-next-heading" className="mt-6">
        <h2 id="review-next-heading" className="font-display text-lg font-bold text-ink">
          Where to look next
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
