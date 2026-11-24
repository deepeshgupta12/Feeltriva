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

const RULES: ListScreen = {
  title: 'Urgency rules',
  intro: (
    <p>
      The rules of the stored rule set with their review status. The full text for review, with each rule&rsquo;s reason
      and quoted basis, is in <code>docs/review/urgency_rules_final.md</code>. Once the rule set is approved its rules
      are not decided again until that approval is withdrawn.
    </p>
  ),
  path: '/rules',
  targetType: 'clinical_rule',
  idField: 'rule_id',
  caption: 'Rules of the stored rule set',
  pageSize: 50,
  titleOf: (item) => field(item, 'rule_id'),
  columns: [
    { heading: 'Rule', cell: (item) => field(item, 'rule_id') },
    { heading: 'Level', cell: (item) => field(part(item, 'action'), 'urgency') },
    { heading: 'Text shown', cell: (item) => field(part(item, 'action'), 'text') },
    { heading: 'Decided by', cell: (item) => field(item, 'decided_by') || 'Nobody yet' },
  ],
  details: (item) => [
    { label: 'Rule set', value: field(item, 'bundle_id') },
    { label: 'Level', value: field(part(item, 'action'), 'urgency') },
    { label: 'Text shown to the person', value: field(part(item, 'action'), 'text') },
    { label: 'Order', value: field(item, 'priority') },
    { label: 'Condition', value: code(field(item, 'condition_ast')) },
    { label: 'Last decision note', value: field(item, 'decision_note') || 'None' },
  ],
};

export const LiveDiseaseMappingsPage = () => <LiveListPage screen={DISEASE_MAPPINGS} />;
export const LiveFeatureMappingsPage = () => <LiveListPage screen={featureMappings(false)} />;
export const LiveDataQualityPage = () => <LiveListPage screen={featureMappings(true)} />;
export const LiveVocabularyLinksPage = () => <LiveListPage screen={VOCABULARY_LINKS} />;
export const LiveRulesPage = () => <LiveListPage screen={RULES} />;
