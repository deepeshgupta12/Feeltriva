import { Clock, FileQuestion, Lock } from 'lucide-react';
import type { ReactNode } from 'react';

import type { Session } from '@/api/types';
import { errorCopy, errorReference } from '@/lib/errorCopy';
import type { AssessmentController, AssessmentViewState } from '@/state/AssessmentController';
import { useServices } from '@/state/services';

import { DeletionReceiptPanel } from './DeletionReceiptPanel';
import { StatusPanel } from './StatusPanel';
import { Button, ButtonLink } from './ui/Button';
import { SkeletonCard } from './ui/Skeleton';

interface SessionGateProps {
  state: AssessmentViewState;
  controller: AssessmentController;
  /** Rendered only when the authoritative session is available. */
  children: (session: Session) => ReactNode;
}

/**
 * Handles every "this session cannot be shown" case in one place: loading, not found,
 * session expired, permission denied, load failure and deleted. Private details are never
 * rendered until the service has returned the session to this caller.
 */
export function SessionGate({ state, controller, children }: SessionGateProps) {
  const { mock } = useServices();

  if (state.load === 'ready' && state.session) {
    return <>{children(state.session)}</>;
  }

  const wrap = (content: ReactNode) => <div className="mx-auto w-full max-w-[760px] px-4 py-8 sm:px-6">{content}</div>;
  const restart = <ButtonLink to="/start">Start a new symptom check</ButtonLink>;

  switch (state.load) {
    case 'deleted':
      return wrap(
        state.deletion ? (
          <DeletionReceiptPanel receipt={state.deletion} headingLevel="h1" actions={restart} />
        ) : (
          <StatusPanel title="This assessment was deleted" headingLevel="h1" actions={restart} />
        ),
      );

    case 'not_found':
      return wrap(
        <StatusPanel
          tone="attention"
          title="We couldn’t find this assessment"
          headingLevel="h1"
          announce="status"
          icon={<FileQuestion aria-hidden="true" className="size-6" />}
          actions={
            <>
              {restart}
              <ButtonLink to="/history" variant="secondary">
                Saved summaries
              </ButtonLink>
            </>
          }
        >
          <p>It may have ended or been deleted.</p>
          {mock ? <p>In this demo, sample sessions are kept in memory and reset when the page reloads.</p> : null}
        </StatusPanel>,
      );

    case 'expired':
      return wrap(
        <StatusPanel
          tone="attention"
          title="Your session has ended"
          headingLevel="h1"
          announce="status"
          icon={<Clock aria-hidden="true" className="size-6" />}
          actions={restart}
        >
          <p>
            For your privacy, sessions end after a period of time or when you sign out. Nothing more can be added to
            this assessment.
          </p>
          <p>Start a new symptom check to continue. If you were signed in, you may be asked to sign in again.</p>
        </StatusPanel>,
      );

    case 'forbidden':
      return wrap(
        <StatusPanel
          tone="attention"
          title="You don’t have access to this assessment"
          headingLevel="h1"
          announce="status"
          icon={<Lock aria-hidden="true" className="size-6" />}
          actions={restart}
        >
          <p>It belongs to a different session or account, so it can’t be shown here.</p>
        </StatusPanel>,
      );

    case 'failed': {
      const copy = state.failure ? errorCopy(state.failure.error) : null;
      const reference = state.failure ? errorReference(state.failure.error) : null;
      return wrap(
        <StatusPanel
          tone="attention"
          title={copy?.title ?? 'We couldn’t load this assessment'}
          headingLevel="h1"
          announce="status"
          actions={
            <>
              <Button
                onClick={() => void controller.load()}
                loading={state.pending.includes('load')}
                loadingLabel="Trying again…"
              >
                Try again
              </Button>
              <ButtonLink to="/start" variant="secondary">
                Start a new symptom check
              </ButtonLink>
            </>
          }
        >
          <p>{copy?.message ?? 'Please try again.'}</p>
          {reference ? <p className="text-sm">{reference}</p> : null}
        </StatusPanel>,
      );
    }

    default:
      return wrap(
        <div className="space-y-4" aria-busy="true">
          <h1 tabIndex={-1} className="sr-only">
            Loading your assessment
          </h1>
          <p role="status" className="text-ink-secondary">
            Loading your assessment…
          </p>
          <SkeletonCard />
          <SkeletonCard lines={2} />
        </div>,
      );
  }
}
