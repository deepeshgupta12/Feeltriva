import { ScrollRegion } from '@/components/ui/ScrollRegion';
import { SampleTag } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

export function ReviewRulesPage() {
  const { review } = useServices();
  const { state, reload } = useAsync('review:rules', () => review.listRules());

  return (
    <div>
      <ReviewPageHeader title="Questions and rules" badge={<SampleTag>Samples</SampleTag>}>
        <p>
          No set of clinical questions or rules has been written or approved in this demo. The questions listed here are
          invented samples used by the demo&rsquo;s example cases; they have no medical meaning.
        </p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading questions…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <ScrollRegion label="Sample questions">
          <table className="w-full min-w-[44rem] border-collapse text-left text-[0.9375rem]">
            <caption className="sr-only">Sample questions</caption>
            <thead className="bg-page text-sm text-ink-secondary">
              <tr>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Name of the question in the system
                </th>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Wording
                </th>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Kind of answer
                </th>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Decision so far
                </th>
              </tr>
            </thead>
            <tbody>
              {state.data.map((item) => (
                <tr key={item.id} className="border-b border-line align-top last:border-b-0">
                  <th scope="row" className="px-3 py-2.5 font-mono text-sm font-normal text-ink">
                    {item.id}
                  </th>
                  <td className="px-3 py-2.5 text-ink">{item.wording}</td>
                  <td className="px-3 py-2.5 font-mono text-sm text-ink-secondary">{item.answerType}</td>
                  <td className="px-3 py-2.5 text-ink-secondary">{item.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      ) : null}

      <section
        aria-labelledby="rules-empty-heading"
        className="mt-5 rounded-control border border-dashed border-line p-4"
      >
        <h2 id="rules-empty-heading" className="font-display text-lg font-bold text-ink">
          Clinical rules
        </h2>
        <p className="mt-1 text-ink-secondary">
          None written. Rules about urgency, about what the service does not cover, and about when to ask again must be
          written and approved by clinicians before they can be part of a published version.
        </p>
      </section>
    </div>
  );
}
