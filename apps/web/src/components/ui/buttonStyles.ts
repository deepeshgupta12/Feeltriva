import { cn } from '@/lib/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'md' | 'sm';

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-control font-semibold text-center transition-colors duration-150 disabled:opacity-60 aria-disabled:opacity-60';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-white hover:bg-primary-hover disabled:hover:bg-primary',
  secondary: 'border border-line bg-surface text-ink hover:border-ink-muted hover:bg-page',
  ghost: 'text-primary hover:bg-teal-soft',
  danger: 'border border-urgent bg-surface text-urgent hover:bg-urgent-soft',
};

/** Primary actions are 48px high; every button is at least 44px. */
const SIZES: Record<ButtonSize, string> = {
  md: 'min-h-12 px-5 py-2.5 text-base',
  sm: 'min-h-11 px-4 py-2 text-[0.9375rem]',
};

export function buttonClasses(variant: ButtonVariant = 'primary', size: ButtonSize = 'md', className?: string): string {
  return cn(BASE, VARIANTS[variant], SIZES[size], className);
}

/** Inline text link. */
export const LINK_CLASSES =
  'font-medium text-primary underline decoration-primary/40 underline-offset-4 hover:text-primary-hover hover:decoration-primary-hover';
