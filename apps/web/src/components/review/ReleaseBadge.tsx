import type { ReleaseStatus, ReviewStatus } from '@/api/reviewService';
import { StatusBadge, type BadgeTone } from '@/components/ui/StatusBadge';
import { REVIEW_STATUS_LABELS } from '@/fixtures/review';

const RELEASE_LABELS: Record<ReleaseStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Draft · not published', tone: 'neutral' },
  in_review: { label: 'Being checked', tone: 'attention' },
  approved: { label: 'Approved', tone: 'info' },
  published: { label: 'Published', tone: 'info' },
};

/** Release state as an icon-and-text badge. */
export function ReleaseBadge({ status }: { status: ReleaseStatus }) {
  const { label, tone } = RELEASE_LABELS[status];
  return <StatusBadge tone={tone}>{label}</StatusBadge>;
}

const REVIEW_TONES: Record<ReviewStatus, BadgeTone> = {
  lexical_only_unreviewed: 'neutral',
  needs_semantic_review: 'attention',
  flagged_demo: 'attention',
  accepted_demo: 'info',
  rejected_demo: 'urgent',
};

/** Mapping review state. None of these states approves content for live serving. */
export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  return <StatusBadge tone={REVIEW_TONES[status]}>{REVIEW_STATUS_LABELS[status]}</StatusBadge>;
}
