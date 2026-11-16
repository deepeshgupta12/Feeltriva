import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router';

import type { CandidateView } from '@/state/selectors';

import { SourceList } from './SourceList';
import { Sheet } from './ui/Sheet';
import { LINK_CLASSES } from './ui/buttonStyles';
import { SampleTag } from './ui/StatusBadge';

interface EvidenceDrawerProps {
  /** The explanation whose supporting information is shown; null closes the drawer. */
  view: CandidateView | null;
  onClose: () => void;
  showInternalDetail?: boolean;
}

/** Supporting information for one possible explanation: right drawer on desktop, bottom sheet on phones. */
export function EvidenceDrawer({ view, onClose, showInternalDetail = false }: EvidenceDrawerProps) {
  return (
    <Sheet
      open={view !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Supporting information"
      description={view ? `For: ${view.candidate.name}` : undefined}
      side="responsive"
    >
      {view ? (
        <div className="space-y-4">
          <SampleTag>Design demo · Sample information</SampleTag>
          <SourceList evidence={view.evidence} showInternalDetail={showInternalDetail} defaultOpen />
          <Link
            to={`/conditions/${encodeURIComponent(view.candidate.disease_id)}`}
            className={`inline-flex min-h-11 items-center gap-1.5 ${LINK_CLASSES}`}
          >
            Read reviewed information about {view.candidate.name}
            <ArrowRight aria-hidden="true" className="size-4 shrink-0" />
          </Link>
        </div>
      ) : null}
    </Sheet>
  );
}
