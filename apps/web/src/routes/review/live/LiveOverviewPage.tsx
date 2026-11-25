import { part, REVIEW_STATE_LABELS, REVIEW_STATES, type ReviewItem } from '@/api/liveReview';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

const QUEUES: ReadonlyArray<{ name: string; label: string }> = [
  { name: 'disease_mappings', label: 'Condition names from the data files' },
  { name: 'feature_mappings', label: 'Symptom and question names (columns of the data files)' },
  { name: 'statements', label: 'Texts about conditions' },
  { name: 'terminology_links', label: 'Matches to medical reference lists' },
  {
    name: 'relation_suggestions',
    label: 'Pairs of names that may mean the same, or where one may be a kind of the other',
  },
];

function count(item: ReviewItem, name: string): string {
  const value = item[name];
  return typeof value === 'number' ? value.toLocaleString('en-IN') : '0';
}

/** What waits for review, by queue and status, read from the API. */
export function LiveOverviewPage() {
  const { liveReview } = useServices();
  const { state, reload } = useAsync('review:live:overview', () => liveReview.get('/overview'));

  return (
    <div>
      <ReviewPageHeader title="Overview" badge={<StatusBadge tone="info">Real stored data</StatusBadge>}>
        <p>
          What is stored and what has been decided so far. Everything that was imported starts as &ldquo;waiting for a
          decision&rdquo;. Each decision is saved under your name with a note. Nothing is shown to a patient until it
          has been approved and then published.
        </p>
      </ReviewPageHeader>
      {state.status === 'loading' ? <ReviewLoading label="Loading overview…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <>
          <p className="text-ink">
            {count(state.data, 'sources')} data sources · {count(state.data, 'disease_candidates')} condition names ·{' '}
            {count(state.data, 'feature_columns_with_repeated_header')} columns whose heading is repeated
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[40rem] border-collapse text-left text-[0.9375rem]">
              <caption className="sr-only">What waits for a decision, by list</caption>
              <thead className="bg-page text-sm text-ink-secondary">
                <tr>
                  <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                    List
                  </th>
                  {REVIEW_STATES.map((status) => (
                    <th key={status} scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                      {REVIEW_STATE_LABELS[status]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {QUEUES.map((queue) => (
                  <tr key={queue.name} className="border-b border-line last:border-b-0">
                    <th scope="row" className="px-3 py-2.5 font-semibold text-ink">
                      {queue.label}
                    </th>
                    {REVIEW_STATES.map((status) => (
                      <td key={status} className="px-3 py-2.5 text-ink-secondary">
                        {count(part(state.data, queue.name), status)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-sm text-ink-secondary">
            Everything here was grouped or matched by its wording only. None of it has been checked by a clinician.
          </p>
        </>
      ) : null}
    </div>
  );
}
