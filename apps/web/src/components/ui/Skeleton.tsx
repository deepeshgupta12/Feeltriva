import { cn } from '@/lib/cn';

/** Structural placeholder while content loads. Purely visual; pair it with a text status. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse rounded-control bg-line/60 motion-reduce:animate-none', className)}
    />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div aria-hidden="true" className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <Skeleton className="h-5 w-2/5" />
      <div className="mt-4 space-y-3">
        {Array.from({ length: lines }, (_, index) => (
          <Skeleton key={index} className={cn('h-4', index === lines - 1 ? 'w-3/5' : 'w-full')} />
        ))}
      </div>
    </div>
  );
}
