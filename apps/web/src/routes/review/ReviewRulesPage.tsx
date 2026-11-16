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
      <ReviewPageHeader title="Questions/rules" badge={<SampleTag>Demo fixtures</SampleTag>}>
        <p>
          No clinical question bundle or rule set has been authored or approved. The questions listed here are the
          synthetic fixtures used by the demo scenarios; they carry no clinical meaning.
        </p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading questions…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <ScrollRegion label="Demo question fixtures">
          <table className="w-full min-w-[44rem] border-collapse text-left text-[0.9375rem]">
            <caption className="sr-only">Demo question fixtures</caption>
            <thead className="bg-page text-sm text-ink-secondary">
              <tr>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Question ID
                </th>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Wording
                </th>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Answer type
                </th>
                <th scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                  Status
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
          None authored. Urgency, scope and clarification rules must be written and approved by clinical reviewers
          before they can be included in a release.
        </p>
      </section>
    </div>
  );
}
