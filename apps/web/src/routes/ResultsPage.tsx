import { ArrowRight, FileText, Pencil, WifiOff } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useParams } from 'react-router';

import { parseSessionState, type Assessment, type Session } from '@/api/types';
import { ContextPanel } from '@/components/ContextPanel';
import { EvidenceDrawer } from '@/components/EvidenceDrawer';
import { NextActionCard } from '@/components/NextActionCard';
import { PageHeading } from '@/components/PageHeading';
import { PossibilityCard } from '@/components/PossibilityCard';
import { SessionGate } from '@/components/SessionGate';
import { SourceList } from '@/components/SourceList';
import { StatusPanel } from '@/components/StatusPanel';
import { UncertaintyPanel } from '@/components/UncertaintyPanel';
import { Button, ButtonLink } from '@/components/ui/Button';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { SampleTag, StatusBadge } from '@/components/ui/StatusBadge';
import { cn } from '@/lib/cn';
import { errorCopy, errorReference } from '@/lib/errorCopy';
import type { AssessmentController, AssessmentViewState } from '@/state/AssessmentController';
import { useDemo } from '@/state/demo';
import { useAssessment, useOnlineStatus, usePageMeta } from '@/state/hooks';
import {
  currentObservations,
  isAssessmentStale,
  selectCandidates,
  urgencyPresentation,
  type CandidateView,
} from '@/state/selectors';

export function ResultsPage() {
  usePageMeta('Your result', { noindex: true });
  const { sessionId = '' } = useParams();
  const { controller, state } = useAssessment(sessionId);

  return (
    <SessionGate state={state} controller={controller}>
      {(session) => <Results key={sessionId} session={session} state={state} controller={controller} />}
    </SessionGate>
  );
}

interface SectionProps {
  id: string;
  title: string;
  children: ReactNode;
  /**
   * The section shows an earlier result that no longer matches the user's details. It is
   * labelled in words as well as de-emphasised, so staleness is never colour-only.
   */
  stale?: boolean;
}

function Section({ id, title, children, stale = false }: SectionProps) {
  return (
    <section aria-labelledby={id}>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 id={id} className="font-display text-[1.375rem] font-bold text-ink">
          {title}
        </h2>
        {stale ? <StatusBadge tone="attention">Earlier result · needs updating</StatusBadge> : null}
      </div>
      <div className={cn(stale && 'opacity-70')}>{children}</div>
    </section>
  );
}

interface ResultsProps {
  session: Session;
  state: AssessmentViewState;
  controller: AssessmentController;
}

