import { useId, useState, type ReactNode } from 'react';
import { Link } from 'react-router';

import { field, part, ReviewApiError, texts, type LiveReviewApi, type ReviewItem } from '@/api/liveReview';
import { Button } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';

import { ReviewPageHeader } from '../ReviewPageHeader';

import { LiveListPage, type ListScreen } from './LiveListPage';
import { answerKind, factKind, itemKind, kindOfText, pairReason, pairSuggestion } from './words';

/**
 * The review lists that had no screen (M2.4i). Each is a list of the review service shown through
 * the same page as the other lists: search and filters by the service, one row opened to read it,
 * write a note and decide, and all rows shown decided at once. The words follow decision E97.
 */
const code = (text: string): ReactNode => <code className="break-all text-sm">{text}</code>;
const decidedBy = (item: ReviewItem): string =>
  field(item, 'decided_by') || field(item, 'reviewer') || field(item, 'approved_by') || 'Nobody yet';
const lastNote = (item: ReviewItem) => ({
  label: 'Note of the last decision',
  value: field(item, 'decision_note') || 'None',
});

const ITEMS: ListScreen = {
  title: 'Symptoms and other items',
  intro: (
    <p>
      Every symptom, question and other thing the service can know about a person, under the name used for it. Approving
      one says that it is a real item and is named correctly. Only approved items can be part of a published list of
      names.
    </p>
  ),
  path: '/features',
  targetType: 'feature',
  idField: 'feature_id',
  caption: 'Symptoms and other items',
  searchLabel: 'Search names',
  filters: [
    {
      param: 'kind',
      label: 'Kind of item',
      options: ['symptom', 'history', 'risk_factor', 'measurement', 'sign', 'other'].map((value) => ({
        value,
        label: itemKind(value),
      })),
    },
  ],
  titleOf: (item) => field(item, 'name'),
  columns: [
    { heading: 'Name', cell: (item) => field(item, 'name') },
    { heading: 'Kind of item', cell: (item) => itemKind(field(item, 'kind')) },
    {
      heading: 'Other names in the data files',
      cell: (item) => texts(item, 'other_names').slice(0, 4).join(' · ') || 'None',
    },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    { label: 'Name', value: field(item, 'name') },
    { label: 'Kind of item', value: itemKind(field(item, 'kind')) },
    { label: 'Kind of answer', value: answerKind(field(item, 'value_type')) },
    { label: 'Unit', value: field(item, 'unit') || 'None' },
    { label: 'Other names in the data files', value: texts(item, 'other_names').join(' · ') || 'None' },
    { label: 'Its name in the system', value: code(field(item, 'feature_id')) },
    lastNote(item),
  ],
};

