import { Copy, Pencil, Printer, Share2 } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router';

import type { Session } from '@/api/types';
import { PageHeading } from '@/components/PageHeading';
import { SessionGate } from '@/components/SessionGate';
import { StatusPanel } from '@/components/StatusPanel';
import { SummaryPreview } from '@/components/SummaryPreview';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { SkeletonCard } from '@/components/ui/Skeleton';
import { SampleTag, StatusBadge } from '@/components/ui/StatusBadge';
import { errorCopy, errorReference } from '@/lib/errorCopy';
import { buildSummaryModel, summaryToPlainText } from '@/lib/summaryModel';
import type { AssessmentController, AssessmentViewState } from '@/state/AssessmentController';
import { useAssessment, usePageMeta } from '@/state/hooks';
import { isAssessmentStale } from '@/state/selectors';

export function SummaryPage() {
  // Generic title only: no symptoms in the title, URL query, analytics or metadata.
  usePageMeta('Consultation summary', { noindex: true });
  const { sessionId = '' } = useParams();
  const { controller, state } = useAssessment(sessionId);

  return (
    <SessionGate state={state} controller={controller}>
      {(session) => <SummaryView key={sessionId} session={session} state={state} controller={controller} />}
    </SessionGate>
  );
}

interface SummaryViewProps {
  session: Session;
  state: AssessmentViewState;
  controller: AssessmentController;
}

const UNAVAILABLE_SHARE_OPTIONS = [
  { label: 'Email it to myself or someone else', reason: 'Not available in this demo. Nothing is emailed.' },
  { label: 'Send to a clinic or health professional', reason: 'Not available. No clinic integration exists yet.' },
  {
    label: 'Create a shareable link',
    reason: 'Not available. Feeltriva does not create public links to health information.',
  },
] as const;

