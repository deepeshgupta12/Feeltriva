import type { ReactNode } from 'react';

import type { DeletionReceipt } from '@/api/types';

import { StatusPanel } from './StatusPanel';

interface DeletionReceiptPanelProps {
  receipt: DeletionReceipt;
  actions?: ReactNode;
  headingLevel?: 'h1' | 'h2' | 'h3';
}

/**
 * Shows exactly the deletion status the service reported. A scheduled deletion is
 * described as queued, never as complete, and no promise is made about backups.
 */
export function DeletionReceiptPanel({ receipt, actions, headingLevel = 'h2' }: DeletionReceiptPanelProps) {
  const completed = receipt.status === 'deleted';
  return (
    <StatusPanel
      tone={completed ? 'info' : 'attention'}
      title={completed ? 'Deletion completed' : 'Deletion scheduled'}
      announce="status"
      headingLevel={headingLevel}
      actions={actions}
    >
      <p>
        {completed
          ? 'The service reports that this assessment has been deleted.'
          : 'The service has queued this assessment for deletion. It has not confirmed that deletion is finished yet.'}
      </p>
      <p>
        Receipt: <code className="font-semibold text-ink">{receipt.receipt_id}</code>
      </p>
      <p className="text-sm">
        Copies in backups may be kept for a limited period under the retention policy, which is still a draft. The
        details have been removed from this device’s memory.
      </p>
    </StatusPanel>
  );
}
