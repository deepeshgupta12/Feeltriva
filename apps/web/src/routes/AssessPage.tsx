import { WifiOff } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';

import { parseSessionState, type Session } from '@/api/types';
import { Composer } from '@/components/Composer';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ContextPanel, CONTEXT_PANEL_TITLE } from '@/components/ContextPanel';
import { ConversationHeader } from '@/components/ConversationHeader';
import { FollowUpQuestion } from '@/components/FollowUpQuestion';
import { MessageCard } from '@/components/MessageCard';
import { SessionGate } from '@/components/SessionGate';
import { StatusPanel } from '@/components/StatusPanel';
import { Button, ButtonLink } from '@/components/ui/Button';
import { Sheet } from '@/components/ui/Sheet';
import { SampleTag, StatusBadge } from '@/components/ui/StatusBadge';
import { errorCopy, errorReference } from '@/lib/errorCopy';
import type { AssessmentController, AssessmentViewState } from '@/state/AssessmentController';
import { useAssessment, useOnlineStatus, usePageMeta } from '@/state/hooks';
import { currentObservations, isAssessmentStale } from '@/state/selectors';
import { useServices } from '@/state/services';

const INTAKE_PLACEHOLDER =
  'Describe what feels different, when it started, and anything that makes it better or worse.';

export function AssessPage() {
  // The title never includes symptoms or other details from the conversation.
  usePageMeta('Symptom check', { noindex: true });
  const { sessionId = '' } = useParams();
  const { controller, state } = useAssessment(sessionId);

  return (
    <SessionGate state={state} controller={controller}>
      {(session) => <Conversation key={sessionId} session={session} state={state} controller={controller} />}
    </SessionGate>
  );
}

interface ConversationProps {
  session: Session;
  state: AssessmentViewState;
  controller: AssessmentController;
}