/** Merging one condition name into another, taking it out again, and what has been done so far. */
function MergePanel({ api, item, onChanged }: { api: LiveReviewApi; item: ReviewItem; onChanged: () => void }) {
  const id = useId();
  const diseaseId = field(item, 'disease_id');
  const [into, setInto] = useState('');
  const [keep, setKeep] = useState('');
  const [note, setNote] = useState('');
  const [asking, setAsking] = useState<'merge' | 'split' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const { state } = useAsync(`review:live:history:${diseaseId}:${version}`, () =>
    api.get(`/diseases/${encodeURIComponent(diseaseId)}/history`),
  );
  const merged = field(item, 'merged_into');
  const past =
    state.status === 'loaded' && Array.isArray(state.data.history) ? (state.data.history as ReviewItem[]) : [];
  const others = state.status === 'loaded' ? texts(state.data, 'synonyms') : [];

  const ask = (what: 'merge' | 'split') => {
    setMessage(null);
    if (note.trim().length === 0 || (what === 'merge' && into.trim().length === 0)) {
      setError(
        what === 'merge'
          ? 'Give the name in the system of the condition to keep, and write a note.'
          : 'Write a note first.',
      );
      return;
    }
    setError(null);
    setAsking(what);
  };

  const send = async () => {
    if (!asking) {
      return;
    }
    setBusy(true);
    try {
      if (asking === 'merge') {
        const body: Record<string, unknown> = {
          source_disease_id: diseaseId,
          target_disease_id: into.trim(),
          note: note.trim(),
        };
        if (keep.trim()) {
          body.kept_name = keep.trim();
        }
        await api.post('/disease-merges', body);
        setMessage('Merged. This name is now kept as another name of that condition.');
      } else {
        await api.post('/disease-splits', { disease_id: diseaseId, note: note.trim() });
        setMessage('Taken out again. This name stands on its own.');
      }
      setNote('');
      setInto('');
      setKeep('');
      setVersion((value) => value + 1);
      onChanged();
    } catch (caught) {
      setError(caught instanceof ReviewApiError ? caught.message : 'The service could not do this.');
    } finally {
      setBusy(false);
      setAsking(null);
    }
  };

  return (
    <section aria-labelledby={`${id}-heading`}>
      <h3 id={`${id}-heading`} className="font-display text-base font-bold text-ink">
        Two names for one condition
      </h3>
      <p className="mt-1 text-ink-secondary">
        If this name and another one mean the same condition, merge this one into the other. Nothing is deleted: this
        name is kept as another name of that condition, and it can be taken out again.
      </p>
      {others.length > 0 ? (
        <p className="mt-1 text-ink">Other names kept under this condition: {others.join(' · ')}</p>
      ) : null}
      {past.length > 0 ? (
        <ul className="mt-2 space-y-1 text-sm text-ink-secondary">
          {past.map((event, index) => (
            <li key={`${field(event, 'at')}-${index}`}>
              {field(event, 'action') === 'merge' ? 'Merged' : 'Taken out again'} · {field(event, 'reviewer')} ·{' '}
              {field(event, 'note')}
            </li>
          ))}
        </ul>
      ) : null}
      {merged ? null : (
        <>
          <label htmlFor={`${id}-into`} className="mb-1 mt-2 block font-medium text-ink">
            Name in the system of the condition to keep
          </label>
          <input
            id={`${id}-into`}
            type="text"
            value={into}
            placeholder="dis_…"
            onChange={(event) => setInto(event.target.value)}
            className="field-control"
          />
          <label htmlFor={`${id}-keep`} className="mb-1 mt-2 block font-medium text-ink">
            Name to show for it (leave empty to keep its present name)
          </label>
          <input
            id={`${id}-keep`}
            type="text"
            value={keep}
            onChange={(event) => setKeep(event.target.value)}
            className="field-control"
          />
        </>
      )}
      <label htmlFor={`${id}-note`} className="mb-1 mt-2 block font-medium text-ink">
        Note for the merge (required)
      </label>
      <textarea
        id={`${id}-note`}
        rows={2}
        value={note}
        maxLength={2000}
        onChange={(event) => {
          setNote(event.target.value);
          setError(null);
          setAsking(null);
        }}
        className="field-control"
      />
      {error ? (
        <p role="alert" className="mt-1 text-sm font-medium text-urgent">
          {error}
        </p>
      ) : null}
      {asking ? (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" loading={busy} loadingLabel="Working…" onClick={() => void send()}>
            {asking === 'merge' ? 'Yes, merge it' : 'Yes, take it out'}
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => setAsking(null)}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className="mt-2">
          {merged ? (
            <Button size="sm" variant="secondary" onClick={() => ask('split')}>
              Take this name out again
            </Button>
          ) : (
            <Button size="sm" variant="secondary" onClick={() => ask('merge')}>
              Merge this name into that condition
            </Button>
          )}
        </div>
      )}
      <p role="status" className="mt-1 min-h-6 font-medium text-info">
        {message}
      </p>
    </section>
  );
}

