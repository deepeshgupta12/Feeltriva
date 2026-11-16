import { CircleHelp } from 'lucide-react';
import type { ReactNode } from 'react';

interface UncertaintyPanelProps {
  /** Open questions and scope limits listed by the assessment service. */
  unknowns: readonly string[];
  /** Explanations withheld because their supporting information was missing. */
  withheld?: number;
  children?: ReactNode;
}

export const INTENDED_USE_STATEMENT =
  'Feeltriva does not confirm a diagnosis. A health professional may need to examine you or arrange tests.';

/** "What is still uncertain": missing information, scope limits and follow-up considerations. */
export function UncertaintyPanel({ unknowns, withheld = 0, children }: UncertaintyPanelProps) {
  return (
    <div className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <div className="flex items-start gap-3">
        <CircleHelp aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-ink-secondary" />
        <div className="min-w-0 flex-1 space-y-3">
          {unknowns.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-ink">
              {unknowns.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="text-ink">
              The assessment service didn’t list specific open questions. This result is still provisional.
            </p>
          )}
          {withheld > 0 ? (
            <p className="rounded-control border border-attention/30 bg-attention-soft px-3.5 py-2.5 text-attention">
              {withheld === 1 ? 'One possible explanation was' : `${withheld} possible explanations were`} withheld
              because supporting information wasn’t available. This result is incomplete.
            </p>
          ) : null}
          {children}
          <p className="text-ink-secondary">{INTENDED_USE_STATEMENT}</p>
        </div>
      </div>
    </div>
  );
}