function Results({ session, state, controller }: ResultsProps) {
  const online = useOnlineStatus();
  const sessionId = session.session_id;
  const flow = parseSessionState(session.state);
  const assessment = state.assessment;
  const stale = isAssessmentStale(session, assessment);
  const assessing = state.pending.includes('assess');
  const assessFailure = state.failure?.op === 'assess' ? state.failure.error : null;
  const nothingToAssess = flow === 'intake';

  // Opening this page is the request for a result: ask once per observation version.
  // A failed request is not repeated automatically.
  const requestedVersion = useRef<number | null>(null);
  useEffect(() => {
    if (assessment || nothingToAssess || state.failure || state.pending.length > 0) {
      return;
    }
    if (requestedVersion.current === session.observation_version) {
      return;
    }
    requestedVersion.current = session.observation_version;
    void controller.assess();
  }, [assessment, nothingToAssess, state.failure, state.pending.length, session.observation_version, controller]);

  const correctDetailsLink = (
    <ButtonLink
      to={`/assess/${sessionId}`}
      variant="secondary"
      icon={<Pencil aria-hidden="true" className="size-4 shrink-0" />}
    >
      Add or correct details
    </ButtonLink>
  );

  const understood = (
    <Section id="understood-heading" title="What we understood">
      <div className="rounded-card border border-line bg-surface p-5 sm:p-6">
        <ContextPanel
          observations={currentObservations(session)}
          busy={controller.isMutating()}
          error={state.failure?.op === 'observation' ? state.failure.error : null}
          onConfirm={(id) => controller.confirmObservation(id)}
          onRevise={(id, revision) => controller.reviseObservation(id, revision)}
          showTitle={false}
          headingLevel="h3"
          optionLabels={state.optionLabels}
        />
        <div className="mt-5">{correctDetailsLink}</div>
      </div>
    </Section>
  );

  const summarySection = (
    <Section id="summary-heading" title="Your consultation summary">
      <div className="rounded-card border border-line bg-surface p-5 sm:p-6">
        <p className="text-ink-secondary">
          A summary of what you shared, to review and then print or copy for a consultation. Nothing is sent anywhere
          automatically.
        </p>
        <div className="mt-4">
          <ButtonLink
            to={`/summary/${sessionId}`}
            variant="secondary"
            icon={<FileText aria-hidden="true" className="size-4 shrink-0" />}
          >
            Preview consultation summary
          </ButtonLink>
        </div>
      </div>
    </Section>
  );

  let body: ReactNode;
  if (nothingToAssess) {
    body = (
      <StatusPanel
        title="There’s nothing to assess yet"
        actions={<ButtonLink to={`/assess/${sessionId}`}>Describe how you’re feeling</ButtonLink>}
      >
        <p>A result can be prepared once you’ve shared some details.</p>
      </StatusPanel>
    );
  } else if (!assessment && assessFailure) {
    const copy = errorCopy(assessFailure);
    const reference = errorReference(assessFailure);
    body = (
      <>
        <StatusPanel
          tone="attention"
          title={assessFailure.kind === 'unavailable' ? 'We couldn’t complete this assessment' : copy.title}
          announce="status"
          actions={
            <>
              <Button onClick={() => void controller.assess()} loading={assessing} loadingLabel="Trying again…">
                Try again
              </Button>
              <ButtonLink to={`/summary/${sessionId}`} variant="secondary">
                View consultation summary
              </ButtonLink>
              {correctDetailsLink}
            </>
          }
        >
          <p>{copy.message}</p>
          <p>No result is shown, and none is being guessed in its place.</p>
          {reference ? <p className="text-sm">{reference}</p> : null}
        </StatusPanel>
        {understood}
      </>
    );
  } else if (!assessment) {
    body = (
      <div className="space-y-4" aria-busy="true">
        <p role="status" className="text-ink-secondary">
          Preparing your result…
        </p>
        <SkeletonCard />
        <SkeletonCard lines={4} />
      </div>
    );
  } else {
    body = (
      <ResultBody
        session={session}
        assessment={assessment}
        stale={stale}
        assessing={assessing}
        refreshFailure={assessFailure ? errorCopy(assessFailure).message : null}
        onRefresh={() => void controller.assess()}
        understood={understood}
        summarySection={summarySection}
        correctDetailsLink={correctDetailsLink}
      />
    );
  }

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-6 sm:px-6 sm:py-10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <PageHeading>Your result</PageHeading>
          <p className="mt-1 text-ink-secondary">
            Provisional, based on the details you’ve shared. It is not a diagnosis.
          </p>
        </div>
        <SampleTag>Design demo · Sample result</SampleTag>
      </div>

      <div className="mt-6 space-y-8">
        {!online ? (
          <StatusPanel
            tone="attention"
            title="You’re offline"
            announce="status"
            icon={<WifiOff aria-hidden="true" className="size-6" />}
            actions={
              <Button
                variant="secondary"
                onClick={() => void controller.refresh()}
                loading={state.pending.includes('refresh')}
                loadingLabel="Reconnecting…"
              >
                Try to reconnect
              </Button>
            }
          >
            <p>Results can’t be requested or updated until you’re back online. Your saved details haven’t changed.</p>
          </StatusPanel>
        ) : null}
        {body}
      </div>
    </div>
  );
}

interface ResultBodyProps {
  session: Session;
  assessment: Assessment;
  stale: boolean;
  assessing: boolean;
  refreshFailure: string | null;
  onRefresh: () => void;
  understood: ReactNode;
  summarySection: ReactNode;
  correctDetailsLink: ReactNode;
}

