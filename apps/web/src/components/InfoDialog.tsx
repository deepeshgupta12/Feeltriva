import { INFO_PAGES, type InfoPageId } from '@/content/infoPages';

import { Button } from './ui/Button';
import { Dialog } from './ui/Dialog';
import { StatusBadge } from './ui/StatusBadge';

interface InfoDialogProps {
  page: InfoPageId | null;
  onClose: () => void;
}

/** Draft About / Privacy / Terms / Contact content, clearly marked as draft. */
export function InfoDialog({ page, onClose }: InfoDialogProps) {
  const content = INFO_PAGES.find((item) => item.id === page);
  return (
    <Dialog
      open={content !== undefined}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={content?.title ?? ''}
      description="Draft content. Final wording has not been supplied or reviewed."
      footer={<Button onClick={onClose}>Close</Button>}
    >
      <StatusBadge tone="attention">Draft</StatusBadge>
      <div className="mt-3 space-y-3 text-ink-secondary">
        {content?.paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
    </Dialog>
  );
}
