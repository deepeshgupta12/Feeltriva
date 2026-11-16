import { PageHeading } from '@/components/PageHeading';
import { ButtonLink } from '@/components/ui/Button';
import { usePageMeta } from '@/state/hooks';

export function NotFoundPage() {
  usePageMeta('Page not found', { noindex: true });
  return (
    <div className="mx-auto max-w-[640px] px-4 py-16 sm:px-6">
      <PageHeading>We couldn’t find that page</PageHeading>
      <p className="mt-3 text-ink-secondary">The address may be mistyped, or the page may have moved.</p>
      <div className="mt-6 flex flex-col gap-2 sm:flex-row">
        <ButtonLink to="/">Go to the introduction</ButtonLink>
        <ButtonLink to="/start" variant="secondary">
          Try a sample assessment
        </ButtonLink>
      </div>
    </div>
  );
}