const CONDITIONS: ListScreen = {
  title: 'Conditions',
  intro: (
    <p>
      Every condition under the name used for it. Approving one says that it is a real condition and is named correctly.
      Where two names mean the same condition, open one of them and merge it into the other; its name in the system is
      shown in the list so that it can be copied.
    </p>
  ),
  path: '/diseases',
  targetType: 'disease',
  idField: 'disease_id',
  caption: 'Conditions',
  searchLabel: 'Search names',
  titleOf: (item) => field(item, 'name'),
  columns: [
    { heading: 'Name', cell: (item) => field(item, 'name') },
    { heading: 'Its name in the system', cell: (item) => code(field(item, 'disease_id')) },
    {
      heading: 'On its own or merged',
      cell: (item) => (field(item, 'merged_into') ? <>Merged into {code(field(item, 'merged_into'))}</> : 'On its own'),
    },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    { label: 'Name', value: field(item, 'name') },
    { label: 'What it is', value: field(item, 'definition') || 'No description stored' },
    { label: 'Its name in the system', value: code(field(item, 'disease_id')) },
    {
      label: 'On its own or merged',
      value: field(item, 'merged_into') ? <>Merged into {code(field(item, 'merged_into'))}</> : 'On its own',
    },
    lastNote(item),
  ],
  extra: (item, tools) => (
    <MergePanel key={field(item, 'disease_id')} api={tools.api} item={item} onChanged={tools.reload} />
  ),
};

function pairWhy(item: ReviewItem): string {
  const signals = Array.isArray(item.signals) ? (item.signals as ReviewItem[]) : [];
  return (
    signals.map((signal) => pairReason(field(signal, 'signal'), texts(signal, 'words'))).join(' · ') || 'Not recorded'
  );
}

const PAIRS: ListScreen = {
  title: 'Names that may mean the same',
  intro: (
    <p>
      Pairs of names that the wording, or a shared code of a reference list, suggests are two names for one thing, or a
      narrower and a wider form of it. Approving a pair records that the suggestion is right; it merges nothing by
      itself. Two condition names are merged on the page of conditions.
    </p>
  ),
  path: '/relation-suggestions',
  targetType: 'relation_suggestion',
  idField: 'suggestion_id',
  caption: 'Pairs of names that may mean the same',
  searchLabel: 'Search names',
  filters: [
    {
      param: 'relation',
      label: 'What is suggested',
      options: ['possible_synonym', 'possible_subtype'].map((value) => ({ value, label: pairSuggestion(value) })),
    },
    {
      param: 'subject_type',
      label: 'Kind of name',
      options: [
        { value: 'disease', label: 'Conditions' },
        { value: 'feature', label: 'Symptoms and other items' },
      ],
    },
  ],
  titleOf: (item) => `${field(part(item, 'left'), 'term')} and ${field(part(item, 'right'), 'term')}`,
  columns: [
    { heading: 'First name', cell: (item) => field(part(item, 'left'), 'term') },
    { heading: 'Second name', cell: (item) => field(part(item, 'right'), 'term') },
    { heading: 'What is suggested', cell: (item) => pairSuggestion(field(item, 'relation')) },
    { heading: 'Why', cell: pairWhy },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    {
      label: 'First name',
      value: (
        <>
          {field(part(item, 'left'), 'term')} {code(field(part(item, 'left'), 'id'))}
        </>
      ),
    },
    {
      label: 'Second name',
      value: (
        <>
          {field(part(item, 'right'), 'term')} {code(field(part(item, 'right'), 'id'))}
        </>
      ),
    },
    { label: 'What is suggested', value: pairSuggestion(field(item, 'relation')) },
    { label: 'Why', value: pairWhy(item) },
    { label: 'Decided by', value: decidedBy(item) },
  ],
};

function howOften(item: ReviewItem): string {
  const share = typeof item.frequency === 'number' ? item.frequency : Number.NaN;
  if (Number.isNaN(share)) {
    return 'Not counted';
  }
  return `${(share * 100).toFixed(1)}% of ${field(item, 'frequency_denominator') || 'the'} rows with this condition`;
}