function Conversation({ session, state, controller }: ConversationProps) {
  const navigate = useNavigate();
  const { mock } = useServices();
  const online = useOnlineStatus();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const flow = parseSessionState(session.state);
  const observations = currentObservations(session);
  const pending = state.pending;
  const busy = controller.isMutating();
  const sendingText = pending.includes('text');
  const sendingAnswer = pending.includes('answer');
  const assessing = pending.includes('assess');
  const loadingQuestion = pending.includes('question');
  const stale = isAssessmentStale(session, state.assessment);
  const hasCurrentResult = state.assessment !== null && !stale;
  const failure = state.failure;
  const failureCopy = failure ? errorCopy(failure.error) : null;
  const failureReference = failure ? errorReference(failure.error) : null;

  const questioningPaused = flow === 'urgent_handoff' || flow === 'out_of_scope' || flow === 'closed';
  const assessmentUnavailable = flow === 'system_unavailable' || failure?.op === 'assess';
  const noFurtherQuestions =
    state.question === null && state.questionVersion === session.observation_version && !loadingQuestion;

  // Keep the newest message or question in view.
  const transcriptLength = state.transcript.length;
  const questionKey = state.question ? `${state.question.question_id}:${state.question.observation_version}` : 'none';
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [transcriptLength, questionKey]);

  const requestResult = async () => {
    await controller.assess();
    void navigate(`/results/${session.session_id}`);
  };

  const contextPanel = (showTitle: boolean) => (
    <ContextPanel
      observations={observations}
      busy={busy}
      error={failure?.op === 'observation' ? failure.error : null}
      onConfirm={(id) => controller.confirmObservation(id)}
      onRevise={(id, revision) => controller.reviseObservation(id, revision)}
      showTitle={showTitle}
    />
  );

  const progressText = sendingText
    ? 'Sending your message…'
    : sendingAnswer
      ? 'Sending your answer…'
      : pending.includes('observation')
        ? 'Saving your change…'
        : loadingQuestion
          ? 'Preparing the next question…'
          : assessing
            ? 'Preparing your result…'
            : null;

  return (
    <div className="flex min-w-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <ConversationHeader
          sessionId={session.session_id}
          state={flow}
          detailCount={observations.length}
          onOpenDetails={() => setDetailsOpen(true)}
          onRestart={() => setRestartOpen(true)}
          onDelete={() => setDeleteOpen(true)}
        />

        <div className="flex-1 px-4 py-5 sm:px-6">
          <div className="mx-auto w-full max-w-[760px] space-y-4">
            {mock ? (
              <p className="flex flex-wrap items-center gap-2 text-[0.9375rem] text-ink-secondary">
                <SampleTag>Sample conversation</SampleTag>
                Demo mode doesn’t analyse what you type. Sample details are shown instead.
              </p>
            ) : null}

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
                    loading={pending.includes('refresh')}
                    loadingLabel="Reconnecting…"
                  >
                    Try to reconnect
                  </Button>
                }
              >
                <p>
                  <strong className="font-semibold text-ink">Not sent:</strong> anything still in the message box or an
                  answer you haven’t sent. It stays here until you’re back online.
                </p>
                <p>
                  <strong className="font-semibold text-ink">Saved:</strong> the details listed under “
                  {CONTEXT_PANEL_TITLE}”. They haven’t changed.
                </p>
              </StatusPanel>
            ) : null}

            {state.transcript.length === 0 && observations.length > 0 ? (
              <p className="rounded-control border border-dashed border-line p-3 text-[0.9375rem] text-ink-secondary">
                Earlier messages aren’t kept on this device. Your saved details are listed under “{CONTEXT_PANEL_TITLE}
                ”.
              </p>
            ) : null}

            <ol role="log" aria-live="polite" aria-label="Conversation" className="space-y-3">
              {state.transcript.map((entry) => (
                <MessageCard key={entry.id} author={entry.role}>
                  {entry.text}
                </MessageCard>
              ))}
            </ol>

            {state.conflict ? (
              <StatusPanel
                tone="info"
                title={
                  state.conflict.refreshing
                    ? 'Your details changed. Refreshing this assessment…'
                    : 'Your details changed'
                }
                announce="status"
                headingLevel="h2"
                actions={
                  state.conflict.refreshing ? undefined : (
                    <Button variant="secondary" size="sm" onClick={() => controller.dismissConflictNotice()}>
                      OK
                    </Button>
                  )
                }
              >
                {state.conflict.refreshing ? (
                  <p>Getting the latest version. Anything you haven’t sent is kept.</p>
                ) : (
                  <p>
                    This assessment was updated somewhere else, so it has been refreshed. Nothing unsent was lost. Check
                    your answer against the current question and send it again.
                  </p>
                )}
              </StatusPanel>
            ) : null}

            {failure && failureCopy && failure.op !== 'assess' && failure.op !== 'answer' && failure.op !== 'text' ? (
              <StatusPanel
                tone="attention"
                title={failure.op === 'question' ? 'We couldn’t load the next question' : failureCopy.title}
                announce="status"
                headingLevel="h2"
                actions={
                  <>
                    {failureCopy.canRetry ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void controller.refresh()}
                        loading={pending.includes('refresh')}
                        loadingLabel="Trying again…"
                      >
                        Try again
                      </Button>
                    ) : null}
                    <Button variant="ghost" size="sm" onClick={() => controller.dismissFailure()}>
                      Dismiss
                    </Button>
                  </>
                }
              >
                <p>{failureCopy.message}</p>
                {failureReference ? <p className="text-sm">{failureReference}</p> : null}
              </StatusPanel>
            ) : null}

            <ConversationBody
              session={session}
              state={state}
              flow={flow}
              online={online}
              busy={busy}
              sendingAnswer={sendingAnswer}
              assessing={assessing}
              stale={stale}
              hasCurrentResult={hasCurrentResult}
              noFurtherQuestions={noFurtherQuestions}
              assessmentUnavailable={assessmentUnavailable}
              onAnswer={(value, label) => void controller.answerQuestion(value, label)}
              onRequestResult={() => void requestResult()}
              onRetryAssessment={() => void controller.assess()}
              onRefresh={() => void controller.refresh()}
            />

            {progressText ? (
              <p role="status" className="text-[0.9375rem] text-ink-secondary">
                {progressText}
              </p>
            ) : null}
            <div ref={endRef} />
          </div>
        </div>

        <div className="sticky bottom-0 z-10 border-t border-line bg-page/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur sm:px-6 print:hidden">
          <div className="mx-auto w-full max-w-[760px]">
            {questioningPaused ? (
              <p className="py-2 text-[0.9375rem] text-ink-secondary">
                {flow === 'closed'
                  ? 'This assessment has ended, so new messages can’t be added.'
                  : 'Routine questions are paused. You can still check and correct your details.'}
              </p>
            ) : (
              <Composer
                label={flow === 'intake' ? 'What have you been feeling?' : 'Add more details'}
                placeholder={flow === 'intake' ? INTAKE_PLACEHOLDER : 'Add or correct anything in your own words.'}
                value={state.draftText}
                onChange={(value) => controller.setDraftText(value)}
                onSend={() => void controller.sendText(state.draftText)}
                pending={sendingText}
                disabled={busy && !sendingText}
                error={failure?.op === 'text' && failureCopy ? failureCopy.message : null}
                note={
                  state.draftText.trim().length > 0 && (!online || failure?.op === 'text')
                    ? 'Not sent yet. This text is only in this box until it’s sent.'
                    : undefined
                }
              />
            )}
          </div>
        </div>
      </div>

      <aside
        aria-label={CONTEXT_PANEL_TITLE}
        className="sticky top-[var(--demo-banner-height,0px)] hidden h-[calc(100dvh-var(--demo-banner-height,0px))] w-80 shrink-0 overflow-y-auto border-l border-line bg-surface/60 p-5 xl:block print:hidden"
      >
        {contextPanel(true)}
      </aside>

      <Sheet
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        title={CONTEXT_PANEL_TITLE}
        description="Saved details. Check them and correct anything that isn’t right."
        side="responsive"
      >
        {contextPanel(false)}
      </Sheet>

      <ConfirmDialog
        open={restartOpen}
        onOpenChange={setRestartOpen}
        title="Start over?"
        description="You’ll begin a new symptom check. This conversation isn’t deleted; you can still find it under Saved summaries or delete it."
        confirmLabel="Start a new check"
        onConfirm={() => {
          setRestartOpen(false);
          void navigate('/start');
        }}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this assessment?"
        description="Your details, answers and any result for this assessment will be queued for deletion. This can’t be undone."
        confirmLabel="Delete assessment"
        destructive
        pending={pending.includes('delete')}
        pendingLabel="Requesting deletion…"
        onConfirm={() => {
          void controller.deleteSession().then((receipt) => {
            if (receipt) {
              setDeleteOpen(false);
            }
          });
        }}
      >
        {failure?.op === 'delete' && failureCopy ? (
          <p role="alert" className="font-medium text-urgent">
            {failureCopy.message}
          </p>
        ) : null}
      </ConfirmDialog>
    </div>
  );
}

