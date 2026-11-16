import { CircleAlert, CircleDashed, FlaskConical, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';
import type { Tone } from '@/state/selectors';

export type BadgeTone = Tone | 'sample';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-page text-ink-secondary border-line',
  info: 'bg-info-soft text-info border-info/25',
  attention: 'bg-attention-soft text-attention border-attention/25',
  urgent: 'bg-urgent-soft text-urgent border-urgent/25',
  sample: 'bg-attention-soft text-attention border-attention/25',
};

const ICONS: Record<BadgeTone, typeof Info> = {
  neutral: CircleDashed,
  info: Info,
  attention: TriangleAlert,
  urgent: CircleAlert,
  sample: FlaskConical,
};

interface StatusBadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  /** Overrides the default icon for the tone. Status always has an icon and a text label. */
  icon?: ReactNode;
}

/** Status is never conveyed by colour alone: every badge carries an icon and text. */
export function StatusBadge({ tone = 'neutral', children, className, icon }: StatusBadgeProps) {
  const Icon = ICONS[tone];
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm font-medium',
        TONES[tone],
        className,
      )}
    >
      {icon ?? <Icon aria-hidden="true" className="size-4 shrink-0" />}
      <span>{children}</span>
    </span>
  );
}

/** Marks sample (non-clinical) content. */
export function SampleTag({ children = 'Sample', className }: { children?: ReactNode; className?: string }) {
  return (
    <StatusBadge tone="sample" className={className}>
      {children}
    </StatusBadge>
  );
}