const FACTS: ListScreen = {
  title: 'Facts from the data files',
  intro: (
    <p>
      Each row links one condition with one symptom or other item, as a data file or a source text gives it. A count
      says how often the two stood together in that data file. It is not how common the symptom is among real patients,
      and several of the data files are of unknown origin or were made by a computer.
    </p>
  ),
  path: '/evidence',
  targetType: 'evidence',
  idField: 'evidence_id',
  caption: 'Facts linking a condition and a symptom',
  filters: [
    {
      param: 'evidence_type',
      label: 'Where it comes from',
      options: ['dataset_cooccurrence', 'source_condition_list', 'narrative_lexical_mention', 'reviewed_claim'].map(
        (value) => ({ value, label: factKind(value) }),
      ),
    },
  ],
  titleOf: (item) => `${field(part(item, 'disease'), 'term')} and ${field(part(item, 'feature'), 'term')}`,
  columns: [
    { heading: 'Condition', cell: (item) => field(part(item, 'disease'), 'term') },
    { heading: 'Symptom or other item', cell: (item) => field(part(item, 'feature'), 'term') },
    { heading: 'Where it comes from', cell: (item) => factKind(field(item, 'evidence_type')) },
    { heading: 'How often in that data file', cell: howOften },
  ],
  details: (item) => {
    const context = part(item, 'context');
    return [
      { label: 'Condition', value: field(part(item, 'disease'), 'term') },
      { label: 'Symptom or other item', value: field(part(item, 'feature'), 'term') },
      { label: 'Where it comes from', value: factKind(field(item, 'evidence_type')) },
      { label: 'Data file', value: field(context, 'source') || 'Not recorded' },
      { label: 'How often in that data file', value: howOften(item) },
      {
        label: 'Rows with this condition that are exact copies of another row',
        value: field(context, 'exact_duplicate_rows_with_label') || 'Not counted',
      },
      { label: 'Its name in the system', value: code(field(item, 'evidence_id')) },
    ];
  },
};

const SOURCES: ListScreen = {
  title: 'Data sources',
  intro: (
    <p>
      Every file or publication that data was taken from. Approving a source says that its licence and its origin allow
      its content to be used and shown. Content of a source that is not approved is never published.
    </p>
  ),
  path: '/sources',
  targetType: 'source',
  idField: 'source_id',
  caption: 'Data sources and their rights',
  plain: true,
  titleOf: (item) => field(item, 'name'),
  columns: [
    { heading: 'Source', cell: (item) => field(item, 'name') },
    { heading: 'Licence', cell: (item) => field(item, 'licence') || 'None recorded' },
    { heading: 'Where it came from', cell: (item) => field(item, 'origin_url') || 'Not recorded' },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    { label: 'Source', value: field(item, 'name') },
    { label: 'Edition', value: field(item, 'version') || 'Not recorded' },
    { label: 'Licence', value: field(item, 'licence') || 'None recorded' },
    { label: 'Where it came from', value: field(item, 'origin_url') || 'Not recorded' },
    { label: 'What may be done with it, as recorded', value: field(item, 'permitted_uses') || 'Not recorded' },
    { label: 'Its name in the system', value: code(field(item, 'source_id')) },
    lastNote(item),
  ],
};

const section = (item: ReviewItem): string => texts(item, 'section_path').join(' › ') || 'Opening part';
const becomes = (item: ReviewItem): string =>
  item.is_references_or_links
    ? 'Nothing: it is a list of references or links, which the service does not approve'
    : `A text about the condition (${kindOfText(field(item, 'statement_type_if_approved')).toLowerCase()})`;