/**
 * The result itself, in the required order: what to do next, what we understood, possible
 * explanations, what is still uncertain, the consultation summary, then sources.
 */
function ResultBody({
  session,
  assessment,
  stale,
  assessing,
  refreshFailure,
  onRefresh,
  understood,
  summarySection,
  correctDetailsLink,
}: ResultBodyProps) {
  const { reviewerPreview } = useDemo();
  const [evidenceFor, setEvidenceFor] = useState<CandidateView | null>(null);
  const sessionId = session.session_id;
  const status = assessment.status;
  const selection = selectCandidates(assessment, session);
  const nextAction = assessment.next_action;

  const staleBanner = stale ? (
    <StatusPanel
      tone="attention"
      title="This result needs updating"
      announce="status"
      actions={
        <>
          <Button onClick={onRefresh} loading={assessing} loadingLabel="Updating your result…">
            Update result
          </Button>
          {correctDetailsLink}
        </>
      }
    >
      <p>
        Your details changed after this result was prepared, so it no longer reflects what you’ve shared. It is shown
        below for reference only.
      </p>
      {refreshFailure ? (
        <p role="alert" className="font-medium text-urgent">
          The update didn’t complete. {refreshFailure}
        </p>
      ) : null}
    </StatusPanel>
  ) : null;

  const summaryAction = (
    <ButtonLink to={`/summary/${sessionId}`} icon={<FileText aria-hidden="true" className="size-4 shrink-0" />}>
      Prepare consultation summary
    </ButtonLink>
  );
  const continueAction = (
    <ButtonLink to={`/assess/${sessionId}`} icon={<ArrowRight aria-hidden="true" className="size-4 shrink-0" />}>
      Answer the next question
    </ButtonLink>
  );

  /** The single primary action for "What to do next", chosen by the service's action type. */
  const primaryAction = (() => {
    switch (nextAction.type) {
      case 'ask_question':
        return continueAction;
      case 'retry':
        return (
          <Button onClick={onRefresh} loading={assessing} loadingLabel="Trying again…">
            Try again
          </Button>
        );
      case 'seek_care':
      case 'show_summary':
        return summaryAction;
    }
  })();

  if (status === 'system_unavailable') {
    return (
      <>
        <StatusPanel
          tone="attention"
          title="We couldn’t complete this assessment"
          announce="status"
          actions={
            <>
              <Button onClick={onRefresh} loading={assessing} loadingLabel="Trying again…">
                Try again
              </Button>
              <ButtonLink to={`/summary/${sessionId}`} variant="secondary">
                View consultation summary
              </ButtonLink>
            </>
          }
        >
          <p>{nextAction.text}</p>
          <p>No result is shown, and none is being guessed in its place.</p>
        </StatusPanel>
        {understood}
      </>
    );
  }

  if (status === 'urgent_handoff') {
    const urgency = urgencyPresentation(assessment.urgency);
    return (
      <>
        {staleBanner}
        <Section id="next-heading" title="What to do next" stale={stale}>
          {/* Announced once when it appears; nothing below it competes for attention. */}
          <StatusPanel
            tone="urgent"
            title="This needs urgent attention"
            announce={stale ? 'none' : 'alert'}
            headingLevel="h3"
            eyebrow={
              <>
                <StatusBadge tone="urgent">Urgent-state preview</StatusBadge>
                <StatusBadge tone={urgency.tone}>{urgency.label}</StatusBadge>
                <SampleTag>Sample action text</SampleTag>
              </>
            }
            actions={stale ? undefined : summaryAction}
          >
            <p className="text-lg font-medium text-ink">{nextAction.text}</p>
            <p>Routine questions are paused. No possible explanations are shown for this assessment.</p>
          </StatusPanel>
        </Section>
        {understood}
        {summarySection}
      </>
    );
  }

  if (status === 'out_of_scope') {
    return (
      <>
        {staleBanner}
        <Section id="next-heading" title="What to do next" stale={stale}>
          <StatusPanel
            tone="attention"
            title="This is outside what Feeltriva can help with"
            headingLevel="h3"
            announce="status"
            eyebrow={<SampleTag>Sample limitation</SampleTag>}
            actions={stale ? undefined : summaryAction}
          >
            <p className="text-ink">{nextAction.text}</p>
            <p>No possible explanations are shown. What you shared is still available as a summary.</p>
          </StatusPanel>
        </Section>
        {understood}
        <Section id="uncertain-heading" title="What is still uncertain" stale={stale}>
          <UncertaintyPanel unknowns={assessment.unknowns} />
        </Section>
        {summarySection}
      </>
    );
  }

  const incomplete = status === 'insufficient_information' || status === 'needs_clarification';

  return (
    <>
      {staleBanner}
      <Section id="next-heading" title="What to do next" stale={stale}>
        {incomplete ? (
          <p className="mb-3 rounded-control border border-attention/30 bg-attention-soft px-4 py-3 font-medium text-attention">
            There isn’t enough information yet to suggest an explanation. This is an incomplete result, not a reassuring
            one.
          </p>
        ) : null}
        <NextActionCard
          assessment={assessment}
          stale={stale}
          action={primaryAction}
          secondaryAction={
            nextAction.type === 'ask_question' ? (
              <ButtonLink to={`/summary/${sessionId}`} variant="secondary">
                View consultation summary
              </ButtonLink>
            ) : (
              correctDetailsLink
            )
          }
        />
      </Section>

      {understood}

      <Section id="explanations-heading" title="Possible explanations" stale={stale}>
        {incomplete ? (
          <p className="rounded-card border border-line bg-surface p-5 text-ink-secondary">
            None are shown, because there isn’t enough information to support one.
          </p>
        ) : selection.shown.length > 0 ? (
          <div className="space-y-4">
            <p className="text-ink-secondary">
              These are possibilities to discuss with a health professional. They are not a diagnosis, and no likelihood
              is implied.
            </p>
            {selection.shown.map((view) => (
              <PossibilityCard
                key={view.candidate.disease_id}
                view={view}
                stale={stale}
                onViewEvidence={() => setEvidenceFor(view)}
              />
            ))}
            {selection.withheld > 0 ? (
              <p className="rounded-card border border-attention/30 bg-attention-soft p-5 text-attention">
                {selection.withheld === 1
                  ? 'One further explanation was'
                  : `${selection.withheld} further explanations were`}{' '}
                withheld because supporting information wasn’t available.
              </p>
            ) : null}
          </div>
        ) : selection.withheld > 0 ? (
          <StatusPanel tone="attention" title="Incomplete result" headingLevel="h3">
            <p>
              {selection.withheld === 1
                ? 'A possible explanation was'
                : `${selection.withheld} possible explanations were`}{' '}
              withheld because the supporting information for it wasn’t available. Feeltriva doesn’t show an explanation
              it can’t support.
            </p>
          </StatusPanel>
        ) : (
          <p className="rounded-card border border-line bg-surface p-5 text-ink-secondary">
            The assessment didn’t identify a possible explanation to show for these details.
          </p>
        )}
      </Section>

      <Section id="uncertain-heading" title="What is still uncertain" stale={stale}>
        <UncertaintyPanel unknowns={assessment.unknowns} withheld={selection.withheld} />
      </Section>

      {summarySection}

      <Section id="sources-heading" title="Sources" stale={stale}>
        <SourceList evidence={assessment.evidence} showInternalDetail={reviewerPreview} />
        {reviewerPreview ? (
          <p className="mt-3 text-sm text-ink-secondary">
            Internal detail · knowledge <code>{assessment.versions.knowledge ?? 'none'}</code> · rules{' '}
            <code>{assessment.versions.rules ?? 'none'}</code> · model{' '}
            <code>{assessment.versions.model ?? 'none'}</code> · prompt{' '}
            <code>{assessment.versions.prompt ?? 'none'}</code>
          </p>
        ) : null}
      </Section>
      <EvidenceDrawer view={evidenceFor} onClose={() => setEvidenceFor(null)} showInternalDetail={reviewerPreview} />
    </>
  );
}
