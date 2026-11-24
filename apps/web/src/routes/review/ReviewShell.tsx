import { ArrowLeft, Lock } from 'lucide-react';
import { Link, NavLink, Outlet } from 'react-router';

import { Logo } from '@/components/Logo';
import { StatusPanel } from '@/components/StatusPanel';
import { ButtonLink } from '@/components/ui/Button';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { cn } from '@/lib/cn';
import { useDemo } from '@/state/demo';
import { usePageMeta } from '@/state/hooks';
import { useServices } from '@/state/services';

const SECTIONS = [
  { to: '/review', label: 'Overview', end: true },
  { to: '/review/diseases', label: 'Disease mappings', end: false },
  { to: '/review/features', label: 'Feature mappings', end: false },
  { to: '/review/evidence', label: 'Evidence', end: false },
  { to: '/review/rules', label: 'Questions/rules', end: false },
  { to: '/review/releases', label: 'Releases', end: false },
  { to: '/review/data', label: 'Data quality', end: false },
  { to: '/review/evaluation', label: 'Model evaluation', end: false },
] as const;

/** The sections in http mode, where every screen reads and writes through the review API. */
const LIVE_SECTIONS = [
  { to: '/review', label: 'Overview', end: true },
  { to: '/review/diseases', label: 'Disease mappings', end: false },
  { to: '/review/features', label: 'Feature mappings', end: false },
  { to: '/review/data', label: 'Data quality', end: false },
  { to: '/review/links', label: 'Vocabulary links', end: false },
  { to: '/review/evidence', label: 'Statements and claims', end: false },
  { to: '/review/rules', label: 'Urgency rules', end: false },
  { to: '/review/releases', label: 'Releases', end: false },
] as const;

/**
 * Internal reviewer workspace: a denser layout with its own navigation, clearly labelled
 * "Internal review".
 *
 * Access here is controlled by the "Reviewer preview" demo switch. That switch is a
 * preview convenience and NOT authorization. Production must enforce reviewer roles on
 * the backend and protect these routes; hiding navigation is never a security control.
 */
export function ReviewShell() {
  usePageMeta('Internal review', { noindex: true });
  const { reviewerPreview, toolsEnabled } = useDemo();
  const { config, liveReview } = useServices();
  const live = config.serviceMode === 'http';

  if (live && liveReview.reviewer === null) {
    return (
      <main id="main-content" className="mx-auto w-full max-w-[760px] flex-1 px-4 py-10 sm:px-6">
        <StatusPanel
          tone="attention"
          title="Reviewer sign-in is not configured"
          headingLevel="h1"
          icon={<Lock aria-hidden="true" className="size-6" />}
          actions={<ButtonLink to="/">Back to Feeltriva</ButtonLink>}
        >
          <p>This area is the internal review workspace. It isn’t part of the symptom check.</p>
          <p>
            This build has no reviewer sign-in, so nothing is requested from the review service. The service checks the
            reviewer role itself on every request; nothing in the browser is authorization.
          </p>
        </StatusPanel>
      </main>
    );
  }

  if (!live && !reviewerPreview) {
    return (
      <main id="main-content" className="mx-auto w-full max-w-[760px] flex-1 px-4 py-10 sm:px-6">
        <StatusPanel
          tone="attention"
          title="Reviewer access is required"
          headingLevel="h1"
          icon={<Lock aria-hidden="true" className="size-6" />}
          actions={<ButtonLink to="/">Back to Feeltriva</ButtonLink>}
        >
          <p>This area is the internal review workspace. It isn’t part of the symptom check.</p>
          <p>
            {toolsEnabled
              ? 'In this demo, turn on “Reviewer preview” in Demo tools to look at it.'
              : 'Reviewer preview is not enabled in this build.'}{' '}
            The preview switch is not real authorization: the production service must check reviewer roles on the server
            before returning any review data.
          </p>
        </StatusPanel>
      </main>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-ink bg-ink text-white print:hidden">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-control bg-white px-2 py-1">
              <Logo />
            </span>
            <span className="font-display text-lg font-bold">Internal review</span>
            {live ? (
              <StatusBadge tone="info">Decisions are recorded under {liveReview.reviewer}</StatusBadge>
            ) : (
              <StatusBadge tone="sample">Reviewer preview · not real authorization</StatusBadge>
            )}
          </div>
          <Link to="/" className="inline-flex min-h-11 items-center gap-1.5 font-medium underline underline-offset-4">
            <ArrowLeft aria-hidden="true" className="size-4" />
            Back to the app
          </Link>
        </div>
        <nav aria-label="Internal review sections" className="mx-auto max-w-[1440px] overflow-x-auto px-2 sm:px-4">
          <ul className="flex min-w-max gap-1 pb-1.5">
            {(live ? LIVE_SECTIONS : SECTIONS).map((section) => (
              <li key={section.to}>
                <NavLink
                  to={section.to}
                  end={section.end}
                  className={({ isActive }) =>
                    cn(
                      'inline-flex min-h-11 items-center rounded-control px-3 text-[0.9375rem] font-medium',
                      isActive ? 'bg-white text-ink' : 'text-white hover:bg-white/15',
                    )
                  }
                >
                  {section.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main-content" className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
