import { NotebookText, RotateCcw } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { Link } from 'react-router';

import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DeletionReceiptPanel } from '@/components/DeletionReceiptPanel';
import { HistoryCard } from '@/components/HistoryCard';
import { PageHeading } from '@/components/PageHeading';
import { StatusPanel } from '@/components/StatusPanel';
import { Button, ButtonLink } from '@/components/ui/Button';
import { LINK_CLASSES } from '@/components/ui/buttonStyles';
import { Dialog } from '@/components/ui/Dialog';
import { SampleTag } from '@/components/ui/StatusBadge';
import { errorCopy } from '@/lib/errorCopy';
import { useDemo } from '@/state/demo';
import { useRegistryEntries, usePageMeta } from '@/state/hooks';
import { usePreferences } from '@/state/preferencesContext';
import { isAssessmentStale } from '@/state/selectors';
import type { RegistryEntry } from '@/state/SessionRegistry';
import { useServices } from '@/state/services';

export function HistoryPage() {
  usePageMeta('Saved summaries', { noindex: true });
  const id = useId();
  const { registry, mock } = useServices();
  const demo = useDemo();
  const { historyEnabled } = usePreferences();
  const entries = useRegistryEntries();

  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<RegistryEntry | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleting, setDeleting] = useState<RegistryEntry | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [resetOpen, setResetOpen] = useState(false);

  const listed = entries.filter((entry) => entry.listed);
  const saved = listed.filter((entry) => entry.controller.getSnapshot().load !== 'deleted');
  const receipts = listed.filter((entry) => entry.controller.getSnapshot().load === 'deleted');

  const createSample = async () => {
    setCreating(true);
    try {
      await demo.createCompletedSample();
    } finally {
      setCreating(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleting) {
      return;
    }
    setDeletePending(true);
    setDeleteError(null);
    const receipt = await deleting.controller.deleteSession();
    setDeletePending(false);
    if (receipt) {
      setDeleting(null);
    } else {
      const failure = deleting.controller.getSnapshot().failure;
      setDeleteError(
        failure ? errorCopy(failure.error).message : 'The deletion request didn’t go through. Please try again.',
      );
    }
  };

  const submitRename = (event: FormEvent) => {
    event.preventDefault();
    if (renaming && renameValue.trim().length > 0) {
      registry.rename(renaming.sessionId, renameValue);
      setRenaming(null);
    }
  };

  const startSampleAction = mock ? (
    <Button onClick={() => void createSample()} loading={creating} loadingLabel="Creating a sample…">
      Start a sample assessment
    </Button>
  ) : (
    <ButtonLink to="/start">Start a sample assessment</ButtonLink>
  );

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-6 sm:px-6 sm:py-10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <PageHeading>Saved summaries</PageHeading>
          <p className="mt-1 text-ink-secondary">
            Assessments from this visit. In the demo they are kept in memory only and are cleared when the page reloads.
          </p>
        </div>
        <SampleTag>Sample sessions</SampleTag>
      </div>

      <div className="mt-6 space-y-5">
        {!historyEnabled ? (
          <StatusPanel tone="info" title="Saved history is off">
            <p>
              New assessments aren’t added to this list. You can change this in{' '}
              <Link to="/settings/privacy" className={LINK_CLASSES}>
                Privacy settings
              </Link>
              .
            </p>
          </StatusPanel>
        ) : null}

        {receipts.length > 0 ? (
          <section aria-label="Deletion receipts" className="space-y-3">
            {receipts.map((entry) => {
              const receipt = entry.controller.getSnapshot().deletion;
              if (!receipt) {
                return null;
              }
              return (
                <DeletionReceiptPanel
                  key={entry.sessionId}
                  receipt={receipt}
                  actions={
                    <>
                      {mock && receipt.status === 'deletion_scheduled' ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            const updated = mock.completeDeletion(entry.sessionId);
                            if (updated) entry.controller.applyDeletionReceipt(updated);
                          }}
                        >
                          Demo: simulate the service finishing deletion
                        </Button>
                      ) : null}
                      <Button variant="ghost" size="sm" onClick={() => registry.forget(entry.sessionId)}>
                        Dismiss receipt
                      </Button>
                    </>
                  }
                />
              );
            })}
          </section>
        ) : null}

        {saved.length === 0 ? (
          <StatusPanel
            title="No saved assessments yet"
            icon={<NotebookText aria-hidden="true" className="size-6" />}
            actions={startSampleAction}
          >
            <p>
              When you complete a symptom check, it appears here with its date and a link to its consultation summary,
              so you can find it again or delete it.
            </p>
          </StatusPanel>
        ) : (
          <>
            <ul className="space-y-3">
              {saved.map((entry) => {
                const snapshot = entry.controller.getSnapshot();
                const current =
                  snapshot.assessment !== null && !isAssessmentStale(snapshot.session, snapshot.assessment);
                return (
                  <HistoryCard
                    key={entry.sessionId}
                    sessionId={entry.sessionId}
                    title={entry.title}
                    createdAt={entry.createdAt}
                    completed={current && snapshot.assessment?.status === 'provisional'}
                    summaryAvailable={
                      snapshot.summary !== null &&
                      snapshot.summary.observation_version === snapshot.session?.observation_version
                    }
                    onRename={() => {
                      setRenameValue(entry.title);
                      setRenaming(entry);
                    }}
                    onDelete={() => {
                      setDeleteError(null);
                      setDeleting(entry);
                    }}
                  />
                );
              })}
            </ul>
            <div className="flex flex-col gap-2 sm:flex-row">{startSampleAction}</div>
          </>
        )}

        <div className="border-t border-line pt-5">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setResetOpen(true)}
            icon={<RotateCcw aria-hidden="true" className="size-4 shrink-0" />}
          >
            Reset demo history
          </Button>
          <p className="mt-2 text-sm text-ink-secondary">
            Clears the sample sessions held in this page’s memory. It is a demo control, not a deletion request.
          </p>
        </div>
      </div>

      <Dialog
        open={renaming !== null}
        onOpenChange={(open) => {
          if (!open) setRenaming(null);
        }}
        title="Rename this assessment"
        description="Choose a title that helps you find it. Avoid putting health details in the title."
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRenaming(null)}>
              Cancel
            </Button>
            <Button type="submit" form={`${id}-rename`} disabled={renameValue.trim().length === 0}>
              Save title
            </Button>
          </>
        }
      >
        <form id={`${id}-rename`} onSubmit={submitRename}>
          <label htmlFor={`${id}-title`} className="mb-1 block font-medium text-ink">
            Title
          </label>
          <input
            id={`${id}-title`}
            type="text"
            value={renameValue}
            maxLength={80}
            autoComplete="off"
            onChange={(event) => setRenameValue(event.target.value)}
            className="field-control"
          />
        </form>
      </Dialog>

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open && !deletePending) setDeleting(null);
        }}
        title="Delete this assessment?"
        description={`“${deleting?.title ?? ''}” and its summary will be queued for deletion. This can’t be undone.`}
        confirmLabel="Delete assessment"
        destructive
        pending={deletePending}
        pendingLabel="Requesting deletion…"
        onConfirm={() => void confirmDelete()}
      >
        {deleteError ? (
          <p role="alert" className="font-medium text-urgent">
            {deleteError}
          </p>
        ) : null}
      </ConfirmDialog>

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Reset demo history?"
        description="Every sample session in this page’s memory will be cleared, along with the demo switches."
        confirmLabel="Reset"
        onConfirm={() => {
          demo.resetDemo();
          setResetOpen(false);
        }}
      />
    </div>
  );
}
