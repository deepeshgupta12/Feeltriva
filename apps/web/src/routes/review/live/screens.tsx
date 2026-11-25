import type { ReactNode } from 'react';

import { field, part, type ReviewItem } from '@/api/liveReview';

import { LiveListPage, type ListScreen } from './LiveListPage';

const code = (text: string): ReactNode => <code className="break-all text-sm">{text}</code>;

function conflictText(item: ReviewItem): string {
  const conflicts = part(item, 'conflicts');
  if (!conflicts.repeated_header) {
    return 'None recorded';
  }
  const positions = Array.isArray(conflicts.repeated_positions) ? conflicts.repeated_positions.join(', ') : '';
  return `The heading is repeated at columns ${positions}; the columns disagree in ${field(conflicts, 'disagreement_rows') || '0'} rows`;
}

const DISEASE_MAPPINGS: ListScreen = {
  title: 'Disease mappings',
  intro: (
    <p>
      Source labels grouped by spelling only. Sharing a group means the labels are spelled alike after normalisation; it
      does not mean they are the same condition. A decision here is recorded under your name.
    </p>
  ),
  path: '/disease-mappings',
  targetType: 'disease_mapping',
  idField: 'mapping_id',
  caption: 'Source labels and the disease label each is mapped to',
  searchLabel: 'Search source labels',
  titleOf: (item) => field(item, 'original_term'),
  columns: [
    { heading: 'Original label', cell: (item) => field(item, 'original_term') },
    { heading: 'Proposed label', cell: (item) => field(item, 'proposed_canonical_term') },
    { heading: 'Mapping method', cell: (item) => field(item, 'mapping_method') },
    { heading: 'Decided by', cell: (item) => field(item, 'reviewer') || 'Nobody yet' },
  ],
  details: (item) => [
    { label: 'Original label, exactly as imported', value: code(field(item, 'original_term')) },
    { label: 'Proposed label', value: field(item, 'proposed_canonical_term') },
    { label: 'Mapping method', value: field(item, 'mapping_method') },
    { label: 'Source', value: code(field(item, 'source_id')) },
    { label: 'ID in the source', value: field(item, 'original_id') || 'None' },
  ],
};

const featureMappings = (duplicatesOnly: boolean): ListScreen => ({
  title: duplicatesOnly ? 'Data quality: repeated column headings' : 'Feature mappings',
  intro: duplicatesOnly ? (
    <p>
      Column headings that appear more than once in a source file. Every column position is kept as imported, with the
      number of rows in which the columns disagree, so that a reviewer can reconcile them. Nothing was merged.
    </p>
  ) : (
    <p>
      One row per source column, with the heading exactly as imported. The proposed terms are candidates by wording.
      They include questionnaire and history items and are not verified symptoms.
    </p>
  ),
  path: '/feature-mappings',
  targetType: 'feature_mapping',
  idField: 'mapping_id',
  caption: duplicatesOnly ? 'Repeated column headings by source file' : 'Feature mappings by source column',
  searchLabel: 'Search column headings',
  fixedParams: duplicatesOnly ? { conflicts_only: true } : undefined,
  titleOf: (item) => `${field(item, 'original_term')} (column ${field(item, 'column_index') || 'list'})`,
  columns: [
    { heading: 'Original heading', cell: (item) => field(item, 'original_term') },
    {
      heading: 'File and column',
      cell: (item) => `${field(item, 'file_path')} · column ${field(item, 'column_index') || 'list term'}`,
    },
    { heading: 'What a zero means', cell: (item) => field(item, 'zero_semantics') },
    { heading: 'Conflicts', cell: conflictText },
  ],
  details: (item) => [
    { label: 'Original heading, exactly as imported', value: code(field(item, 'original_term')) },
    {
      label: 'File and column position',
      value: `${field(item, 'file_path')} · column ${field(item, 'column_index') || 'list term'}`,
    },
    { label: 'Proposed feature', value: code(field(item, 'proposed_canonical_id')) },
    { label: 'What a zero means (proposal)', value: field(item, 'zero_semantics') },
    { label: 'Conflicts', value: conflictText(item) },
    { label: 'Source', value: code(field(item, 'source_id')) },
  ],
});

