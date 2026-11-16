import { ChevronDown, ExternalLink } from 'lucide-react';

import type { Evidence } from '@/api/types';
import { safeExternalUrl } from '@/lib/format';

import { LINK_CLASSES } from './ui/buttonStyles';

interface SourceListProps {
  evidence: readonly Evidence[];
  /** Knowledge-release identifiers are internal detail: only shown in reviewer preview. */
  showInternalDetail?: boolean;
  /** Start with every source expanded (used inside the evidence drawer). */
  defaultOpen?: boolean;
}

/**
 * Expandable source details. Only evidence that is actually present in the response is
 * listed. Links are rendered only for http(s) URLs and open in a new tab without giving
 * the destination access to this page.
 */
export function SourceList({ evidence, showInternalDetail = false, defaultOpen = false }: SourceListProps) {
  if (evidence.length === 0) {
    return <p className="text-ink-secondary">No sources were supplied with this result.</p>;
  }
  return (
    <ul className="space-y-2">
      {evidence.map((item) => {
        const url = safeExternalUrl(item.source_url);
        return (
          <li key={item.evidence_id}>
            <details open={defaultOpen} className="group rounded-control border border-line bg-surface">
              <summary className="flex min-h-12 list-none items-center gap-2 rounded-control px-3.5 py-2 font-semibold text-ink [&::-webkit-details-marker]:hidden">
                <span className="min-w-0 flex-1">{item.source_title}</span>
                <ChevronDown
                  aria-hidden="true"
                  className="size-4 shrink-0 transition-transform duration-150 group-open:rotate-180"
                />
              </summary>
              <div className="space-y-2.5 px-3.5 pb-3.5">
                <blockquote className="border-l-2 border-line pl-3 text-ink-secondary">{item.excerpt}</blockquote>
                {url ? (
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex min-h-11 items-center gap-1.5 ${LINK_CLASSES}`}
                  >
                    <ExternalLink aria-hidden="true" className="size-4 shrink-0" />
                    <span>
                      Open source<span className="sr-only">: {item.source_title}</span> (opens in a new tab)
                    </span>
                  </a>
                ) : (
                  <p className="text-sm text-ink-secondary">No link was supplied for this source.</p>
                )}
                {showInternalDetail ? (
                  <p className="text-sm text-ink-secondary">
                    Internal detail · knowledge release <code>{item.knowledge_release}</code> · evidence{' '}
                    <code>{item.evidence_id}</code>
                  </p>
                ) : null}
              </div>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
