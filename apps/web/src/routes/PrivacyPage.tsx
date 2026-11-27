import { Download, Trash2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';

import type { DeletionReceipt } from '@/api/types';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { DeletionReceiptPanel } from '@/components/DeletionReceiptPanel';
import { PageHeading } from '@/components/PageHeading';
import { Button } from '@/components/ui/Button';
import { LINK_CLASSES } from '@/components/ui/buttonStyles';
import { Dialog } from '@/components/ui/Dialog';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Switch } from '@/components/ui/Switch';
import { formatDateTime } from '@/lib/format';
import { useRegistryEntries, usePageMeta } from '@/state/hooks';
import { usePreferences } from '@/state/preferencesContext';
import { currentObservations, observationLabel } from '@/state/selectors';
import type { RegistryEntry } from '@/state/SessionRegistry';

function SettingsSection({
  id,
  title,
  badge,
  children,
}: {
  id: string;
  title: string;
  badge?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="font-display text-xl font-bold text-ink">
          {title}
        </h2>
        {badge}
      </div>
      <div className="mt-3 space-y-3 text-ink-secondary">{children}</div>
    </section>
  );
}

function isActive(entry: RegistryEntry): boolean {
  return entry.controller.getSnapshot().session !== null;
}

/** Plain description of what an export would contain, built from what is in memory. */
function exportPreview(entries: readonly RegistryEntry[]): string {
  if (entries.length === 0) {
    return 'There are no assessments in this visit, so an export would be empty.';
  }
  return entries
    .map((entry) => {
      const snapshot = entry.controller.getSnapshot();
      const observations = currentObservations(snapshot.session);
      const lines = [
        `${entry.title} · ${formatDateTime(entry.createdAt)}`,
        `  State: ${snapshot.session?.state ?? 'unknown'}`,
        `  Saved details (${observations.length}):`,
        ...observations.map((observation) => `    - ${observationLabel(observation)} [${observation.presence}]`),
        `  Result: ${snapshot.assessment ? snapshot.assessment.status : 'none'}`,
        `  Summary prepared: ${snapshot.summary ? 'yes' : 'no'}`,
      ];
      return lines.join('\n');
    })
    .join('\n\n');
}