const VOCABULARY_LINKS: ListScreen = {
  title: 'Vocabulary links',
  intro: (
    <>
      <p>
        Candidate links from our own terms to outside vocabularies. A link is a match of names, or an equivalence a
        vocabulary states; it is a candidate until a reviewer decides. Codes are shown here for reviewers only and are
        never shown to a user.
      </p>
      <p>
        Rejecting a MONDO link retires the links taken through it. Where a term has a general and a narrower candidate,
        the general one is the default: the service refuses the narrower one and says why.
      </p>
    </>
  ),
  path: '/terminology-links',
  targetType: 'terminology_link',
  idField: 'link_id',
  caption: 'Candidate links to outside vocabularies',
  searchLabel: 'Search our terms, titles or codes',
  filters: [
    {
      param: 'system',
      label: 'Vocabulary',
      options: ['ICD-11 MMS', 'ICD-11 Foundation', 'MONDO', 'HPO', 'SNOMED CT', 'LOINC', 'ICD-10'].map((value) => ({
        value,
        label: value,
      })),
    },
    {
      param: 'subject_type',
      label: 'Kind of term',
      options: [
        { value: 'disease', label: 'Disease labels' },
        { value: 'feature', label: 'Features' },
      ],
    },
  ],
  titleOf: (item) => `${field(part(item, 'subject'), 'term')} → ${field(item, 'title')}`,
  columns: [
    { heading: 'Our term', cell: (item) => field(part(item, 'subject'), 'term') },
    { heading: 'Vocabulary', cell: (item) => field(item, 'system') },
    { heading: 'Term in the vocabulary', cell: (item) => field(item, 'title') },
    { heading: 'Code', cell: (item) => code(field(item, 'code')) },
    { heading: 'How it was found', cell: (item) => field(item, 'match_method') },
  ],
  details: (item) => {
    const via = part(part(item, 'detail'), 'via');
    const category = part(part(item, 'detail'), 'category_through_mondo');
    return [
      { label: 'Our term', value: `${field(part(item, 'subject'), 'term')} (${field(part(item, 'subject'), 'type')})` },
      { label: 'Vocabulary and version', value: `${field(item, 'system')} · ${field(item, 'system_version')}` },
      { label: 'Term in the vocabulary', value: field(item, 'title') },
      { label: 'Code (reviewers only)', value: code(field(item, 'code')) },
      { label: 'How it was found', value: field(item, 'match_method') },
      {
        label: 'Taken through',
        value: via.link_id ? `MONDO term "${field(via, 'title')}" (${field(via, 'our_match')})` : 'Its own name match',
      },
      {
        label: 'Category this is the unspecified sub-code of',
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
  term_not_linkable: 'The only entry with our name is out of use or of another kind, so it cannot be used',
  no_term_near: 'No entry has this name or a similar one',
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
    detail.score !== undefined ? `Search score ${field(detail, 'score')} out of 1` : '',
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
        { value: 'term_not_linkable', label: 'Entry cannot be used' },
        { value: 'no_term_near', label: 'No similar entry' },
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
    { heading: 'Suggested entry', cell: (item) => field(part(item, 'term'), 'title') || 'No suggestion' },
    { heading: 'Why it was not matched automatically', cell: whyNotMatched },
    { heading: 'Match made', cell: matchMade },
  ],
  details: (item) => {
    const via = part(part(item, 'detail'), 'via');
    const term = part(item, 'term');
    return [
      {
        label: 'Our name',
        value: `${field(part(item, 'subject'), 'term')} (${field(part(item, 'subject'), 'type') === 'disease' ? 'a condition' : 'a symptom or other item'})`,
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