const TEXT_PARTS: ListScreen = {
  title: 'Parts of the text files',
  intro: (
    <p>
      The longer texts about conditions, cut into parts at their own section headings. A part is used for nothing until
      a reviewer approves it. An approved part becomes one text about its condition, with the file and the place in it
      kept as its source.
    </p>
  ),
  path: '/chunks',
  targetType: 'chunk',
  idField: 'chunk_id',
  caption: 'Parts of the text files',
  searchLabel: 'Search the text',
  pageSize: 20,
  titleOf: (item) => `${field(part(item, 'disease'), 'term')}: ${section(item)}`,
  columns: [
    { heading: 'Condition and section', cell: (item) => `${field(part(item, 'disease'), 'term')}: ${section(item)}` },
    {
      heading: 'Text',
      cell: (item) => `${field(item, 'text').slice(0, 180)}${field(item, 'text').length > 180 ? '…' : ''}`,
    },
    { heading: 'If approved it becomes', cell: becomes },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    { label: 'Condition', value: field(part(item, 'disease'), 'term') },
    { label: 'Section of the text', value: section(item) },
    { label: 'The text', value: <span className="whitespace-pre-wrap">{field(item, 'text')}</span> },
    { label: 'If approved it becomes', value: becomes(item) },
    { label: 'File', value: field(item, 'file') },
    { label: 'Where the text was taken from', value: field(item, 'source_url') || 'Not recorded' },
  ],
};

const QUESTIONS: ListScreen = {
  title: 'Follow-up questions',
  intro: (
    <p>
      The questions the service may ask after a person has described what is wrong. A question is asked only when it is
      approved and its set of rules is published. The questions stored today are invented samples used by the tests.
    </p>
  ),
  path: '/questions',
  targetType: 'followup_question',
  idField: 'question_id',
  caption: 'Follow-up questions',
  titleOf: (item) => field(item, 'wording'),
  columns: [
    { heading: 'Question', cell: (item) => field(item, 'wording') },
    { heading: 'Kind of answer', cell: (item) => answerKind(field(item, 'answer_type')) },
    { heading: 'What it asks about', cell: (item) => field(part(item, 'asks_about'), 'term') || 'Nothing named' },
    { heading: 'Set of rules it belongs to', cell: (item) => code(field(item, 'bundle_id')) },
  ],
  details: (item) => [
    { label: 'Question', value: field(item, 'wording') },
    { label: 'Kind of answer', value: answerKind(field(item, 'answer_type')) },
    { label: 'What it asks about', value: field(part(item, 'asks_about'), 'term') || 'Nothing named' },
    { label: 'Set of rules it belongs to (its name in the system)', value: code(field(item, 'bundle_id')) },
    { label: 'Its name in the system', value: code(field(item, 'question_id')) },
  ],
};

const REPLY_USES: ReadonlyArray<readonly [string, string]> = [
  ['confirm_details', 'Before going on, to check what was understood'],
  ['provisional_next_step', 'With the possible explanations'],
  ['insufficient_information', 'When there is not enough reviewed information'],
  ['system_unavailable', 'When the assessment cannot be completed'],
];

const REPLIES: ListScreen = {
  title: 'Standard replies',
  intro: (
    <p>
      The four fixed texts a person is shown outside the urgency rules. They are approved together, as one set, and
      every word is shown here as stored. The service never writes such a text by itself.
    </p>
  ),
  path: '/response-texts',
  targetType: 'response_texts',
  idField: 'set_id',
  caption: 'Sets of standard replies',
  plain: true,
  titleOf: (item) => field(item, 'version'),
  columns: [
    { heading: 'Set (its name in the system)', cell: (item) => code(field(item, 'version')) },
    { heading: 'Texts in it', cell: (item) => String(Object.keys(part(item, 'texts')).length) },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    ...REPLY_USES.map(([name, use]) => ({ label: use, value: field(part(item, 'texts'), name) || 'No text stored' })),
    { label: 'Fingerprint of the file the texts were stored from', value: code(field(item, 'fingerprint')) },
  ],
};

