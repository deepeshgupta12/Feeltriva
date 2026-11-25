import type { ReactNode } from 'react';

import { field, part, type ReviewItem } from '@/api/liveReview';

import { LiveListPage, type ListScreen } from './LiveListPage';

/**
 * The urgency rules in words (M2.4c). The words come from the review service, which writes them
 * with the same functions as the review document `docs/review/urgency_rules_draft.md`: what a
 * reviewer reads here is what that document says. A rule the service cannot put into words is
 * shown as stored, with the reason.
 */
interface ConditionLine {
  depth: number;
  text: string;
  heads_a_group: boolean;
}

interface QuotedSource {
  publisher: string;
  title: string;
  url: string;
  page_reviewed: string;
  quotes: string[];
}

interface RuleWords {
  number: number;
  of: number;
  title: string;
  level: string;
  level_meaning: string;
  fires_when: ConditionLine[];
  shown: string;
  why_this_level: string;
  checked_with: { fires: string; does_not_fire: string };
  basis: QuotedSource[];
}

const wordsOf = (item: ReviewItem): RuleWords | null =>
  item.in_words !== null && typeof item.in_words === 'object' ? (item.in_words as RuleWords) : null;

const INDENT = ['', 'ml-5', 'ml-10', 'ml-16', 'ml-20'];

function Condition({ lines }: { lines: ConditionLine[] }) {
  return (
    <ul className="space-y-1.5">
      {lines.map((line, index) => (
        <li
          // The lines of one condition never change order.
          key={index}
          className={`${INDENT[Math.min(line.depth, INDENT.length - 1)]} ${line.heads_a_group ? 'font-semibold' : ''}`}
        >
          {line.text}
        </li>
      ))}
    </ul>
  );
}

function Basis({ sources }: { sources: QuotedSource[] }) {
  return (
    <ul className="space-y-3">
      {sources.map((source) => (
        <li key={source.url}>
          <p>
            {source.publisher},{' '}
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary underline underline-offset-4"
            >
              {source.title}
            </a>
            {source.page_reviewed ? `, page last reviewed ${source.page_reviewed}` : ''}:
          </p>
          <ul className="mt-1 space-y-1 border-l-2 border-line pl-3 text-ink-secondary">
            {source.quotes.map((quote) => (
              <li key={quote}>“{quote}”</li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

const code = (text: string): ReactNode => <code className="break-all text-sm">{text}</code>;
const level = (item: ReviewItem): string => wordsOf(item)?.level ?? field(part(item, 'action'), 'urgency');
const title = (item: ReviewItem): string => {
  const words = wordsOf(item);
  return words ? `${words.number}. ${words.title}` : field(item, 'rule_id');
};

const RULES: ListScreen = {
  title: 'Urgency rules',
  intro: (
    <>
      <p>
        An urgency rule decides when the service stops its routine questions and tells a person to get help quickly.
        Each rule is shown here in words: when it applies, what the person is told, why it has its level, and the
        published advice it is based on, quoted word for word. The same words are in the review document{' '}
        <code>docs/review/urgency_rules_draft.md</code>.
      </p>
      <p>
        A rule applies only when what has been recorded makes its condition true. A symptom nobody has asked about is
        unknown: it counts neither as present nor as absent. Once the whole set of rules is approved, a single rule
        cannot be decided again until that approval is withdrawn.
      </p>
    </>
  ),
  path: '/rules',
  targetType: 'clinical_rule',
  idField: 'rule_id',
  caption: 'The urgency rules, in the order in which they are checked',
  pageSize: 50,
  titleOf: title,
  columns: [
    { heading: 'Rule', cell: title },
    { heading: 'Level', cell: level },
    { heading: 'What the person is told', cell: (item) => field(part(item, 'action'), 'text') },
    { heading: 'Decided by', cell: (item) => field(item, 'decided_by') || 'Nobody yet' },
  ],
  details: (item) => {
    const words = wordsOf(item);
    const stored = [
      { label: 'Set of rules it belongs to', value: field(item, 'bundle_id') },
      { label: 'Name of the rule in the system', value: code(field(item, 'rule_id')) },
      { label: 'Note of the last decision', value: field(item, 'decision_note') || 'None' },
    ];
    if (!words) {
      return [
        { label: 'Why this rule is not shown in words', value: field(item, 'in_words_unavailable') || 'Not recorded' },
        { label: 'Level', value: level(item) },
        { label: 'What the person is told', value: field(part(item, 'action'), 'text') },
        { label: 'When the rule applies, as stored', value: code(field(item, 'condition_ast')) },
        ...stored,
      ];
    }
    return [
      { label: 'Level', value: `${words.level}. ${words.level_meaning}` },
      { label: 'When this rule applies', value: <Condition lines={words.fires_when} /> },
      { label: 'What the person is told', value: words.shown },
      { label: 'Why it has this level', value: words.why_this_level },
      {
        label: 'Checked with two examples',
        value: (
          <ul className="space-y-1.5">
            <li>The rule applies: {words.checked_with.fires}.</li>
            <li>The rule does not apply: {words.checked_with.does_not_fire}.</li>
          </ul>
        ),
      },
      { label: 'What it is based on, quoted word for word', value: <Basis sources={words.basis} /> },
      { label: 'Place in the order of checking', value: `${words.number} of ${words.of}` },
      ...stored,
    ];
  },
};

export const LiveRulesPage = () => <LiveListPage screen={RULES} />;