export function PrivacyPage() {
  usePageMeta('Privacy settings', { noindex: true });
  const { historyEnabled, setHistoryEnabled, trainingConsent, setTrainingConsent } = usePreferences();
  const entries = useRegistryEntries();
  const active = entries.filter(isActive);

  const [exportOpen, setExportOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [receipts, setReceipts] = useState<DeletionReceipt[]>([]);
  const [failedCount, setFailedCount] = useState(0);

  const deleteAll = async () => {
    setDeleting(true);
    setFailedCount(0);
    const collected: DeletionReceipt[] = [];
    let failed = 0;
    // One request per assessment; each receipt is shown exactly as the service returned it.
    for (const entry of active) {
      const receipt = await entry.controller.deleteSession();
      if (receipt) {
        collected.push(receipt);
      } else {
        failed += 1;
      }
    }
    setReceipts((previous) => [...collected, ...previous]);
    setFailedCount(failed);
    setDeleting(false);
    setDeleteOpen(false);
  };

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-6 sm:px-6 sm:py-10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <PageHeading>Privacy</PageHeading>
          <p className="mt-1 text-ink-secondary">
            Choose what is kept, see what an export would contain, and delete your assessments.
          </p>
        </div>
        <StatusBadge tone="attention">Draft policy</StatusBadge>
      </div>

      <p className="mt-4 rounded-card border border-attention/30 bg-attention-soft p-4 text-attention">
        Final privacy and retention policies have not been supplied. The descriptions on this page are drafts and are
        not commitments.
      </p>

      <div className="mt-6 space-y-4">
        <SettingsSection id="history-heading" title="Saved history">
          <Switch
            label="Keep new assessments under Saved summaries"
            description="Optional. In this demo, history lives in this page’s memory only and is cleared on reload."
            checked={historyEnabled}
            onCheckedChange={setHistoryEnabled}
          />
          <p>
            Turning this off stops new assessments from being listed. It does not delete assessments that already exist;
            use the delete controls below for that.{' '}
            <Link to="/history" className={LINK_CLASSES}>
              View saved summaries
            </Link>
          </p>
        </SettingsSection>

        <SettingsSection
          id="retention-heading"
          title="How long information is kept"
          badge={<StatusBadge tone="attention">Draft</StatusBadge>}
        >
          <p>
            <strong className="font-semibold text-ink">In this demo:</strong> sample sessions exist only in this page’s
            memory. Reloading or closing the page clears them. Health details are not written to browser storage.
          </p>
          <p>
            <strong className="font-semibold text-ink">In the live service:</strong> what is kept, and for how long, is
            written in the terms you agree to before a check starts. Those terms are a draft until they have been
            reviewed.
          </p>
        </SettingsSection>

        <SettingsSection id="export-heading" title="Export your information">
          <p>Preview what an export would contain. The demo shows a preview only; it does not create or send a file.</p>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setExportOpen(true)}
            icon={<Download aria-hidden="true" className="size-4 shrink-0" />}
          >
            Preview export
          </Button>
        </SettingsSection>

        <SettingsSection id="delete-heading" title="Delete assessments">
          <p>
            Deleting asks the service to remove an assessment’s details, answers, results and summary. Deletion is
            queued and may take time. Copies in backups may be kept for a limited period under the retention policy;
            immediate removal from every backup is not promised.
          </p>
          <p>Deleting an assessment is also how you take back your agreement to the terms for it.</p>
          <Button
            variant="danger"
            size="sm"
            disabled={active.length === 0}
            onClick={() => setDeleteOpen(true)}
            icon={<Trash2 aria-hidden="true" className="size-4 shrink-0" />}
          >
            Delete all assessments from this visit ({active.length})
          </Button>
          {active.length === 0 ? <p className="text-sm">There are no assessments to delete.</p> : null}
          {failedCount > 0 ? (
            <p role="alert" className="font-medium text-urgent">
              {failedCount === 1 ? 'One deletion request' : `${failedCount} deletion requests`} didn’t go through. Those
              assessments have not been deleted. Please try again.
            </p>
          ) : null}
          {receipts.length > 0 ? (
            <div className="space-y-3 pt-1">
              {receipts.map((receipt) => (
                <DeletionReceiptPanel key={receipt.receipt_id} receipt={receipt} headingLevel="h3" />
              ))}
            </div>
          ) : null}
        </SettingsSection>

        <SettingsSection id="training-heading" title="Helping improve Feeltriva">
          <Switch
            label="Allow my information to be used to improve the service"
            description="Separate from using the symptom check, and off unless you turn it on."
            checked={trainingConsent}
            onCheckedChange={setTrainingConsent}
          />
          <p>
            The choice is recorded with each check you start from now on, and you are asked again on the first step of a
            new check. It does not change a check you have already started. In the demo it has no effect: nothing you
            enter is used for training or analysis, whichever way it is set.
          </p>
        </SettingsSection>
      </div>

      <Dialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        title="Export preview"
        description="What an export of this visit would contain. Nothing is downloaded or sent."
        size="lg"
        footer={<Button onClick={() => setExportOpen(false)}>Close</Button>}
      >
        <pre className="whitespace-pre-wrap rounded-control border border-line bg-page p-4 font-mono text-sm text-ink">
          {exportPreview(active)}
        </pre>
      </Dialog>

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={(open) => {
          if (!deleting) setDeleteOpen(open);
        }}
        title="Delete all assessments from this visit?"
        description={`${active.length === 1 ? '1 assessment' : `${active.length} assessments`} will be queued for deletion. This can’t be undone.`}
        confirmLabel="Delete all"
        destructive
        pending={deleting}
        pendingLabel="Requesting deletion…"
        onConfirm={() => void deleteAll()}
      />
    </div>
  );
}
