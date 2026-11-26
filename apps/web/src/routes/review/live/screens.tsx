import type { ReactNode } from 'react';

import { field, part, type ReviewItem } from '@/api/liveReview';

import { LiveListPage, type ListScreen } from './LiveListPage';
import { howGrouped, howMatched, kindOfName, zeroMeaning } from './words';

const code = (text: string): ReactNode => <code className="break-all text-sm">{text}</code>;

function conflictText(item: ReviewItem): string {
  const conflicts = part(item, 'conflicts');
  if (!conflicts.repeated_header) {
    return 'Not repeated';
  }
  const positions = Array.isArray(conflicts.repeated_positions) ? conflicts.repeated_positions.join(', ') : '';
  return `The heading is repeated at columns ${positions}; the columns disagree in ${field(conflicts, 'disagreement_rows') || '0'} rows`;
}

const DISEASE_MAPPINGS: ListScreen = {
  title: 'Condition names',
  intro: (
    <p>
      The names of conditions exactly as they appear in the data files, and the name each is grouped under. A name
      stands here once for every data file that uses it, so the same name on several rows is not a mistake: each row is
      that name in another file. Names are grouped only when they are spelled the same once capital letters and extra
      spaces are ignored. Being in one group does not mean the names are the same condition.
    </p>
  ),
  path: '/disease-mappings',
  targetType: 'disease_mapping',
  idField: 'mapping_id',
  caption: 'Condition names from the data files and the name each is grouped under',
  searchLabel: 'Search names from the data files',
  titleOf: (item) => `${field(item, 'original_term')} (${field(item, 'source_name') || field(item, 'source_id')})`,
  columns: [
    { heading: 'Name in the data file', cell: (item) => field(item, 'original_term') },
    { heading: 'Data file', cell: (item) => field(item, 'source_name') || field(item, 'source_id') },
    { heading: 'Name it is grouped under', cell: (item) => field(item, 'proposed_canonical_term') },
    { heading: 'How it was grouped', cell: (item) => howGrouped(field(item, 'mapping_method')) },
    { heading: 'Decided by', cell: (item) => field(item, 'reviewer') || 'Nobody yet' },
  ],
  details: (item) => [
    { label: 'Name exactly as in the data file', value: code(field(item, 'original_term')) },
    { label: 'Name it is grouped under', value: field(item, 'proposed_canonical_term') },
    { label: 'How it was grouped', value: howGrouped(field(item, 'mapping_method')) },
    { label: 'Data file it came from', value: field(item, 'source_name') || 'Not recorded' },
    { label: 'Data file it came from (name in the system)', value: code(field(item, 'source_id')) },
    { label: 'Number the data file gives it', value: field(item, 'original_id') || 'None' },
  ],
};

const featureMappings = (duplicatesOnly: boolean): ListScreen => ({
  title: duplicatesOnly ? 'Repeated columns in the data files' : 'Symptom and question names',
  intro: duplicatesOnly ? (
    <p>
      Column headings that appear more than once in the same data file. Each column is kept exactly as it came, with the
      number of rows in which the repeated columns disagree, so that someone can decide which one to trust. Nothing was
      merged.
    </p>
  ) : (
    <p>
      One row for each column of a data file, with its heading exactly as it came. The name suggested for it is based on
      its wording only. The columns include questions and past history, not only symptoms, and none has been checked by
      a clinician.
    </p>
  ),
  path: '/feature-mappings',
  targetType: 'feature_mapping',
  idField: 'mapping_id',
  caption: duplicatesOnly ? 'Repeated column headings, by data file' : 'Columns of the data files and their names',
  searchLabel: 'Search column headings',
  fixedParams: duplicatesOnly ? { conflicts_only: true } : undefined,
  titleOf: (item) => `${field(item, 'original_term')} (column ${field(item, 'column_index') || 'list'})`,
  columns: [
    { heading: 'Heading in the data file', cell: (item) => field(item, 'original_term') },
    {
      heading: 'File and column number',
      cell: (item) => `${field(item, 'file_path')} · column ${field(item, 'column_index') || 'list term'}`,
    },
    { heading: 'What a 0 in this column means', cell: (item) => zeroMeaning(field(item, 'zero_semantics')) },
    { heading: 'Repeated columns', cell: conflictText },
  ],
  details: (item) => [
    { label: 'Heading exactly as in the data file', value: code(field(item, 'original_term')) },
    {
      label: 'File and column number',
      value: `${field(item, 'file_path')} · column ${field(item, 'column_index') || 'list term'}`,
    },
    { label: 'Name suggested for it (name in the system)', value: code(field(item, 'proposed_canonical_id')) },
    { label: 'What a 0 in this column means (suggested)', value: zeroMeaning(field(item, 'zero_semantics')) },
    { label: 'Repeated columns', value: conflictText(item) },
    { label: 'Data file it came from (name in the system)', value: code(field(item, 'source_id')) },
  ],
});

