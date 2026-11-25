import { useId, useState, type FormEvent, type ReactNode } from 'react';

import {
  field,
  REVIEW_STATE_LABELS,
  REVIEW_STATES,
  type ReviewItem,
  type ReviewParams,
  type ReviewState,
} from '@/api/liveReview';
import { Button } from '@/components/ui/Button';
import { ScrollRegion } from '@/components/ui/ScrollRegion';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

import { BulkDecision } from './BulkDecision';
import { DecisionDrawer, StateBadge, type ReviewTarget } from './DecisionDrawer';

/** How many rows a page can hold. The largest is the most the service decides at once. */
const PAGE_SIZES = [25, 100, 200] as const;

export interface ListScreen {
  title: string;
  intro: ReactNode;
  /** Path under the review routes of the API, for example `/disease-mappings`. */
  path: string;
  /** The review target type a decision on a row is recorded for. */
  targetType: string;
  idField: string;
  caption: string;
  titleOf: (item: ReviewItem) => string;
  columns: ReadonlyArray<{ heading: string; cell: (item: ReviewItem) => ReactNode }>;
  details: (item: ReviewItem) => ReviewTarget['details'];
  fixedParams?: ReviewParams;
  filters?: ReadonlyArray<{ param: string; label: string; options: ReadonlyArray<{ value: string; label: string }> }>;
  /** The label of the search field; leave out for a list that cannot be searched. */
  searchLabel?: string;
  pageSize?: number;
  /** For a row that takes notes but no decision: the reason, in words. Otherwise null. */
  notesOnly?: (item: ReviewItem) => string | null;
  decisionLabels?: ReviewTarget['decisionLabels'];
}

/**
 * One list of the live review workspace: search, filters and paging are done by the API; a row
 * opens the drawer in which notes and decisions are recorded.
 */
