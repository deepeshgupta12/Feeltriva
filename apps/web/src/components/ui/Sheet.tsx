import * as RadixDialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

import { IconButton } from './Button';
import { useRestoreFocus } from './useRestoreFocus';

export type SheetSide = 'left' | 'right' | 'responsive';

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  /**
   * `responsive`: bottom sheet on phones, right-hand drawer from tablet width up.
   * `left` / `right`: side drawer at every width.
   */
  side?: SheetSide;
  /** Visual treatment. `tools` is used for the demo tools so they read as separate from the product. */
  tone?: 'default' | 'tools';
}

const SIDES: Record<SheetSide, string> = {
  left: 'inset-y-0 left-0 w-[min(22rem,calc(100vw-2.5rem))] animate-sheet-left border-r',
  right: 'inset-y-0 right-0 w-[min(26rem,calc(100vw-2.5rem))] animate-sheet-right border-l',
  responsive:
    'inset-x-0 bottom-0 max-h-[88dvh] animate-sheet-up rounded-t-card border-t md:inset-x-auto md:inset-y-0 md:right-0 md:max-h-none md:w-[26rem] md:animate-sheet-right md:rounded-none md:border-l md:border-t-0',
};

/**
 * Drawer / bottom sheet built on the Radix dialog primitive: focus is trapped while open,
 * Escape closes it and focus returns to the trigger.
 */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  side = 'responsive',
  tone = 'default',
}: SheetProps) {
  const tools = tone === 'tools';
  const focus = useRestoreFocus();
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 animate-fade-in bg-ink/45 print:hidden" />
        <RadixDialog.Content
          {...(description ? {} : { 'aria-describedby': undefined })}
          onOpenAutoFocus={focus.onOpenAutoFocus}
          onCloseAutoFocus={focus.onCloseAutoFocus}
          className={cn(
            'fixed z-50 flex flex-col shadow-float print:hidden',
            tools ? 'border-ink bg-ink text-white' : 'border-line bg-surface',
            SIDES[side],
          )}
        >
          <div
            className={cn(
              'flex items-start justify-between gap-3 border-b px-5 py-4',
              tools ? 'border-white/20' : 'border-line',
            )}
          >
            <div className="min-w-0">
              <RadixDialog.Title className={cn('font-display text-lg font-bold', tools ? 'text-white' : 'text-ink')}>
                {title}
              </RadixDialog.Title>
              {description ? (
                <RadixDialog.Description className={cn('mt-1 text-sm', tools ? 'text-white/85' : 'text-ink-secondary')}>
                  {description}
                </RadixDialog.Description>
              ) : null}
            </div>
            <RadixDialog.Close asChild>
              <IconButton
                label="Close"
                className={cn('-mr-2 -mt-1', tools && 'text-white hover:bg-white/15 hover:text-white')}
              >
                <X aria-hidden="true" className="size-5" />
              </IconButton>
            </RadixDialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
            {children}
          </div>
          {footer ? (
            <div
              className={cn(
                'border-t px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]',
                tools ? 'border-white/20' : 'border-line',
              )}
            >
              {footer}
            </div>
          ) : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
