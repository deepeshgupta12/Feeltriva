import { field, part, REVIEW_STATE_LABELS, REVIEW_STATES, type ReviewItem } from '@/api/liveReview';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

const QUEUES: ReadonlyArray<{ name: string; label: string }> = [
  { name: 'disease_mappings', label: 'Disease mappings' },
  { name: 'feature_mappings', label: 'Feature mappings' },
  { name: 'statements', label: 'Statements' },
  { name: 'terminology_links', label: 'Vocabulary links' },
  { name: 'relation_suggestions', label: 'Synonym and subtype suggestions' },
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
      <ReviewPageHeader title="Review overview" badge={<StatusBadge tone="info">Live review data</StatusBadge>}>
        <p>
          What is stored and what has been decided. Everything imported starts as pending. A decision is recorded under
          your name with a note; nothing is shown to a person until a published release holds it.
        </p>
      </ReviewPageHeader>
      {state.status === 'loading' ? <ReviewLoading label="Loading overview…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <>
          <p className="text-ink">
            {count(state.data, 'sources')} sources · {count(state.data, 'disease_candidates')} disease labels ·{' '}
            {count(state.data, 'feature_columns_with_repeated_header')} column positions with a repeated heading
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[40rem] border-collapse text-left text-[0.9375rem]">
              <caption className="sr-only">Review queues by status</caption>
              <thead className="bg-page text-sm text-ink-secondary">
                <tr>
                  <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                    Queue
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
          <p className="mt-3 text-sm text-ink-secondary">{field(state.data, 'label')}</p>
        </>
      ) : null}
    </div>
  );
}
