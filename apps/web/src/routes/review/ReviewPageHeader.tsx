import type { ReactNode } from 'react';

import { PageHeading } from '@/components/PageHeading';

/** Compact page header for the denser internal layout. */
export function ReviewPageHeader({
  title,
  children,
  badge,
}: {
  title: string;
  children?: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-3">
        <PageHeading className="!text-2xl">{title}</PageHeading>
        {badge}
      </div>
      {children ? (
        <div className="mt-1.5 max-w-4xl space-y-1 text-[0.9375rem] text-ink-secondary">{children}</div>
      ) : null}
    </div>
  );
}

export function ReviewLoading({ label }: { label: string }) {
  return (
    <p role="status" className="py-6 text-ink-secondary">
      {label}
    </p>
  );
}

export function ReviewLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="rounded-control border border-attention/30 bg-attention-soft p-4 text-attention">
      <p className="font-semibold">This review data couldn’t be loaded.</p>
      <button type="button" onClick={onRetry} className="mt-1 min-h-11 font-semibold underline underline-offset-4">
        Try again
      </button>
    </div>
  );
}