const RULE_SETS: ListScreen = {
  title: 'Sets of urgency rules',
  intro: (
    <p>
      A set of urgency rules is approved as a whole, after its rules. The service refuses the approval until every rule
      of the set has been decided, the rule file is the one that was stored, and every telephone number in it has been
      confirmed. Only an approved set can be published.
    </p>
  ),
  path: '/rule-sets',
  targetType: 'rule_bundle',
  idField: 'bundle_id',
  caption: 'Sets of urgency rules',
  plain: true,
  titleOf: (item) => field(item, 'bundle_id'),
  columns: [
    { heading: 'Set (its name in the system)', cell: (item) => code(field(item, 'bundle_id')) },
    {
      heading: 'Its rules by decision',
      cell: (item) =>
        Object.entries(part(item, 'rules_by_status'))
          .map(([status, count]) => `${String(count)} ${status === 'pending' ? 'waiting for a decision' : status}`)
          .join(' · ') || 'No rules',
    },
    { heading: 'Decided by', cell: decidedBy },
  ],
  details: (item) => [
    { label: 'Edition', value: field(item, 'version') },
    {
      label: 'Fingerprint of the rule file it was stored from',
      value: field(item, 'fingerprint') ? code(field(item, 'fingerprint')) : 'None: not stored from a rule file',
    },
    { label: 'Approved by', value: field(item, 'approved_by') || 'Nobody yet' },
  ],
};

export const LiveItemsPage = () => <LiveListPage screen={ITEMS} />;
export const LiveConditionsPage = () => <LiveListPage screen={CONDITIONS} />;
export const LivePairsPage = () => <LiveListPage screen={PAIRS} />;
export const LiveFactsPage = () => <LiveListPage screen={FACTS} />;
export const LiveSourcesPage = () => <LiveListPage screen={SOURCES} />;
export const LiveTextPartsPage = () => <LiveListPage screen={TEXT_PARTS} />;
export const LiveQuestionsPage = () => <LiveListPage screen={QUESTIONS} />;
export const LiveRepliesPage = () => <LiveListPage screen={REPLIES} />;
export const LiveRuleSetsPage = () => <LiveListPage screen={RULE_SETS} />;

const MORE: ReadonlyArray<{ to: string; label: string; detail: string }> = [
  {
    to: '/review/conditions',
    label: 'Conditions',
    detail: 'Approve a condition itself, and merge two names that mean the same condition.',
  },
  {
    to: '/review/items',
    label: 'Symptoms and other items',
    detail: 'Approve a symptom, question or other item itself.',
  },
  {
    to: '/review/pairs',
    label: 'Names that may mean the same',
    detail: 'Pairs the wording or a shared code suggests are the same thing.',
  },
  {
    to: '/review/facts',
    label: 'Facts from the data files',
    detail: 'Which symptom goes with which condition, as the data files give it.',
  },
  {
    to: '/review/text-parts',
    label: 'Parts of the text files',
    detail: 'The longer texts, cut at their section headings.',
  },
  { to: '/review/sources', label: 'Data sources', detail: 'Whether a source may be used and shown.' },
  { to: '/review/questions', label: 'Follow-up questions', detail: 'The questions the service may ask.' },
  { to: '/review/replies', label: 'Standard replies', detail: 'The four fixed texts a person is shown.' },
  { to: '/review/rule-sets', label: 'Sets of urgency rules', detail: 'Approve a whole set of rules after its rules.' },
];

/** The lists that have no entry of their own in the navigation. */
export function LiveMorePage() {
  return (
    <div>
      <ReviewPageHeader title="More lists to review" badge={<StatusBadge tone="info">Real stored data</StatusBadge>}>
        <p>
          Everything else that waits for a decision. Each list works like the others: open a row to read it, write a
          note and decide; or decide all the rows shown at once.
        </p>
      </ReviewPageHeader>
      <ul className="grid gap-3 md:grid-cols-2">
        {MORE.map((entry) => (
          <li key={entry.to}>
            <Link
              to={entry.to}
              className="block min-h-11 rounded-control border border-line bg-surface p-4 hover:border-ink-muted"
            >
              <span className="block font-semibold text-primary underline underline-offset-4">{entry.label}</span>
              <span className="block text-sm text-ink-secondary">{entry.detail}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
