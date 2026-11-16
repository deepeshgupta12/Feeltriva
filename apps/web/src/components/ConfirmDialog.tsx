import type { ReactNode } from 'react';

import { Button } from './ui/Button';
import { Dialog } from './ui/Dialog';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** Destructive actions use the danger style. */
  destructive?: boolean;
  pending?: boolean;
  pendingLabel?: string;
  onConfirm: () => void;
  children?: ReactNode;
}

/** Asks for explicit confirmation before a consequential action. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  cancelLabel = 'Cancel',
  destructive = false,
  pending = false,
  pendingLabel,
  onConfirm,
  children,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={description}
      size="sm"
      role="alertdialog"
      footer={
        <>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={pending}>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={pending}
            loadingLabel={pendingLabel}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
