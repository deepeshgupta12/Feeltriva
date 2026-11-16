import { ArrowLeft } from 'lucide-react';
import type { ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router';

import { PageHeading } from '@/components/PageHeading';
import { SourceList } from '@/components/SourceList';
import { StatusPanel } from '@/components/StatusPanel';
import { Button, ButtonLink } from '@/components/ui/Button';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { SampleTag } from '@/components/ui/StatusBadge';
import { INTENDED_USE_STATEMENT } from '@/components/UncertaintyPanel';
import { useAsync } from '@/lib/useAsync';
import { useDemo } from '@/state/demo';
import { usePageMeta } from '@/state/hooks';
import { useServices } from '@/state/services';

function InfoSection({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <h2 id={id} className="font-display text-xl font-bold text-ink">
        {title}
      </h2>
      <div className="mt-2 text-ink-secondary">{children}</div>
    </section>
  );
}

function BulletList({ items }: { items: readonly string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item, index) => (
        <li key={`${item}-${index}`}>{item}</li>
      ))}
    </ul>
  );
}

/**
 * Reviewed condition information reached from a result or source link. A section is shown
 * only when reviewed content exists for it; missing sections are hidden, never filled in.
 * There is no dosing, no promise of cure and no purchase or referral action.
 */
export function ConditionPage() {
  usePageMeta('Condition information', { noindex: true });
  const { diseaseId = '' } = useParams();
  const navigate = useNavigate();
  const { conditions } = useServices();
  const { reviewerPreview } = useDemo();
  const { state, reload } = useAsync(`condition:${diseaseId}`, () => conditions.getCondition(diseaseId));

  const back = (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => void navigate(-1)}
      icon={<ArrowLeft aria-hidden="true" className="size-4 shrink-0" />}
    >
      Back
    </Button>
  );

  if (state.status === 'loading') {
    return (
      <div className="mx-auto w-full max-w-[860px] space-y-4 px-4 py-6 sm:px-6 sm:py-10" aria-busy="true">
        <h1 tabIndex={-1} className="sr-only">
          Loading condition information
        </h1>
        <p role="status" className="text-ink-secondary">
          Loading information…
        </p>
        <SkeletonCard />
        <SkeletonCard lines={4} />
      </div>
    );
  }

  if (state.status === 'failed') {
    return (
      <div className="mx-auto w-full max-w-[760px] px-4 py-8 sm:px-6">
        <StatusPanel
          tone="attention"
          title="We couldn’t load this information"
          headingLevel="h1"
          announce="status"
          actions={
            <>
              <Button onClick={reload}>Try again</Button>
              {back}
            </>
          }
        >
          <p>Please try again.</p>
        </StatusPanel>
      </div>
    );
  }

  const condition = state.data;
  if (!condition) {
    return (
      <div className="mx-auto w-full max-w-[760px] px-4 py-8 sm:px-6">
        <StatusPanel
          title="No reviewed information is available"
          headingLevel="h1"
          actions={
            <>
              {back}
              <ButtonLink to="/history" variant="secondary">
                Saved summaries
              </ButtonLink>
            </>
          }
        >
          <p>
            There is no reviewed information for this condition yet, so nothing is shown rather than an unreviewed
            description.
          </p>
        </StatusPanel>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-6 sm:px-6 sm:py-10">
      <div className="mb-3">{back}</div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">Condition information</p>
          <PageHeading>{condition.name}</PageHeading>
        </div>
        {condition.is_sample ? <SampleTag>Design demo · Placeholder content</SampleTag> : null}
      </div>

      {condition.is_sample ? (
        <p className="mt-4 rounded-card border border-attention/30 bg-attention-soft p-4 text-attention">
          This page shows the layout only. Every section below is labelled placeholder text and does not describe a real
          condition.
        </p>
      ) : null}

      <div className="mt-6 space-y-4">
        {condition.overview ? (
          <InfoSection id="overview-heading" title="Overview">
            <p>{condition.overview}</p>
          </InfoSection>
        ) : null}
        {condition.symptoms?.length ? (
          <InfoSection id="symptoms-heading" title="Symptoms">
            <BulletList items={condition.symptoms} />
          </InfoSection>
        ) : null}
        {condition.causes?.length ? (
          <InfoSection id="causes-heading" title="Causes and risk context">
            <BulletList items={condition.causes} />
          </InfoSection>
        ) : null}
        {condition.management?.length ? (
          <InfoSection id="management-heading" title="Management information">
            <BulletList items={condition.management} />
            <p className="mt-3 text-sm">
              General educational information linked to its sources. It is not personal treatment advice and does not
              include doses.
            </p>
          </InfoSection>
        ) : null}
        {condition.questions_for_clinician?.length ? (
          <InfoSection id="questions-heading" title="Questions to ask a clinician">
            <BulletList items={condition.questions_for_clinician} />
          </InfoSection>
        ) : null}
        <InfoSection id="condition-sources-heading" title="Sources">
          <SourceList evidence={condition.sources} showInternalDetail={reviewerPreview} />
        </InfoSection>
        <p className="text-ink-secondary">{INTENDED_USE_STATEMENT}</p>
      </div>
    </div>
  );
}
