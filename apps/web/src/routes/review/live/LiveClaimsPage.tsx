import { useId, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router';

import {
  field,
  part,
  REVIEW_STATE_LABELS,
  REVIEW_STATES,
  ReviewApiError,
  texts,
  type LiveReviewApi,
  type ReviewItem,
  type ReviewParams,
  type ReviewState,
} from '@/api/liveReview';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from '../ReviewPageHeader';

import { DecisionDrawer, StateBadge, type ReviewTarget } from './DecisionDrawer';
import { kindOfText, thingToCheck, wordingCue } from './words';

const PAGE_SIZE = 10;

function list(item: ReviewItem, name: string): ReviewItem[] {
  const value = item[name];
  return Array.isArray(value) ? (value as ReviewItem[]) : [];
}

function cueText(claim: ReviewItem): string {
  const cues = part(claim, 'cues');
  return Object.entries(cues)
    .map(([name, words]) => `${wordingCue(name)}: ${Array.isArray(words) ? words.join(', ') : String(words)}`)
    .join(' · ');
}

/** The applicability a reviewer records for a claim: for whom or when it holds, in words. */
function ApplicabilityForm({ api, claim, onSaved }: { api: LiveReviewApi; claim: ReviewItem; onSaved: () => void }) {
  const id = useId();
  const current = field(part(claim, 'applicability'), 'text');
  const [text, setText] = useState(current);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const value = text.trim();
      await api.setApplicability(
        field(claim, 'claim_id'),
        value.length > 0 ? value : null,
        value.length > 0 ? `For whom or when this holds: ${value}` : 'Removed for whom or when this holds.',
      );
      setMessage(value.length > 0 ? 'Saved.' : 'Removed.');
      onSaved();
    } catch (caught) {
      setError(caught instanceof ReviewApiError ? caught.message : 'This could not be recorded.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={(event) => void save(event)} noValidate>
      <label htmlFor={`${id}-applies`} className="mb-1 block font-display text-base font-bold text-ink">
        For whom or when this holds
      </label>
      <p className="mb-1 text-ink-secondary">
        In your own words, for example &ldquo;in children&rdquo;. For now this is a note only: nothing else changes
        because of it. Leave it empty to remove what was written.
      </p>
      <input
        id={`${id}-applies`}
        type="text"
        value={text}
        maxLength={500}
        onChange={(event) => setText(event.target.value)}
        className="field-control"
      />
      {error ? (
        <p role="alert" className="mt-1 text-sm font-medium text-urgent">
          {error}
        </p>
      ) : null}
      <Button type="submit" size="sm" variant="secondary" className="mt-2" loading={busy} loadingLabel="Saving…">
        Save for whom or when
      </Button>
      <p role="status" className="mt-1 min-h-6 font-medium text-info">
        {message}
      </p>
    </form>
  );
}

/**
 * Statements with their single claims: each sentence with the items of its lists, the wording
 * cues, the marks a reviewer should check and the feature an item is proposed for. Statements
 * that carry a mark are listed first by the API. Each claim is decided on its own.
 */
export function LiveClaimsPage() {
  const id = useId();
  const { liveReview } = useServices();
  const [mark, setMark] = useState('');
  const [status, setStatus] = useState<ReviewState | ''>('');
  const [withFeature, setWithFeature] = useState(false);
  const [applied, setApplied] = useState<ReviewParams>({});
  const [offset, setOffset] = useState(0);
  const [openClaim, setOpenClaim] = useState<{ claim: ReviewItem; statement: ReviewItem } | null>(null);

  // A link may name one statement (`?statement=<id>`); the list then holds that statement only.
  const [search] = useSearchParams();
  const params: ReviewParams = { ...applied, statement_id: search.get('statement'), limit: PAGE_SIZE, offset };
  const { state, reload } = useAsync(`review:live:claims:${JSON.stringify(params)}`, () =>
    liveReview.list('/claims', params),
  );

  const apply = (event: FormEvent) => {
    event.preventDefault();
    setOffset(0);
    setApplied({ mark, status, with_feature: withFeature });
  };

  const statements = state.status === 'loaded' ? state.data.items : [];
  const total = state.status === 'loaded' ? state.data.total : 0;
  const marks = state.status === 'loaded' ? part(state.data, 'marks') : {};

  const claim = openClaim?.claim;
  const target: ReviewTarget | null =
    claim && openClaim
      ? {
          type: 'claim',
          id: field(claim, 'claim_id'),
          title: field(claim, 'text'),
          status: field(claim, 'review_status'),
          details: [
            { label: 'What it is', value: field(claim, 'kind') === 'list_item' ? 'An item of a list' : 'A sentence' },
            { label: 'Condition', value: field(part(openClaim.statement, 'disease'), 'term') },
            { label: 'The whole text', value: field(openClaim.statement, 'text') },
            { label: 'Words in it that change the meaning', value: cueText(claim) || 'None found' },
            {
              label: 'What to check',
              value:
                texts(claim, 'marks')
                  .map((name) => field(marks, name))
                  .join(' ') || 'Nothing in particular.',
            },
            {
              label: 'Symptom recognised in this item',
              value: field(part(claim, 'proposed_feature'), 'term') || 'None',
            },
            { label: 'How it was split out (name of the rule in the system)', value: field(claim, 'rule') },
          ],
        }
      : null;

  const claimRow = (entry: ReviewItem, statement: ReviewItem, nested: boolean) => (
    <li key={field(entry, 'claim_id')} className={nested ? 'ml-6 list-disc' : 'list-none'}>
      <div className="flex flex-wrap items-center gap-2 py-1">
        <button
          type="button"
          onClick={() => setOpenClaim({ claim: entry, statement })}
          className="min-h-11 text-left font-semibold text-primary underline decoration-primary/40 underline-offset-4 hover:text-primary-hover"
          aria-label={`Review claim: ${field(entry, 'text')}`}
        >
          {field(entry, 'text')}
        </button>
        <StateBadge status={field(entry, 'review_status')} />
        {texts(entry, 'marks').map((name) => (
          <StatusBadge key={name} tone="attention">
            Check: {thingToCheck(name)}
          </StatusBadge>
        ))}
        {field(part(entry, 'proposed_feature'), 'term') ? (
          <StatusBadge tone="neutral">Symptom recognised: {field(part(entry, 'proposed_feature'), 'term')}</StatusBadge>
        ) : null}
      </div>
      {list(entry, 'items').length > 0 ? (
        <ul>{list(entry, 'items').map((item) => claimRow(item, statement, true))}</ul>
      ) : null}
    </li>
  );

  return (
    <div>
      <ReviewPageHeader title="Texts about conditions" badge={<StatusBadge tone="info">Real stored data</StatusBadge>}>
        <p>
          Every stored text about a condition, split into its sentences and, where a sentence lists things, into the
          items of that list. None of these single points is used for anything until a reviewer approves it. When you
          approve a list item in which a symptom was recognised, it is recorded as a fact that links the condition and
          that symptom.
        </p>
      </ReviewPageHeader>

      <form onSubmit={apply} className="flex flex-wrap items-end gap-3">
        <div className="min-w-[14rem]">
          <label htmlFor={`${id}-mark`} className="mb-1 block text-sm font-medium text-ink-secondary">
            Things to check
          </label>
          <select
            id={`${id}-mark`}
            value={mark}
            onChange={(event) => setMark(event.target.value)}
            className="field-control"
          >
            <option value="">All texts, those with something to check first</option>
            <option value="cut_off">Text cut short by its source</option>
            <option value="first_item_preposition">List whose first item starts with shared words</option>
          </select>
        </div>
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
        <label className="flex min-h-11 items-center gap-2 text-ink">
          <input type="checkbox" checked={withFeature} onChange={(event) => setWithFeature(event.target.checked)} />
          Only texts in which a symptom was recognised
        </label>
        <Button type="submit" size="sm" variant="secondary">
          Show results
        </Button>
      </form>

      {state.status === 'loading' ? <ReviewLoading label="Loading texts…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <>
          <p role="status" className="mt-3 text-sm text-ink-secondary">
            {total === 0
              ? 'Nothing matches.'
              : `Showing texts ${offset + 1} to ${offset + statements.length} of ${total.toLocaleString('en-IN')}`}
          </p>
          <ul className="mt-2 space-y-4">
            {statements.map((statement) => (
              <li key={field(statement, 'statement_id')} className="rounded-control border border-line p-4">
                <p className="text-sm font-semibold text-ink-secondary">
                  {field(part(statement, 'disease'), 'term')} · {kindOfText(field(statement, 'statement_type'))}
                  {statement.has_a_mark ? ' · has something to check' : ''}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-ink">{field(statement, 'text')}</p>
                <ul className="mt-2">{list(statement, 'claims').map((entry) => claimRow(entry, statement, false))}</ul>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="secondary"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous page
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={offset + statements.length >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next page
            </Button>
          </div>
        </>
      ) : null}

      <DecisionDrawer
        api={liveReview}
        target={target}
        onClose={() => setOpenClaim(null)}
        onChanged={(result) => {
          if (openClaim) {
            setOpenClaim({ ...openClaim, claim: { ...openClaim.claim, review_status: result.review_status } });
          }
          reload();
        }}
      >
        {claim ? (
          <ApplicabilityForm key={field(claim, 'claim_id')} api={liveReview} claim={claim} onSaved={reload} />
        ) : null}
      </DecisionDrawer>
    </div>
  );
}
