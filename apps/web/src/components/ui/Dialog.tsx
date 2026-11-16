import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { IconButton } from './Button';
import { useRestoreFocus } from './useRestoreFocus';

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Short supporting sentence, announced with the title. */
  description?: ReactNode;
  children?: ReactNode;
  /** Action row. */
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  /** Use for dialogs that require a decision (focus trapped, announced as alertdialog). */
  role?: 'dialog' | 'alertdialog';
}

const WIDTHS = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl' } as const;

/**
 * Centred modal. Radix traps focus while open, closes on Escape and returns focus to the
 * control that opened it.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  size = 'md',
  role = 'dialog',
}: DialogProps) {
  const focus = useRestoreFocus();
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 animate-fade-in bg-ink/45 print:hidden" />
        <RadixDialog.Content
          role={role}
          {...(description ? {} : { 'aria-describedby': undefined })}
          onOpenAutoFocus={focus.onOpenAutoFocus}
          onCloseAutoFocus={focus.onCloseAutoFocus}
          className={cn(
            'fixed inset-x-3 top-1/2 z-50 mx-auto flex max-h-[calc(100dvh-2rem)] -translate-y-1/2 animate-fade-in flex-col rounded-card border border-line bg-surface shadow-float print:hidden',
            WIDTHS[size],
          )}
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
            <div className="min-w-0">
              <RadixDialog.Title className="font-display text-xl font-bold text-ink">{title}</RadixDialog.Title>
              {description ? (
                <RadixDialog.Description className="mt-1 text-[0.9375rem] text-ink-secondary">
                  {description}
                </RadixDialog.Description>
              ) : null}
            </div>
            <RadixDialog.Close asChild>
              <IconButton label="Close" className="-mr-2 -mt-1">
                <X aria-hidden="true" className="size-5" />
              </IconButton>
            </RadixDialog.Close>
          </div>
          {children ? <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-6">{children}</div> : null}
          {footer ? (
            <div className="flex flex-col-reverse gap-2 border-t border-line px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
              {footer}
            </div>
          ) : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
