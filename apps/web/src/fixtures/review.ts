/**
 * Reviewer console fixtures.
 *
 * Two kinds of data, kept visibly apart:
 * - Imported dataset audit: real figures generated from data_audit/ (see
 *   reviewAudit.generated.ts). Lexical candidates only; nothing is clinically approved.
 * - Synthetic placeholders (evidence, questions, release): marked `isSample`.
 *
 * The research baseline figures are the measured archive-11 values from
 * docs/02_MEASURED_RESULTS.md. They are research-only and must never be shown to patients.
 */
import type {
  EvaluationSummary,
  EvidenceReviewItem,
  MappingRow,
  ReleaseInfo,
  ReviewOverview,
  ReviewStatus,
  RuleReviewItem,
} from '@/api/reviewService';
import { formatCount } from '@/lib/format';

import { AUDIT_FACTS, DISEASE_MAPPING_SAMPLE, FEATURE_MAPPING_SAMPLE, REPEATED_HEADERS } from './reviewAudit.generated';
import { DEMO_KNOWLEDGE_RELEASE, DEMO_RULES_VERSION, SAMPLE_QUESTIONS } from './sampleContent';

type Mutable<T> = { -readonly [K in keyof T]: T[K] };

export interface ReviewFixtures {
  overview: ReviewOverview;
  mappings: Mutable<MappingRow>[];
  evidence: Mutable<EvidenceReviewItem>[];
  rules: RuleReviewItem[];
  releases: ReleaseInfo[];
  evaluation: EvaluationSummary;
}

const LEXICAL_METHOD = 'Same spelling, ignoring capital letters and extra spaces';

function buildMappings(): Mutable<MappingRow>[] {
  const dataQuality: Mutable<MappingRow>[] = REPEATED_HEADERS.map((header) => ({
    id: `dq:${header.candidateFeatureId}`,
    kind: 'data_quality',
    source: AUDIT_FACTS.repeatedHeaderFile,
    originalTerm: [...new Set(header.columns.map((column) => column.originalHeader))].join(' / '),
    columns: header.columns.map((column) => ({ ...column })),
    proposedCanonicalTerm: header.candidateTerm,
    candidateId: header.candidateFeatureId,
    mappingMethod: LEXICAL_METHOD,
    reviewStatus: header.mappingStatus,
    conflicts: `The heading appears in ${header.columns.length} columns; their values disagree in ${formatCount(header.conflictingRows)} rows`,
    conflictingRows: header.conflictingRows,
    lastReviewed: null,
    notes: [],
    demoChanged: false,
  }));

  const features: Mutable<MappingRow>[] = FEATURE_MAPPING_SAMPLE.map((row) => ({
    id: `feature:${row.archive}:${row.file}:${row.columnIndex}`,
    kind: 'feature',
    source: `${row.archive} / ${row.file}`,
    originalTerm: row.originalHeader,
    columns: [{ columnIndex: row.columnIndex, originalHeader: row.originalHeader }],
    proposedCanonicalTerm: row.candidateTerm,
    candidateId: row.candidateFeatureId,
    mappingMethod: LEXICAL_METHOD,
    reviewStatus: row.mappingStatus,
    conflicts: null,
    conflictingRows: null,
    lastReviewed: null,
    notes: [],
    demoChanged: false,
  }));

  const diseases: Mutable<MappingRow>[] = DISEASE_MAPPING_SAMPLE.map((row) => ({
    id: `disease:${row.archive}:${row.file}:${row.sourceLabel}`,
    kind: 'disease',
    source: `${row.archive} / ${row.file}`,
    originalTerm: row.sourceLabel,
    columns: [],
    proposedCanonicalTerm: row.normalizedLabel,
    candidateId: row.candidateDiseaseId,
    mappingMethod: LEXICAL_METHOD,
    reviewStatus: row.mappingStatus,
    conflicts:
      row.spellingsInGroup > 1
        ? `${row.spellingsInGroup} spellings from ${row.sourceFilesInGroup} files are in this group; nobody has checked that they mean the same`
        : null,
    conflictingRows: null,
    lastReviewed: null,
    notes: [],
    demoChanged: false,
  }));

  return [...dataQuality, ...features, ...diseases];
}

const overview: ReviewOverview = {
  facts: [
    {
      id: 'source_archives',
      label: 'Data archives received',
      value: AUDIT_FACTS.sourceArchives,
      detail: `${AUDIT_FACTS.sourceFiles} files checked. These are data sets that were handed over, not reviewed medical knowledge.`,
    },
    {
      id: 'lexical_disease_candidates',
      label: 'Different condition names',
      value: AUDIT_FACTS.lexicalDiseaseCandidates,
      detail:
        'Names that still differ once capital letters and extra spaces are ignored. Not clinically approved conditions.',
    },
    {
      id: 'repeated_header_names',
      label: 'Column headings that appear more than once',
      value: AUDIT_FACTS.repeatedHeaderNames,
      detail:
        'In the symptom table of archive 16. For every one of them there are rows in which the repeated columns disagree.',
    },
    {
      id: 'shared_profile_signatures',
      label: 'Answer patterns found in both files of archive 15',
      value: AUDIT_FACTS.sharedArchive15ProfileSignatures,
      detail:
        'The same set of answers appears in the training file and in the test file, leaving the patient number aside. Not a count of unique patients.',
    },
  ],
  normalization: AUDIT_FACTS.normalization,
  clinicalDedupStatus: AUDIT_FACTS.clinicalDedupStatus,
};