interface ConversationBodyProps {
  session: Session;
  state: AssessmentViewState;
  flow: ReturnType<typeof parseSessionState>;
  online: boolean;
  busy: boolean;
  sendingAnswer: boolean;
  assessing: boolean;
  stale: boolean;
  hasCurrentResult: boolean;
  noFurtherQuestions: boolean;
  assessmentUnavailable: boolean;
  onAnswer: (value: Parameters<AssessmentController['answerQuestion']>[0], label: string) => void;
  onRequestResult: () => void;
  onRetryAssessment: () => void;
  onRefresh: () => void;
}

/** The part of the conversation that depends on the server-reported state. */
function ConversationBody({
  session,
  state,
  flow,
  online,
  busy,
  sendingAnswer,
  assessing,
  stale,
  hasCurrentResult,
  noFurtherQuestions,
  assessmentUnavailable,
  onAnswer,
  onRequestResult,
  onRetryAssessment,
  onRefresh,
}: ConversationBodyProps) {
  const sessionId = session.session_id;
  const summaryLink = (
    <ButtonLink to={`/summary/${sessionId}`} variant="secondary">
      View consultation summary
    </ButtonLink>
  );
  const currentAssessment = hasCurrentResult ? state.assessment : null;

  if (flow === 'urgent_handoff') {
    // Routine questioning stops here: no follow-up question and no explanation cards.
    if (!currentAssessment) {
      if (state.failure?.op === 'assess') {
        return (
          <StatusPanel
            tone="urgent"
            title="This needs urgent attention"
            announce="alert"
            eyebrow={<StatusBadge tone="urgent">Urgent-state preview</StatusBadge>}
            actions={
              <Button onClick={onRetryAssessment} loading={assessing} loadingLabel="Loading…">
                Try again
              </Button>
            }
          >
            <p>We couldn’t load the recommended action from the assessment service. Routine questions are paused.</p>
          </StatusPanel>
        );
      }
      return (
        <p role="status" className="text-ink-secondary">
          Loading the recommended action…
        </p>
      );
    }
    return (
      <StatusPanel
        tone="urgent"
        title="This needs urgent attention"
        announce="alert"
        eyebrow={
          <>
            <StatusBadge tone="urgent">Urgent-state preview</StatusBadge>
            <SampleTag>Sample action text</SampleTag>
          </>
        }
        actions={
          <>
            <ButtonLink to={`/results/${sessionId}`}>View what to do next</ButtonLink>
            {summaryLink}
          </>
        }
      >
        <p className="text-lg font-medium text-ink">{currentAssessment.next_action.text}</p>
        <p>Routine questions are paused.</p>
      </StatusPanel>
    );
  }

  if (flow === 'out_of_scope') {
    return (
      <StatusPanel
        tone="attention"
        title="This is outside what Feeltriva can help with"
        announce="status"
        eyebrow={<SampleTag>Sample limitation</SampleTag>}
        actions={
          <>
            <ButtonLink to={`/results/${sessionId}`}>View details</ButtonLink>
            {summaryLink}
          </>
        }
      >
        {currentAssessment ? <p className="text-ink">{currentAssessment.next_action.text}</p> : <p>Loading details…</p>}
        <p>No explanation is shown for this assessment. What you shared is still available as a summary.</p>
      </StatusPanel>
    );
  }

  if (flow === 'closed') {
    return (
      <StatusPanel
        title="This assessment has ended"
        announce="status"
        actions={<ButtonLink to="/start">Start a new symptom check</ButtonLink>}
      >
        <p>You can start a new symptom check at any time.</p>
      </StatusPanel>
    );
  }

  if (flow === 'unknown') {
    return (
      <StatusPanel
        tone="attention"
        title="We can’t show this step"
        announce="status"
        actions={
          <Button variant="secondary" onClick={onRefresh}>
            Refresh
          </Button>
        }
      >
        <p>This assessment is in a state this version of the app doesn’t recognise, so nothing is assumed about it.</p>
      </StatusPanel>
    );
  }

  if (assessmentUnavailable) {
    return (
      <StatusPanel
        tone="attention"
        title="We couldn’t complete this assessment"
        announce="status"
        actions={
          <>
            <Button onClick={onRetryAssessment} loading={assessing} loadingLabel="Trying again…" disabled={busy}>
              Try again
            </Button>
            {summaryLink}
          </>
        }
      >
        <p>The assessment service is unavailable right now. No result has been produced and none is being guessed.</p>
        <p>Your details are saved. You can try again, or use the summary of what you shared.</p>
      </StatusPanel>
    );
  }

  if (state.question) {
    return (
      <FollowUpQuestion
        key={`${state.question.question_id}:${state.question.observation_version}`}
        question={state.question}
        unsentAnswer={state.unsentAnswer}
        pending={sendingAnswer}
        busy={busy}
        serverError={state.failure?.op === 'answer' ? errorCopy(state.failure.error).message : null}
        onSubmit={onAnswer}
      />
    );
  }

  // While offline nothing is presented as finished: there is no "result ready" step.
  if (!online || flow === 'intake' || !noFurtherQuestions) {
    return null;
  }

  if (flow === 'insufficient_information') {
    return (
      <StatusPanel
        tone="attention"
        title="More information is needed"
        announce="status"
        actions={
          <>
            <ButtonLink to={`/results/${sessionId}`}>See what’s missing</ButtonLink>
            {summaryLink}
          </>
        }
      >
        <p>There are no more questions right now, and there isn’t enough information to suggest a next step.</p>
      </StatusPanel>
    );
  }

  return (
    <StatusPanel
      tone="neutral"
      title={
        hasCurrentResult
          ? 'Your result is available'
          : stale
            ? 'Your details changed'
            : 'That’s all the questions for now'
      }
      announce="status"
      actions={
        <>
          {hasCurrentResult ? (
            <ButtonLink to={`/results/${sessionId}`}>View your result</ButtonLink>
          ) : (
            <Button onClick={onRequestResult} loading={assessing} loadingLabel="Preparing your result…" disabled={busy}>
              {stale ? 'See your updated result' : 'See your next step'}
            </Button>
          )}
          {summaryLink}
        </>
      }
    >
      <p>
        {hasCurrentResult
          ? 'It reflects the details you’ve shared so far. You can still add or correct details below.'
          : stale
            ? 'The earlier result no longer matches your details. Ask for an updated result when you’re ready.'
            : 'Check the details you’ve shared, then continue when you’re ready. You can still add more below.'}
      </p>
    </StatusPanel>
  );
}
