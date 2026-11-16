import { cn } from '@/lib/cn';

/**
 * Feeltriva mark: two overlapping leaf-shaped speech forms (a conversation in two parts).
 * Deliberately abstract; it is not a medical seal or certification badge.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn('size-8 shrink-0', className)}>
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path d="M8 17.5C8 12.3 12.3 8 17.5 8H22v4.5C22 17.7 17.7 22 12.5 22H8v-4.5Z" fill="#FFFFFF" />
      <path d="M17 24.5c0-3 2.5-5.5 5.5-5.5H25v2.5c0 3-2.5 5.500-5.500 5.500H17v-2.500Z" fill="#BFE5DB" />
    </svg>
  );
}

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark />
      <span className={cn('font-display text-xl font-bold tracking-tight text-ink', compact && 'sr-only')}>
        Feeltriva
      </span>
    </span>
  );
}