const VOCABULARY_LINKS: ListScreen = {
  title: 'Matches to medical reference lists',
  intro: (
    <>
      <p>
        Our names for conditions and symptoms, matched to entries in standard medical reference lists (ICD-11, HPO,
        MONDO, SNOMED CT, LOINC). A match was made automatically when a list has an entry with exactly our name, or when
        one list says that its entry is the same as an entry of another list. Every match is a suggestion until a
        reviewer decides. The codes are shown to reviewers only and never to a patient.
      </p>
      <p>
        Some codes were reached by way of a MONDO entry. If you reject that MONDO match, the codes reached through it
        are set aside as well. Where a name has both a general entry and a more specific one, the general one is
        preferred: the service will not approve the specific one while the general one stands, and tells you why.
      </p>
    </>
  ),
  path: '/terminology-links',
  targetType: 'terminology_link',
  idField: 'link_id',
  caption: 'Matches to medical reference lists',
  searchLabel: 'Search our names, entries or codes',
  filters: [
    {
      param: 'system',
      label: 'Reference list',
      options: ['ICD-11 MMS', 'ICD-11 Foundation', 'MONDO', 'HPO', 'SNOMED CT', 'LOINC', 'ICD-10'].map((value) => ({
        value,
        label: value,
      })),
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
  titleOf: (item) => `${field(part(item, 'subject'), 'term')} → ${field(item, 'title')}`,
  columns: [
    { heading: 'Our name', cell: (item) => field(part(item, 'subject'), 'term') },
    { heading: 'Reference list', cell: (item) => field(item, 'system') },
    { heading: 'Entry in the list', cell: (item) => field(item, 'title') },
    { heading: 'Code', cell: (item) => code(field(item, 'code')) },
    { heading: 'How the match was found', cell: (item) => howMatched(field(item, 'match_method')) },
  ],
  details: (item) => {
    const via = part(part(item, 'detail'), 'via');
    const category = part(part(item, 'detail'), 'category_through_mondo');
    return [
      {
        label: 'Our name',
        value: `${field(part(item, 'subject'), 'term')} (${kindOfName(field(part(item, 'subject'), 'type'))})`,
      },
      { label: 'Reference list and its edition', value: `${field(item, 'system')} · ${field(item, 'system_version')}` },
      { label: 'Entry in the list', value: field(item, 'title') },
      { label: 'Code of the entry (for reviewers only)', value: code(field(item, 'code')) },
      { label: 'How the match was found', value: howMatched(field(item, 'match_method')) },
      {
        label: 'Found by way of',
        value: via.link_id
          ? `The MONDO entry "${field(via, 'title')}", which our name is matched to`
          : 'Our name itself',
      },
      {
        label: 'Group this entry is the “unspecified” member of',
        value: category.icd_title ? field(category, 'icd_title') : 'Not recorded',
      },
      { label: 'Decided by', value: field(item, 'reviewer') || 'Nobody yet' },
    ];
  },
};

export const LiveDiseaseMappingsPage = () => <LiveListPage screen={DISEASE_MAPPINGS} />;
export const LiveFeatureMappingsPage = () => <LiveListPage screen={featureMappings(false)} />;
export const LiveDataQualityPage = () => <LiveListPage screen={featureMappings(true)} />;
export const LiveVocabularyLinksPage = () => <LiveListPage screen={VOCABULARY_LINKS} />;

// ---- Names that were not matched automatically, and the entries suggested for them (M2.4b) ----------------

/** Why a row is on the page, in plain words, by the kind the service gives. */
const WHY_NOT_MATCHED: Record<string, string> = {
  abbreviation_only: 'Our name is only an abbreviation of this entry, and an abbreviation can stand for several things',
  several_terms_carry_the_name: 'Several entries have this name, so one has to be chosen',
  several_identifiers_marked_equivalent:
    'The reference list gives several codes for this condition, so one has to be chosen',
  close_search_result: 'The search found an entry that comes close, but none with exactly our name',
  looser_synonym: 'Our name is listed for this entry only as a broader, narrower or related name',
  nearest_by_shared_words: 'No entry has our name; this one shares the most words with it',
  plain_word_not_the_abbreviation:
    'Our name is an ordinary word, not the abbreviation it looks like; this entry shares the most words with it',
  weak_search_result: 'The search found only an entry that is not close; it is probably not the same thing',
  term_not_linkable: 'The only entry with our name is out of use or of another kind, so it cannot be used',
  no_term_near: 'No entry has this name or a similar one',
  no_search_result: 'The search of this list found nothing for this name',
  question_sentence_not_looked_up: 'This is a whole question, not a name, so it was not looked up',
};

const NO_SUGGESTION =
  'There is no suggested entry to confirm or reject for this row. It is listed so that you can see why the name has no match. You can still write a note.';

const whyNotMatched = (item: ReviewItem): string => WHY_NOT_MATCHED[field(item, 'basis')] ?? field(item, 'meaning');

function matchMade(item: ReviewItem): string {
  const made = field(part(item, 'link'), 'review_status');
  if (!item.can_be_confirmed) {
    return 'Not possible: nothing to confirm';
  }
  if (made === 'approved') {
    return 'Yes, confirmed';
  }
  if (made === 'rejected' || (!made && field(item, 'review_status') === 'rejected')) {
    return 'No, rejected';
  }
  return made === 'pending' ? 'Also found another way; waiting for a decision' : 'Not yet';
}

function howClose(item: ReviewItem): string {
  const detail = part(item, 'detail');
  const parts = [
    // The search's own score: 1 when every word matches; it falls, below 0 too, the further the entry is.
    detail.score !== undefined ? `Search score ${field(detail, 'score')} (the best possible is 1)` : '',
    field(detail, 'note'),
    field(detail, 'matched_text') ? `Compared with the name "${field(detail, 'matched_text')}"` : '',
    field(detail, 'read_as') ? `Our name was read as "${field(detail, 'read_as')}"` : '',
  ].filter((text) => text.length > 0);
  return parts.length > 0 ? parts.join(' · ') : 'Not recorded';
}

const LINK_PROPOSALS: ListScreen = {
  title: 'Suggested matches to check',
  intro: (
    <>
      <p>
        Each of our names for a condition or a symptom is looked up in standard medical reference lists (ICD-11, HPO,
        MONDO, SNOMED CT). A name is matched automatically only when a list has an entry with exactly the same name.
        This page shows the names that were not matched, and why.
      </p>
      <p>
        Where the look-up found an entry that comes close, confirm it if it means the same as our name, or reject it if
        it does not. Nothing on this page counts as a match until a reviewer confirms it. Rows without a suggestion are
        here so that you can see why a name has no match.
      </p>
    </>
  ),
  path: '/link-proposals',
  targetType: 'link_proposal',
  idField: 'proposal_id',
  caption: 'Names without a match and the entries suggested for them',
  searchLabel: 'Search our names, suggested entries or codes',
  filters: [
    {
      param: 'decidable',
      label: 'What you can do',
      options: [
        { value: 'true', label: 'Confirm or reject a suggestion' },
        { value: 'false', label: 'Read only: no suggestion' },
      ],
    },
    {
      param: 'system',
      label: 'Reference list',
      options: ['ICD-11 MMS', 'ICD-11 Foundation', 'MONDO', 'HPO', 'SNOMED CT'].map((value) => ({
        value,
        label: value,
      })),
    },
    {
      param: 'basis',
      label: 'Why it is here',
      options: [
        { value: 'close_search_result', label: 'Close search result' },
        { value: 'several_identifiers_marked_equivalent', label: 'Several codes to choose from' },
        { value: 'several_terms_carry_the_name', label: 'Several entries with this name' },
        { value: 'abbreviation_only', label: 'Abbreviation only' },
        { value: 'looser_synonym', label: 'Broader, narrower or related name' },
        { value: 'nearest_by_shared_words', label: 'Nearest entry by shared words' },
        { value: 'plain_word_not_the_abbreviation', label: 'Ordinary word, not an abbreviation' },
        { value: 'weak_search_result', label: 'Weak search result' },
        { value: 'term_not_linkable', label: 'Entry cannot be used' },
        { value: 'no_term_near', label: 'No similar entry' },
        { value: 'no_search_result', label: 'Search found nothing' },
        { value: 'question_sentence_not_looked_up', label: 'A question, not looked up' },
      ],
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
  titleOf: (item) =>
    `${field(part(item, 'subject'), 'term')} → ${field(part(item, 'term'), 'title') || 'no suggestion'} (${field(item, 'system')})`,
  columns: [
    { heading: 'Our name', cell: (item) => field(part(item, 'subject'), 'term') },
    { heading: 'Reference list', cell: (item) => field(item, 'system') },
    {
      heading: 'Suggested entry',
      // Two suggestions for one name can carry the same title (two codes of one list), so the code is shown too.
      cell: (item) =>
        field(part(item, 'term'), 'title') ? (
          <>
            {field(part(item, 'term'), 'title')}
            <span className="block text-sm">Code {code(field(part(item, 'term'), 'code'))}</span>
          </>
        ) : (
          'No suggestion'
        ),
    },
    { heading: 'Why it was not matched automatically', cell: whyNotMatched },
    { heading: 'Match made', cell: matchMade },
  ],
  details: (item) => {
    const via = part(part(item, 'detail'), 'via');
    const term = part(item, 'term');
    return [
      {
        label: 'Our name',
        value: `${field(part(item, 'subject'), 'term')} (${kindOfName(field(part(item, 'subject'), 'type'))})`,
      },
      { label: 'Reference list and its edition', value: `${field(item, 'system')} · ${field(item, 'system_version')}` },
      { label: 'Suggested entry', value: field(term, 'title') || 'No suggestion' },
      { label: 'Code of the entry (for reviewers only)', value: term.code ? code(field(term, 'code')) : 'None' },
      { label: 'Why it was not matched automatically', value: whyNotMatched(item) },
      { label: 'What the look-up recorded', value: field(item, 'reason') },
      { label: 'How close it is', value: howClose(item) },
      {
        label: 'Found by way of',
        value: via.title ? `The MONDO entry "${field(via, 'title')}", which our name is matched to` : 'Our name itself',
      },
      { label: 'Match made', value: matchMade(item) },
      { label: 'Decided by', value: field(item, 'reviewer') || 'Nobody yet' },
    ];
  },
  notesOnly: (item) => (item.can_be_confirmed ? null : NO_SUGGESTION),
  decisionLabels: { approved: 'Confirm match', rejected: 'Reject match' },
};

export const LiveLinkProposalsPage = () => <LiveListPage screen={LINK_PROPOSALS} />;