export function LiveListPage({ screen }: { screen: ListScreen }) {
  const id = useId();
  const { liveReview } = useServices();
  const [pageSize, setPageSize] = useState<number>(screen.pageSize ?? 25);
  const [chosenSize, setChosenSize] = useState<number>(screen.pageSize ?? 25);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<ReviewState | ''>('');
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const [applied, setApplied] = useState<ReviewParams>({});
  const [offset, setOffset] = useState(0);
  const [openItem, setOpenItem] = useState<ReviewItem | null>(null);

  const params: ReviewParams = { ...screen.fixedParams, ...applied, limit: pageSize, offset };
  const { state, reload } = useAsync(`review:live:${screen.path}:${JSON.stringify(params)}`, () =>
    liveReview.list(screen.path, params),
  );

  const apply = (event: FormEvent) => {
    event.preventDefault();
    setOffset(0);
    setPageSize(chosenSize);
    setApplied({ q: query.trim(), status, ...chosen });
  };

  const items = state.status === 'loaded' ? state.data.items : [];
  const total = state.status === 'loaded' ? state.data.total : 0;
  // While the list is read again after a decision the opened row stays as it was, so the drawer stays open.
  const openId = openItem ? field(openItem, screen.idField) : null;
  const open = openItem ? (items.find((item) => field(item, screen.idField) === openId) ?? openItem) : undefined;
  const target: ReviewTarget | null = open
    ? {
        type: screen.targetType,
        id: field(open, screen.idField),
        title: screen.titleOf(open),
        status: field(open, 'review_status'),
        details: screen.details(open),
        notesOnly: screen.notesOnly?.(open) ?? null,
        decisionLabels: screen.decisionLabels,
      }
    : null;

  return (
    <div>
      <ReviewPageHeader title={screen.title} badge={<StatusBadge tone="info">Real stored data</StatusBadge>}>
        {screen.intro}
      </ReviewPageHeader>

      <form onSubmit={apply} className="flex flex-wrap items-end gap-3">
        {screen.searchLabel ? (
          <div className="min-w-[14rem] flex-1">
            <label htmlFor={`${id}-search`} className="mb-1 block text-sm font-medium text-ink-secondary">
              {screen.searchLabel}
            </label>
            <input
              id={`${id}-search`}
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="field-control"
            />
          </div>
        ) : null}
        <div className="min-w-[11rem]">
          <label htmlFor={`${id}-status`} className="mb-1 block text-sm font-medium text-ink-secondary">
            Decision so far
          </label>
          <select
            id={`${id}-status`}
            value={status}
            onChange={(event) => setStatus(event.target.value as ReviewState | '')}
            className="field-control"
          >
            <option value="">Any</option>
            {REVIEW_STATES.map((value) => (
              <option key={value} value={value}>
                {REVIEW_STATE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
        {(screen.filters ?? []).map((filter) => (
          <div key={filter.param} className="min-w-[11rem]">
            <label htmlFor={`${id}-${filter.param}`} className="mb-1 block text-sm font-medium text-ink-secondary">
              {filter.label}
            </label>
            <select
              id={`${id}-${filter.param}`}
              value={chosen[filter.param] ?? ''}
              onChange={(event) => setChosen({ ...chosen, [filter.param]: event.target.value })}
              className="field-control"
            >
              <option value="">All</option>
              {filter.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        ))}
        <div className="min-w-[8rem]">
          <label htmlFor={`${id}-size`} className="mb-1 block text-sm font-medium text-ink-secondary">
            Rows on a page
          </label>
          <select
            id={`${id}-size`}
            value={chosenSize}
            onChange={(event) => setChosenSize(Number(event.target.value))}
            className="field-control"
          >
            {[...new Set([screen.pageSize ?? 25, ...PAGE_SIZES])]
              .sort((a, b) => a - b)
              .map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
          </select>
        </div>
        <Button type="submit" size="sm" variant="secondary">
          Show results
        </Button>
      </form>

      {state.status === 'loading' ? <ReviewLoading label="Loading…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <>
          <p role="status" className="mt-3 text-sm text-ink-secondary">
            {total === 0
              ? 'Nothing matches.'
              : `Showing ${offset + 1} to ${offset + items.length} of ${total.toLocaleString('en-IN')}`}
          </p>
          <ScrollRegion label={screen.caption} className="mt-2">
            <table className="w-full min-w-[60rem] border-collapse text-left text-[0.9375rem]">
              <caption className="sr-only">{screen.caption}</caption>
              <thead className="bg-page text-sm text-ink-secondary">
                <tr>
                  {[...screen.columns.map((column) => column.heading), 'Decision so far'].map((heading) => (
                    <th key={heading} scope="col" className="border-b border-line px-3 py-2.5 font-semibold">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const rowId = field(item, screen.idField);
                  return (
                    <tr key={rowId} className="border-b border-line align-top last:border-b-0">
                      {screen.columns.map((column, index) =>
                        index === 0 ? (
                          <th key={column.heading} scope="row" className="px-3 py-2.5 font-normal">
                            <button
                              type="button"
                              onClick={() => setOpenItem(item)}
                              className="min-h-11 text-left font-semibold text-primary underline decoration-primary/40 underline-offset-4 hover:text-primary-hover"
                              aria-label={`Review ${screen.titleOf(item)}`}
                            >
                              {column.cell(item)}
                            </button>
                          </th>
                        ) : (
                          <td key={column.heading} className="px-3 py-2.5 text-ink-secondary">
                            {column.cell(item)}
                          </td>
                        ),
                      )}
                      <td className="px-3 py-2.5">
                        {screen.notesOnly?.(item) ? (
                          <StatusBadge tone="neutral">No decision needed</StatusBadge>
                        ) : (
                          <StateBadge status={field(item, 'review_status')} />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </ScrollRegion>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
            >
              Previous page
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={offset + items.length >= total}
              onClick={() => setOffset(offset + pageSize)}
            >
              Next page
            </Button>
          </div>
        </>
      ) : null}

      {/* Kept on the page while the list is read again, so that what it reports after a decision stays visible. */}
      {state.status === 'failed' ? null : (
        <BulkDecision
          key={screen.path}
          api={liveReview}
          targetType={screen.targetType}
          ids={items.filter((item) => !screen.notesOnly?.(item)).map((item) => field(item, screen.idField))}
          labels={screen.decisionLabels}
          onDone={reload}
        />
      )}

      <DecisionDrawer
        api={liveReview}
        target={target}
        onClose={() => setOpenItem(null)}
        onChanged={(result) => {
          if (open) {
            setOpenItem({ ...open, review_status: result.review_status });
          }
          reload();
        }}
      />
    </div>
  );
}