function SummaryView({ session, state, controller }: SummaryViewProps) {
  const id = useId();
  const sessionId = session.session_id;
  const [generatedAt] = useState(() => new Date());
  const [reviewed, setReviewed] = useState(false);
  const [reviewPrompt, setReviewPrompt] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [manualCopyOpen, setManualCopyOpen] = useState(false);

  const stale = isAssessmentStale(session, state.assessment);
  const summaryIsCurrent = state.summary !== null && state.summary.observation_version === session.observation_version;
  const preparing = state.pending.includes('summary');
  const summaryFailure = state.failure?.op === 'summary' ? state.failure.error : null;

  // Ask the service for the summary once per observation version; never retry automatically.
  const requestedVersion = useRef<number | null>(null);
  useEffect(() => {
    if (summaryIsCurrent || preparing || summaryFailure) {
      return;
    }
    if (requestedVersion.current === session.observation_version) {
      return;
    }
    requestedVersion.current = session.observation_version;
    void controller.createSummary();
  }, [summaryIsCurrent, preparing, summaryFailure, session.observation_version, controller]);

  const model = useMemo(
    () =>
      buildSummaryModel({
        session,
        assessment: state.assessment,
        assessmentIsStale: stale,
        summary: state.summary,
        transcript: state.transcript,
        generatedAt,
      }),
    [session, state.assessment, stale, state.summary, state.transcript, generatedAt],
  );

  /**
   * Exports only ever run from an explicit click, after the review acknowledgement.
   * Pressing an export button before acknowledging explains what is needed, the same way
   * the other forms validate on submit.
   */
  const guardExport = (): boolean => {
    if (!summaryIsCurrent) {
      return false;
    }
    if (!reviewed) {
      setReviewPrompt(true);
      return false;
    }
    return true;
  };

  const handlePrint = () => {
    if (guardExport()) {
      window.print();
    }
  };

  const handleCopy = async () => {
    if (!guardExport()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(summaryToPlainText(model));
      setNotice('Summary text copied to your clipboard.');
    } catch {
      // Clipboard access can be blocked. Offer the text for manual copying instead.
      setManualCopyOpen(true);
    }
  };

  const copy = summaryFailure ? errorCopy(summaryFailure) : null;
  const reference = summaryFailure ? errorReference(summaryFailure) : null;

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-6 sm:px-6 sm:py-10">
      <div className="print:hidden">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <PageHeading>Consultation summary</PageHeading>
            <p className="mt-1 text-ink-secondary">
              Review it, then print or copy it if you want to take it to a consultation.
            </p>
          </div>
          <SampleTag>Design demo · Sample information</SampleTag>
        </div>

        <div className="mt-5 space-y-4">
          {stale ? (
            <StatusPanel
              tone="attention"
              title="The result needs updating"
              actions={<ButtonLink to={`/results/${sessionId}`}>Go to the result</ButtonLink>}
            >
              <p>
                Your details changed after the last result, so this summary leaves out the next step and explanations
                until the result is updated.
              </p>
            </StatusPanel>
          ) : null}

          {summaryFailure && copy ? (
            <StatusPanel
              tone="attention"
              title="We couldn’t prepare the summary"
              announce="status"
              actions={
                <Button
                  onClick={() => void controller.createSummary()}
                  loading={preparing}
                  loadingLabel="Trying again…"
                >
                  Try again
                </Button>
              }
            >
              <p>{copy.message}</p>
              <p>Printing and copying are unavailable until the summary has been prepared.</p>
              {reference ? <p className="text-sm">{reference}</p> : null}
            </StatusPanel>
          ) : null}

          <div className="rounded-card border border-line bg-surface p-5">
            <label className="flex cursor-pointer items-start gap-3">
              <input
                type="checkbox"
                checked={reviewed}
                disabled={!summaryIsCurrent}
                aria-describedby={reviewPrompt && !reviewed ? `${id}-review-error` : undefined}
                onChange={(event) => {
                  setReviewed(event.target.checked);
                  setReviewPrompt(false);
                }}
                className="mt-0.5 size-5 shrink-0 accent-primary"
              />
              <span className="font-medium text-ink">
                I’ve reviewed this summary and it reflects what I shared.
                <span className="block font-normal text-ink-secondary">
                  Required before printing, copying or sharing.
                </span>
              </span>
            </label>
            {reviewPrompt && !reviewed ? (
              <p id={`${id}-review-error`} role="alert" className="mt-2 text-[0.9375rem] font-medium text-urgent">
                Tick the box to confirm you’ve reviewed the summary first.
              </p>
            ) : null}

            <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              <Button
                onClick={handlePrint}
                disabled={!summaryIsCurrent}
                icon={<Printer aria-hidden="true" className="size-4 shrink-0" />}
              >
                Print or save as PDF
              </Button>
              <Button
                variant="secondary"
                onClick={() => void handleCopy()}
                disabled={!summaryIsCurrent}
                icon={<Copy aria-hidden="true" className="size-4 shrink-0" />}
              >
                Copy text
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  if (guardExport()) setShareOpen(true);
                }}
                disabled={!summaryIsCurrent}
                icon={<Share2 aria-hidden="true" className="size-4 shrink-0" />}
              >
                Share…
              </Button>
              <ButtonLink
                to={`/assess/${sessionId}`}
                variant="ghost"
                icon={<Pencil aria-hidden="true" className="size-4 shrink-0" />}
              >
                Edit details
              </ButtonLink>
            </div>
            <p role="status" className="mt-2 min-h-6 text-[0.9375rem] font-medium text-info">
              {notice}
            </p>
          </div>
        </div>
      </div>

      <div className="mt-5 print:mt-0">
        {summaryIsCurrent || summaryFailure ? (
          <SummaryPreview model={model} />
        ) : (
          <div aria-busy="true" className="space-y-3 print:hidden">
            <p role="status" className="text-ink-secondary">
              Preparing your summary…
            </p>
            <SkeletonCard lines={5} />
          </div>
        )}
      </div>

      <Dialog
        open={shareOpen}
        onOpenChange={setShareOpen}
        title="Share this summary"
        description="Nothing is sent automatically. Choose how you want to take it with you."
        footer={<Button onClick={() => setShareOpen(false)}>Done</Button>}
      >
        <div className="space-y-3">
          <SampleTag>Design demo · Sample information</SampleTag>
          <ul className="space-y-2">
            <li>
              <Button
                variant="secondary"
                className="w-full justify-start"
                icon={<Printer aria-hidden="true" className="size-4 shrink-0" />}
                onClick={() => {
                  setShareOpen(false);
                  // Let the dialog close before the print preview opens.
                  window.setTimeout(() => window.print(), 250);
                }}
              >
                Print or save as PDF
              </Button>
            </li>
            <li>
              <Button
                variant="secondary"
                className="w-full justify-start"
                icon={<Copy aria-hidden="true" className="size-4 shrink-0" />}
                onClick={() => {
                  setShareOpen(false);
                  void handleCopy();
                }}
              >
                Copy text
              </Button>
            </li>
            {UNAVAILABLE_SHARE_OPTIONS.map((option) => (
              <li key={option.label} className="rounded-control border border-dashed border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-ink-secondary">{option.label}</span>
                  <StatusBadge tone="neutral">Unavailable</StatusBadge>
                </div>
                <p className="mt-1 text-sm text-ink-secondary">{option.reason}</p>
              </li>
            ))}
          </ul>
        </div>
      </Dialog>

      <Dialog
        open={manualCopyOpen}
        onOpenChange={setManualCopyOpen}
        title="Copy the summary text"
        description="Your browser blocked automatic copying. Select the text below and copy it."
        size="lg"
        footer={<Button onClick={() => setManualCopyOpen(false)}>Close</Button>}
      >
        <label htmlFor={`${id}-manual-copy`} className="sr-only">
          Summary text
        </label>
        <textarea
          id={`${id}-manual-copy`}
          readOnly
          rows={14}
          value={summaryToPlainText(model)}
          onFocus={(event) => event.currentTarget.select()}
          className="field-control font-mono text-sm"
        />
      </Dialog>
    </div>
  );
}
