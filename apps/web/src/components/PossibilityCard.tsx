import { BookOpenText } from 'lucide-react';

import { observationLabel, type CandidateView } from '@/state/selectors';

import { Button } from './ui/Button';
import { SampleTag } from './ui/StatusBadge';

interface PossibilityCardProps {
  view: CandidateView;
  onViewEvidence: () => void;
  /** The result this card belongs to is out of date; its actions are disabled. */
  stale?: boolean;
}

function DetailList({ title, items, emptyText }: { title: string; items: string[]; emptyText: string }) {
  return (
    <div>
      <h4 className="font-display text-base font-bold text-ink">{title}</h4>
      {items.length > 0 ? (
        <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-secondary">
          {items.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-ink-secondary">{emptyText}</p>
      )}
    </div>
  );
}

/**
 * One possible explanation supplied by the assessment service. It is headed "Possible
 * explanation" and carries no probability, score or ranking bar: the service does not
 * provide one and the interface must not suggest one.
 */
export function PossibilityCard({ view, onViewEvidence, stale = false }: PossibilityCardProps) {
  const { candidate } = view;
  return (
    <article className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">Possible explanation</p>
        <SampleTag>Sample · not a real condition</SampleTag>
      </div>
      <h3 className="mt-1.5 font-display text-xl font-bold text-ink">{candidate.name}</h3>
      <p className="mt-2 text-ink-secondary">{candidate.explanation}</p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <DetailList title="Details that fit" items={view.fits.map(observationLabel)} emptyText="None listed." />
        <DetailList
          title="Details that need clarification"
          items={view.needsClarification.map(observationLabel)}
          emptyText="None listed."
        />
      </div>

      <div className="mt-5">
        <Button
          variant="secondary"
          size="sm"
          onClick={onViewEvidence}
          disabled={stale}
          icon={<BookOpenText aria-hidden="true" className="size-4 shrink-0" />}
          aria-label={`View supporting information for ${candidate.name}`}
        >
          View supporting information
        </Button>
      </div>
    </article>
  );
}
