import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

export function ReviewEvaluationPage() {
  const { review } = useServices();
  const { state, reload } = useAsync('review:evaluation', () => review.getEvaluation());

  return (
    <div>
      <ReviewPageHeader title="Model test results" badge={<StatusBadge tone="attention">Research only</StatusBadge>}>
        <p>Internal test results. These figures must not be shown to patients or used in advertising.</p>
      </ReviewPageHeader>

      {state.status === 'loading' ? <ReviewLoading label="Loading the results…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <div className="space-y-5">
          <section
            aria-labelledby="baseline-heading"
            className="rounded-control border border-line bg-surface p-4 sm:p-5"
          >
            <h2 id="baseline-heading" className="font-display text-lg font-bold text-ink">
              {state.data.title}
            </h2>
            <p className="mt-1 text-[0.9375rem] text-ink-secondary">{state.data.scope}</p>
            <p className="mt-3 rounded-control border border-urgent/40 bg-urgent-soft px-3.5 py-2.5 font-semibold text-urgent">
              {state.data.verdict}
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[30rem] border-collapse text-left text-[0.9375rem]">
                <caption className="sr-only">
                  Measured results of the trial model on the test rows of archive 11
                </caption>
                <thead className="text-sm text-ink-secondary">
                  <tr>
                    <th scope="col" className="border-b border-line px-3 py-2 font-semibold">
                      What was measured (on the test rows)
                    </th>
                    <th scope="col" className="border-b border-line px-3 py-2 font-semibold">
                      Value
                    </th>
                    <th scope="col" className="border-b border-line px-3 py-2 font-semibold">
                      Note
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.researchMetrics.map((metric) => (
                    <tr key={metric.label} className="border-b border-line align-top last:border-b-0">
                      <th scope="row" className="px-3 py-2 font-medium text-ink">
                        {metric.label}
                      </th>
                      <td className="px-3 py-2 font-mono text-ink">{metric.value ?? 'Not evaluated'}</td>
                      <td className="px-3 py-2 text-ink-secondary">{metric.note ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section
            aria-labelledby="clinical-heading"
            className="rounded-control border border-line bg-surface p-4 sm:p-5"
          >
            <h2 id="clinical-heading" className="font-display text-lg font-bold text-ink">
              Checks by clinicians
            </h2>
            <p className="mt-1 text-[0.9375rem] text-ink-secondary">
              No clinician has checked anything yet. These fields are empty, which is not the same as a result of zero.
            </p>
            <dl className="mt-3 grid gap-3 sm:grid-cols-3">
              {state.data.clinicalValidation.map((metric) => (
                <div key={metric.label} className="rounded-control border border-dashed border-line p-3">
                  <dt className="text-sm font-semibold text-ink-secondary">{metric.label}</dt>
                  <dd className="mt-1 font-semibold text-ink">{metric.value ?? 'Not evaluated'}</dd>
                </div>
              ))}
            </dl>
          </section>
        </div>
      ) : null}
    </div>
  );
}
