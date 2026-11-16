import { useId, type ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  description?: ReactNode;
  disabled?: boolean;
  /** `tools` renders for the dark demo-tools panel. */
  tone?: 'default' | 'tools';
}

/** Accessible on/off switch with a visible text label and state. */
export function Switch({
  checked,
  onCheckedChange,
  label,
  description,
  disabled = false,
  tone = 'default',
}: SwitchProps) {
  const id = useId();
  const tools = tone === 'tools';
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <span id={`${id}-label`} className={cn('block font-medium', tools ? 'text-white' : 'text-ink')}>
          {label}
        </span>
        {description ? (
          <span
            id={`${id}-description`}
            className={cn('mt-0.5 block text-sm', tools ? 'text-white/85' : 'text-ink-secondary')}
          >
            {description}
          </span>
        ) : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={description ? `${id}-description` : undefined}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          'relative inline-flex h-11 w-[4.25rem] shrink-0 items-center rounded-full border px-1 transition-colors duration-150 disabled:opacity-50',
          checked
            ? tools
              ? 'border-white bg-white'
              : 'border-primary bg-primary'
            : tools
              ? 'border-white/60 bg-transparent'
              : 'border-ink-muted bg-surface',
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            'inline-block size-8 rounded-full transition-transform duration-150',
            checked ? 'translate-x-[1.5rem]' : 'translate-x-0',
            checked ? (tools ? 'bg-ink' : 'bg-white') : tools ? 'bg-white/70' : 'bg-ink-muted',
          )}
        />
        <span
          aria-hidden="true"
          className={cn(
            'absolute text-xs font-semibold',
            checked ? 'left-2.5' : 'right-2',
            checked ? (tools ? 'text-ink' : 'text-white') : tools ? 'text-white' : 'text-ink-secondary',
          )}
        >
          {checked ? 'On' : 'Off'}
        </span>
      </button>
    </div>
  );
}
