import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/**
 * The page's single h1. It is focusable (tabIndex -1) so the route change handler can move
 * keyboard and screen-reader focus to it after navigation.
 */
export function PageHeading({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <h1
      tabIndex={-1}
      className={cn('font-display text-[1.75rem] font-bold leading-tight text-ink sm:text-[2rem]', className)}
    >
      {children}
    </h1>
  );
}
