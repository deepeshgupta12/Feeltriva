import { buildReviewFixtures } from '@/fixtures/review';

/**
 * Internal reviewer console data.
 *
 * specs/openapi.json has no review endpoints yet, so this runs on fixtures: real figures
 * from the repository's dataset audit plus clearly synthetic placeholders. Every change
 * made through this service is demo state only. Nothing here approves content for serving.
 */
export type MappingKind = 'disease' | 'feature' | 'data_quality';

/** `lexical_only_unreviewed` and `needs_semantic_review` come from the audit files. */
export type ReviewStatus =
  'lexical_only_unreviewed' | 'needs_semantic_review' | 'flagged_demo' | 'accepted_demo' | 'rejected_demo';

export interface SourceColumn {
  columnIndex: number;
  originalHeader: string;
}

export interface ReviewNote {
  id: string;
  text: string;
  createdAt: string;
}

export interface MappingRow {
  id: string;
  kind: MappingKind;
  /** Archive and file the term came from. */
  source: string;
  /** Source term exactly as imported. */
  originalTerm: string;
  /** Column positions in the source file; empty for label-column values. */
  columns: readonly SourceColumn[];
  proposedCanonicalTerm: string;
  candidateId: string;
  mappingMethod: string;
  reviewStatus: ReviewStatus;
  /** Short description of the conflict, or null when the audit recorded none. */
  conflicts: string | null;
  conflictingRows: number | null;
  /** ISO timestamp; null means no reviewer has looked at this row. */
  lastReviewed: string | null;
  notes: readonly ReviewNote[];
  /** True once a demo action has touched the row in this browser session. */
  demoChanged: boolean;
}

export interface AuditFact {
  id: string;
  label: string;
  value: number;
  detail: string;
}

export interface ReviewOverview {
  facts: readonly AuditFact[];
  normalization: string;
  clinicalDedupStatus: string;
}

export interface EvidenceReviewItem {
  id: string;
  originalStatement: string;
  sourceTitle: string;
  sourceUrl: string | null;
  locator: string;
  proposedAtomicClaim: string;
  applicability: string;
  status: 'draft' | 'needs_review';
  notes: readonly ReviewNote[];
  isSample: boolean;
}

export interface RuleReviewItem {
  id: string;
  kind: 'question' | 'rule';
  wording: string;
  answerType: string;
  status: string;
  isSample: boolean;
}

export type ReleaseStatus = 'draft' | 'in_review' | 'approved' | 'published';

export interface ReleaseInfo {
  version: string;
  status: ReleaseStatus;
  isSample: boolean;
  included: readonly { label: string; value: string }[];
  pendingItems: readonly string[];
  publication: { enabled: boolean; reason: string };
}

export interface EvaluationMetric {
  label: string;
  /** Formatted value, or null when the measurement does not exist ("Not evaluated"). */
  value: string | null;
  note?: string;
}

export interface EvaluationSummary {
  title: string;
  scope: string;
  verdict: string;
  researchMetrics: readonly EvaluationMetric[];
  clinicalValidation: readonly EvaluationMetric[];
}

export interface ReviewService {
  getOverview(): Promise<ReviewOverview>;
  listMappings(kind: MappingKind): Promise<MappingRow[]>;
  saveNote(rowId: string, text: string): Promise<MappingRow>;
  setStatus(rowId: string, status: ReviewStatus): Promise<MappingRow>;
  listEvidence(): Promise<EvidenceReviewItem[]>;
  saveEvidenceNote(evidenceId: string, text: string): Promise<EvidenceReviewItem>;
  listRules(): Promise<RuleReviewItem[]>;
  listReleases(): Promise<ReleaseInfo[]>;
  getEvaluation(): Promise<EvaluationSummary>;
}

/** In-memory implementation. State resets on reload. */
export class FixtureReviewService implements ReviewService {
  private readonly data = buildReviewFixtures();
  private readonly now: () => Date;
  private noteCounter = 0;

  constructor(options: { now?: () => Date } = {}) {
    this.now = options.now ?? (() => new Date());
  }

  getOverview(): Promise<ReviewOverview> {
    return Promise.resolve(structuredClone(this.data.overview));
  }

  listMappings(kind: MappingKind): Promise<MappingRow[]> {
    return Promise.resolve(structuredClone(this.data.mappings.filter((row) => row.kind === kind)));
  }

  saveNote(rowId: string, text: string): Promise<MappingRow> {
    const row = this.requireRow(rowId);
    const trimmed = text.trim();
    if (trimmed.length === 0) {
      return Promise.reject(new Error('A note cannot be empty.'));
    }
    row.notes = [...row.notes, this.createNote(trimmed)];
    row.demoChanged = true;
    return Promise.resolve(structuredClone(row));
  }

  setStatus(rowId: string, status: ReviewStatus): Promise<MappingRow> {
    const row = this.requireRow(rowId);
    row.reviewStatus = status;
    row.lastReviewed = this.now().toISOString();
    row.demoChanged = true;
    return Promise.resolve(structuredClone(row));
  }

  listEvidence(): Promise<EvidenceReviewItem[]> {
    return Promise.resolve(structuredClone(this.data.evidence));
  }

  saveEvidenceNote(evidenceId: string, text: string): Promise<EvidenceReviewItem> {
    const item = this.data.evidence.find((entry) => entry.id === evidenceId);
    const trimmed = text.trim();
    if (!item) {
      return Promise.reject(new Error('Evidence item not found.'));
    }
    if (trimmed.length === 0) {
      return Promise.reject(new Error('A note cannot be empty.'));
    }
    item.notes = [...item.notes, this.createNote(trimmed)];
    return Promise.resolve(structuredClone(item));
  }

  listRules(): Promise<RuleReviewItem[]> {
    return Promise.resolve(structuredClone(this.data.rules));
  }

  listReleases(): Promise<ReleaseInfo[]> {
    return Promise.resolve(structuredClone(this.data.releases));
  }

  getEvaluation(): Promise<EvaluationSummary> {
    return Promise.resolve(structuredClone(this.data.evaluation));
  }

  private requireRow(rowId: string): MappingRow {
    const row = this.data.mappings.find((entry) => entry.id === rowId);
    if (!row) {
      throw new Error('Mapping row not found.');
    }
    return row;
  }

  private createNote(text: string): ReviewNote {
    this.noteCounter += 1;
    return { id: `demo-note-${this.noteCounter}`, text, createdAt: this.now().toISOString() };
  }
}
