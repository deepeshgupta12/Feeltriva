import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface ScrollRegionProps {
  /** Accessible name announced for the region. */
  label: string;
  className?: string;
  children: ReactNode;
}

/**
 * Horizontally scrollable container for wide tables. It is a named, focusable region so
 * keyboard users can scroll it; the page itself never scrolls sideways.
 */
export function ScrollRegion({ label, className, children }: ScrollRegionProps) {
  return (
    <div
      role="region"
      aria-label={label}
      // A scrollable region must be focusable so it can be scrolled from the keyboard.
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      className={cn('overflow-x-auto rounded-control border border-line bg-surface', className)}
    >
      {children}
    </div>
  );
}
