import { CircleAlert, Info, TriangleAlert } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';
import type { Tone } from '@/state/selectors';

interface StatusPanelProps {
  tone?: Tone;
  title: string;
  children?: ReactNode;
  /** Buttons or links. The first one should be the primary action. */
  actions?: ReactNode;
  /** Small label above the title, for example "Urgent-state preview". */
  eyebrow?: ReactNode;
  icon?: ReactNode;
  /**
   * How assistive technology is told about the panel:
   * `alert` announces immediately (urgent states), `status` politely, `none` not at all.
   */
  announce?: 'alert' | 'status' | 'none';
  headingLevel?: 'h1' | 'h2' | 'h3';
  className?: string;
}

const TONES: Record<Tone, { box: string; icon: string }> = {
  neutral: { box: 'border-line bg-surface', icon: 'text-ink-secondary' },
  info: { box: 'border-info/30 bg-info-soft', icon: 'text-info' },
  attention: { box: 'border-attention/30 bg-attention-soft', icon: 'text-attention' },
  urgent: { box: 'border-urgent/40 bg-urgent-soft', icon: 'text-urgent' },
};

const ICONS: Record<Tone, typeof Info> = {
  neutral: Info,
  info: Info,
  attention: TriangleAlert,
  urgent: CircleAlert,
};

/**
 * One layout for every non-routine state: urgent, incomplete, unsupported, unavailable,
 * offline, expired, empty and permission-denied. Tone is always paired with an icon and
 * a text title, never colour alone.
 */
export function StatusPanel({
  tone = 'neutral',
  title,
  children,
  actions,
  eyebrow,
  icon,
  announce = 'none',
  headingLevel = 'h2',
  className,
}: StatusPanelProps) {
  const Heading = headingLevel;
  const Icon = ICONS[tone];
  const styles = TONES[tone];
  return (
    <section
      role={announce === 'none' ? undefined : announce}
      className={cn('rounded-card border p-5 sm:p-6', styles.box, className)}
    >
      <div className="flex items-start gap-3.5">
        <span className={cn('mt-0.5 shrink-0', styles.icon)}>
          {icon ?? <Icon aria-hidden="true" className="size-6" />}
        </span>
        <div className="min-w-0 flex-1">
          {eyebrow ? <div className="mb-1.5 flex flex-wrap items-center gap-2">{eyebrow}</div> : null}
          <Heading
            className="font-display text-xl font-bold text-ink"
            tabIndex={headingLevel === 'h1' ? -1 : undefined}
          >
            {title}
          </Heading>
          {children ? <div className="mt-2 space-y-2 text-ink-secondary">{children}</div> : null}
          {actions ? <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">{actions}</div> : null}
        </div>
      </div>
    </section>
  );
}
