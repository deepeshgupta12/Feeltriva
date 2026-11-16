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

const LEXICAL_METHOD = 'Lexical normalisation (casefold, trim, collapse whitespace)';

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
    conflicts: `Header repeated in ${header.columns.length} columns; values disagree in ${formatCount(header.conflictingRows)} rows`,
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
        ? `${row.spellingsInGroup} source spellings share this lexical group across ${row.sourceFilesInGroup} files; equivalence not reviewed`
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
      label: 'Source archives',
      value: AUDIT_FACTS.sourceArchives,
      detail: `${AUDIT_FACTS.sourceFiles} files audited. Imported datasets, not reviewed knowledge sources.`,
    },
    {
      id: 'lexical_disease_candidates',
      label: 'Lexical disease candidates',
      value: AUDIT_FACTS.lexicalDiseaseCandidates,
      detail: 'Distinct labels after lexical normalisation. Not clinically approved conditions.',
    },
    {
      id: 'repeated_header_names',
      label: 'Repeated header names requiring review',
      value: AUDIT_FACTS.repeatedHeaderNames,
      detail: 'In the archive 16 symptom matrix. Every repeated header has rows where its columns disagree.',
    },
    {
      id: 'shared_profile_signatures',
      label: 'Shared archive-15 train/test profile signatures',
      value: AUDIT_FACTS.sharedArchive15ProfileSignatures,
      detail: 'Profile signatures present in both files, excluding patient ID. Not a count of unique patients.',
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
      proposedAtomicClaim: 'Sample claim: one checkable statement derived from the original wording.',
      applicability: 'Sample applicability: not specified',
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
      proposedAtomicClaim: 'Sample claim: a second placeholder claim.',
      applicability: 'Sample applicability: not specified',
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
  status: 'Demo fixture · not approved',
  isSample: true,
}));

const releases: ReleaseInfo[] = [
  {
    version: DEMO_KNOWLEDGE_RELEASE,
    status: 'draft',
    isSample: true,
    included: [
      {
        label: 'Sources',
        value: `${AUDIT_FACTS.sourceArchives} imported archives audited · 0 approved knowledge sources`,
      },
      {
        label: 'Mappings',
        value: `0 approved · ${formatCount(AUDIT_FACTS.lexicalDiseaseCandidates)} lexical disease candidates and ${formatCount(AUDIT_FACTS.positionalFeatureMappings)} positional feature mappings unreviewed`,
      },
      { label: 'Rules and questions', value: `0 approved · bundle ${DEMO_RULES_VERSION} contains demo fixtures only` },
    ],
    pendingItems: [
      `${AUDIT_FACTS.repeatedHeaderNames} repeated header names need reconciliation`,
      'Lexical disease and feature candidates need semantic review',
      'No evidence items are approved',
      'No clinical rule bundle has been authored or approved',
    ],
    publication: {
      enabled: false,
      reason:
        'Publishing needs a reviewer role enforced by the backend and a completed clinical approval. Neither exists in this demo.',
    },
  },
];

const evaluation: EvaluationSummary = {
  title: 'Research baseline · archive 11 only',
  scope:
    'Experimental classifier scored against dataset labels. It does not measure real diagnoses or the product, and is research-only.',
  verdict: 'Baseline rejected for clinical serving.',
  researchMetrics: [
    { label: 'Test accuracy', value: '15.71%' },
    {
      label: 'Majority-class comparator',
      value: '20.56%',
      note: 'Always predicts the most frequent training label. The baseline does not beat it.',
    },
    { label: 'Top-3 accuracy', value: '39.67%' },
    { label: 'Test labels represented', value: '39 / 46', note: 'Seven labels have no test examples.' },
  ],
  clinicalValidation: [
    { label: 'Clinical accuracy', value: null },
    { label: 'Urgency/triage safety', value: null },
    { label: 'Calibration approved for display', value: null },
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
  lexical_only_unreviewed: 'Lexical only · unreviewed',
  needs_semantic_review: 'Needs semantic review',
  flagged_demo: 'Flagged for reconciliation',
  accepted_demo: 'Marked acceptable',
  rejected_demo: 'Marked rejected',
};
