import { Info } from 'lucide-react';
import type { ReactNode } from 'react';

import { LogoMark } from './Logo';

interface MessageCardProps {
  /** Who the entry is from. (Named `author`, not `role`, so it is not mistaken for an ARIA role.) */
  author: 'assistant' | 'user' | 'notice';
  children: ReactNode;
}

/**
 * One entry in the conversation. Assistant messages are white cards with the brand mark,
 * the user's messages sit on the soft teal surface, and notices (revisions, refreshes)
 * are quiet inline rows. Long text wraps; nothing is truncated.
 */
export function MessageCard({ author, children }: MessageCardProps) {
  if (author === 'notice') {
    return (
      <li className="flex items-start gap-2 rounded-control border border-info/25 bg-info-soft px-3.5 py-2.5 text-[0.9375rem] text-info">
        <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        <p>
          <span className="sr-only">Notice: </span>
          {children}
        </p>
      </li>
    );
  }

  if (author === 'user') {
    return (
      <li className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-card rounded-br-md bg-teal-soft px-4 py-3 text-ink">
          <span className="sr-only">You said: </span>
          {children}
        </div>
      </li>
    );
  }

  return (
    <li className="flex items-start gap-3">
      <LogoMark className="mt-1 size-7" />
      <div className="min-w-0 max-w-[90%] whitespace-pre-wrap rounded-card rounded-tl-md border border-line bg-surface px-4 py-3 text-ink">
        <span className="sr-only">Feeltriva said: </span>
        {children}
      </div>
    </li>
  );
}