function buildEvidence(): Mutable<EvidenceReviewItem>[] {
  return [
    {
      id: 'evr.sample_1',
      originalStatement: 'Sample statement. The original wording from a reviewed source would be shown here.',
      sourceTitle: 'Sample source A (placeholder)',
      sourceUrl: 'https://example.org/feeltriva-sample-source-a',
      locator: 'Sample locator: section 2, paragraph 3',
      proposedAtomicClaim: 'Sample point: one statement that can be checked, taken from the original wording.',
      applicability: 'Sample: for whom or when it holds is not stated',
      status: 'needs_review',
      notes: [],
      isSample: true,
    },
    {
      id: 'evr.sample_2',
      originalStatement: 'Sample statement for a second evidence item that has no link.',
      sourceTitle: 'Sample source B (placeholder, no link supplied)',
      sourceUrl: null,
      locator: 'Sample locator: page 4',
      proposedAtomicClaim: 'Sample point: a second placeholder.',
      applicability: 'Sample: for whom or when it holds is not stated',
      status: 'draft',
      notes: [],
      isSample: true,
    },
  ];
}

const rules: RuleReviewItem[] = Object.values(SAMPLE_QUESTIONS).map((question) => ({
  id: question.question_id,
  kind: 'question',
  wording: question.wording,
  answerType: question.answer_schema.type,
  status: 'Sample · not approved',
  isSample: true,
}));

const releases: ReleaseInfo[] = [
  {
    version: DEMO_KNOWLEDGE_RELEASE,
    status: 'draft',
    isSample: true,
    included: [
      {
        label: 'Data sources',
        value: `${AUDIT_FACTS.sourceArchives} data archives checked · 0 approved sources of medical knowledge`,
      },
      {
        label: 'Names',
        value: `0 approved · ${formatCount(AUDIT_FACTS.lexicalDiseaseCandidates)} condition names grouped by spelling and ${formatCount(AUDIT_FACTS.positionalFeatureMappings)} columns with a suggested name, none checked`,
      },
      { label: 'Rules and questions', value: `0 approved · the set ${DEMO_RULES_VERSION} holds samples only` },
    ],
    pendingItems: [
      `${AUDIT_FACTS.repeatedHeaderNames} column headings that appear more than once need sorting out`,
      'The grouped condition names and the suggested column names need their meaning checked',
      'No texts or facts are approved',
      'No set of clinical rules has been written or approved',
    ],
    publication: {
      enabled: false,
      reason:
        'Publishing needs a reviewer permission that the service itself checks, and a completed approval by clinicians. Neither exists in this demo.',
    },
  },
];

const evaluation: EvaluationSummary = {
  title: 'Research test of a trial model · archive 11 only',
  scope:
    'A trial model was scored against the labels in the data set. That measures neither real diagnoses nor this product. For research only.',
  verdict: 'Baseline rejected for clinical serving. In plain words: the trial model must not be used for patients.',
  researchMetrics: [
    { label: 'Right answers on the test rows', value: '15.71%' },
    {
      label: 'Always answering with the most common label',
      value: '20.56%',
      note: 'What one gets without any model, by always giving the most frequent label. The trial model does worse.',
    },
    { label: 'Right answer among its three best guesses', value: '39.67%' },
    { label: 'Labels that have test rows', value: '39 / 46', note: 'Seven labels have no test rows.' },
  ],
  clinicalValidation: [
    { label: 'Accuracy checked by clinicians', value: null },
    { label: 'Safety of the urgency advice', value: null },
    { label: 'Certainty figures approved for showing', value: null },
  ],
};

/** Fresh, mutable copies for one FixtureReviewService instance. */
export function buildReviewFixtures(): ReviewFixtures {
  return {
    overview,
    mappings: buildMappings(),
    evidence: buildEvidence(),
    rules,
    releases,
    evaluation,
  };
}

export const REVIEW_STATUS_LABELS: Record<ReviewStatus, string> = {
  lexical_only_unreviewed: 'Grouped by spelling only · not checked',
  needs_semantic_review: 'Meaning needs checking',
  flagged_demo: 'Marked: needs sorting out',
  accepted_demo: 'Marked acceptable',
  rejected_demo: 'Marked rejected',
};
